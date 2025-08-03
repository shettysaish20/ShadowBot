import asyncio
from typing import List, Dict, Any
from browserMCP.browser import BrowserSession, BrowserProfile
from browserMCP.controller.service import Controller
from browserMCP.mcp_utils.mcp_models import ActionResultOutput, ElementInfo, StructuredElementsOutput, FormGroup, ContextItem
import json
import re
from urllib.parse import urlparse
import base64
import os
from datetime import datetime
from pathlib import Path
import sys
import gc
import time

# Global browser session (these will be accessed from the main server file)
browser_session = None
controller = None

async def ensure_browser_session():
    """Ensure browser session is initialized"""
    global browser_session, controller
    
    if browser_session is None:
        profile = BrowserProfile(
            headless=False,
            allowed_domains=None,
            highlight_elements=True,
            bypass_csp=True,
            viewport_expansion=0,
            include_dynamic_attributes=True,
            keep_alive=True,  # Keep browser alive between commands
        )
        browser_session = BrowserSession(profile=profile)
        controller = Controller()
        await browser_session.start()

async def execute_controller_action(action_name: str, action_params=None, **kwargs) -> ActionResultOutput:
    """Helper to execute controller actions consistently"""
    try:
        await ensure_browser_session()
        
        page = await browser_session.get_current_page()
        ActModel = controller.registry.create_action_model(page=page)
        
        # Handle actions without parameters
        if action_params is None or action_params == {}:
            action_obj = ActModel(**{action_name: {}})
        else:
            # Convert Pydantic model to dict if needed
            if hasattr(action_params, 'model_dump'):
                action_params_dict = action_params.model_dump()
            elif hasattr(action_params, 'dict'):
                action_params_dict = action_params.dict()
            else:
                action_params_dict = action_params
            
            action_obj = ActModel(**{action_name: action_params_dict})
        
        result = await controller.act(
            action=action_obj,
            browser_session=browser_session,
            page_extraction_llm=None,
            **kwargs
        )
        result_content = result.extracted_content if hasattr(result, 'extracted_content') else ""
        
        # Enhanced validation for navigation actions
        success = True
        error_msg = None
        
        if action_name in ["open_tab", "go_to_url"]:
            current_page = await browser_session.get_current_page()
            current_url = current_page.url
            
            # Check for browser error pages
            if any(error_indicator in current_url.lower() for error_indicator in [
                "chrome-error://", "about:neterror", "edge://", "about:blank"
            ]):
                success = False
                error_msg = f"Navigation failed - browser error page: {current_url}"
            
            # For open_tab, check if we have a valid domain
            elif action_name == "open_tab" and action_params:
                requested_url = action_params.url if hasattr(action_params, 'url') else str(action_params.get('url', ''))
                if requested_url and not validate_normalized_url(requested_url, current_url):
                    success = False
                    error_msg = f"Open tab failed. Requested: {requested_url}, Final: {current_url}"
        
        # Check if this is a navigation action that needs element refresh
        navigation_actions = [
            "open_tab", "go_to_url", "go_back", "search_google", 
            "click_element_by_index",  # This often causes navigation
            "input_text_by_index",     # This can trigger popups/dropdowns
            "scroll_down", "scroll_up", "scroll_to_text"  # These can reveal new elements
        ]
        
        if action_name in navigation_actions and success:
            # Force refresh and get interactive elements WITH context (this creates overlays)
            state = await browser_session.get_state_summary(cache_clickable_elements_hashes=False)
            
            # Take automatic screenshot AFTER overlays are created
            screenshot_path = await take_page_update_screenshot()
            
            elements_result = await create_structured_elements_output(
                state.element_tree, 
                strict_mode=False
            )
            elements_json = elements_result.model_dump_json(indent=2, exclude_none=True)
            
            # Combine original result with interactive elements and screenshot info
            if result_content and result_content.strip():
                combined_content = f"{result_content}\n\nWebpage Elements:\n{elements_json}"
            else:
                # For successful clicks without content, provide a success message
                if action_name == "click_element_by_index":
                    index = action_params_dict.get('index', 'unknown') if action_params_dict else 'unknown'
                    combined_content = f"✅ Successfully clicked element at index {index}\n\nWebpage Elements:\n{elements_json}"
                else:
                    combined_content = f"✅ Action '{action_name}' completed successfully\n\nWebpage Elements:\n{elements_json}"
            
            # Add screenshot info if available
            if screenshot_path:
                combined_content += f"\n\nSeraphineScreenshot: {screenshot_path}"
            
            return ActionResultOutput(
                success=success,
                content=combined_content,
                error=error_msg,
                is_done=False
            )
        
        return ActionResultOutput(
            success=success,
            content=result_content,
            error=error_msg,
            is_done=False
        )
        
    except Exception as e:
        return ActionResultOutput(success=False, error=str(e))

def categorize_element(element) -> tuple[str, str, str]:
    """
    Categorize element and determine action type
    Returns: (category, element_type, action_type)
    """
    tag_name = element.tag_name.lower()
    role = element.attributes.get('role', '').lower()
    element_type = element.attributes.get('type', '').lower()
    href = element.attributes.get('href', '')
    
    # Custom dropdown detection FIRST (Google-style dropdowns with role="combobox")
    if role == 'combobox':
        return 'form', 'custom_dropdown', 'click_element_by_index'
    
    # Form elements
    if tag_name == 'input':
        input_type = element.attributes.get('type', '').lower()
        if input_type in ['text', 'search', 'tel', 'url', 'email']:
            return 'form', 'text_input', 'input_text_by_index'
        elif input_type == 'password':
            return 'form', 'password_input', 'input_text_by_index'
        elif input_type in ['number', 'range']:
            return 'form', 'number_input', 'input_text_by_index'
        elif input_type == 'date':
            return 'form', 'date_input', 'input_text_by_index'
        elif input_type == 'checkbox':
            return 'form', 'checkbox', 'click_element_by_index'
        elif input_type == 'radio':
            return 'form', 'radio_button', 'click_element_by_index'
        elif input_type == 'file':
            return 'form', 'file_upload', 'drag_drop'
        elif input_type == 'submit':
            return 'form', 'submit_button', 'click_element_by_index'
    
    elif tag_name == 'textarea':
        return 'form', 'text_area', 'input_text_by_index'
    
    elif tag_name == 'select':
        return 'form', 'native_dropdown', 'select_dropdown_option_by_index'
    
    elif tag_name == 'button':
        if element_type == 'submit':
            return 'form', 'submit_button', 'click_element_by_index'
        elif role == 'checkbox':
            return 'form', 'toggle_button', 'click_element_by_index'
        elif role in ['tab', 'menuitem']:
            return 'interactive', 'tab_button', 'click_element_by_index'
        else:
            return 'interactive', 'button', 'click_element_by_index'
    
    # Navigation elements
    elif tag_name == 'a':
        if href and href not in ['#', 'javascript:void(0)', 'javascript:;']:
            if href.startswith('mailto:'):
                return 'interactive', 'email_link', 'click_element_by_index'
            elif href.startswith('tel:'):
                return 'interactive', 'phone_link', 'click_element_by_index'
            else:
                return 'navigation', 'link', 'click_element_by_index'
        else:
            # Links with no real destination - treat as interactive buttons
            return 'interactive', 'button_link', 'click_element_by_index'
    
    # Hoverable paragraph elements
    elif tag_name == 'p':
        return 'interactive', 'hoverable_text', 'hover item, not implemented yet'
    
    elif tag_name == 'li':
        # Li elements are typically dropdown/menu options - treat as form elements
        return 'form', 'dropdown_option', 'click_element_by_index'
    
    # Default for other interactive elements
    return 'interactive', 'clickable_element', 'click_element_by_index'

def create_element_description(element, category: str, element_type: str) -> str:
    """Generate a helpful description for the element"""
    text = element.get_all_text_till_next_clickable_element().strip()
    placeholder = element.attributes.get('placeholder', '')
    title = element.attributes.get('title', '')
    href = element.attributes.get('href', '')
    
    if category == 'navigation':
        if href.startswith('http'):
            return f"Navigate to external link: {text or href}"
        else:
            return f"Navigate to: {text or 'page section'}"
    
    elif category == 'form':
        if element_type == 'text_input':
            return f"Text input field: {placeholder or text or 'enter text'}"
        elif element_type == 'email_input':
            return f"Email input field: {placeholder or 'enter email address'}"
        elif element_type == 'password_input':
            return f"Password input field: {placeholder or 'enter password'}"
        elif element_type == 'submit_button':
            return f"Submit form: {text or 'submit'}"
        elif element_type == 'dropdown':
            return f"Dropdown menu: {text or placeholder or 'select option'}"
        elif element_type == 'checkbox':
            return f"Checkbox: {text or 'toggle option'}"
        elif element_type == 'file_upload':
            return f"File upload: {text or 'select file'}"
        
    elif category == 'interactive':
        if element_type == 'button':
            return f"Button: {text or 'click to activate'}"
        elif element_type == 'tab_button':
            return f"Tab: {text or 'switch tab'}"
        elif element_type == 'email_link':
            return f"Send email to: {href.replace('mailto:', '')}"
    
    return f"{element_type.replace('_', ' ').title()}: {text or 'interactive element'}"

async def filter_essential_interactive_elements(element_tree, strict_mode: bool = False) -> List:
    """Filter for only essential interactive elements that an LLM would want to interact with"""
    from browserMCP.dom.clickable_element_processor.service import ClickableElementProcessor
    
    all_elements = ClickableElementProcessor.get_clickable_elements(element_tree)
    essential_elements = []
    
    for element in all_elements:
        # ALWAYS filter by is_visible
        if not element.is_visible:
            continue
            
        tag_name = element.tag_name.lower()
        href = element.attributes.get('href', '')
        
        # Include ALL interactive elements (p, div, span with click handlers)
        if tag_name in ['p', 'div', 'span', 'li']:
            text = element.get_all_text_till_next_clickable_element().strip()
            if text and len(text) > 2:  # Only include elements with meaningful text
                essential_elements.append(element)
                continue
        
        # STRICT MODE: Only allow essential form/navigation elements
        if strict_mode:
            # Essential form elements only
            if tag_name in ['input', 'textarea', 'select', 'button']:
                # Skip generic buttons without clear purpose
                if tag_name == 'button':
                    text = element.get_all_text_till_next_clickable_element().strip()
                    if not text or len(text) < 2:
                        continue
                essential_elements.append(element)
                continue
                
            # Essential navigation only (with real destinations, no external company logos)
            if tag_name == 'a' and href and href not in ['#', 'javascript:void(0)', 'javascript:;']:
                text = element.get_all_text_till_next_clickable_element().strip()
                # Skip if it's just a logo/image link with no text
                if not text and href.startswith('http'):
                    continue
                essential_elements.append(element)
                continue
        else:
            # NORMAL MODE: More permissive but still filtered
            
            # Skip useless links
            if tag_name == 'a' and href in ['#', 'javascript:void(0)', 'javascript:;', '']:
                text = element.get_all_text_till_next_clickable_element().strip()
                if not text or len(text) > 100:
                    continue
            
            # Skip duplicate company logo links (common pattern)
            if tag_name == 'a' and href and href.startswith('http'):
                text = element.get_all_text_till_next_clickable_element().strip()
                if not text:  # Logo links with no text
                    # Check if we already have this domain
                    domain = href.split('/')[2] if '/' in href[8:] else href[8:]
                    duplicate = any(
                        e.tag_name.lower() == 'a' and 
                        e.attributes.get('href', '').startswith('http') and
                        domain in e.attributes.get('href', '') and
                        not e.get_all_text_till_next_clickable_element().strip()
                        for e in essential_elements
                    )
                    if duplicate:
                        continue
            
            # Essential form elements
            if tag_name in ['input', 'textarea', 'select', 'button']:
                essential_elements.append(element)
                continue
                
            # Essential navigation elements (with real destinations)
            if tag_name == 'a' and href and href not in ['#', 'javascript:void(0)', 'javascript:;']:
                essential_elements.append(element)
                continue
                
            # Essential interactive roles
            role = element.attributes.get('role', '').lower()
            if role in ['button', 'link', 'menuitem', 'tab', 'checkbox', 'radio', 'combobox', 'searchbox', 'textbox']:
                essential_elements.append(element)
                continue
    
    return essential_elements

def create_smart_description(element, category: str, element_type: str) -> str:
    # Get the element's actual text content first
    text = element.get_all_text_till_next_clickable_element().strip()
    
    # For dropdown options and clickable elements, prioritize the visible text
    if text and len(text) > 0 and len(text) < 50:
        # If it's a dropdown option or clickable element, use the text directly
        if category == 'form' and text not in ['', 'Select', 'Choose', 'Pick']:
            return text  # Return "January", "February", etc. directly
    
    # ENHANCED: Try to get the ACTUAL current value using multiple methods
    current_value = ''
    
    # 1. Check standard HTML value attribute
    current_value = element.attributes.get('value', '').strip()
    
    # 2. For input fields, try to get the ACTUAL current value via JavaScript
    if not current_value and category == 'form' and element_type in ['text_input', 'email_input', 'password_input', 'number_input']:
        try:
            global browser_session
            if browser_session:
                page = browser_session.get_current_page()
                # Use JavaScript to get the actual current value
                js_value = page.evaluate(f"""
                    () => {{
                        const element = document.querySelector('[data-highlight-index="{element.highlight_index}"]');
                        if (element) {{
                            return element.value || element.textContent || '';
                        }}
                        return '';
                    }}
                """)
                if js_value and js_value.strip():
                    current_value = js_value.strip()
        except:
            pass  # Continue with other methods if JavaScript fails
    
    # 3. If no standard value, check ALL data-* attributes for potential values
    if not current_value:
        for attr_name, attr_value in element.attributes.items():
            if (attr_name.startswith('data-') and 
                attr_value.strip() and 
                len(attr_value.strip()) > 0 and
                len(attr_value.strip()) < 50):  # Reasonable value length
                current_value = attr_value.strip()
                break
    
    # 4. If still no value, try the element's actual text content
    if not current_value:
        if text and len(text) < 50:
            current_value = text
    
    # If we found a value, show it
    if current_value and category == 'form':
        # For dropdown options, just return the value directly
        if current_value in ['January', 'February', 'March', 'April', 'May', 'June', 
                           'July', 'August', 'September', 'October', 'November', 'December']:
            return current_value
        
        field_name = (element.attributes.get('name', '') or 
                     element.attributes.get('aria-label', '') or 
                     element.attributes.get('placeholder', '') or 
                     'Username')  # Better default for this case
        
        # Show the current value for input fields
        if element_type in ['text_input', 'email_input', 'password_input', 'number_input']:
            if current_value and current_value not in ['ltr', 'rtl']:  # Filter out direction attributes
                return f"{field_name}: {current_value}"
            else:
                return f"{field_name} (empty)"
        
        return f"{field_name}: {current_value}"
    
    # Rest of existing logic unchanged...
    placeholder = element.attributes.get('placeholder', '')
    title = element.attributes.get('title', '')
    name = element.attributes.get('name', '')
    element_id = element.attributes.get('id', '')
    href = element.attributes.get('href', '')
    
    # Build description parts - avoid duplication
    description_parts = []
    
    # Add primary text
    if text:
        description_parts.append(text)
    
    # Add placeholder ONLY if different from primary text and not already included
    if placeholder and placeholder != text and placeholder not in text:
        description_parts.append(placeholder)
    
    # Add meaningful name/id in parentheses
    identifier = None
    if name and len(name) > 1 and not name.startswith(('formfield', 'form-', 'input-')):
        identifier = name
    elif element_id and len(element_id) > 1 and not element_id.startswith(('radix-', 'form-', 'input-')):
        identifier = element_id
    
    # Construct final description
    if description_parts:
        result = " ".join(description_parts)
        if identifier:
            result += f" ({identifier})"
    else:
        # Fallback handling for form fields
        if category == 'form':
            if element_type in ['text_input', 'email_input', 'password_input', 'number_input']:
                field_name = (element.attributes.get('aria-label', '') or 
                             element.attributes.get('placeholder', '') or 
                             'Input')
                result = f"{field_name} (empty)"
            elif element_type in ['dropdown', 'native_dropdown', 'custom_dropdown']:
                result = "Select option"
            else:
                result = f"{element_type.replace('_', ' ').title()}"
        else:
            result = "Interactive element"
    
    return result

async def create_structured_elements_output(element_tree, strict_mode: bool = False) -> StructuredElementsOutput:
    """Create spatially-ordered output that preserves page structure - VIEWPORT ONLY VERSION"""
    try:
        # SIMPLE APPROACH: Use our existing working functions directly
        interactive_elements = await filter_essential_interactive_elements(element_tree, strict_mode)
        context_elements = await get_viewport_text_context()
        
        # ENHANCED: Get real-time values for input elements with modern UI support
        global browser_session
        page = await browser_session.get_current_page()
        
        # Enhanced input value detection for modern UIs
        element_values = await page.evaluate("""
            () => {
                const values = {};
                const inputs = document.querySelectorAll('input, textarea, select');
                
                inputs.forEach((input, i) => {
                    let value = '';
                    
                    // Method 1: Standard input.value
                    if (input.value && input.value.trim()) {
                        value = input.value.trim();
                    }
                    
                    // Method 2: For tag/pill inputs, look for selected tags in parent container
                    if (!value || value === input.placeholder) {
                        const parent = input.closest('div, span, section');
                        if (parent) {
                            // Look for tag/pill elements (common patterns)
                            const tags = parent.querySelectorAll('.tag, .chip, .pill, [class*="tag"], [class*="chip"], [class*="pill"], [class*="selected"]');
                            if (tags.length > 0) {
                                const tagTexts = Array.from(tags).map(tag => tag.textContent?.trim()).filter(text => text && text.length > 0);
                                if (tagTexts.length > 0) {
                                    value = tagTexts.join(', ');
                                }
                            }
                            
                            // Alternative: Look for any small clickable elements that might be tags
                            if (!value) {
                                const possibleTags = parent.querySelectorAll('span, div, button');
                                const tagCandidates = Array.from(possibleTags).filter(el => {
                                    const text = el.textContent?.trim();
                                    const rect = el.getBoundingClientRect();
                                    // Small elements with text that look like tags
                                    return text && text.length > 0 && text.length < 30 && 
                                           rect.width < 200 && rect.height < 50 &&
                                           !text.includes('Add') && !text.includes('Search') &&
                                           !text.includes('+');
                                });
                                
                                if (tagCandidates.length > 0) {
                                    const candidateTexts = tagCandidates.map(el => el.textContent?.trim()).filter(text => text);
                                    if (candidateTexts.length > 0) {
                                        value = candidateTexts.join(', ');
                                    }
                                }
                            }
                        }
                    }
                    
                    // Method 3: Check for data attributes that might contain the value
                    if (!value || value === input.placeholder) {
                        const dataAttrs = ['data-value', 'data-selected', 'data-tags', 'data-items'];
                        for (const attr of dataAttrs) {
                            const dataValue = input.getAttribute(attr);
                            if (dataValue && dataValue.trim()) {
                                value = dataValue.trim();
                                break;
                            }
                        }
                    }
                    
                    // Method 4: Check aria-label or aria-describedby for current state
                    if (!value || value === input.placeholder) {
                        const ariaLabel = input.getAttribute('aria-label');
                        const ariaDesc = input.getAttribute('aria-describedby');
                        if (ariaLabel && ariaLabel.includes(':')) {
                            const parts = ariaLabel.split(':');
                            if (parts.length > 1) {
                                value = parts[1].trim();
                            }
                        }
                    }
                    
                    // Store the detected value
                    values[`input_${i}`] = value || '';
                });
                
                return { values };
            }
        """)
        
        actual_values = element_values.get('values', {})
        
        # Build final element list with reading order
        all_elements = []
        
        # Add interactive elements
        input_counter = 0
        for element in interactive_elements:
            category, element_type, action_type = categorize_element(element)
            
            # Get real-time value for inputs
            real_time_value = ''
            if category == 'form' and element_type in ['text_input', 'email_input', 'password_input', 'number_input']:
                real_time_value = actual_values.get(f'input_{input_counter}', '')
                input_counter += 1
            
            smart_description = create_smart_description_with_value(element, category, element_type, real_time_value)
            
            # Use element's bounding box if available, otherwise use index * 1000
            y_position = getattr(element.bounding_box, 'y', element.highlight_index * 1000) if hasattr(element, 'bounding_box') and element.bounding_box else element.highlight_index * 1000
            x_position = getattr(element.bounding_box, 'x', 0) if hasattr(element, 'bounding_box') and element.bounding_box else 0
            
            all_elements.append({
                'type': 'interactive',
                'sort_key': y_position * 1000 + x_position,  # Reading order: Y primary, X secondary
                'index': element.highlight_index,
                'desc': smart_description,
                'action': action_type,
                'category': category
            })
        
        # Add context elements (filter out Y=0 elements that are likely off-screen)
        for ctx in context_elements:
            y_pos = ctx.get('y', 9999)
            x_pos = ctx.get('x', 0)
            if y_pos > 50:  # Filter out off-screen elements
                all_elements.append({
                    'type': 'context',
                    'sort_key': y_pos * 1000 + x_pos,  # Same reading order logic
                    'text': ctx.get('text', ''),
                    'tag': ctx.get('tag', 'text')
                })
        
        # Sort by reading order (top-to-bottom, left-to-right)
        all_elements.sort(key=lambda x: x['sort_key'])
        
        # Convert to final format
        elements = []
        for elem in all_elements:
            if elem['type'] == 'interactive':
                elements.append({
                    'type': 'interactive',
                    'index': elem['index'],
                    'desc': elem['desc'],
                    'action': elem['action'],
                    'category': elem['category']
                })
            else:
                elements.append({
                    'type': 'context',
                    'text': elem['text'],
                    'tag': elem['tag']
                })
        
        return StructuredElementsOutput(
            success=True,
            elements=elements,
            total=len(elements)
        )
        
    except Exception as e:
        import traceback
        return StructuredElementsOutput(
            success=False,
            elements=[],
            total=0,
            error=f"Error creating structured output: {str(e)}\n{traceback.format_exc()}"
        )

def create_smart_description_with_value(element, category: str, element_type: str, real_time_value: str) -> str:
    """GENERIC description creator that uses real-time DOM values"""
    
    # Get basic element info
    text = element.get_all_text_till_next_clickable_element().strip()
    placeholder = element.attributes.get('placeholder', '')
    name = element.attributes.get('name', '')
    aria_label = element.attributes.get('aria-label', '')
    element_type_attr = element.attributes.get('type', '')
    element_id = element.attributes.get('id', '')
    
    # ENHANCED: For form elements, prioritize showing current value with better field detection
    if category == 'form':
        # SPECIAL HANDLING for checkboxes - find associated label
        if element_type == 'checkbox' or element_type_attr == 'checkbox':
            # Try to find the label text in multiple ways
            label_text = ''
            
            # Method 1: aria-label
            if aria_label:
                label_text = aria_label
            # Method 2: nearby text (next sibling or parent text)
            elif text and len(text) < 50:
                label_text = text
            # Method 3: for/id association (common pattern)
            elif element_id:
                # This would require DOM traversal to find label[for="element_id"]
                # For now, use a simple heuristic based on common patterns
                if 'show' in element_id.lower() and 'password' in element_id.lower():
                    label_text = 'Show password'
                elif 'remember' in element_id.lower():
                    label_text = 'Remember me'
                elif 'agree' in element_id.lower() or 'terms' in element_id.lower():
                    label_text = 'Agree to terms'
            
            if label_text:
                # Check if checkbox is checked (this would need real-time state)
                return f"{label_text} checkbox"
            else:
                return "Checkbox"
        
        # Determine field name with better detection for other form elements
        field_name = ''
        
        # Priority order: aria-label > placeholder > name > nearby text > type-based guess
        if aria_label:
            field_name = aria_label
        elif placeholder:
            field_name = placeholder
        elif name:
            field_name = name
        elif text and len(text) < 30:  # Short text likely to be a label
            field_name = text
        elif element_type_attr == 'password':
            # Check if it's likely a confirm field based on context
            if 'confirm' in (name + placeholder + aria_label + text).lower():
                field_name = 'Confirm password'
            else:
                field_name = 'Password'
        elif element_type in ['text_input', 'email_input', 'password_input', 'number_input', 'text_area']:
            field_name = element_type.replace('_', ' ').title()
        else:
            field_name = 'Input'
        
        field_name = field_name.replace(':', '').strip()
        
        # For password fields, don't show the actual value for security
        if element_type_attr == 'password' or element_type == 'password_input':
            if real_time_value and len(real_time_value.strip()) > 0:
                return f"{field_name} (filled)"
            else:
                return f"{field_name} (empty)"
        
        # For other input fields, show current value if meaningful
        if element_type in ['text_input', 'email_input', 'number_input', 'text_area']:
            if real_time_value and real_time_value.strip() and len(real_time_value.strip()) > 0:
                # Filter out technical attributes that aren't user values
                if real_time_value.strip() not in ['ltr', 'rtl', 'on', 'off', 'true', 'false']:
                    return f"{field_name}: {real_time_value.strip()}"
            
            return f"{field_name} (empty)"
        
        # For other form elements (dropdowns, etc.)
        if text and len(text) > 0 and len(text) < 50:
            return text
        
        return field_name
    
    # For non-form elements, use text content
    if text and len(text) > 0 and len(text) < 50:
        return text
    
    # Fallback to existing logic
    return create_smart_description_fallback(element, category, element_type)

def create_smart_description_fallback(element, category: str, element_type: str) -> str:
    """Fallback description logic for non-input elements"""
    text = element.get_all_text_till_next_clickable_element().strip()
    
    if text:
        return text
    elif category == 'form':
        return f"{element_type.replace('_', ' ').title()}"
    elif category == 'navigation':
        return "Link"
    else:
        return "Interactive element"

async def get_viewport_text_context():
    """Get contextual text elements in viewport with accurate positions"""
    global browser_session
    page = await browser_session.get_current_page()
    
    context_data = await page.evaluate("""
        () => {
            const result = [];
            
            // Get important text elements
            const elements = document.querySelectorAll('h1,h2,h3,h4,h5,h6,label,p,div,span');
            
            elements.forEach(elem => {
                const rect = elem.getBoundingClientRect();
                let text = '';
                
                // IMPROVED: Better text extraction with proper spacing
                function extractTextWithSpacing(element) {
                    let result = '';
                    
                    for (let node of element.childNodes) {
                        if (node.nodeType === Node.TEXT_NODE) {
                            const nodeText = node.textContent?.trim();
                            if (nodeText) {
                                result += nodeText + ' ';
                            }
                        } else if (node.nodeType === Node.ELEMENT_NODE) {
                            // For element nodes, check if they're inline or block
                            const style = window.getComputedStyle(node);
                            const display = style.display;
                            
                            const childText = node.textContent?.trim();
                            if (childText) {
                                result += childText;
                                
                                // Add space after inline elements, newline after block elements
                                if (display === 'inline' || display === 'inline-block' || 
                                    node.tagName === 'SPAN' || node.tagName === 'A' || 
                                    node.tagName === 'BUTTON' || node.tagName === 'INPUT') {
                                    result += ' ';
                                } else if (display === 'block' || display === 'list-item') {
                                    result += ' ';
                                }
                            }
                        }
                    }
                    
                    return result.trim();
                }
                
                // Try improved extraction first
                text = extractTextWithSpacing(elem);
                
                // Fallback to simple textContent if extraction is too complex
                if (!text || text.length < 3) {
                    text = elem.textContent?.trim() || '';
                }
                
                // IMPROVED: Clean up spacing issues
                text = text
                    .replace(/\s+/g, ' ')  // Multiple spaces to single space
                    .replace(/([a-z])([A-Z])/g, '$1 $2')  // Add space between camelCase
                    .trim();
                
                if (rect.top >= 0 && rect.left >= 0 && 
                    rect.bottom <= window.innerHeight && 
                    rect.right <= window.innerWidth &&
                    text.length > 8 && text.length < 200 &&
                    !text.includes('function') && !text.includes('gtag') &&
                    !text.includes('dataLayer') && !text.includes('window.') &&
                    // Filter out the weird number sequences
                    !/^\d{10,}$/.test(text) &&
                    // Filter out very repetitive content
                    !text.match(/(.)\1{5,}/) &&
                    !elem.onclick && !elem.getAttribute('onclick') &&
                    !elem.closest('[onclick]')) {
                    
                    result.push({
                        tag: elem.tagName.toLowerCase(),
                        text: text,
                        x: Math.round(rect.x),
                        y: Math.round(rect.y)
                    });
                }
            });
            
            // Remove duplicates and filter better
            const unique = [];
            const seen = new Set();
            result.forEach(item => {
                // Better deduplication - also check for substrings
                const isDuplicate = seen.has(item.text) || 
                    Array.from(seen).some(seenText => 
                        seenText.includes(item.text) || item.text.includes(seenText)
                    );
                
                if (!isDuplicate) {
                    seen.add(item.text);
                    unique.push(item);
                }
            });
            
            return unique;
        }
    """)
    
    return context_data

async def get_browser_session():
    """Get the current browser session, ensuring it's initialized"""
    await ensure_browser_session()
    return browser_session

async def stop_browser_session():
    """Stop the browser session and clean up"""
    global browser_session, controller
    
    if browser_session is not None:
        await browser_session.stop()
        browser_session = None
        controller = None

def format_elements_for_llm(element_tree, format_type: str = "structured") -> str:
    """Simple formatter using browser-use's existing filtering"""
    
    if format_type == "structured":
        return format_structured_output(element_tree)
    else:
        return element_tree.clickable_elements_to_string(
            include_attributes=["id", "name", "placeholder", "type", "href"]
        )

def format_structured_output(element_tree) -> str:
    """Format in categories but use existing browser-use data"""
    from browserMCP.dom.clickable_element_processor.service import ClickableElementProcessor
    
    elements = ClickableElementProcessor.get_clickable_elements(element_tree)
    
    nav_elements = []
    form_elements = []
    interactive_elements = []
    
    for element in elements:
        if not element.is_visible:  # Use browser-use's visibility flag
            continue
            
        # Simple categorization using existing data
        tag = element.tag_name.lower()
        href = element.attributes.get('href', '')
        
        element_info = {
            "id": element.highlight_index,
            "type": tag,
            "text": element.get_all_text_till_next_clickable_element()[:50],
            "action": "click_element_by_index",
            "params": {"index": element.highlight_index}
        }
        
        if tag == 'a' and href and href not in ['#', '']:
            nav_elements.append(element_info)
        elif tag in ['input', 'textarea', 'select', 'button']:
            form_elements.append(element_info)
        else:
            interactive_elements.append(element_info)
    
    return json.dumps({
        "navigation": nav_elements,
        "forms": form_elements, 
        "interactive": interactive_elements
    }, indent=2)

def normalize_url(url: str) -> str:
    """
    Normalize URL by adding protocol if missing and validating format
    
    Examples:
    - "news.ycombinator.com" -> "https://news.ycombinator.com"
    - "google.com" -> "https://google.com"
    - "http://example.com" -> "http://example.com" (unchanged)
    - "https://test.com" -> "https://test.com" (unchanged)
    - "localhost:3000" -> "http://localhost:3000"
    - "127.0.0.1:8080" -> "http://127.0.0.1:8080"
    """
    if not url or not isinstance(url, str):
        return url
    
    url = url.strip()
    
    # If already has protocol, return as-is
    if url.startswith(('http://', 'https://', 'file://', 'ftp://')):
        return url
    
    # Special cases for localhost and IP addresses - use http
    if url.startswith(('localhost', '127.0.0.1', '0.0.0.0')) or re.match(r'^\d+\.\d+\.\d+\.\d+', url):
        return f"http://{url}"
    
    # For everything else, use https as default
    # Handle cases like "www.example.com" or "example.com"
    return f"https://{url}"

def validate_normalized_url(original_url: str, final_url: str) -> bool:
    """
    Validate that the browser actually navigated to the expected domain
    
    Args:
        original_url: The URL we tried to navigate to
        final_url: The URL the browser actually ended up at
    
    Returns:
        True if navigation was successful, False otherwise
    """
    if not original_url or not final_url:
        return False
    
    # Parse both URLs to get domains
    try:
        original_parsed = urlparse(normalize_url(original_url))
        final_parsed = urlparse(final_url)
        
        original_domain = original_parsed.netloc.lower()
        final_domain = final_parsed.netloc.lower()
        
        # Remove 'www.' prefix for comparison
        original_domain = original_domain.replace('www.', '')
        final_domain = final_domain.replace('www.', '')
        
        # Check for error pages
        error_indicators = [
            'chrome-error://', 'about:neterror', 'edge://', 
            'about:blank', 'data:text/html', 'chrome://new-tab'
        ]
        
        if any(indicator in final_url.lower() for indicator in error_indicators):
            return False
        
        # Check if domains match
        return original_domain == final_domain or original_domain in final_domain or final_domain in original_domain
        
    except Exception:
        return False

def save_base64_as_png(base64_data: str, prefix: str = "screenshot") -> str:
    """
    Convert base64 image data to PNG file and return the file path
    Saves the new screenshot first, then deletes old ones
    
    Args:
        base64_data: Base64 encoded image string
        prefix: Prefix for the filename (e.g., "screenshot", "page_update")
    
    Returns:
        File path of the saved PNG image
    """
    import sys
    import gc
    import time
    
    try:
        # Create screenshots directory if it doesn't exist
        screenshots_dir = Path("media/screenshots")
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate unique filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]  # microseconds to milliseconds
        filename = f"{prefix}_{timestamp}.png"
        filepath = screenshots_dir / filename
        
        # Remove data URL prefix if present (data:image/png;base64,)
        if base64_data.startswith('data:'):
            base64_data = base64_data.split(',', 1)[1]
        
        # Decode base64 and save as PNG FIRST
        image_bytes = base64.b64decode(base64_data)
        
        # Ensure file is properly closed after writing
        with open(filepath, 'wb') as f:
            f.write(image_bytes)
            f.flush()  # Force write to disk
            os.fsync(f.fileno())  # Force OS to write to disk
        
        # Force garbage collection to release any file handles
        gc.collect()
        
        # Small delay to ensure file handles are released
        time.sleep(0.1)
        
        # NOW delete old screenshots (keeping the one we just saved)
        all_png_files = list(screenshots_dir.glob("*.png"))
        existing_files = [f for f in all_png_files if f.name != filename]
        
        deleted_count = 0
        failed_files = []
        
        for existing_file in existing_files:
            try:
                # Try to force release any handles on this file
                if existing_file.exists():
                    # On Windows, try to force close any handles
                    try:
                        # Force garbage collection before deletion
                        gc.collect()
                        time.sleep(0.05)  # Small delay
                        
                        existing_file.unlink()
                        deleted_count += 1
                    except PermissionError:
                        # File is locked, try alternative approach
                        # Try moving to temp name first, then delete
                        temp_name = existing_file.with_suffix('.tmp_delete')
                        try:
                            existing_file.rename(temp_name)
                            temp_name.unlink()
                            deleted_count += 1
                        except Exception as e2:
                            failed_files.append(existing_file.name)
                    
            except Exception as e:
                failed_files.append(existing_file.name)
        
        # Return relative path for portability
        return str(filepath)
        
    except Exception as e:
        return f"Error saving image: {str(e)}"

def get_image_info(filepath: str) -> dict:
    """Get basic info about the saved image"""
    try:
        from PIL import Image
        
        with Image.open(filepath) as img:
            return {
                "width": img.width,
                "height": img.height,
                "format": img.format,
                "size_kb": round(os.path.getsize(filepath) / 1024, 2)
            }
    except ImportError:
        # PIL not available, return basic info
        size_bytes = os.path.getsize(filepath)
        return {
            "size_kb": round(size_bytes / 1024, 2)
        }
    except Exception:
        return {}

async def remove_browser_overlays(browser_session):
    """Remove browser automation overlays from the page"""
    try:
        page = await browser_session.get_current_page()
        await page.evaluate("""
            () => {
                // Remove browser-use and automation overlays
                const selectors = [
                    '[data-browser-use]',
                    '[class*="highlight"]', 
                    '[style*="outline"]',
                    '[style*="border: 2px"]',
                    '[style*="border: 3px"]',
                    'div[style*="position: absolute"][style*="z-index"]',
                    '[data-element-index]',
                    '[data-highlight]'
                ];
                
                selectors.forEach(selector => {
                    const elements = document.querySelectorAll(selector);
                    elements.forEach(el => el.remove());
                });
                
                // Remove inline styles that look like automation overlays
                const allElements = document.querySelectorAll('*');
                allElements.forEach(el => {
                    if (el.style.outline) el.style.outline = '';
                    if (el.style.border && (el.style.border.includes('2px') || el.style.border.includes('3px'))) {
                        el.style.border = '';
                    }
                    // Remove any background colors that look like highlights
                    if (el.style.backgroundColor && el.style.backgroundColor.includes('rgba(255, 0, 0')) {
                        el.style.backgroundColor = '';
                    }
                });
                
                return true;
            }
        """)
        return True
    except Exception as e:
        print(f"Warning: Could not remove overlays: {e}")
        return False

async def take_clean_screenshot(browser_session, full_page: bool = False, remove_overlays: bool = True):
    """Take a screenshot with optional overlay removal"""
    try:
        # Remove overlays if requested
        if remove_overlays:
            await remove_browser_overlays(browser_session)
            # Small delay to ensure overlays are removed
            import asyncio
            await asyncio.sleep(0.1)
        
        # Take the screenshot
        screenshot_base64 = await browser_session.take_screenshot(full_page=full_page)
        return screenshot_base64
        
    except Exception as e:
        # Fallback to regular screenshot if overlay removal fails
        return await browser_session.take_screenshot(full_page=full_page)

async def take_page_update_screenshot() -> str:
    """
    Take a screenshot automatically for page updates and return the file path
    Uses include_overlays=True to match the original take_screenshot function behavior
    """
    try:
        global browser_session
        if browser_session is None:
            return ""
        
        # Take screenshot with overlays (include_overlays=True)
        screenshot_base64 = await take_clean_screenshot(
            browser_session, 
            full_page=False,  # Viewport screenshot
            remove_overlays=False  # Keep overlays (include_overlays=True)
        )
        
        if screenshot_base64:
            # Save to media/screenshots directory with "page_update" prefix
            screenshot_path = save_base64_as_png(screenshot_base64, "page_update")
            
            if not screenshot_path.startswith("Error"):
                return screenshot_path
        
        return ""
        
    except Exception as e:
        return ""