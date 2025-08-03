import os
import sys
import logging

# More aggressive logging suppression - MUST be done BEFORE importing controller
logging.basicConfig(level=logging.CRITICAL)
logging.getLogger().setLevel(logging.CRITICAL)
logging.getLogger().disabled = True

# Suppress all existing and future loggers
for name in logging.root.manager.loggerDict:
    logging.getLogger(name).setLevel(logging.CRITICAL)
    logging.getLogger(name).disabled = True

# Disable controller logging specifically
logging.getLogger('browserMCP').setLevel(logging.CRITICAL)
logging.getLogger('browserMCP').disabled = True

# Add the parent directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server.fastmcp import FastMCP, Context
from browserMCP.mcp_tools import get_tools, handle_tool_call

# Initialize FastMCP server
mcp = FastMCP("browser-automation", timeout=30)

# Helper function to create a generic tool wrapper
async def generic_tool_handler(tool_name: str, ctx: Context, **kwargs) -> str:
    """Generic handler that delegates to mcp_tools"""
    try:
        # Convert kwargs to arguments dict, filtering out None values
        arguments = {k: v for k, v in kwargs.items() if v is not None}
        
        # Call the centralized handler
        result = await handle_tool_call(tool_name, arguments)
        
        # Extract text from result
        if isinstance(result, list) and len(result) > 0:
            if isinstance(result[0], dict) and "text" in result[0]:
                return result[0]["text"]
            else:
                return str(result[0])
        return str(result)
        
    except Exception as e:
        return f"❌ Error executing tool '{tool_name}': {str(e)}"

# Now create individual tool functions - this is verbose but works with FastMCP
@mcp.tool()
async def open_tab(ctx: Context, url: str) -> str:
    """Open a new browser tab with the specified URL and ALWAYS RETURNS NEW PAGE STATE. Returns the next state of the webpage which WILL CHANGE ALL IDs. If used MUST immediately Capture and use NEW STATE IDs."""
    return await generic_tool_handler("open_tab", ctx, url=url)

@mcp.tool()
async def go_to_url(ctx: Context, url: str) -> str:
    """Navigate to URL in the current tab and ALWAYS RETURNS NEW PAGE STATE. Returns the next state of the webpage which WILL CHANGE ALL IDs. If used MUST immediately Capture and use NEW STATE IDs."""
    return await generic_tool_handler("go_to_url", ctx, url=url)

@mcp.tool()
async def go_back(ctx: Context) -> str:
    """Go back to the previous page and ALWAYS RETURNS NEW PAGE STATE. Returns the next state of the webpage which WILL CHANGE ALL IDs. If used MUST immediately Capture and use NEW STATE IDs."""
    return await generic_tool_handler("go_back", ctx)

@mcp.tool()
async def search_google(ctx: Context, query: str) -> str:
    """Search the query in Google in the current tab and ALWAYS RETURNS NEW PAGE STATE. Returns the next state of the webpage which WILL CHANGE ALL IDs. If used MUST immediately Capture and use NEW STATE IDs."""
    return await generic_tool_handler("search_google", ctx, query=query)

@mcp.tool()
async def click_element_by_index(ctx: Context, index: int) -> str:
    """Click an element by its index in the current page and ALWAYS REFRESHES AND RETURN NEW STATE. EITHER Returns the next state of the webpage OR REFRESHES the current state which WILL CHANGE IDs. If used MUST immediately Capture and use NEW STATE IDs."""
    return await generic_tool_handler("click_element_by_index", ctx, index=index)

@mcp.tool()
async def input_text_by_index(ctx: Context, index: int, text: str) -> str:
    """Input text into an interactive element and MAY TRIGGER POPUPS/DROPDOWNS RETURNING NEW STATE. Can trigger dropdowns or popups which WILL CHANGE IDs. If triggers state change MUST immediately Capture and use NEW STATE IDs."""
    return await generic_tool_handler("input_text_by_index", ctx, index=index, text=text)

@mcp.tool()
async def send_keys(ctx: Context, keys: str) -> str:
    """Send special keys like Escape, Backspace, Enter, or shortcuts like Control+C"""
    return await generic_tool_handler("send_keys", ctx, keys=keys)

@mcp.tool()
async def scroll_down(ctx: Context, pixels: int = 500) -> str:
    """Scroll down the page by pixel amount and ALWAYS RETURNS NEW PAGE STATE. Returns the next state of the webpage which WILL CHANGE ALL IDs. If used MUST immediately Capture and use NEW STATE IDs."""
    return await generic_tool_handler("scroll_down", ctx, pixels=pixels)

@mcp.tool()
async def scroll_up(ctx: Context, pixels: int = 500) -> str:
    """Scroll up the page by pixel amount and ALWAYS RETURNS NEW PAGE STATE. Returns the next state of the webpage which WILL CHANGE ALL IDs. If used MUST immediately Capture and use NEW STATE IDs."""
    return await generic_tool_handler("scroll_up", ctx, pixels=pixels)

@mcp.tool()
async def scroll_to_text(ctx: Context, text: str) -> str:
    """Scroll to specific text on the page and ALWAYS RETURNS NEW PAGE STATE. Returns the next state of the webpage which WILL CHANGE ALL IDs. If used MUST immediately Capture and use NEW STATE IDs."""
    return await generic_tool_handler("scroll_to_text", ctx, text=text)

@mcp.tool()
async def switch_tab(ctx: Context, tab_id: int) -> str:
    """Switch to a specific tab"""
    return await generic_tool_handler("switch_tab", ctx, tab_id=tab_id)

@mcp.tool()
async def close_tab(ctx: Context, tab_id: int) -> str:
    """Close a specific tab"""
    return await generic_tool_handler("close_tab", ctx, tab_id=tab_id)

# @mcp.tool()
# async def get_dropdown_options(ctx: Context, index: int) -> str:
#     """Get all options from a native dropdown element"""
#     return await generic_tool_handler("get_dropdown_options", ctx, index=index)

# @mcp.tool()
# async def select_dropdown_option(ctx: Context, index: int, option_text: str) -> str:
#     """Select dropdown option by text"""
#     return await generic_tool_handler("select_dropdown_option", ctx, index=index, option_text=option_text)

@mcp.tool()
async def drag_drop(ctx: Context, from_index: int, to_index: int) -> str:
    """Drag and drop elements or between coordinates - useful for canvas, sliders, file uploads"""
    return await generic_tool_handler("drag_drop", ctx, from_index=from_index, to_index=to_index)

# @mcp.tool()
# async def get_enhanced_page_structure(ctx: Context) -> str:
#     """Get comprehensive page structure as JSON with all content AND interactive element IDs"""
#     return await generic_tool_handler("get_enhanced_page_structure", ctx)

@mcp.tool()
async def get_comprehensive_markdown(ctx: Context) -> str:
    """Get comprehensive page markdown with all content AND interactive element IDs"""
    return await generic_tool_handler("get_comprehensive_markdown", ctx)

@mcp.tool()
async def save_pdf(ctx: Context) -> str:
    """Save PDF from current page by temporarily removing overlays"""
    return await generic_tool_handler("save_pdf", ctx)

# @mcp.tool()
# async def wait(ctx: Context, seconds: int = 3) -> str:
#     """Wait for specified number of seconds (default 3)"""
#     return await generic_tool_handler("wait", ctx, seconds=seconds)

# @mcp.tool()
# async def done(ctx: Context, success: bool, message: str = "") -> str:
#     """Complete task - indicates if task is finished successfully or not"""
#     return await generic_tool_handler("done", ctx, success=success, message=message)

# ✅ Fixed screenshot tools - no Pydantic input models needed
# @mcp.tool()
# async def get_session_snapshot(ctx: Context, include_screenshot: bool = False, include_overlays: bool = False) -> str:
#     """Get current browser session snapshot with elements and optional clean screenshot"""
#     return await generic_tool_handler("get_session_snapshot", ctx, include_screenshot=include_screenshot, include_overlays=include_overlays)

@mcp.tool()
async def take_screenshot(ctx: Context, full_page: bool = False, include_overlays: bool = False) -> str:
    """Take a screenshot of the current page and save as PNG file (overlays removed by default)"""
    return await generic_tool_handler("take_screenshot", ctx, full_page=full_page, include_overlays=include_overlays)

# @mcp.tool()
# async def get_interactive_elements(ctx: Context, viewport_mode: str = "visible", strict_mode: bool = True, structured_output: bool = False) -> str:
#     """Get interactive elements with smart viewport and strict filtering"""
#     return await generic_tool_handler("get_interactive_elements", ctx, viewport_mode=viewport_mode, strict_mode=strict_mode, structured_output=structured_output)

@mcp.tool()
async def close_browser_session(ctx: Context) -> str:
    """Close the browser session"""
    return await generic_tool_handler("close_browser_session", ctx)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "dev":
        mcp.run()  # Run without transport for dev server
    else:
        mcp.run(transport="stdio")  # Run with stdio for direct execution
