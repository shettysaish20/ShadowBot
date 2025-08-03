import asyncio
import json
import os
from pathlib import Path
import sys
from mcp.types import Tool

# Add the parent directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import all the necessary modules
from browserMCP.controller.views import (
    OpenTabAction, ClickElementAction, InputTextAction, GoToUrlAction,
    SearchGoogleAction, DoneAction, SwitchTabAction, CloseTabAction,
    ScrollAction, SendKeysAction, DragDropAction, NoParamsAction,
    WaitAction, ExtractContentAction, GetAxTreeAction, ScrollToTextAction,
    GetDropdownOptionsAction, SelectDropdownOptionAction,
    GoogleSheetsRangeAction, GoogleSheetsTextAction, GoogleSheetsUpdateAction
)
from browserMCP.mcp_utils.mcp_models import (
    SuccessOutput, SnapshotOutput, ScreenshotOutput, ElementsOutput, 
    ActionResultOutput, SnapshotInputAction, ScreenshotInputAction,
    InteractiveElementsInputAction, StructuredElementsOutput
)
from browserMCP.mcp_utils.utils import (
    execute_controller_action, get_browser_session, stop_browser_session,
    filter_essential_interactive_elements, format_elements_for_llm,
    create_structured_elements_output, format_structured_output,
    normalize_url, validate_normalized_url, save_base64_as_png, get_image_info,
    take_clean_screenshot
)
from browserMCP.mcp_utils.page_to_markdown import get_comprehensive_page_markdown
from browserMCP.mcp_utils.page_to_enhanced_json import get_enhanced_page_json

def get_tools() -> list[Tool]:
    """Return all available MCP tools"""
    return [
        # Core Browser Actions
        Tool(
            name="open_tab",
            description="Open a new browser tab with the specified URL",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to open"}
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="go_to_url",
            description="Navigate to URL in the current tab",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to navigate to"}
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="go_back",
            description="Go back to the previous page",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="search_google",
            description="Search the query in Google in the current tab",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"}
                },
                "required": ["query"]
            }
        ),
        
        # Element Interaction
        Tool(
            name="click_element_by_index",
            description="Click an element by its index in the current page",
            inputSchema={
                "type": "object",
                "properties": {
                    "index": {"type": "integer", "description": "Element index to click"}
                },
                "required": ["index"]
            }
        ),
        Tool(
            name="input_text_by_index",
            description="Input text into an interactive element",
            inputSchema={
                "type": "object",
                "properties": {
                    "index": {"type": "integer", "description": "Element index"},
                    "text": {"type": "string", "description": "Text to input"}
                },
                "required": ["index", "text"]
            }
        ),
        Tool(
            name="send_keys",
            description="Send special keys like Escape, Backspace, Enter, or shortcuts like Control+C",
            inputSchema={
                "type": "object",
                "properties": {
                    "keys": {"type": "string", "description": "Keys to send"}
                },
                "required": ["keys"]
            }
        ),
        
        # Scrolling
        Tool(
            name="scroll_down",
            description="Scroll down the page by pixel amount - if none given, scroll one page",
            inputSchema={
                "type": "object",
                "properties": {
                    "pixels": {"type": "integer", "description": "Pixels to scroll", "default": 500}
                }
            }
        ),
        Tool(
            name="scroll_up",
            description="Scroll up the page by pixel amount - if none given, scroll one page",
            inputSchema={
                "type": "object",
                "properties": {
                    "pixels": {"type": "integer", "description": "Pixels to scroll", "default": 500}
                }
            }
        ),
        Tool(
            name="scroll_to_text",
            description="Scroll to specific text on the page",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to scroll to"}
                },
                "required": ["text"]
            }
        ),
        
        # Tab Management
        Tool(
            name="switch_tab",
            description="Switch to a specific tab",
            inputSchema={
                "type": "object",
                "properties": {
                    "tab_id": {"type": "integer", "description": "Tab ID to switch to"}
                },
                "required": ["tab_id"]
            }
        ),
        Tool(
            name="close_tab",
            description="Close a specific tab",
            inputSchema={
                "type": "object",
                "properties": {
                    "tab_id": {"type": "integer", "description": "Tab ID to close"}
                },
                "required": ["tab_id"]
            }
        ),
        
        # Dropdown Actions
        # Tool(
        #     name="get_dropdown_options",
        #     description="Get all options from a native dropdown element",
        #     inputSchema={
        #         "type": "object",
        #         "properties": {
        #             "index": {"type": "integer", "description": "Dropdown element index"}
        #         },
        #         "required": ["index"]
        #     }
        # ),
        # Tool(
        #     name="select_dropdown_option",
        #     description="Select dropdown option by text",
        #     inputSchema={
        #         "type": "object",
        #         "properties": {
        #             "index": {"type": "integer", "description": "Dropdown element index"},
        #             "option_text": {"type": "string", "description": "Option text to select"}
        #         },
        #         "required": ["index", "option_text"]
        #     }
        # ),
        
        # Drag and Drop
        # Tool(
        #     name="drag_drop",
        #     description="Drag and drop elements or between coordinates - useful for canvas, sliders, file uploads",
        #     inputSchema={
        #         "type": "object",
        #         "properties": {
        #             "from_index": {"type": "integer", "description": "Source element index"},
        #             "to_index": {"type": "integer", "description": "Target element index"}
        #         },
        #         "required": ["from_index", "to_index"]
        #     }
        # ),
        
        # Content Extraction
        # Tool(
        #     name="get_enhanced_page_structure",
        #     description="Get comprehensive page structure as JSON with all content AND interactive element IDs",
        #     inputSchema={"type": "object", "properties": {}}
        # ),
        Tool(
            name="get_comprehensive_markdown",
            description="Get comprehensive page markdown with all content AND interactive element IDs",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="save_pdf",
            description="Save PDF from current page by temporarily removing overlays",
            inputSchema={"type": "object", "properties": {}}
        ),
        
        # Utility Actions
        Tool(
            name="wait",
            description="Wait for specified number of seconds (default 3)",
            inputSchema={
                "type": "object",
                "properties": {
                    "seconds": {"type": "integer", "description": "Seconds to wait", "default": 3}
                }
            }
        ),
        Tool(
            name="done",
            description="Complete task - indicates if task is finished successfully or not",
            inputSchema={
                "type": "object",
                "properties": {
                    "success": {"type": "boolean", "description": "Whether task completed successfully"},
                    "message": {"type": "string", "description": "Completion message"}
                },
                "required": ["success"]
            }
        ),
        
        # Browser State Inspection
        # Tool(
        #     name="get_session_snapshot",
        #     description="Get current browser session snapshot with elements and optional screenshot saved as PNG file",
        #     inputSchema={
        #         "type": "object",
        #         "properties": {
        #             "include_screenshot": {"type": "boolean", "description": "Include screenshot saved as PNG file", "default": False},
        #             "include_overlays": {"type": "boolean", "description": "Include browser automation overlays in screenshot", "default": False}
        #         }
        #     }
        # ),
        Tool(
            name="take_screenshot",
            description="Take a screenshot of the current page and save as PNG file (returns file path, not base64)",
            inputSchema={
                "type": "object",
                "properties": {
                    "full_page": {"type": "boolean", "description": "Take full page screenshot", "default": False},
                    "include_overlays": {"type": "boolean", "description": "Include browser automation overlays", "default": False}
                }
            }
        ),
        # Tool(
        #     name="get_interactive_elements",
        #     description="Get interactive elements with smart viewport and strict filtering",
        #     inputSchema={
        #         "type": "object",
        #         "properties": {
        #             "viewport_mode": {"type": "string", "description": "visible or all", "default": "visible"},
        #             "strict_mode": {"type": "boolean", "description": "Use strict filtering", "default": True},
        #             "structured_output": {"type": "boolean", "description": "Return structured output", "default": False}
        #         }
        #     }
        # ),
        
        # Session Management
        Tool(
            name="close_browser_session",
            description="Close the browser session",
            inputSchema={"type": "object", "properties": {}}
        )
    ]

async def handle_tool_call(name: str, arguments: dict) -> list[dict]:
    """Handle tool execution and return standardized response"""
    try:
        # Core Browser Actions
        if name == "open_tab":
            # Normalize URL before creating input object
            normalized_url = normalize_url(arguments["url"])
            input_obj = OpenTabAction(url=normalized_url)
            result = await execute_controller_action("open_tab", input_obj)
            
            # Enhanced validation for open_tab
            if result.success:
                try:
                    browser_session = await get_browser_session()
                    page = await browser_session.get_current_page()
                    final_url = page.url
                    
                    if not validate_normalized_url(arguments["url"], final_url):
                        return [{"type": "text", "text": f"❌ Failed to open tab. Requested: {arguments['url']}, Final URL: {final_url}"}]
                        
                except Exception as e:
                    # If we can't validate, still return the original result
                    pass
            
            return [{"type": "text", "text": result.content if result.success else result.error}]
            
        elif name == "go_to_url":
            # Normalize URL before creating input object
            normalized_url = normalize_url(arguments["url"])
            input_obj = GoToUrlAction(url=normalized_url)
            result = await execute_controller_action("go_to_url", input_obj)
            
            # Enhanced validation for go_to_url
            if result.success:
                try:
                    browser_session = await get_browser_session()
                    page = await browser_session.get_current_page()
                    final_url = page.url
                    
                    if not validate_normalized_url(arguments["url"], final_url):
                        return [{"type": "text", "text": f"❌ Navigation failed. Requested: {arguments['url']}, Final URL: {final_url}"}]
                        
                except Exception as e:
                    # If we can't validate, still return the original result
                    pass
            
            return [{"type": "text", "text": result.content if result.success else result.error}]
            
        elif name == "go_back":
            result = await execute_controller_action("go_back", NoParamsAction())
            return [{"type": "text", "text": result.content if result.success else result.error}]
            
        elif name == "search_google":
            input_obj = SearchGoogleAction(query=arguments["query"])
            result = await execute_controller_action("search_google", input_obj)
            return [{"type": "text", "text": result.content if result.success else result.error}]
            
        # Element Interaction
        elif name == "click_element_by_index":
            input_obj = ClickElementAction(index=arguments["index"])
            result = await execute_controller_action("click_element_by_index", input_obj)
            return [{"type": "text", "text": result.content if result.success else result.error}]
            
        elif name == "input_text_by_index":
            input_obj = InputTextAction(index=arguments["index"], text=arguments["text"])
            result = await execute_controller_action("input_text_by_index", input_obj)
            return [{"type": "text", "text": result.content if result.success else result.error}]
            
        elif name == "send_keys":
            input_obj = SendKeysAction(keys=arguments["keys"])
            result = await execute_controller_action("send_keys", input_obj)
            return [{"type": "text", "text": result.content if result.success else result.error}]
            
        # Scrolling
        elif name == "scroll_down":
            pixels = arguments.get("pixels", 500)
            input_obj = ScrollAction(pixels=pixels)
            result = await execute_controller_action("scroll_down", input_obj)
            return [{"type": "text", "text": result.content if result.success else result.error}]
            
        elif name == "scroll_up":
            pixels = arguments.get("pixels", 500)
            input_obj = ScrollAction(pixels=pixels)
            result = await execute_controller_action("scroll_up", input_obj)
            return [{"type": "text", "text": result.content if result.success else result.error}]
            
        elif name == "scroll_to_text":
            input_obj = ScrollToTextAction(text=arguments["text"])
            try:
                browser_session = await get_browser_session()
                page = await browser_session.get_current_page()
                
                scroll_result = await page.evaluate(f"""
                    (text) => {{
                        const walker = document.createTreeWalker(
                            document.body,
                            NodeFilter.SHOW_TEXT,
                            null,
                            false
                        );
                        
                        let node;
                        while (node = walker.nextNode()) {{
                            if (node.textContent.toLowerCase().includes(text.toLowerCase())) {{
                                const element = node.parentElement;
                                element.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                                return {{ success: true, found: true, text: node.textContent.trim() }};
                            }}
                        }}
                        return {{ success: false, found: false }};
                    }}
                """, input_obj.text)
                
                if scroll_result['found']:
                    return [{"type": "text", "text": f"✅ Scrolled to text '{input_obj.text}'"}]
                else:
                    return [{"type": "text", "text": f"❌ Text '{input_obj.text}' not found on page"}]
                    
            except Exception as e:
                return [{"type": "text", "text": f"Error: {str(e)}"}]
            
        # Tab Management
        elif name == "switch_tab":
            input_obj = SwitchTabAction(tab_id=arguments["tab_id"])
            result = await execute_controller_action("switch_tab", input_obj)
            return [{"type": "text", "text": result.content if result.success else result.error}]
            
        elif name == "close_tab":
            input_obj = CloseTabAction(tab_id=arguments["tab_id"])
            result = await execute_controller_action("close_tab", input_obj)
            return [{"type": "text", "text": result.content if result.success else result.error}]
            
        # # Dropdown Actions
        # elif name == "get_dropdown_options":
        #     input_obj = GetDropdownOptionsAction(index=arguments["index"])
        #     result = await execute_controller_action("get_dropdown_options", input_obj)
        #     return [{"type": "text", "text": result.content if result.success else result.error}]
            
        # elif name == "select_dropdown_option":
        #     input_obj = SelectDropdownOptionAction(index=arguments["index"], option_text=arguments["option_text"])
        #     result = await execute_controller_action("select_dropdown_option", input_obj)
        #     return [{"type": "text", "text": result.content if result.success else result.error}]
            
        # Drag and Drop
        elif name == "drag_drop":
            input_obj = DragDropAction(from_index=arguments["from_index"], to_index=arguments["to_index"])
            result = await execute_controller_action("drag_drop", input_obj)
            return [{"type": "text", "text": result.content if result.success else result.error}]
            
        # Content Extraction
        elif name == "get_enhanced_page_structure":
            try:
                browser_session = await get_browser_session()
                enhanced_structure = await get_enhanced_page_json(browser_session)
                return [{"type": "text", "text": json.dumps(enhanced_structure, indent=2)}]
            except Exception as e:
                return [{"type": "text", "text": f"Error creating enhanced page structure: {str(e)}"}]
                
        elif name == "get_comprehensive_markdown":
            try:
                browser_session = await get_browser_session()
                comprehensive_markdown = await get_comprehensive_page_markdown(browser_session)
                return [{"type": "text", "text": comprehensive_markdown}]
            except Exception as e:
                return [{"type": "text", "text": f"Error creating comprehensive markdown: {str(e)}"}]
                
        elif name == "save_pdf":
            try:
                browser_session = await get_browser_session()
                page = await browser_session.get_current_page()
                current_url = page.url
                
                # Remove overlays with JavaScript
                await page.evaluate("""
                    () => {
                        const selectors = [
                            '[data-browser-use]',
                            '[class*="highlight"]', 
                            '[style*="outline"]',
                            '[style*="border: 2px"]',
                            'div[style*="position: absolute"][style*="z-index"]'
                        ];
                        
                        selectors.forEach(selector => {
                            const elements = document.querySelectorAll(selector);
                            elements.forEach(el => el.remove());
                        });
                        
                        const allElements = document.querySelectorAll('*');
                        allElements.forEach(el => {
                            if (el.style.outline) el.style.outline = '';
                            if (el.style.border && el.style.border.includes('2px')) el.style.border = '';
                        });
                    }
                """)
                
                import re
                # Create and prepare output directory
                pdf_dir = Path("media/pdf")
                pdf_dir.mkdir(parents=True, exist_ok=True)
                short_url = re.sub(r'^https?://(?:www\.)?|/$', '', current_url)
                slug = re.sub(r'[^a-zA-Z0-9]+', '-', short_url).strip('-').lower()
                sanitized_filename = f'{slug}.pdf'
                pdf_path = pdf_dir / sanitized_filename
                
                await page.emulate_media(media='screen')
                await page.pdf(
                    path=pdf_path, 
                    format='A4', 
                    print_background=True,
                    margin={'top': '0.5in', 'right': '0.5in', 'bottom': '0.5in', 'left': '0.5in'}
                )
                
                current_dir = os.getcwd()
                msg = f'Saved PDF (overlay removal attempt) of {current_url} to {current_dir}/{pdf_path}'
                return [{"type": "text", "text": msg}]
                
            except Exception as e:
                return [{"type": "text", "text": f"Error saving PDF: {str(e)}"}]
                
        # Utility Actions
        elif name == "wait":
            seconds = arguments.get("seconds", 3)
            input_obj = WaitAction(seconds=seconds)
            result = await execute_controller_action("wait", input_obj)
            return [{"type": "text", "text": result.content if result.success else result.error}]
            
        elif name == "done":
            success = arguments["success"]
            message = arguments.get("message", "")
            input_obj = DoneAction(success=success, message=message)
            result = await execute_controller_action("done", input_obj)
            return [{"type": "text", "text": result.content if result.success else result.error}]
            
        # # Browser State Inspection
        # elif name == "get_session_snapshot":
        #     include_screenshot = arguments.get("include_screenshot", False)
        #     include_overlays = arguments.get("include_overlays", False)
            
        #     browser_session = await get_browser_session()
        #     state = await browser_session.get_state_summary(cache_clickable_elements_hashes=False)
        #     elements = state.element_tree.clickable_elements_to_string(
        #         include_attributes=["id", "name", "placeholder", "type", "href", "role", "aria-label"]
        #     )
            
        #     result_text = f"Elements:\n{elements}"
            
        #     if include_screenshot:
        #         try:
        #             # Use clean screenshot function with overlay control
        #             screenshot_base64 = await take_clean_screenshot(
        #                 browser_session, 
        #                 full_page=False, 
        #                 remove_overlays=not include_overlays
        #             )
                    
        #             if screenshot_base64:
        #                 prefix = "snapshot"
        #                 if not include_overlays:
        #                     prefix += "_clean"
                            
        #                 screenshot_path = save_base64_as_png(screenshot_base64, prefix)
                        
        #                 if not screenshot_path.startswith("Error"):
        #                     img_info = get_image_info(screenshot_path)
        #                     info_str = f" ({img_info.get('width', '?')}x{img_info.get('height', '?')}, {img_info.get('size_kb', '?')} KB)" if img_info else ""
        #                     overlay_status = "with overlays" if include_overlays else "clean (overlays removed)"
                            
        #                     result_text += f"\nScreenshot saved: {screenshot_path}{info_str} ({overlay_status})"
        #                 else:
        #                     result_text += f"\nScreenshot error: {screenshot_path}"
        #             else:
        #                 result_text += "\nScreenshot: Failed to capture"
                        
        #         except Exception as e:
        #             result_text += f"\nScreenshot error: {str(e)}"
                
        #     return [{"type": "text", "text": result_text}]
            
        elif name == "take_screenshot":
            full_page = arguments.get("full_page", False)
            include_overlays = arguments.get("include_overlays", False)
            
            try:
                browser_session = await get_browser_session()
                
                # Use clean screenshot function with overlay control
                screenshot_base64 = await take_clean_screenshot(
                    browser_session, 
                    full_page=full_page, 
                    remove_overlays=not include_overlays
                )
                
                if screenshot_base64:
                    prefix = "fullpage" if full_page else "screenshot"
                    if not include_overlays:
                        prefix += "_clean"
                    
                    screenshot_path = save_base64_as_png(screenshot_base64, prefix)
                    
                    if not screenshot_path.startswith("Error"):
                        page = await browser_session.get_current_page()
                        current_url = page.url
                        img_info = get_image_info(screenshot_path)
                        info_str = f" ({img_info.get('width', '?')}x{img_info.get('height', '?')}, {img_info.get('size_kb', '?')} KB)" if img_info else ""
                        
                        page_type = "Full page" if full_page else "Viewport"
                        overlay_status = "with overlays" if include_overlays else "clean (overlays removed)"
                        
                        return [{"type": "text", "text": f"{page_type} screenshot of {current_url} saved: {screenshot_path}{info_str} ({overlay_status})"}]
                    else:
                        return [{"type": "text", "text": f"Screenshot error: {screenshot_path}"}]
                else:
                    return [{"type": "text", "text": "Failed to capture screenshot"}]
                    
            except Exception as e:
                return [{"type": "text", "text": f"Error taking screenshot: {str(e)}"}]
                
        # elif name == "get_interactive_elements":
        #     viewport_mode = arguments.get("viewport_mode", "visible")
        #     strict_mode = arguments.get("strict_mode", True)
        #     structured_output = arguments.get("structured_output", False)
            
        #     try:
        #         browser_session = await get_browser_session()
                
        #         if viewport_mode == "visible":
        #             viewport_expansion = 0
        #         else:
        #             viewport_expansion = -1
                    
        #         original_viewport = browser_session.browser_profile.viewport_expansion
        #         browser_session.browser_profile.viewport_expansion = viewport_expansion
                
        #         try:
        #             state = await browser_session.get_state_summary(cache_clickable_elements_hashes=False)
                    
        #             if structured_output:
        #                 result = await create_structured_elements_output(
        #                     state.element_tree, 
        #                     strict_mode=strict_mode
        #                 )
        #                 return [{"type": "text", "text": result.model_dump_json(indent=2, exclude_none=True)}]
        #             else:
        #                 elements = await filter_essential_interactive_elements(
        #                     state.element_tree, 
        #                     strict_mode=strict_mode
        #                 )
                        
        #                 formatted_elements = []
        #                 for element in elements:
        #                     text = element.get_all_text_till_next_clickable_element().strip()[:50]
        #                     attributes = []
                            
        #                     for attr in ["id", "name", "placeholder", "type", "href"]:
        #                         if attr in element.attributes and element.attributes[attr]:
        #                             attributes.append(f"{attr}='{element.attributes[attr]}'")
                            
        #                     attr_str = " " + " ".join(attributes) if attributes else ""
        #                     formatted_elements.append(f"[{element.highlight_index}]<{element.tag_name}{attr_str}>{text} />")
                        
        #                 return [{"type": "text", "text": "\n".join(formatted_elements)}]
        #         finally:
        #             browser_session.browser_profile.viewport_expansion = original_viewport
                    
        #     except Exception as e:
        #         return [{"type": "text", "text": f"Error getting interactive elements: {str(e)}"}]
                
        # Session Management
        elif name == "close_browser_session":
            try:
                await stop_browser_session()
                return [{"type": "text", "text": "Browser session closed successfully"}]
            except Exception as e:
                return [{"type": "text", "text": f"Error closing browser session: {str(e)}"}]
        
        else:
            return [{"type": "text", "text": f"❌ Unknown tool '{name}'"}]
            
    except Exception as e:
        return [{"type": "text", "text": f"❌ Error executing tool '{name}': {str(e)}"}]
