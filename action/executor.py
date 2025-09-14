import os
import json
import time
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Dict, Any
import traceback
import matplotlib
import pytesseract
from bs4 import BeautifulSoup
import ast
import re
import io
import tokenize
import cssutils
from config.log_config import (
    get_logger,
    logger_step,
    logger_json_block,
    logger_prompt,
    logger_code_block,
    logger_error,
)

logger = get_logger(__name__)

# Simple imports for Python execution
SAFE_BUILTINS = {
    "__builtins__": {
        "len": len,
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "list": list,
        "dict": dict,
        "tuple": tuple,
        "set": set,
        "enumerate": enumerate,
        "range": range,
        "zip": zip,
        "print": print,
        "type": type,
        "isinstance": isinstance,
        "ValueError": ValueError,
        "TypeError": TypeError,
        "KeyError": KeyError,
        "IndexError": IndexError,
        "FileNotFoundError": FileNotFoundError,
        "Exception": Exception,
        "min": min,
        "max": max,
        "sum": sum,
        "open": open,
        "json": json,
        "os": os,
        "Path": Path,
        "matplotlib": matplotlib,
        "pytesseract": pytesseract,
        "__import__": __import__,
    }
}

def log_step(message, symbol="🔧"):
    """Simple logging with timestamp"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"{symbol} [{timestamp}] {message}")


def _build_async_module(from_body: list[ast.stmt], tool_func_names: set[str]) -> ast.Module:
    """Construct an async wrapper function and await known tool calls.

    Parameters:
    - from_body: list of AST statements comprising the body to execute.
    - tool_func_names: names that should be awaited when called.
    """
    async_func = ast.AsyncFunctionDef(
        name="__async_exec",
        args=ast.arguments(
            args=[],
            posonlyargs=[],
            kwonlyargs=[],
            kw_defaults=[],
            defaults=[],
            vararg=None,
            kwarg=None,
        ),
        body=from_body,
        decorator_list=[],
        returns=None,
        type_comment=None,
    )

    class _AwaitTransformer(ast.NodeTransformer):
        def visit_Call(self, node):
            self.generic_visit(node)
            if isinstance(node.func, ast.Name) and node.func.id in tool_func_names:
                return ast.Await(value=node)
            return node

    async_func = _AwaitTransformer().visit(async_func)
    module = ast.Module(body=[async_func], type_ignores=[])
    ast.fix_missing_locations(module)
    return module


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

    results: Dict[str, Any] = {
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
        log_step(
            f"🎉 Created {results['file_count']} files in {results['execution_time']:.2f}s",
            symbol="✅",
        )
    return results


def make_tool_proxy(tool_name: str, mcp):
    """Create async proxy function for MCP tools."""
    async def _tool_fn(*args, **kwargs):
        return await mcp.function_wrapper(tool_name, *args, **kwargs)

    return _tool_fn


def create_file_utilities(session_id: str):
    """Create file utility functions for the execution context."""
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
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    def write_session_file(filename: str, content: str) -> str:
        """Write a file to the session directory"""
        session_dir.mkdir(parents=True, exist_ok=True)
        file_path = session_dir / filename
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return str(file_path)

    return {
        "find_file": find_file,
        "get_session_files": get_session_files,
        "read_session_file": read_session_file,
        "write_session_file": write_session_file,
    }


async def execute_python_code_variant(
    code: str, multi_mcp, session_id: str, inputs: dict | None = None
) -> dict:
    """Execute a single Python code variant with safety and async tool support."""
    start_time = time.perf_counter()
    
    # Setup execution environment
    output_dir = Path(f"media/generated/{session_id}")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create tool proxies using function_wrapper
    tool_funcs: Dict[str, Any] = {}
    tool_func_names: set[str] = set()
    if multi_mcp:
        for tool in multi_mcp.get_all_tools():
            tool_funcs[tool.name] = make_tool_proxy(tool.name, multi_mcp)
            tool_func_names.add(tool.name)

    # Build safe execution context
    file_utils = create_file_utilities(session_id)
    # Normalize inputs for downstream usage
    inputs_dict = inputs or {}

    # Provide a resilient session_context for generated code that expects it
    default_session_context = {
        "session_id": session_id,
        "output_dir": str(output_dir),
        "file_manifest": inputs_dict.get("file_manifest") or [],
        "created_at": datetime.now().isoformat(),
    }
    provided_session_context = inputs_dict.get("session_context")
    session_context_obj = provided_session_context or default_session_context

    safe_globals: Dict[str, Any] = {
        **SAFE_BUILTINS,
        **tool_funcs,
        **file_utils,
        "multi_mcp": multi_mcp,
        "session_id": session_id,
        "output_dir": str(output_dir),
        "inputs": inputs_dict,
        # Commonly-referenced alias for session metadata expected by prompts/codegen
        "session_context": session_context_obj,
        "context": session_context_obj,
        "log_step": log_step,
    }
    if inputs_dict:
        # Expose provided inputs as globals for convenience, without overriding session_context alias
        # (session_context already set above; keep that value stable)
        safe_globals.update({k: v for k, v in inputs_dict.items() if k != "session_context"})

    def _evenize_before_uUxX(text: str) -> str:
        """Ensure an even number of backslashes immediately before u/U/x to avoid unicode escapes.

        For any run of N backslashes followed by [uUxX], if N is odd, add one more backslash.
        """
        def repl(m: re.Match) -> str:
            slashes = m.group(1)
            ch = m.group(2)
            if len(slashes) % 2 == 1:
                slashes += "\\"
            return slashes + ch

        return re.sub(r"(\\+)([uUxX])", repl, text)

    def _sanitize_unicode_escapes_basic(s: str) -> str:
        # Basic pass: evenize backslashes before u/U/x globally to prevent unicode/hex escapes
        return _evenize_before_uUxX(s)

    def _sanitize_unicode_escapes_in_strings(s: str) -> str:
        # Token-based pass: only modify non-raw string literals' contents
        out = []
        try:
            for tok in tokenize.generate_tokens(io.StringIO(s).readline):
                ttype, tstr, start, end, line = tok
                if ttype == tokenize.STRING:
                    # Detect prefix like r, u, b, f (any order, any case)
                    m = re.match(r"^([rRuUbBfF]*)('''|\"\"\"|'|\")([\s\S]*)\2$", tstr)
                    if m:
                        prefix, quote, body = m.groups()
                        is_raw = 'r' in prefix.lower()
                        # Only adjust non-raw strings; raw strings shouldn't need fix
                        if not is_raw:
                            body = _evenize_before_uUxX(body)
                        tstr = f"{prefix}{quote}{body}{quote}"
                out.append((ttype, tstr))
        except Exception:
            return s  # if tokenizing fails, return original
        # Reconstruct code
        return tokenize.untokenize(out)

    def _convert_backslashes_to_slashes_in_strings(s: str) -> str:
        """As a last resort, convert backslashes to forward slashes inside non-raw string literals only."""
        out = []
        try:
            for tok in tokenize.generate_tokens(io.StringIO(s).readline):
                ttype, tstr, *_ = tok
                if ttype == tokenize.STRING:
                    m = re.match(r"^([rRuUbBfF]*)('''|\"\"\"|'|\")([\s\S]*)\2$", tstr)
                    if m:
                        prefix, quote, body = m.groups()
                        is_raw = 'r' in prefix.lower()
                        if not is_raw:
                            body = body.replace("\\", "/")
                        tstr = f"{prefix}{quote}{body}{quote}"
                out.append((ttype, tstr))
        except Exception:
            return s
        return tokenize.untokenize(out)

    def _normalize_pathlike_strings(s: str) -> str:
        """Convert backslashes to forward slashes in likely path literals to avoid escapes like \a, \t, etc.

        Heuristic: operate only on non-raw string tokens whose body contains a backslash and looks path-like
        (mentions 'media' or 'uploads' or has a common file extension).
        """
        path_exts = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".pdf", ".txt", ".md", ".html", ".css", ".js")
        out = []
        try:
            for tok in tokenize.generate_tokens(io.StringIO(s).readline):
                ttype, tstr, *_ = tok
                if ttype == tokenize.STRING:
                    m = re.match(r"^([rRuUbBfF]*)('''|\"\"\"|'|\")([\s\S]*)\2$", tstr)
                    if m:
                        prefix, quote, body = m.groups()
                        is_raw = 'r' in prefix.lower()
                        if not is_raw and "\\" in body:
                            body_lc = body.lower()
                            looks_path = ("media" in body_lc) or ("uploads" in body_lc) or any(ext in body_lc for ext in path_exts)
                            if looks_path:
                                body = body.replace("\\", "/")
                        tstr = f"{prefix}{quote}{body}{quote}"
                out.append((ttype, tstr))
        except Exception:
            return s
        return tokenize.untokenize(out)

    try:
        # First pass: global basic sanitize + normalize path-like strings to use forward slashes
        code = _sanitize_unicode_escapes_basic(code)
        code = _normalize_pathlike_strings(code)

        # Parse and transform code to handle async tool calls
        tree = ast.parse(code)
        
        # Create async wrapper function
        func_body = tree.body

        # Safely return 'output' if defined; else return None
        try_assign = ast.Try(
            body=[
                ast.Assign(
                    targets=[ast.Name(id="_executor_tmp_output", ctx=ast.Store())],
                    value=ast.Name(id="output", ctx=ast.Load()),
                )
            ],
            handlers=[
                ast.ExceptHandler(
                    type=ast.Name(id="NameError", ctx=ast.Load()),
                    name=None,
                    body=[
                        ast.Assign(
                            targets=[
                                ast.Name(id="_executor_tmp_output", ctx=ast.Store())
                            ],
                            value=ast.Constant(value=None),
                        )
                    ],
                )
            ],
            orelse=[],
            finalbody=[],
        )

        func_body.append(try_assign)
        func_body.append(
            ast.Return(value=ast.Name(id="_executor_tmp_output", ctx=ast.Load()))
        )

        module = _build_async_module(func_body, tool_func_names)

        compiled = compile(module, "<string>", "exec")
        local_vars: Dict[str, Any] = {}
        exec(compiled, safe_globals, local_vars)
        try:
            result = await local_vars["__async_exec"]()
        except Exception as runtime_e:
            # Fallback: if pytesseract is missing, rewrite code to use MCP caption tool(s)
            if isinstance(runtime_e, ModuleNotFoundError) and "pytesseract" in str(runtime_e):
                # Choose an available caption tool name
                fallback_tool = None
                for name in ("caption_images", "caption_image"):
                    if name in tool_func_names:
                        fallback_tool = name
                        break
                if not fallback_tool:
                    raise

                class _PytesseractFallback(ast.NodeTransformer):
                    def visit_Import(self, node: ast.Import):
                        # Drop any direct import of pytesseract to avoid ModuleNotFoundError
                        for alias in node.names:
                            if alias.name == "pytesseract":
                                return None
                        return node

                    def visit_ImportFrom(self, node: ast.ImportFrom):
                        if node.module == "pytesseract":
                            return None
                        return node

                    def visit_Call(self, node: ast.Call):
                        self.generic_visit(node)
                        # Replace pytesseract.image_to_string(...) -> caption tool(...)
                        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                            if node.func.value.id == "pytesseract" and node.func.attr in ("image_to_string", "image_to_data"):
                                return ast.Call(
                                    func=ast.Name(id=fallback_tool, ctx=ast.Load()),
                                    args=node.args,
                                    keywords=node.keywords,
                                )
                        return node

                # Rebuild module with transformed body
                tree2 = ast.parse(code)
                func_body2 = _PytesseractFallback().visit(tree2).body

                # Safely return 'output' if defined; else return None
                try_assign2 = ast.Try(
                    body=[
                        ast.Assign(
                            targets=[ast.Name(id="_executor_tmp_output", ctx=ast.Store())],
                            value=ast.Name(id="output", ctx=ast.Load()),
                        )
                    ],
                    handlers=[
                        ast.ExceptHandler(
                            type=ast.Name(id="NameError", ctx=ast.Load()),
                            name=None,
                            body=[
                                ast.Assign(
                                    targets=[ast.Name(id="_executor_tmp_output", ctx=ast.Store())],
                                    value=ast.Constant(value=None),
                                )
                            ],
                        )
                    ],
                    orelse=[],
                    finalbody=[],
                )
                func_body2.append(try_assign2)
                func_body2.append(
                    ast.Return(value=ast.Name(id="_executor_tmp_output", ctx=ast.Load()))
                )

                module2 = _build_async_module(func_body2, tool_func_names)
                compiled2 = compile(module2, "<string>", "exec")
                local_vars2: Dict[str, Any] = {}
                exec(compiled2, safe_globals, local_vars2)
                result = await local_vars2["__async_exec"]()
            else:
                raise

        created_files = []
        if output_dir.exists():
            created_files = [str(f) for f in output_dir.iterdir() if f.is_file()]
        
        # Extract result
        if result is None:
            result = {k: v for k, v in local_vars.items() if not k.startswith('__')}
        
        # 🚨 DEBUG: Print code execution result
        # print(f"\n🚨 CODE EXECUTION RESULT:")
        # print(f"Result: {result}")
        print(f"Local vars: {[k for k in local_vars.keys() if not k.startswith('__')]}")
        print("=" * 30)
        
        return {
            "status": "success",
            "result": result,
            "created_files": created_files,
            "execution_time": time.perf_counter() - start_time,
            "error": None
        }
    except SyntaxError as se:
        # If unicodeescape still slipped through, retry with token-based string sanitizer
        if "unicodeescape" in str(se).lower():
            try:
                log_step("🛠️ Detected unicodeescape during parse; retrying with string-literal sanitizer", symbol="🩹")
                code_retry = _sanitize_unicode_escapes_in_strings(code)
                tree = ast.parse(code_retry)

                func_body = tree.body
                try_assign = ast.Try(
                    body=[
                        ast.Assign(
                            targets=[ast.Name(id="_executor_tmp_output", ctx=ast.Store())],
                            value=ast.Name(id="output", ctx=ast.Load()),
                        )
                    ],
                    handlers=[
                        ast.ExceptHandler(
                            type=ast.Name(id="NameError", ctx=ast.Load()),
                            name=None,
                            body=[
                                ast.Assign(
                                    targets=[ast.Name(id="_executor_tmp_output", ctx=ast.Store())],
                                    value=ast.Constant(value=None),
                                )
                            ],
                        )
                    ],
                    orelse=[],
                    finalbody=[],
                )
                func_body.append(try_assign)
                func_body.append(
                    ast.Return(value=ast.Name(id="_executor_tmp_output", ctx=ast.Load()))
                )

                log_step(
                    f"🔁 Retrying parse success; sanitized code length={len(code_retry)}",
                    symbol="🩹",
                )
                module = _build_async_module(func_body, tool_func_names)
                compiled = compile(module, "<string>", "exec")
                local_vars: Dict[str, Any] = {}
                exec(compiled, safe_globals, local_vars)
                result = await local_vars["__async_exec"]()

                created_files = []
                if output_dir.exists():
                    created_files = [str(f) for f in output_dir.iterdir() if f.is_file()]

                return {
                    "status": "success",
                    "result": result,
                    "created_files": created_files,
                    "execution_time": time.perf_counter() - start_time,
                    "error": None,
                }
            except Exception as e2:
                # Try one more fallback by converting backslashes to forward slashes in strings
                try:
                    if "unicodeescape" in str(e2).lower():
                        log_step("🛡️ Second fallback: converting backslashes to slashes inside strings", symbol="🩹")
                        code_retry2 = _convert_backslashes_to_slashes_in_strings(code)
                        tree = ast.parse(code_retry2)

                        func_body = tree.body
                        try_assign = ast.Try(
                            body=[
                                ast.Assign(
                                    targets=[ast.Name(id="_executor_tmp_output", ctx=ast.Store())],
                                    value=ast.Name(id="output", ctx=ast.Load()),
                                )
                            ],
                            handlers=[
                                ast.ExceptHandler(
                                    type=ast.Name(id="NameError", ctx=ast.Load()),
                                    name=None,
                                    body=[
                                        ast.Assign(
                                            targets=[ast.Name(id="_executor_tmp_output", ctx=ast.Store())],
                                            value=ast.Constant(value=None),
                                        )
                                    ],
                                )
                            ],
                            orelse=[],
                            finalbody=[],
                        )
                        func_body.append(try_assign)
                        func_body.append(
                            ast.Return(value=ast.Name(id="_executor_tmp_output", ctx=ast.Load()))
                        )

                        module = _build_async_module(func_body, tool_func_names)
                        compiled = compile(module, "<string>", "exec")
                        local_vars: Dict[str, Any] = {}
                        exec(compiled, safe_globals, local_vars)
                        result = await local_vars["__async_exec"]()

                        created_files = []
                        if output_dir.exists():
                            created_files = [str(f) for f in output_dir.iterdir() if f.is_file()]

                        return {
                            "status": "success",
                            "result": result,
                            "created_files": created_files,
                            "execution_time": time.perf_counter() - start_time,
                            "error": None,
                        }
                except Exception as e3:
                    return {
                        "status": "failed",
                        "result": {},
                        "created_files": [],
                        "execution_time": time.perf_counter() - start_time,
                        "error": f"{type(se).__name__}: {str(se)} | retry_failed: {type(e2).__name__}: {str(e2)} | final_failed: {type(e3).__name__}: {str(e3)}",
                    }
                return {
                    "status": "failed",
                    "result": {},
                    "created_files": [],
                    "execution_time": time.perf_counter() - start_time,
                    "error": f"{type(se).__name__}: {str(se)} | retry_failed: {type(e2).__name__}: {str(e2)}",
                }
        # Other syntax errors
        return {
            "status": "failed",
            "result": {},
            "created_files": [],
            "execution_time": time.perf_counter() - start_time,
            "error": f"{type(se).__name__}: {str(se)}",
        }
    except Exception as e:
        return {
            "status": "failed",
            "result": {},
            "created_files": [],
            "execution_time": time.perf_counter() - start_time,
            "error": f"{type(e).__name__}: {str(e)}"
        }


async def execute_code_variants(
    code_variants: dict,
    multi_mcp,
    session_id: str,
    inputs: dict | None = None,
    step_id: str | None = None,
    iteration: str | None = None,
) -> dict:
    """Execute multiple code variants sequentially until one succeeds."""
    start_time = time.perf_counter()

    # Sort variants by key name; callers often use CODE_1, CODE_2, etc.
    sorted_variants = sorted(code_variants.items(), key=lambda kv: kv[0])
    log_step(f"🐍 Executing {len(sorted_variants)} Python code variants", symbol="🧪")

    all_errors: list[str] = []

    for variant_name, code in sorted_variants:
        log_step(f"⚡ Trying {variant_name}", symbol="🔬")

        # Extra safety: sanitize unicode-like escapes once at variant level too
        code = re.sub(r"\\([uUxX])", r"\\\\\1", code)

        result = await execute_python_code_variant(code, multi_mcp, session_id, inputs)

        try:
            logger_code_block(
                logger,
                f"⚡ Executor results for session {session_id} step {step_id}, iteration {iteration} - variant {variant_name}",
                code,
                result,
            )
        except Exception:
            pass

        if result.get("status") == "success":
            result["successful_variant"] = variant_name
            result["total_variants_tried"] = len(all_errors) + 1
            result["all_errors"] = all_errors
            log_step(f"✅ {variant_name} succeeded!", symbol="🎉")
            return result

        # Failed, try next
        error_msg = f"{variant_name}: {result.get('error')}"
        all_errors.append(error_msg)
        log_step(f"❌ {variant_name} failed: {result.get('error')}", symbol="🚨")

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
    """Apply AST operations to HTML content."""
    soup = BeautifulSoup(content, "html.parser")
    for op in operations:
        if op.get("type") == "insert_before":
            target = soup.select_one(op.get("selector", ""))
            if target:
                new_element = BeautifulSoup(op.get("content", ""), "html.parser")
                target.insert_before(new_element)
        elif op.get("type") == "insert_after":
            target = soup.select_one(op.get("selector", ""))
            if target:
                new_element = BeautifulSoup(op.get("content", ""), "html.parser")
                target.insert_after(new_element)
        elif op.get("type") == "replace":
            target = soup.select_one(op.get("selector", ""))
            if target:
                new_element = BeautifulSoup(op.get("content", ""), "html.parser")
                target.replace_with(new_element)
        elif op.get("type") == "append_to":
            target = soup.select_one(op.get("selector", ""))
            if target:
                new_element = BeautifulSoup(op.get("content", ""), "html.parser")
                target.append(new_element)
    return str(soup)


def apply_css_operations(content: str, operations: list) -> str:
    """Apply operations to CSS content."""
    for op in operations:
        if op.get("type") == "add_rule":
            content += f"\n{op['selector']} {{\n{op['properties']}\n}}\n"
        elif op.get("type") == "replace_rule":
            pattern = rf"{re.escape(op['selector'])}\s*{{[^}}]*}}"
            replacement = f"{op['selector']} {{\n{op['properties']}\n}}"
            content = re.sub(pattern, replacement, content, flags=re.DOTALL)
    return content


def apply_js_operations(content: str, operations: list) -> str:
    """Apply operations to JavaScript content."""
    for op in operations:
        if op.get("type") == "append_function":
            content += f"\n{op['function_code']}\n"
        elif op.get("type") == "replace_function":
            pattern = rf"function\s+{re.escape(op['function_name'])}\s*\([^)]*\)\s*{{[^}}]*}}"
            content = re.sub(pattern, op["function_code"], content, flags=re.DOTALL)
    return content


async def run_user_code(
    output_data: dict,
    multi_mcp,
    session_id: str = "default_session",
    inputs: dict | None = None,
) -> dict:
    """Main execution: handle direct files, Python code variants, and AST updates."""
    start_time = time.perf_counter()

    results: Dict[str, Any] = {
        "status": "success",
        "session_id": session_id,
        "operations": [],
        "created_files": [],
        "file_results": {},
        "code_results": {},
        "total_time": 0.0,
        "error": None,
    }

    log_step(f"🚀 Executor starting for session {session_id}", symbol="⚡")

    try:
        # Phase 1: Direct files
        if output_data.get("files"):
            log_step("📁 Phase 1: Direct file creation", symbol="🎯")
            file_results = await process_direct_files(output_data["files"], session_id)
            results["file_results"] = file_results
            results["operations"].append("direct_files")
            results["created_files"].extend(file_results.get("created_files", []))
            if file_results.get("status") != "success":
                results["status"] = "partial_failure"
                results["error"] = f"File creation issues: {file_results.get('errors', [])}"

        # Phase 2: Execute Python Code (if present)
        if output_data.get("code_variants"):
            log_step("🐍 Phase 2: Python code execution", symbol="⚙️")
            code_results = await execute_code_variants(
                output_data["code_variants"], multi_mcp, session_id, inputs
            )
            results["code_results"] = code_results
            results["operations"].append("python_code")
            if code_results.get("created_files"):
                results["created_files"].extend(code_results["created_files"])
            if code_results.get("status") != "success":
                if results["status"] == "success":
                    results["status"] = "partial_failure"
                results["error"] = f"Code execution failed: {code_results.get('error')}"

        # Phase 3: AST updates
        if output_data.get("ast_updates"):
            log_step("🌳 Phase 3: AST-based file updates", symbol="🔄")
            ast_results = await process_ast_updates(output_data["ast_updates"], session_id)
            results["ast_results"] = ast_results
            results["operations"].append("ast_updates")
            if ast_results.get("status") != "success":
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
        ## DEBUG
        # print(f"Code results: {results.get('code_results', {}).get('result', 'NO_CODE_RESULT')}")
        # print(f"Full results: {results}")
        print("=" * 60)
        
        return results
        
    except Exception as e:
        results["status"] = "failed"
        results["error"] = str(e)
        results["total_time"] = time.perf_counter() - start_time
        log_step(f"💥 Executor failed: {e}", symbol="❌")
        return results
