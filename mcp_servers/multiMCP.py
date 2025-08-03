from utils.utils import log_step, log_error
import os
import sys
import asyncio
import json
from typing import Optional, Any, List, Dict
from inspect import signature
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import ast

try:
    from mcp.client.sse import sse_client
    SSE_SUPPORTED = True
except ImportError:
    SSE_SUPPORTED = False

class MCP:
    def __init__(
        self,
        server_script: str = "mcp_server_2.py",
        working_dir: Optional[str] = None,
        server_command: Optional[str] = None,
        transport: str = "stdio"
    ):
        self.server_script = server_script
        self.working_dir = working_dir or os.getcwd()
        self.server_command = server_command or sys.executable
        self.transport = transport
        self.session: Optional[ClientSession] = None
        self.session_context = None
        self._session_stack = []  # Track context managers

    async def ensure_session(self):
        if self.session:
            return self.session

        if self.transport == "stdio":
            params = StdioServerParameters(
                command=self.server_command,
                args=[self.server_script],
                cwd=self.working_dir
            )
            self.session_context = stdio_client(params)
        elif self.transport == "sse":
            if not SSE_SUPPORTED:
                raise ImportError("MCP SSE client not available. Please update your MCP SDK.")
            self.session_context = sse_client(self.server_script)
        else:
            raise ValueError(f"Unsupported transport: {self.transport}")

        # ✅ Proper async context management
        read, write = await self.session_context.__aenter__()
        self._session_stack.append(('context', self.session_context))
        
        self.session = ClientSession(read, write)
        await self.session.__aenter__()
        self._session_stack.append(('session', self.session))
        
        await self.session.initialize()
        return self.session

    async def list_tools(self):
        session = await self.ensure_session()
        tools_result = await session.list_tools()
        return tools_result.tools

    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        session = await self.ensure_session()
        return await session.call_tool(tool_name, arguments)

    async def shutdown(self):
        # ✅ Exit in reverse order (LIFO) with proper error handling
        for item_type, item in reversed(self._session_stack):
            try:
                await item.__aexit__(None, None, None)
            except asyncio.CancelledError:
                # ✅ Gracefully handle cancellation during shutdown
                log_step(f"⚠️  {item_type} shutdown cancelled (program terminating)", symbol="→ ")
                break  # Stop trying to shutdown remaining items
            except Exception as e:
                log_error(f"Error shutting down {item_type}: {e}")
        
        self._session_stack.clear()
        self.session = None
        self.session_context = None

class MultiMCP:
    def __init__(self, server_configs: List[dict]):
        self.server_configs = server_configs
        self.tool_map: Dict[str, Dict[str, Any]] = {}
        self.server_tools: Dict[str, List[Any]] = {}
        self.client_cache: Dict[str, MCP] = {}

    async def initialize(self):
        for config in self.server_configs:
            try:
                transport = config.get("transport", "stdio")
                client = MCP(
                    server_script=config["script"],
                    working_dir=config.get("cwd", os.getcwd()),
                    transport=transport
                )
                self.client_cache[config["id"]] = client

                log_step(f"Scanning tools from: {config['script']} ({transport})", symbol="→ ")
                tools = await client.list_tools()
                log_step(f"Tools received: {[tool.name for tool in tools]}", symbol="→ ")
                for tool in tools:
                    self.tool_map[tool.name] = {
                        "config": config,
                        "tool": tool
                    }
                    server_key = config["id"]
                    if server_key not in self.server_tools:
                        self.server_tools[server_key] = []
                    self.server_tools[server_key].append(tool)
            except Exception as e:
                log_step(f"Error initializing MCP server {config['script']}: {e}", symbol="❌")

    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        entry = self.tool_map.get(tool_name)
        if not entry:
            raise ValueError(f"Tool '{tool_name}' not found on any server.")

        config = entry["config"]
        client = self.client_cache[config["id"]]
        return await client.call_tool(tool_name, arguments)

    async def function_wrapper(self, tool_name: str, *args):
        if isinstance(tool_name, str) and len(args) == 0:
            stripped = tool_name.strip()
            if stripped.endswith(")") and "(" in stripped:
                try:
                    expr = ast.parse(stripped, mode='eval').body
                    if not isinstance(expr, ast.Call) or not isinstance(expr.func, ast.Name):
                        raise ValueError("Invalid function call format")
                    tool_name = expr.func.id
                    args = [ast.literal_eval(arg) for arg in expr.args]
                except Exception as e:
                    raise ValueError(f"Failed to parse function string '{tool_name}': {e}")

        tool_entry = self.tool_map.get(tool_name)
        if not tool_entry:
            raise ValueError(f"Tool '{tool_name}' not found.")

        tool = tool_entry["tool"]
        schema = tool.inputSchema
        params = {}

        if "input" in schema.get("properties", {}):
            inner_key = next(iter(schema.get("$defs", {})), None)
            inner_props = schema["$defs"][inner_key]["properties"]
            param_names = list(inner_props.keys())
            if len(param_names) != len(args):
                raise ValueError(f"{tool_name} expects {len(param_names)} args, got {len(args)}")
            params["input"] = dict(zip(param_names, args))
        else:
            param_names = list(schema["properties"].keys())
            if len(param_names) != len(args):
                raise ValueError(f"{tool_name} expects {len(param_names)} args, got {len(args)}")
            params = dict(zip(param_names, args))

        result = await self.call_tool(tool_name, params)

        try:
            content_text = getattr(result, "content", [])[0].text.strip()
            parsed = json.loads(content_text)

            if isinstance(parsed, dict):
                if "result" in parsed:
                    return parsed["result"]
                if len(parsed) == 1:
                    return next(iter(parsed.values()))
                return parsed

            return parsed
        except Exception:
            return result

    def tool_description_wrapper(self) -> List[str]:
        examples = []
        for tool in self.get_all_tools():
            schema = tool.inputSchema
            if "input" in schema.get("properties", {}):
                inner_key = next(iter(schema.get("$defs", {})), None)
                props = schema["$defs"][inner_key]["properties"]
            else:
                props = schema["properties"]

            arg_types = []
            for k, v in props.items():
                t = v.get("type", "any")
                arg_types.append(t)

            signature_str = ", ".join(arg_types)
            examples.append(f"{tool.name}({signature_str})  # {tool.description}")
        return examples

    async def list_all_tools(self) -> List[str]:
        return list(self.tool_map.keys())

    def get_all_tools(self) -> List[Any]:
        return [entry["tool"] for entry in self.tool_map.values()]

    def get_tools_from_servers(self, selected_servers: List[str]) -> List[Any]:
        tools = []
        for server in selected_servers:
            if server in self.server_tools:
                tools.extend(self.server_tools[server])
        return tools

    async def shutdown(self):
        # ✅ Properly shutdown all clients with cancellation handling
        for client in self.client_cache.values():
            try:
                await client.shutdown()
            except asyncio.CancelledError:
                # ✅ Gracefully handle cancellation during shutdown
                log_step("⚠️  Client shutdown cancelled (program terminating)", symbol="→ ")
                break  # Stop trying to shutdown remaining clients
            except Exception as e:
                log_error(f"Error shutting down client: {e}")
        
        self.client_cache.clear()

