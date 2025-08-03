import os
import json
import time
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
import traceback
import matplotlib
from bs4 import BeautifulSoup
import ast
import re
import cssutils

# Simple imports for Python execution
SAFE_BUILTINS = {
    '__builtins__': {
        'len': len, 'str': str, 'int': int, 'float': float, 'bool': bool,
        'list': list, 'dict': dict, 'tuple': tuple, 'set': set,
        'enumerate': enumerate, 'range': range, 'zip': zip,
        'print': print, 'type': type, 'isinstance': isinstance,
        'ValueError': ValueError, 'TypeError': TypeError, 'KeyError': KeyError,
        'IndexError': IndexError, 'FileNotFoundError': FileNotFoundError,
        'Exception': Exception, 'min': min, 'max': max, 'sum': sum,
        'open': open, 'json': json, 'os': os, 'Path': Path,
        'matplotlib': matplotlib,
        '__import__': __import__
    }
}

def log_step(message, symbol="🔧"):
    """Simple logging with timestamp"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"{symbol} [{timestamp}] {message}")

async def process_direct_files(files_dict: Dict[str, str], session_id: str) -> Dict[str, Any]:
    """
    Process direct file creation from CoderAgent 'files' field
    
    Args:
        files_dict: {"filename.html": "content", "styles.css": "content"}
        session_id: Session identifier
        
    Returns:
        Results with created file paths and metadata
    """
    start_time = time.perf_counter()
    
    # Setup session directory
    output_dir = Path(f"media/generated/{session_id}")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    results = {
        "created_files": [],
        "file_count": 0,
        "total_size": 0,
        "status": "success",
        "errors": []
    }
    
    log_step(f"📁 Creating {len(files_dict)} files directly", symbol="🎯")
    
    for filename, content in files_dict.items():
        try:
            # Ensure safe filename (no path traversal)
            safe_filename = Path(filename).name
            filepath = output_dir / safe_filename
            
            # Write file with UTF-8 encoding (handles Unicode)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # Track results
            file_size = len(content.encode('utf-8'))
            results["created_files"].append(str(filepath))
            results["total_size"] += file_size
            
            log_step(f"✅ Created {safe_filename} ({file_size:,} bytes)", symbol="📄")
            
        except Exception as e:
            error_msg = f"Failed to create {filename}: {str(e)}"
            results["errors"].append(error_msg)
            results["status"] = "partial_failure"
            log_step(f"❌ {error_msg}", symbol="🚨")
    
    results["file_count"] = len(results["created_files"])
    results["execution_time"] = time.perf_counter() - start_time
    
    if results["created_files"]:
        log_step(f"🎉 Created {results['file_count']} files in {results['execution_time']:.2f}s", symbol="✅")
    
    return results

def make_tool_proxy(tool_name: str, mcp):
    """Create async proxy function for MCP tools"""
    async def _tool_fn(*args):
        return await mcp.function_wrapper(tool_name, *args)
    return _tool_fn

def create_file_utilities(session_id: str):
    """Create file utility functions for the execution context"""
    session_dir = Path(f"media/generated/{session_id}")
    
    def find_file(filename: str) -> str:
        """Find a file in the session directory"""
        file_path = session_dir / filename
        if file_path.exists():
            return str(file_path)
        raise FileNotFoundError(f"File '{filename}' not found in session {session_id}")
    
    def get_session_files() -> list:
        """Get all files in the session directory"""
        if session_dir.exists():
            return [str(f) for f in session_dir.iterdir() if f.is_file()]
        return []
    
    def read_session_file(filename: str) -> str:
        """Read a file from the session directory"""
        file_path = find_file(filename)
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def write_session_file(filename: str, content: str) -> str:
        """Write a file to the session directory"""
        session_dir.mkdir(parents=True, exist_ok=True)
        file_path = session_dir / filename
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return str(file_path)
    
    return {
        'find_file': find_file,
        'get_session_files': get_session_files,
        'read_session_file': read_session_file,
        'write_session_file': write_session_file
    }

async def execute_python_code_variant(code: str, multi_mcp, session_id: str, inputs: dict = None) -> dict:
    """
    Execute a single Python code variant with safety
    """
    start_time = time.perf_counter()
    
    # Setup execution environment
    output_dir = Path(f"media/generated/{session_id}")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create tool proxies using function_wrapper
    tool_funcs = {}
    if multi_mcp:
        for tool in multi_mcp.get_all_tools():
            tool_funcs[tool.name] = make_tool_proxy(tool.name, multi_mcp)
    
    # Build safe execution context
    file_utils = create_file_utilities(session_id)
    safe_globals = {
        **SAFE_BUILTINS,
        **tool_funcs,
        **file_utils,
        'multi_mcp': multi_mcp,
        'session_id': session_id,
        'output_dir': str(output_dir),
        'inputs': inputs or {}
    }
    
    # Add input variables directly to execution context
    if inputs:
        safe_globals.update(inputs)
    
    try:
        # Handle async execution properly
        
        # Parse and transform code to handle async tool calls
        tree = ast.parse(code)
        
        # Create async wrapper function
        func_body = tree.body
        
        # 🚨 FIX: Add return statement for 'output' variable
        return_stmt = ast.Return(value=ast.Name(id='output', ctx=ast.Load()))
        func_body.append(return_stmt)
        
        async_func = ast.AsyncFunctionDef(
            name='__async_exec',
            args=ast.arguments(
                args=[], defaults=[], kwonlyargs=[], 
                kw_defaults=[], posonlyargs=[], vararg=None, kwarg=None
            ),
            body=func_body,
            decorator_list=[],
            returns=None
        )
        
        # Transform tool calls to be awaited
        class AwaitTransformer(ast.NodeTransformer):
            def visit_Call(self, node):
                self.generic_visit(node)
                if isinstance(node.func, ast.Name) and node.func.id in tool_funcs:
                    return ast.Await(value=node)
                return node
        
        async_func = AwaitTransformer().visit(async_func)
        
        # Create module with async function
        module = ast.Module(body=[async_func], type_ignores=[])
        ast.fix_missing_locations(module)
        
        # Compile and execute
        compiled = compile(module, '<string>', 'exec')
        local_vars = {}
        exec(compiled, safe_globals, local_vars)
        
        # Execute the async function
        result = await local_vars['__async_exec']()
        
        # Find created files
        created_files = []
        if output_dir.exists():
            created_files = [str(f) for f in output_dir.iterdir() if f.is_file()]
        
        # Extract result
        if result is None:
            result = {k: v for k, v in local_vars.items() if not k.startswith('__')}
        
        # 🚨 DEBUG: Print code execution result
        print(f"\n🚨 CODE EXECUTION RESULT:")
        print(f"Result: {result}")
        print(f"Local vars: {[k for k in local_vars.keys() if not k.startswith('__')]}")
        print("=" * 30)
        
        return {
            "status": "success",
            "result": result,
            "created_files": created_files,
            "execution_time": time.perf_counter() - start_time,
            "error": None
        }
        
    except Exception as e:
        return {
            "status": "failed",
            "result": {},
            "created_files": [],
            "execution_time": time.perf_counter() - start_time,
            "error": f"{type(e).__name__}: {str(e)}"
        }

async def execute_code_variants(code_variants: dict, multi_mcp, session_id: str, inputs: dict = None) -> dict:
    """
    Execute multiple code variants sequentially until one succeeds
    """
    start_time = time.perf_counter()
    
    # Sort variants by priority (CODE_1A, CODE_1B, CODE_1C)
    sorted_variants = sorted(code_variants.items())
    
    log_step(f"🐍 Executing {len(sorted_variants)} Python code variants", symbol="🧪")
    
    all_errors = []
    
    for variant_name, code in sorted_variants:
        log_step(f"⚡ Trying {variant_name}", symbol="🔬")
        
        result = await execute_python_code_variant(code, multi_mcp, session_id, inputs)

        print("HALT HERE")
        print(result)
        
        if result["status"] == "success":
            # Success!
            result["successful_variant"] = variant_name
            result["total_variants_tried"] = len(all_errors) + 1
            result["all_errors"] = all_errors
            
            log_step(f"✅ {variant_name} succeeded!", symbol="🎉")
            return result
        else:
            # Failed, try next
            error_msg = f"{variant_name}: {result['error']}"
            all_errors.append(error_msg)
            log_step(f"❌ {variant_name} failed: {result['error']}", symbol="🚨")
    
    # All variants failed
    log_step(f"💀 All {len(sorted_variants)} variants failed", symbol="❌")
    return {
        "status": "failed",
        "result": {},
        "created_files": [],
        "execution_time": time.perf_counter() - start_time,
        "error": f"All code variants failed. Errors: {'; '.join(all_errors)}",
        "failed_variants": len(sorted_variants),
        "all_errors": all_errors
    }

async def process_ast_updates(ast_updates: dict, session_id: str) -> dict:
    """Process AST-based file updates"""
    results = {
        "status": "success",
        "updated_files": [],
        "errors": []
    }
    
    session_dir = Path(f"media/generated/{session_id}")
    
    for filename, operations in ast_updates.items():
        try:
            file_path = session_dir / filename
            if not file_path.exists():
                results["errors"].append(f"File not found: {filename}")
                continue
                
            # Read existing file
            with open(file_path, 'r', encoding='utf-8') as f:
                original_content = f.read()
            
            # Apply operations based on file type
            if filename.endswith('.html'):
                updated_content = apply_html_operations(original_content, operations)
            elif filename.endswith('.css'):
                updated_content = apply_css_operations(original_content, operations)
            elif filename.endswith('.js'):
                updated_content = apply_js_operations(original_content, operations)
            else:
                results["errors"].append(f"Unsupported file type: {filename}")
                continue
            
            # Write updated file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(updated_content)
            
            results["updated_files"].append(filename)
            log_step(f"✅ Updated {filename}")
            
        except Exception as e:
            results["errors"].append(f"Error updating {filename}: {str(e)}")
            results["status"] = "partial_failure"
    
    return results

def apply_html_operations(content: str, operations: list) -> str:
    """Apply AST operations to HTML content"""
    soup = BeautifulSoup(content, 'html.parser')
    
    for op in operations:
        if op["type"] == "insert_before":
            target = soup.select_one(op["selector"])
            if target:
                new_element = BeautifulSoup(op["content"], 'html.parser')
                target.insert_before(new_element)
                
        elif op["type"] == "insert_after":
            target = soup.select_one(op["selector"])
            if target:
                new_element = BeautifulSoup(op["content"], 'html.parser')
                target.insert_after(new_element)
                
        elif op["type"] == "replace":
            target = soup.select_one(op["selector"])
            if target:
                new_element = BeautifulSoup(op["content"], 'html.parser')
                target.replace_with(new_element)
                
        elif op["type"] == "append_to":
            target = soup.select_one(op["selector"])
            if target:
                new_element = BeautifulSoup(op["content"], 'html.parser')
                target.append(new_element)
    
    return str(soup)

def apply_css_operations(content: str, operations: list) -> str:
    """Apply operations to CSS content"""
    for op in operations:
        if op["type"] == "add_rule":
            content += f"\n{op['selector']} {{\n{op['properties']}\n}}\n"
        elif op["type"] == "replace_rule":
            # Simple regex replacement for now
            pattern = rf"{re.escape(op['selector'])}\s*{{[^}}]*}}"
            replacement = f"{op['selector']} {{\n{op['properties']}\n}}"
            content = re.sub(pattern, replacement, content, flags=re.DOTALL)
    
    return content

def apply_js_operations(content: str, operations: list) -> str:
    """Apply operations to JavaScript content"""
    for op in operations:
        if op["type"] == "append_function":
            content += f"\n{op['function_code']}\n"
        elif op["type"] == "replace_function":
            # Simple regex replacement for function
            pattern = rf"function\s+{re.escape(op['function_name'])}\s*\([^)]*\)\s*{{[^}}]*}}"
            content = re.sub(pattern, op['function_code'], content, flags=re.DOTALL)
    
    return content

async def run_user_code(output_data: dict, multi_mcp, session_id: str = "default_session", inputs: dict = None) -> dict:
    """
    Main execution function: handles direct files, Python code, or both
    
    Args:
        output_data: CoderAgent output with 'files' and/or 'code_variants'
        multi_mcp: MCP client for tool calls
        session_id: Session identifier
        inputs: Input data for current task (from output_chain)
        
    Returns:
        Combined results from file creation and/or code execution
    """
    start_time = time.perf_counter()
    
    # 🚨 DEBUG: Print input data
    print(f"\n🚨 EXECUTOR RECEIVED:")
    print(f"Session: {session_id}")
    print(f"Output data keys: {list(output_data.keys()) if output_data else 'NONE'}")
    print(f"Inputs: {inputs}")
    if 'code_variants' in output_data:
        print(f"Code variants: {list(output_data['code_variants'].keys())}")
    print("=" * 50)
    
    results = {
        "status": "success",
        "session_id": session_id,
        "operations": [],
        "created_files": [],
        "file_results": {},
        "code_results": {},
        "total_time": 0.0,
        "error": None
    }
    
    log_step(f"🚀 Executor starting for session {session_id}", symbol="⚡")
    
    try:
        # Phase 1: Process Direct Files (if present)
        if "files" in output_data and output_data["files"]:
            log_step("📁 Phase 1: Direct file creation", symbol="🎯")
            
            file_results = await process_direct_files(output_data["files"], session_id)
            results["file_results"] = file_results
            results["operations"].append("direct_files")
            results["created_files"].extend(file_results["created_files"])
            
            if file_results["status"] != "success":
                results["status"] = "partial_failure"
                results["error"] = f"File creation issues: {file_results.get('errors', [])}"
        
        # Phase 2: Execute Python Code (if present)
        if "code_variants" in output_data and output_data["code_variants"]:
            log_step("🐍 Phase 2: Python code execution", symbol="⚙️")
            
            code_results = await execute_code_variants(
                output_data["code_variants"], multi_mcp, session_id, inputs
            )
            results["code_results"] = code_results
            results["operations"].append("python_code")
            
            if code_results.get("created_files"):
                results["created_files"].extend(code_results["created_files"])
            
            if code_results["status"] != "success":
                if results["status"] == "success":
                    results["status"] = "partial_failure"
                results["error"] = f"Code execution failed: {code_results['error']}"
        
        # Phase 3: Process AST Updates (if present)
        if "ast_updates" in output_data and output_data["ast_updates"]:
            log_step("🌳 Phase 3: AST-based file updates", symbol="🔄")
            
            ast_results = await process_ast_updates(output_data["ast_updates"], session_id)
            results["ast_results"] = ast_results
            results["operations"].append("ast_updates")
            
            if ast_results["status"] != "success":
                results["status"] = "partial_failure"
                results["error"] = f"AST update issues: {ast_results.get('errors', [])}"

        # Phase 3: Validate
        if not results["operations"]:
            results["status"] = "no_operation"
            results["error"] = "No files or code_variants found in output"
            log_step("⚠️ Nothing to execute", symbol="🤔")
        
        results["total_time"] = time.perf_counter() - start_time
        
        # Summary
        ops = ", ".join(results["operations"])
        file_count = len(results["created_files"])
        variant_info = ""
        if results.get("code_results", {}).get("successful_variant"):
            variant_info = f" ({results['code_results']['successful_variant']} succeeded)"
        
        log_step(f"🏁 Completed: {ops} | {file_count} files{variant_info} | {results['total_time']:.2f}s", symbol="✅")
        
        # 🚨 DEBUG: Print final executor result
        print(f"\n🚨 EXECUTOR FINAL RESULT:")
        print(f"Status: {results['status']}")
        print(f"Operations: {results['operations']}")
        print(f"Code results: {results.get('code_results', {}).get('result', 'NO_CODE_RESULT')}")
        print(f"Full results: {results}")
        print("=" * 60)
        
        return results
        
    except Exception as e:
        results["status"] = "failed"
        results["error"] = str(e)
        results["total_time"] = time.perf_counter() - start_time
        log_step(f"💥 Executor failed: {e}", symbol="❌")
        return results
