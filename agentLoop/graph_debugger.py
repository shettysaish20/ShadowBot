"""
Graph Debugger - Replay individual nodes for rapid development iteration
"""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.syntax import Syntax
from rich.columns import Columns
import shlex
import yaml
import networkx as nx


# Add parent directory to path so we can import modules
sys.path.append(str(Path(__file__).parent.parent))

# Try to import required modules with fallbacks
try:
    from agentLoop.contextManager import ExecutionContextManager
    from agentLoop.agents import AgentRunner
    from agentLoop.session_serializer import SessionSerializer
    from agentLoop.graph_validator import GraphValidator
    HAS_AGENT_LOOP = True
except ImportError as e:
    print(f"❌ Cannot import agentLoop modules: {e}")
    HAS_AGENT_LOOP = False

# Try to import MCP with correct paths
try:
    from mcp_servers.multiMCP import MultiMCP
    HAS_MCP = True
except ImportError as e:
    print(f"⚠️  MCP modules not found: {e}")
    HAS_MCP = False
    
    # Create mock classes for read-only functionality
    class MockMCP:
        async def initialize(self): pass
        async def shutdown(self): pass
    
    MultiMCP = MockMCP

def load_server_configs():
    """Load MCP server configurations from YAML file"""
    try:
        config_path = Path("config/mcp_server_config.yaml")
        if not config_path.exists():
            print(f"❌ MCP server config not found: {config_path}")
            return []
        
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        
        return config.get("mcp_servers", [])
    except Exception as e:
        print(f"❌ Error loading MCP config: {e}")
        return []

class GraphDebugger:
    def __init__(self, multi_mcp=None):
        self.multi_mcp = multi_mcp
        self.agent_runner = AgentRunner(multi_mcp) if multi_mcp else None
        self.console = Console()
        self.context: Optional[ExecutionContextManager] = None
        self.read_only = not HAS_MCP
        self.original_session_file = None  # 👈 Track original file
        
    async def load_session(self, session_path: str) -> bool:
        """Load a session from file"""
        if not HAS_AGENT_LOOP:
            self.console.print("❌ AgentLoop modules not available")
            return False
            
        try:
            session_file = Path(session_path)
            if not session_file.exists():
                self.console.print(f"❌ Session file not found: {session_path}")
                return False
                
            self.original_session_file = Path(session_path)
            
            # Use centralized loading
            plan_graph = SessionSerializer.load_session(session_file)
            
            # Create context with loaded graph
            from agentLoop.contextManager import ExecutionContextManager
            self.context = ExecutionContextManager.__new__(ExecutionContextManager)
            self.context.plan_graph = plan_graph
            self.context.debug_mode = True
            self.context.log_messages = []
            
            # 🔧 CRITICAL FIX: Change session ID to avoid overwriting
            original_session_id = self.context.plan_graph.graph['session_id']
            debug_session_id = f"{original_session_id}_debug_{datetime.now().strftime('%H%M%S')}"
            self.context.plan_graph.graph['session_id'] = debug_session_id
            
            # Display session info using centralized method
            session_info = SessionSerializer.get_session_info(self.context.plan_graph)
            mode_info = " (READ-ONLY)" if self.read_only else ""
            
            self.console.print(Panel(
                f"📋 Session: {session_info['session_id']}\n"
                f"🕐 Created: {session_info['created_at']}\n"
                f"📝 Query: {session_info['original_query']}\n"
                f"🎯 Nodes: {session_info['node_count']} total{mode_info}",
                title="🔄 Session Loaded",
                border_style="green"
            ))
            
            if self.read_only:
                self.console.print("⚠️  Running in read-only mode. Node replay not available.")
            
            return True
            
        except Exception as e:
            self.console.print(f"❌ Error loading session: {e}")
            import traceback
            self.console.print(traceback.format_exc())
            return False
    
    def show_graph_status(self):
        """Display current graph execution status"""
        if not self.context:
            self.console.print("❌ No session loaded")
            return
            
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Node ID")
        table.add_column("Agent")
        table.add_column("Status")
        table.add_column("Reads")
        table.add_column("Writes")
        table.add_column("Description")
        
        for node_id in self.context.plan_graph.nodes:
            if node_id == "ROOT":
                continue
                
            node_data = self.context.plan_graph.nodes[node_id]
            status = node_data.get('status', 'unknown')
            
            # Format status with colors
            if status == 'completed':
                status_display = "[green]✅ completed[/green]"
            elif status == 'failed':
                status_display = "[red]❌ failed[/red]"
            elif status == 'pending':
                status_display = "[yellow]🔲 pending[/yellow]"
            else:
                status_display = f"[dim]{status}[/dim]"
            
            table.add_row(
                node_id,
                node_data.get('agent', 'Unknown'),
                status_display,
                str(node_data.get('reads', [])),
                str(node_data.get('writes', [])),
                node_data.get('description', '')[:50] + "..." if len(node_data.get('description', '')) > 50 else node_data.get('description', '')
            )
        
        self.console.print(table)
    
    def show_node_details(self, node_id: str):
        """Show detailed information about a specific node"""
        if not self.context or node_id not in self.context.plan_graph.nodes:
            self.console.print(f"❌ Node {node_id} not found")
            return
            
        node_data = self.context.plan_graph.nodes[node_id]
        reads = node_data.get('reads', [])
        writes = node_data.get('writes', [])
        
        # Check available inputs
        available_inputs = self.context.get_inputs(reads)
        missing_inputs = [r for r in reads if r not in available_inputs]
        
        # Basic node info
        self.console.print(Panel(
            f"🤖 Agent: {node_data.get('agent', 'Unknown')}\n"
            f"📝 Description: {node_data.get('description', 'No description')}\n"
            f"📥 Reads: {reads}\n"
            f"📤 Writes: {writes}\n"
            f"⚡ Status: {node_data.get('status', 'unknown')}\n"
            f"✅ Available Inputs: {list(available_inputs.keys())}\n"
            f"❌ Missing Inputs: {missing_inputs}",
            title=f"🔍 Node {node_id} Details",
            border_style="blue"
        ))
        
        # Show current output if exists
        if node_data.get('output'):
            self.console.print("\n💾 Current Output:")
            output_json = json.dumps(node_data['output'], indent=2)
            self.console.print(Syntax(output_json, "json", theme="monokai", line_numbers=True))
        
        # Show output_chain keys for debugging  
        output_chain_keys = list(self.context.plan_graph.graph.get('output_chain', {}).keys())
        self.console.print(f"\n🔗 All output_chain keys: {output_chain_keys}")
    
    def _save_debug_data(self, node_id: str, inputs: Dict, outputs: List[Dict]):
        """Save exact input/output to temp.json for detailed analysis"""
        debug_data = {
            "timestamp": datetime.now().isoformat(),
            "node_id": node_id,
            "iterations": [
                {"iteration": 1, "output": outputs[0]},
                {"iteration": 2, "output": outputs[1]} if len(outputs) > 1 else None
            ],
            "final_output": outputs[-1]  # Last iteration
        }
        
        # Save to memory/temp.json
        memory_dir = Path("memory")
        memory_dir.mkdir(exist_ok=True)
        temp_file = memory_dir / "temp.json"
        
        try:
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(debug_data, f, indent=2, default=str, ensure_ascii=False)
            self.console.print(f"💾 Debug data saved to [cyan]{temp_file}[/cyan]")
        except Exception as e:
            self.console.print(f"❌ Failed to save debug data: {e}")
    
    async def replay_node(self, node_id: str, show_comparison: bool = True) -> Dict[str, Any]:
        """Replay a specific node with existing inputs"""
        if self.read_only:
            self.console.print("❌ Node replay not available in read-only mode")
            return {}
            
        if not self.context or node_id not in self.context.plan_graph.nodes:
            self.console.print(f"❌ Node {node_id} not found")
            return {}
            
        node_data = self.context.plan_graph.nodes[node_id]
        
        # Store old output for comparison
        old_output = node_data.get('output')
        
        # Get inputs from existing output_chain
        inputs = self.context.get_inputs(node_data.get("reads", []))
        
        self.console.print(Panel(
            f"🔄 Re-running {node_id} ({node_data.get('agent', 'Unknown')})\n"
            f"📥 Using inputs: {list(inputs.keys())}",
            title="🚀 Node Replay",
            border_style="yellow"
        ))
        
        # Reset node status
        node_data['status'] = 'pending'
        node_data['output'] = None
        
        # 🔧 SPECIAL HANDLING FOR FORMATTERAGENT - Send ALL output_chain data
        if node_data["agent"] == "FormatterAgent":
            # Send ALL gathered information to FormatterAgent
            all_outputs = self.context.plan_graph.graph['output_chain'].copy()
            
            agent_input = {
                "step_id": node_id,
                "agent_prompt": node_data.get("agent_prompt", node_data["description"]),
                "reads": node_data.get("reads", []),
                "writes": node_data.get("writes", []),
                "inputs": inputs,  # Specific inputs planner requested
                "all_outputs": all_outputs,  # ✅ ALL gathered information from output_chain
                "original_query": self.context.plan_graph.graph['original_query'],
                "session_context": {
                    "session_id": self.context.plan_graph.graph['session_id'],
                    "created_at": self.context.plan_graph.graph['created_at'],
                    "file_manifest": self.context.plan_graph.graph['file_manifest']
                }
            }
        else:
            # Regular agent input
            agent_input = {
                "step_id": node_id,
                "agent_prompt": node_data.get("agent_prompt", node_data["description"]),
                "reads": node_data.get("reads", []),
                "writes": node_data.get("writes", []),
                "inputs": inputs
            }
        
        # Execute the node
        start_time = datetime.now()
        
        result = await self.agent_runner.run_agent(node_data["agent"], agent_input)
        
        execution_time = (datetime.now() - start_time).total_seconds()
        
        # Update the graph with new results
        if result["success"]:
            self.context.mark_done(node_id, result["output"])
            new_output = result["output"]
            
            # 💾 Save exact input/output to temp.json
            self._save_debug_data(node_id, inputs, [result["output"]])
            
            self.console.print(Panel(
                f"✅ {node_id} completed successfully!\n"
                f"⏱️ Execution time: {execution_time:.2f}s",
                title="✅ Success",
                border_style="green"
            ))

            MAX_ITERATIONS = 4
            
            # Show comparison if requested
            if show_comparison and old_output:
                self._show_output_comparison(node_id, old_output, new_output)
                
            if result["output"].get("call_self"):
                # Store first iteration
                iterations = [{"iteration": 1, "output": result["output"]}]
                
                # Run second iteration
                second_result = await self.agent_runner.run_agent(node_data["agent"], {
                    "step_id": node_id,
                    "agent_prompt": result["output"].get("next_instruction", "Continue the task"),
                    "reads": node_data.get("reads", []),
                    "writes": node_data.get("writes", []),
                    "inputs": inputs,
                    "previous_output": result["output"],
                    "iteration_context": result["output"].get("iteration_context", {})
                })
                
                if second_result["success"]:
                    iterations.append({"iteration": 2, "output": second_result["output"]})
                    final_output = second_result["output"]
                else:
                    iterations.append(None)
                    final_output = result["output"]
                
                # Store both iterations
                debug_data = {
                    "timestamp": datetime.now().isoformat(),
                    "node_id": node_id,
                    "iterations": iterations,
                    "final_output": final_output
                }
                
                # Save to temp.json
                with open("memory/temp.json", 'w', encoding='utf-8') as f:
                    json.dump(debug_data, f, indent=2, default=str, ensure_ascii=False)
            
            return new_output
        else:
            # 💾 Save inputs and error for debugging
            error_output = {"error": result["error"], "success": False}
            self._save_debug_data(node_id, inputs, [error_output])
            
            self.console.print(Panel(
                f"❌ {node_id} failed: {result['error']}\n"
                f"⏱️ Execution time: {execution_time:.2f}s",
                title="❌ Failed",
                border_style="red"
            ))
            return {}
    
    def _show_output_comparison(self, node_id: str, old_output: Dict, new_output: Dict):
        """Show side-by-side comparison of old vs new output"""
        self.console.print(f"\n🔍 Output Comparison for {node_id}:")
        
        # Convert to formatted JSON
        old_json = json.dumps(old_output, indent=2)
        new_json = json.dumps(new_output, indent=2)
        
        # Create side-by-side panels
        old_panel = Panel(
            Syntax(old_json, "json", theme="monokai", line_numbers=True),
            title="📜 OLD OUTPUT",
            border_style="red"
        )
        
        new_panel = Panel(
            Syntax(new_json, "json", theme="monokai", line_numbers=True),
            title="🆕 NEW OUTPUT", 
            border_style="green"
        )
        
        self.console.print(Columns([old_panel, new_panel]))
    
    def show_output_chain(self, filter_key: Optional[str] = None):
        """Show current output_chain (optionally filtered)"""
        if not self.context:
            self.console.print("❌ No session loaded")
            return
            
        output_chain = self.context.plan_graph.graph.get('output_chain', {})
        
        if filter_key:
            if filter_key in output_chain:
                filtered_data = {filter_key: output_chain[filter_key]}
                self.console.print(f"🎯 Filtered output_chain['{filter_key}']:")
                self.console.print(Syntax(json.dumps(filtered_data, indent=2, default=str), "json", theme="monokai"))
            else:
                self.console.print(f"❌ Key '{filter_key}' not found in output_chain")
                self.console.print(f"Available keys: {list(output_chain.keys())}")
        else:
            self.console.print("🔗 Current output_chain:")
            self.console.print(f"📊 Total steps: {len(output_chain)}")
            for step_id in output_chain.keys():
                self.console.print(f"  📄 {step_id}")
    
    def save_session(self, output_path: Optional[str] = None):
        """Save current session state to file"""
        if not self.context:
            self.console.print("❌ No session loaded")
            return
            
        try:
            session_file = SessionSerializer.save_session(
                self.context.plan_graph, 
                session_type="debug",
                output_path=output_path,
                original_session_file=self.original_session_file
            )
            self.console.print(f"💾 Debug session saved to {session_file}")
        except Exception as e:
            self.console.print(f"❌ Save failed: {e}")

    def analyze_graph(self):
        """Analyze graph structure and dependencies"""
        if not self.context:
            self.console.print("❌ No session loaded")
            return
            
        validator = GraphValidator(self.console)
        
        # Re-validate current state
        self.console.print("🔍 **CURRENT GRAPH VALIDATION:**")
        validation_results = validator.validate_execution_graph(self.context.plan_graph, verbose=True)
        
        # Critical path analysis
        self.console.print("\n📈 **CRITICAL PATH ANALYSIS:**")
        critical_path_info = validator.analyze_critical_path(self.context.plan_graph)
        
        if "error" in critical_path_info:
            self.console.print(f"❌ {critical_path_info['error']}")
        else:
            self.console.print(f"🎯 Critical Path: {' → '.join(critical_path_info['critical_path'])}")
            self.console.print(f"📏 Path Length: {critical_path_info['path_length']} steps")
            self.console.print(f"⚡ Parallel Opportunities: {critical_path_info['parallel_opportunities']} nodes can run in parallel")
        
        # Blocked nodes analysis
        self.console.print("\n🚫 **BLOCKED NODES ANALYSIS:**")
        blocked_nodes = validator.find_blocked_nodes(self.context.plan_graph)
        
        if blocked_nodes:
            for node, failed_deps in blocked_nodes.items():
                self.console.print(f"❌ {node} blocked by failed dependencies: {failed_deps}")
        else:
            self.console.print("✅ No nodes are blocked by failed dependencies")


# CLI Interface for interactive debugging
class GraphDebuggerCLI:
    def __init__(self):
        self.console = Console()
        self.debugger: Optional[GraphDebugger] = None
    
    async def start(self):
        """Start interactive debugging session"""
        self.console.print(Panel(
            "🔧 Graph Debugger - Interactive Node Replay Tool\n\n"
            "Commands:\n"
            "  load <session_file>     - Load a session\n"
            "  status                  - Show graph status\n"
            "  analyze                 - Analyze graph structure & dependencies\n"
            "  node <node_id>          - Show node details\n"
            "  replay <node_id>        - Replay a specific node (if MCP available)\n"
            "  outputs [key]           - Show output_chain\n"
            "  save [path]             - Save current session\n"
            "  exit                    - Exit debugger",
            title="🚀 Graph Debugger",
            border_style="cyan"
        ))
        
        # Initialize MCP if available
        multi_mcp = None
        if HAS_MCP:
            try:
                server_configs = load_server_configs()
                multi_mcp = MultiMCP(server_configs)
                await multi_mcp.initialize()
                self.console.print("✅ MCP initialized")
            except Exception as e:
                self.console.print(f"⚠️  MCP initialization failed: {e}")
                multi_mcp = None
        
        self.debugger = GraphDebugger(multi_mcp)
        
        while True:
            try:
                command_line = Prompt.ask("🔧 debugger").strip()
                # Handle quoted arguments properly
                try:
                    command = shlex.split(command_line)
                except ValueError:
                    # Fallback to simple split if shlex fails
                    command = command_line.split()
                
                if not command:
                    continue
                
                cmd = command[0].lower()
                
                if cmd == "exit":
                    break
                elif cmd == "load":
                    if len(command) < 2:
                        self.console.print("❌ Usage: load <session_file>")
                        continue
                    await self.debugger.load_session(command[1])
                    
                elif cmd == "status":
                    self.debugger.show_graph_status()
                    
                elif cmd == "analyze":
                    self.debugger.analyze_graph()
                    
                elif cmd == "node":
                    if len(command) < 2:
                        self.console.print("❌ Usage: node <node_id>")
                        continue
                    self.debugger.show_node_details(command[1])
                    
                elif cmd == "replay":
                    if len(command) < 2:
                        self.console.print("❌ Usage: replay <node_id>")
                        continue
                    await self.debugger.replay_node(command[1])
                    
                elif cmd == "outputs":
                    filter_key = command[1] if len(command) > 1 else None
                    self.debugger.show_output_chain(filter_key)
                    
                elif cmd == "save":
                    output_path = command[1] if len(command) > 1 else None
                    self.debugger.save_session(output_path)
                    
                else:
                    self.console.print(f"❌ Unknown command: {cmd}")
                    
            except KeyboardInterrupt:
                break
            except Exception as e:
                self.console.print(f"❌ Error: {e}")
        
        if multi_mcp and HAS_MCP:
            await multi_mcp.shutdown()
        self.console.print("👋 Goodbye!")


# Direct usage functions  
async def replay_node_from_session(session_file: str, node_id: str):
    """Convenience function to replay a node from a session file"""
    multi_mcp = None
    if HAS_MCP:
        try:
            server_configs = load_server_configs()
            multi_mcp = MultiMCP(server_configs)
            await multi_mcp.initialize()
        except Exception as e:
            print(f"⚠️  MCP initialization failed: {e}")
    
    debugger = GraphDebugger(multi_mcp)
    
    if await debugger.load_session(session_file):
        result = await debugger.replay_node(node_id)
        if multi_mcp and HAS_MCP:
            await multi_mcp.shutdown()
        return result
    
    if multi_mcp and HAS_MCP:
        await multi_mcp.shutdown()
    return None


# Read-only session inspector (works without MCP)
async def inspect_session(session_file: str):
    """Read-only session inspection"""
    debugger = GraphDebugger()
    
    if await debugger.load_session(session_file):
        debugger.show_graph_status()
        print("\n" + "="*60)
        debugger.show_output_chain()


# Main entry point
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) == 3:
        # Direct replay: python graph_debugger.py <session_file> <node_id>
        session_file, node_id = sys.argv[1], sys.argv[2]
        if HAS_MCP:
            asyncio.run(replay_node_from_session(session_file, node_id))
        else:
            print("⚠️  Running in read-only mode (MCP not available)")
            asyncio.run(inspect_session(session_file))
    elif len(sys.argv) == 2:
        # Read-only inspection: python graph_debugger.py <session_file>
        session_file = sys.argv[1]
        asyncio.run(inspect_session(session_file))
    else:
        # Interactive CLI
        cli = GraphDebuggerCLI()
        asyncio.run(cli.start())


# uv run agentLoop/graph_debugger.py memory/session_summaries_index/2025/06/26/session_50916864.json T012
# uv run agentLoop/graph_debugger.py memory/session_summaries_index/2025/06/27/session_51008030.json T009
# uv run agentLoop/graph_debugger.py
# 🔧 debugger> load memory/session_summaries_index/2025/06/26/session_XXXXX.json
# 🔧 debugger> outputs
# 🔧 debugger> load memory/session_summaries_index/2025/06/26/session_XXXXX.json
# 🔧 debugger> status
# 🔧 debugger> replay T012
# 🔧 debugger> save