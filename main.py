# main.py – 100% NetworkX Graph-First (FIXED MultiMCP)

from utils.utils import log_step, log_error
import asyncio
import yaml
from dotenv import load_dotenv
from mcp_servers.multiMCP import MultiMCP
from agentLoop.flow import AgentLoop4
from agentLoop.output_analyzer import analyze_results
from pathlib import Path
from pprint import pprint

BANNER = """
──────────────────────────────────────────────────────
🔸  Agentic Query Assistant  🔸
Files first, then your question.
Type 'exit' or 'quit' to leave.
──────────────────────────────────────────────────────
"""

def load_server_configs():
    """Load MCP server configurations from YAML file"""
    config_path = Path("config/mcp_server_config.yaml")
    if not config_path.exists():
        log_error(f"MCP server config not found: {config_path}")
        return []
    
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    
    return config.get("mcp_servers", [])

def get_file_input():
    """Get file paths from user"""
    log_step("📁 File Input (optional):", symbol="")
    print("Enter file paths (one per line), or press Enter to skip:")
    print("Example: /path/to/file.csv")
    print("Press Enter twice when done.")
    
    uploaded_files = []
    file_manifest = []
    
    while True:
        file_path = input("📄 File path: ").strip()
        if not file_path:
            break
        
        # Strip quotes from drag-and-drop paths
        if file_path.startswith('"') and file_path.endswith('"'):
            file_path = file_path[1:-1]
        
        if Path(file_path).exists():
            uploaded_files.append(file_path)
            file_manifest.append({
                "path": file_path,
                "name": Path(file_path).name,
                "size": Path(file_path).stat().st_size
            })
            print(f"✅ Added: {Path(file_path).name}")
        else:
            print(f"❌ File not found: {file_path}")
    
    return uploaded_files, file_manifest

def get_user_query():
    """Get query from user"""
    log_step("📝 Your Question:", symbol="")
    return input().strip()

async def main():
    load_dotenv()
    print(BANNER)
    
    # 🔧 FIX: Load server configs and initialize MultiMCP properly
    log_step("📥 Loading MCP Servers...")
    server_configs = load_server_configs()
    multi_mcp = MultiMCP(server_configs)  # ✅ Pass server_configs
    await multi_mcp.initialize()          # ✅ Use initialize() not start()
    
    # Initialize AgentLoop4
    agent_loop = AgentLoop4(multi_mcp)
    
    while True:
        try:
            # Get file input first
            uploaded_files, file_manifest = get_file_input()
            
            # Get user query
            query = get_user_query()
            if query.lower() in ['exit', 'quit']:
                break
            
            # Process with AgentLoop4 - returns ExecutionContextManager object
            log_step("🔄 Processing with AgentLoop4...")
            execution_context = await agent_loop.run(query, file_manifest, uploaded_files)
            
            # Analyze results directly from NetworkX graph
            print("\n" + "="*60)
            analyze_results(execution_context)
            print("="*60)
            
            print("\n😴 Agent Resting now")
            
        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            break
        except Exception as e:
            log_error(f"Error: {e}")
            print("Let's try again...")
        
        # Continue prompt
        cont = input("\nContinue? (press Enter) or type 'exit': ").strip()
        if cont.lower() in ['exit', 'quit']:
            break

    await multi_mcp.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
