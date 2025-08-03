from mcp.server.fastmcp import FastMCP, Context
import httpx
from bs4 import BeautifulSoup
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
import urllib.parse
import sys
import traceback
from datetime import datetime, timedelta
import time
import re
from pydantic import BaseModel, Field
from models import SearchInput, UrlInput, URLListOutput, SummaryInput
from models import PythonCodeOutput
from tools.web_tools_async import smart_web_extract
from tools.switch_search_method import smart_search
from mcp.types import TextContent
from google import genai
from dotenv import load_dotenv
import asyncio
import os
import random

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Initialize FastMCP server
mcp = FastMCP("ddg-search", timeout=20)

@mcp.tool()
async def search_web_with_text_content(input: SearchInput, ctx: Context) -> dict:
    """Search web and return URLs with extracted text content. Gets both URLs and readable text from top search results."""
    
    try:
        # Step 1: Get URLs using existing function
        urls = await smart_search(input.query, input.max_results)
        
        if not urls:
            return {
                "content": [
                    TextContent(
                        type="text",
                        text="[error] No search results found"
                    )
                ]
            }
        
        # Step 2: Extract text content from each URL
        results = []
        max_extracts = min(len(urls), 5)  # Limit to avoid timeout
        
        for i, url in enumerate(urls[:max_extracts]):
            try:
                # Use existing web extraction function
                web_result = await asyncio.wait_for(smart_web_extract(url), timeout=15)
                text_content = web_result.get("best_text", "")[:4000]  # Limit length
                text_content = text_content.replace('\n', ' ').replace('  ', ' ').strip()
                
                results.append({
                    "url": url,
                    "content": text_content if text_content.strip() else "[error] No readable content found",
                    "images": web_result.get("images", []),  # ✅ NEW: Include images
                    "rank": i + 1
                })
                
            except asyncio.TimeoutError:
                results.append({
                    "url": url,
                    "content": "[error] Timeout while extracting content",
                    "rank": i + 1
                })
            except Exception as e:
                results.append({
                    "url": url,
                    "content": f"[error] {str(e)}",
                    "rank": i + 1
                })
        
        # Add remaining URLs without content extraction
        for i, url in enumerate(urls[max_extracts:], start=max_extracts):
            results.append({
                "url": url,
                "content": "[not extracted] Content limit reached",
                "rank": i + 1
            })
        
        # Return structured results
        return {
            "content": [
                TextContent(
                    type="text",
                    text=str(results)  # RetrieverAgent can parse this
                )
            ]
        }
        
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        return {
            "content": [
                TextContent(
                    type="text",
                    text=f"[error] {str(e)}"
                )
            ]
        }


# Duckduck not responding? Check this: https://html.duckduckgo.com/html?q=Model+Context+Protocol
# @mcp.tool()
# async def fetch_search_urls(input: SearchInput, ctx: Context) -> URLListOutput:
#     """Get top website URLs for your search query. Just get's the URL's not the contents"""

#     try:
#         urls = await smart_search(input.query, input.max_results)
#         return URLListOutput(result=urls)
#     except Exception as e:
#         traceback.print_exc(file=sys.stderr)
#         return URLListOutput(result=[f"[error] {str(e)}"])


# @mcp.tool()
# async def webpage_url_to_raw_text(url: str) -> dict:
#     """Extract readable text from a webpage"""
#     try:
#         result = await asyncio.wait_for(smart_web_extract(url), timeout=25)
#         return {
#             "content": [
#                 TextContent(
#                     type="text",
#                     text=f"[{result.get('best_text_source', '')}] " + result.get("best_text", "")[:8000]
#                 )
#             ]
#         }
#     except asyncio.TimeoutError:
#         return {
#             "content": [
#                 TextContent(
#                     type="text",
#                     text="[error] Timed out while extracting web content"
#                 )
#             ]
#         }


# @mcp.tool()
# async def webpage_url_to_llm_summary(input: SummaryInput, ctx: Context) -> dict:
#     """Summarize the webpage using a custom prompt if provided, otherwise fallback to default."""
#     try:
#         result = await asyncio.wait_for(smart_web_extract(input.url), timeout=25)
#         text = result.get("best_text", "")[:8000]

#         if not text.strip():
#             return {
#                 "content": [
#                     TextContent(
#                         type="text",
#                         text="[error] Empty or unreadable content from webpage."
#                     )
#                 ]
#             }

#         clean_text = text.encode("utf-8", errors="replace").decode("utf-8").strip()

#         prompt = input.prompt or (
#             "Summarize this text as best as possible. Keep important entities and values intact. "
#             "Only reply back in summary, and not extra description."
#         )

#         full_prompt = f"{prompt.strip()}\n\n[text below]\n{clean_text}"

#         response = client.models.generate_content(
#             model="gemini-2.0-flash",
#             contents=full_prompt
#         )

#         raw = response.candidates[0].content.parts[0].text
#         summary = raw.encode("utf-8", errors="replace").decode("utf-8").strip()

#         return {
#             "content": [
#                 TextContent(
#                     type="text",
#                     text=summary
#                 )
#             ]
#         }

#     except asyncio.TimeoutError:
#         return {
#             "content": [
#                 TextContent(
#                     type="text",
#                     text="[error] Timed out while extracting web content."
#                 )
#             ]
#         }

#     except Exception as e:
#         return {
#             "content": [
#                 TextContent(
#                     type="text",
#                     text=f"[error] {str(e)}"
#                 )
#             ]
#         }


def mcp_log(level: str, message: str) -> None:
    sys.stderr.write(f"{level}: {message}\n")
    sys.stderr.flush()


if __name__ == "__main__":
    print("mcp_server_3.py READY")
    if len(sys.argv) > 1 and sys.argv[1] == "dev":
            mcp.run()  # Run without transport for dev server
    else:
        mcp.run(transport="stdio")  # Run with stdio for direct execution
        print("\nShutting down...")