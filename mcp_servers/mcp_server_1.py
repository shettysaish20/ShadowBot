from mcp.server.fastmcp import FastMCP, Image
from mcp.server.fastmcp.prompts import base
from mcp.types import TextContent
from mcp import types
from PIL import Image as PILImage
import math
import sys
import os
import json
import faiss
import numpy as np
from pathlib import Path
import requests
import subprocess
import sqlite3
from io import StringIO
from tqdm import tqdm
import hashlib

# Models
from models import (
    AddInput, AddOutput,
    SubtractInput, SubtractOutput,
    MultiplyInput, MultiplyOutput,
    DivideInput, DivideOutput,
    PowerInput, PowerOutput,
    CbrtInput, CbrtOutput,
    FactorialInput, FactorialOutput,
    RemainderInput, RemainderOutput,
    SinInput, SinOutput,
    CosInput, CosOutput,
    TanInput, TanOutput,
    MineInput, MineOutput,
    CreateThumbnailInput, ImageOutput,
    StringsToIntsInput, StringsToIntsOutput,
    ExpSumInput, ExpSumOutput,
    FibonacciInput, FibonacciOutput,
    PythonCodeInput, PythonCodeOutput,
    ShellCommandInput,
)

mcp = FastMCP("Calculator")

# ------------------- Tools -------------------

@mcp.tool()
def add(input: AddInput) -> AddOutput:
    """Add two numbers. """
    print("CALLED: add(AddInput) -> AddOutput")
    return AddOutput(result=input.a + input.b)

@mcp.tool()
def subtract(input: SubtractInput) -> SubtractOutput:
    """Subtract one number from another. """
    print("CALLED: subtract(SubtractInput) -> SubtractOutput")
    return SubtractOutput(result=input.a - input.b)

@mcp.tool()
def multiply(input: MultiplyInput) -> MultiplyOutput:
    """Multiply two integers. """
    print("CALLED: multiply(MultiplyInput) -> MultiplyOutput")
    return MultiplyOutput(result=input.a * input.b)

@mcp.tool()
def divide(input: DivideInput) -> DivideOutput:
    """Divide one number by another. """
    print("CALLED: divide(DivideInput) -> DivideOutput")
    return DivideOutput(result=input.a / input.b)

@mcp.tool()
def power(input: PowerInput) -> PowerOutput:
    """Compute a raised to the power of b. """
    print("CALLED: power(PowerInput) -> PowerOutput")
    return PowerOutput(result=input.a ** input.b)

@mcp.tool()
def cbrt(input: CbrtInput) -> CbrtOutput:
    """Compute the cube root of a number. """
    print("CALLED: cbrt(CbrtInput) -> CbrtOutput")
    return CbrtOutput(result=input.a ** (1/3))

@mcp.tool()
def factorial(input: FactorialInput) -> FactorialOutput:
    """Compute the factorial of a number. """
    print("CALLED: factorial(FactorialInput) -> FactorialOutput")
    return FactorialOutput(result=math.factorial(input.a))

@mcp.tool()
def remainder(input: RemainderInput) -> RemainderOutput:
    """Compute the remainder of a divided by b. """
    print("CALLED: remainder(RemainderInput) -> RemainderOutput")
    return RemainderOutput(result=input.a % input.b)

@mcp.tool()
def sin(input: SinInput) -> SinOutput:
    """Compute sine of an angle in radians. """
    print("CALLED: sin(SinInput) -> SinOutput")
    return SinOutput(result=math.sin(input.a))

@mcp.tool()
def cos(input: CosInput) -> CosOutput:
    """Compute cosine of an angle in radians. """
    print("CALLED: cos(CosInput) -> CosOutput")
    return CosOutput(result=math.cos(input.a))

@mcp.tool()
def tan(input: TanInput) -> TanOutput:
    """Compute tangent of an angle in radians. """
    print("CALLED: tan(TanInput) -> TanOutput")
    return TanOutput(result=math.tan(input.a))

@mcp.tool()
def mine(input: MineInput) -> MineOutput:
    """Special mining tool. """
    print("CALLED: mine(MineInput) -> MineOutput")
    return MineOutput(result=input.a - input.b - input.b)

@mcp.tool()
def create_thumbnail(input: CreateThumbnailInput) -> ImageOutput:
    """Create a 100x100 thumbnail from image. """
    print("CALLED: create_thumbnail(CreateThumbnailInput) -> ImageOutput")
    img = PILImage.open(input.image_path)
    img.thumbnail((100, 100))
    return ImageOutput(data=img.tobytes(), format="png")

@mcp.tool()
def strings_to_chars_to_int(input: StringsToIntsInput) -> StringsToIntsOutput:
    """Convert characters to ASCII values. """
    print("CALLED: strings_to_chars_to_int(StringsToIntsInput) -> StringsToIntsOutput")
    ascii_values = [ord(char) for char in input.string]
    return StringsToIntsOutput(ascii_values=ascii_values)



@mcp.tool()
def int_list_to_exponential_sum(input: ExpSumInput) -> ExpSumOutput:
    """Sum exponentials of int list. """
    print("CALLED: int_list_to_exponential_sum(ExpSumInput) -> ExpSumOutput")
    result = sum(math.exp(i) for i in input.numbers)
    return ExpSumOutput(result=result)

@mcp.tool()
def fibonacci_numbers(input: FibonacciInput) -> FibonacciOutput:
    """Generate first n Fibonacci numbers. """
    print("CALLED: fibonacci_numbers(FibonacciInput) -> FibonacciOutput")
    n = input.n
    if n <= 0:
        return FibonacciOutput(result=[])
    fib_sequence = [0, 1]
    for _ in range(2, n):
        fib_sequence.append(fib_sequence[-1] + fib_sequence[-2])
    return FibonacciOutput(result=fib_sequence[:n])



# @mcp.tool()
# def run_python_sandbox(input: PythonCodeInput) -> PythonCodeOutput:
#     """Run math code in Python sandbox. """
#     allowed_globals = {"__builtins__": __builtins__}
#     local_vars = {}

#     stdout_backup = sys.stdout
#     output_buffer = StringIO()
#     sys.stdout = output_buffer

#     try:
#         exec(input.code, allowed_globals, local_vars)
#         sys.stdout = stdout_backup
#         result = local_vars.get("result", output_buffer.getvalue().strip() or "Executed.")
#         return PythonCodeOutput(result=str(result))
#     except Exception as e:
#         sys.stdout = stdout_backup
#         return PythonCodeOutput(result=f"ERROR: {e}")

# @mcp.tool()
# def run_shell_command(input: ShellCommandInput) -> PythonCodeOutput:
#     """Run a safe shell command. """
#     allowed_commands = ["ls", "cat", "pwd", "df", "whoami"]

#     tokens = input.command.strip().split()
#     if tokens[0] not in allowed_commands:
#         return PythonCodeOutput(result="Command not allowed.")

#     try:
#         result = subprocess.run(
#             input.command, shell=True,
#             capture_output=True, timeout=3
#         )
#         output = result.stdout.decode() or result.stderr.decode()
#         return PythonCodeOutput(result=output.strip())
#     except Exception as e:
#         return PythonCodeOutput(result=f"ERROR: {e}")

# @mcp.tool()
# def run_sql_query(input: PythonCodeInput) -> PythonCodeOutput:
#     """Run safe SELECT-only SQL query. """
#     if not input.code.strip().lower().startswith("select"):
#         return PythonCodeOutput(result="Only SELECT queries allowed.")

#     try:
#         conn = sqlite3.connect("example.db")
#         cursor = conn.cursor()
#         cursor.execute(input.code)
#         rows = cursor.fetchall()
#         result = "\n".join(str(row) for row in rows)
#         return PythonCodeOutput(result=result or "No results.")
#     except Exception as e:
#         return PythonCodeOutput(result=f"ERROR: {e}")

# ------------------- Resources -------------------

@mcp.resource("greeting://{name}")
def get_greeting(name: str) -> str:
    """Get a personalized greeting. """
    print("CALLED: get_greeting(name: str) -> str")
    return f"Hello, {name}!"

# ------------------- Prompts -------------------

@mcp.prompt()
def review_code(code: str) -> str:
    """Ask to review a code snippet. """
    return f"Please review this code:\n\n{code}"

@mcp.prompt()
def debug_error(error: str) -> list:
    """Help debug an error. """
    return [
        base.UserMessage("I'm seeing this error:"),
        base.UserMessage(error),
        base.AssistantMessage("I'll help debug that. What have you tried so far?"),
    ]

# ------------------- Main -------------------

if __name__ == "__main__":
    print("mcp_server_1.py starting")
    if len(sys.argv) > 1 and sys.argv[1] == "dev":
        mcp.run()  # Run without transport for dev server
    else:
        mcp.run(transport="stdio")  # Run with stdio for direct execution
        print("\nShutting down...")
