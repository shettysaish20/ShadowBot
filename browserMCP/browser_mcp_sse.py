import asyncio
import os
import sys
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool

# Add the parent directory to Python path (same as in mcp_tools.py)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import our tools module
from browserMCP.mcp_tools import get_tools, handle_tool_call

# Create server
server = Server(name="browser-automation")

@server.list_tools()
async def list_tools() -> list[Tool]:
    """Return all available MCP tools"""
    return get_tools()

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[dict]:
    """Handle tool calls by delegating to mcp_tools module"""
    return await handle_tool_call(name, arguments)

# Create transport
transport = SseServerTransport("/messages")

async def app(scope, receive, send):
    """Main ASGI application with exact path matching"""
    path = scope.get("path", "")
    method = scope.get("method", "GET")
    
    print(f"🔍 Request: {method} {path}")  # Debug logging
    
    if path == "/sse" and method == "GET":
        print("📡 Handling SSE connection")
        try:
            async with transport.connect_sse(scope, receive, send) as streams:
                await server.run(streams[0], streams[1], server.create_initialization_options())
        except Exception as e:
            print(f"❌ SSE Error: {e}")
            # Send error response
            await send({
                "type": "http.response.start",
                "status": 500,
                "headers": [[b"content-type", b"text/plain"]],
            })
            await send({
                "type": "http.response.body",
                "body": f"SSE Error: {str(e)}".encode(),
            })
    elif path == "/messages" and method == "POST":
        print("📨 Handling POST message")
        try:
            await transport.handle_post_message(scope, receive, send)
        except Exception as e:
            print(f"❌ POST Error: {e}")
            # Send error response
            await send({
                "type": "http.response.start",
                "status": 500,
                "headers": [[b"content-type", b"text/plain"]],
            })
            await send({
                "type": "http.response.body",
                "body": f"POST Error: {str(e)}".encode(),
            })
    else:
        # 404 Not Found
        await send({
            "type": "http.response.start",
            "status": 404,
            "headers": [[b"content-type", b"text/plain"]],
        })
        await send({
            "type": "http.response.body",
            "body": b"Not Found",
        })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8100) 