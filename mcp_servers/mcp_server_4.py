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
    CbrtInput, CbrtOutput,
    FactorialInput, FactorialOutput,
    RemainderInput, RemainderOutput,
    SinInput, SinOutput,
    CosInput, CosOutput,
    TanInput, TanOutput,
    MineInput, MineOutput,
    CreateThumbnailInput, ImageOutput,
    StringsToIntsInput, StringsToIntsOutput,
    ExpSumInput, ExpSumOutput
)

mcp = FastMCP("Mixed 4")

@mcp.tool()
def add(input: AddInput) -> AddOutput:
    """Add two numbers. """
    print("CALLED: add(AddInput) -> AddOutput")
    return AddOutput(result=input.a + input.b)

@mcp.tool()
def subtract(input: SubtractInput) -> SubtractOutput:
    """Subtract one number from another."""
    print("CALLED: subtract(SubtractInput) -> SubtractOutput")
    return SubtractOutput(result=input.a - input.b)

@mcp.tool()
def multiply(a, b):
    """Multiply two integers."""
    print("CALLED: multiply(a, b) -> result")
    return a * b

@mcp.tool()
def no_input():
    """Doesn't take any input."""
    print("CALLED: multiply(a, b) -> result")
    return "hello"

@mcp.tool()
def int_list_to_exponential_sum(input: ExpSumInput) -> ExpSumOutput:
    """Sum exponentials of int list. """
    print("CALLED: int_list_to_exponential_sum(ExpSumInput) -> ExpSumOutput")
    result = sum(math.exp(i) for i in input.numbers)  # ✅ FIXED
    return ExpSumOutput(result=result)


@mcp.tool()
def strings_to_chars_to_int(input: StringsToIntsInput) -> StringsToIntsOutput:
    """Convert characters to ASCII values. """
    print("CALLED: strings_to_chars_to_int(StringsToIntsInput) -> StringsToIntsOutput")
    ascii_values = [ord(char) for char in input.string]
    return StringsToIntsOutput(ascii_values=ascii_values)

# ------------------- Main -------------------

if __name__ == "__main__":
    print("mcp_server_4.py starting")
    if len(sys.argv) > 1 and sys.argv[1] == "dev":
        mcp.run()  # Run without transport for dev server
    else:
        mcp.run(transport="stdio")  # Run with stdio for direct execution
        print("\nShutting down...")