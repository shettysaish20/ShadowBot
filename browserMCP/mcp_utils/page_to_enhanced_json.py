import json
from typing import Dict, List, Any, Optional, Union

async def get_enhanced_page_json(browser_session) -> Dict[str, Any]:
    """Create comprehensive JSON with all content + interactive elements with IDs in reading order"""
    page = await browser_session.get_current_page()
    
    # Get interactive elements with IDs (same as get_interactive_elements)
    # Override viewport settings to get ALL elements
    original_viewport = browser_session.browser_profile.viewport_expansion
    browser_session.browser_profile.viewport_expansion = -1  # All elements
    
    try:
        state = await browser_session.get_state_summary(cache_clickable_elements_hashes=False)
        
        # Create structured elements output (same logic as get_interactive_elements)
        from browserMCP.mcp_utils.utils import create_structured_elements_output
        structured_result = await create_structured_elements_output(
            state.element_tree, 
            strict_mode=True  # Use strict mode
        )
        
        # Extract all interactive elements with their IDs and positions
        interactive_elements = extract_all_interactive_elements(structured_result, state)
        
    finally:
        # Restore original viewport
        browser_session.browser_profile.viewport_expansion = original_viewport
    
    # Get accessibility tree for content structure
    ax_tree = await page.accessibility.snapshot(interesting_only=True)
    
    # Get DOM positioning data for accurate merging
    dom_data = await page.evaluate("""
        () => {
            const result = {
                elements: []
            };
            
            // Get all meaningful elements with their positions
            const allElements = document.querySelectorAll('h1,h2,h3,h4,h5,h6,p,div,span,a,button,input,select,textarea,label');
            
            allElements.forEach((elem, index) => {
                const rect = elem.getBoundingClientRect();
                const text = elem.textContent?.trim() || '';
                
                // Only include elements that are visible and have content
                if (rect.width > 0 && rect.height > 0 && (text.length > 0 || elem.tagName.toLowerCase() === 'input')) {
                    result.elements.push({
                        tag: elem.tagName.toLowerCase(),
                        text: text.slice(0, 200), // Limit text length
                        x: Math.round(rect.x),
                        y: Math.round(rect.y),
                        width: Math.round(rect.width),
                        height: Math.round(rect.height),
                        index: index,
                        // Additional attributes for matching
                        id: elem.id || '',
                        className: elem.className || '',
                        type: elem.type || '',
                        placeholder: elem.placeholder || '',
                        href: elem.href || ''
                    });
                }
            });
            
            // Sort by reading order (top to bottom, left to right)
            result.elements.sort((a, b) => {
                if (Math.abs(a.y - b.y) < 20) { // Same row
                    return a.x - b.x; // Left to right
                } else {
                    return a.y - b.y; // Top to bottom
                }
            });
            
            return result;
        }
    """)
    
    # Create comprehensive JSON in reading order
    enhanced_json = create_enhanced_json_structure(ax_tree, interactive_elements, dom_data)
    return enhanced_json

def extract_all_interactive_elements(structured_result, state) -> Dict[int, Dict]:
    """Extract ALL interactive elements with IDs, positions, and metadata"""
    interactive_map = {}
    
    # Parse the structured JSON result
    if hasattr(structured_result, 'model_dump'):
        data = structured_result.model_dump()
    else:
        data = structured_result
    
    # Try to get clickable elements from state
    clickable_positions = {}
    
    # Check if state has clickable elements - different possible attributes
    clickable_elements = None
    if hasattr(state, 'clickable_elements'):
        clickable_elements = state.clickable_elements
    elif hasattr(state, 'element_tree') and hasattr(state.element_tree, 'clickable_elements'):
        clickable_elements = state.element_tree.clickable_elements
    elif hasattr(state, 'elements'):
        clickable_elements = state.elements
    
    # If we found clickable elements, extract position data
    if clickable_elements:
        try:
            for elem in clickable_elements:
                if hasattr(elem, 'highlight_index') and hasattr(elem, 'bounding_box'):
                    clickable_positions[elem.highlight_index] = {
                        'x': elem.bounding_box.x if elem.bounding_box else 0,
                        'y': elem.bounding_box.y if elem.bounding_box else 0,
                        'width': elem.bounding_box.width if elem.bounding_box else 0,
                        'height': elem.bounding_box.height if elem.bounding_box else 0,
                        'text': elem.get_all_text_till_next_clickable_element().strip()[:100] if hasattr(elem, 'get_all_text_till_next_clickable_element') else ''
                    }
        except Exception:
            # If position extraction fails, continue without positions
            pass
    
    # Extract navigation elements
    for nav_item in data.get('nav', []):
        elem_id = nav_item['index']
        position = clickable_positions.get(elem_id, {})
        interactive_map[elem_id] = {
            'type': 'nav_link',
            'index': elem_id,
            'text': nav_item['desc'],
            'action': nav_item['action'],
            'category': 'navigation',
            'x': position.get('x', 0),
            'y': position.get('y', 0),
            'clickable_text': position.get('text', nav_item['desc'])
        }
    
    # Extract form elements
    for form_item in data.get('forms', []):
        for element in form_item.get('elements', []):
            elem_id = element['index']
            position = clickable_positions.get(elem_id, {})
            interactive_map[elem_id] = {
                'type': get_form_element_type(element),
                'index': elem_id,
                'text': element['desc'],
                'action': element['action'],
                'category': 'form',
                'options': element.get('options'),
                'options_count': len(element.get('options', [])) if element.get('options') else None,
                'x': position.get('x', 0),
                'y': position.get('y', 0),
                'clickable_text': position.get('text', element['desc'])
            }
    
    # Extract button elements
    for button_item in data.get('buttons', []):
        elem_id = button_item['index']
        position = clickable_positions.get(elem_id, {})
        interactive_map[elem_id] = {
            'type': 'button',
            'index': elem_id,
            'text': button_item['desc'],
            'action': button_item['action'],
            'category': 'button',
            'x': position.get('x', 0),
            'y': position.get('y', 0),
            'clickable_text': position.get('text', button_item['desc'])
        }
    
    return interactive_map

def get_form_element_type(form_item: Dict) -> str:
    """Determine the specific form element type"""
    action = form_item.get('action', '')
    desc = form_item.get('desc', '').lower()
    
    if 'select_dropdown_option' in action:
        return 'dropdown'
    elif 'toggle' in desc or 'checkbox' in desc:
        return 'checkbox'
    elif 'radio' in desc:
        return 'radio'
    elif 'date' in desc:
        return 'date_input'
    elif 'email' in desc:
        return 'email_input'
    elif 'phone' in desc:
        return 'phone_input'
    elif 'number' in desc or 'sqft' in desc:
        return 'number_input'
    else:
        return 'text_input'

def create_enhanced_json_structure(ax_tree: Dict, interactive_elements: Dict, dom_data: Dict) -> Dict[str, Any]:
    """Create comprehensive JSON structure prioritizing accessibility tree content"""
    
    # Start with accessibility tree as the primary content source
    content_items = []
    processed_interactive_ids = set()
    
    # Flatten accessibility tree to get structured content
    content_nodes = flatten_ax_tree_with_hierarchy(ax_tree)
    
    # Process accessibility tree nodes in order
    for node in content_nodes:
        role = node.get('role', '')
        name = node.get('name', '').strip()
        value = node.get('value', '').strip()
        
        if not name and not value:
            continue
            
        # Skip very short or meaningless content
        if len(name) < 3 and name.isdigit():
            continue
            
        # Try to find matching interactive element for this content
        matched_interactive = find_interactive_by_text_similarity(name, interactive_elements, processed_interactive_ids)
        
        if matched_interactive:
            # Add interactive element
            content_items.append({
                "type": "interactive",
                "element_type": matched_interactive['type'],
                "index": matched_interactive['index'],
                "text": clean_text(matched_interactive['text']),
                "action": matched_interactive['action'],
                "category": matched_interactive['category'],
                **get_element_specific_data(matched_interactive)
            })
            processed_interactive_ids.add(matched_interactive['index'])
        else:
            # Add content item
            content_item = create_content_item_from_node(node)
            if content_item:
                content_items.append(content_item)
    
    # Add any unmatched interactive elements at the end
    unmatched_interactive = []
    for elem_id, elem_data in interactive_elements.items():
        if elem_id not in processed_interactive_ids:
            unmatched_interactive.append({
                "type": "interactive",
                "element_type": elem_data['type'],
                "index": elem_id,
                "text": clean_text(elem_data['text']),
                "action": elem_data['action'],
                "category": elem_data['category'],
                **get_element_specific_data(elem_data)
            })
    
    if unmatched_interactive:
        content_items.append({
            "type": "section",
            "content": "Additional Interactive Elements",
            "level": 2
        })
        content_items.extend(unmatched_interactive)
    
    # Create final structure
    result = {
        "page_structure": {
            "total_interactive_elements": len(interactive_elements),
            "categories": {
                "navigation": len([e for e in interactive_elements.values() if e['category'] == 'navigation']),
                "forms": len([e for e in interactive_elements.values() if e['category'] == 'form']),
                "buttons": len([e for e in interactive_elements.values() if e['category'] == 'button'])
            }
        },
        "content": clean_and_deduplicate_content(content_items)
    }
    
    return result

def find_interactive_by_text_similarity(text: str, interactive_elements: Dict, processed_ids: set) -> Optional[Dict]:
    """Find interactive element by text similarity only (no position)"""
    if not text or len(text.strip()) < 2:
        return None
        
    best_match = None
    best_score = 0
    
    for elem_id, elem_data in interactive_elements.items():
        if elem_id in processed_ids:
            continue
            
        # Text matching with multiple fields
        text_scores = [
            calculate_text_similarity(text, elem_data['text']),
            calculate_text_similarity(text, elem_data.get('clickable_text', '')),
            calculate_text_similarity(text, elem_data['text'].split('(')[0].strip())  # Remove parenthetical info
        ]
        
        best_text_score = max(text_scores)
        
        if best_text_score > best_score and best_text_score > 0.6:  # Higher threshold
            best_score = best_text_score
            best_match = elem_data
    
    return best_match

def calculate_text_similarity(text1: str, text2: str) -> float:
    """Calculate text similarity score"""
    if not text1 or not text2:
        return 0
    
    text1 = text1.lower().strip()
    text2 = text2.lower().strip()
    
    if text1 == text2:
        return 1.0
    
    if text1 in text2 or text2 in text1:
        return min(len(text1), len(text2)) / max(len(text1), len(text2))
    
    # Word overlap
    words1 = set(text1.split())
    words2 = set(text2.split())
    if words1 and words2:
        overlap = len(words1.intersection(words2))
        total = len(words1.union(words2))
        return overlap / total if total > 0 else 0
    
    return 0

def create_content_item_from_node(node: Dict) -> Optional[Dict]:
    """Create content item from accessibility tree node"""
    role = node.get('role', '')
    
    # Fix: Convert to string before calling strip
    name = str(node.get('name', '')).strip() if node.get('name') is not None else ''
    value = str(node.get('value', '')).strip() if node.get('value') is not None else ''
    depth = node.get('depth', 0)
    
    if not name:
        return None
    
    # Filter out noise
    if len(name) < 3:
        return None
    if name.isdigit():
        return None
    if name in ['construct', 'measure', 'improve'] and len(name) < 10:  # Skip repeated single words
        return None
    
    # Create appropriate content items
    if role == 'heading':
        level = node.get('level', min(depth + 1, 6))
        return {
            "type": "heading",
            "level": level,
            "content": clean_text(name)
        }
    elif role in ['text', 'paragraph']:
        if len(name) > 50:  # Only include substantial text
            return {
                "type": "paragraph",
                "content": clean_text(name)
            }
        elif len(name) > 10:
            return {
                "type": "text",
                "content": clean_text(name)
            }
    elif role in ['list', 'listbox'] and len(name) > 5:
        return {
            "type": "section",
            "content": clean_text(name),
            "level": 3
        }
    elif role == 'listitem' and len(name) > 3:
        return {
            "type": "list_item",
            "content": clean_text(name)
        }
    elif role == 'link' and len(name) > 2:
        return {
            "type": "text", 
            "content": f"[{clean_text(name)}]"
        }
    
    # Default for other meaningful content
    if len(name) > 15:  # Only include substantial content
        return {
            "type": "text",
            "content": clean_text(name)
        }
    
    return None

def get_element_specific_data(elem_data: Dict) -> Dict:
    """Get element-specific additional data"""
    additional_data = {}
    
    if elem_data['type'] == 'dropdown' and elem_data.get('options_count'):
        additional_data['options_count'] = elem_data['options_count']
    
    if elem_data.get('options'):
        additional_data['has_options'] = True
        additional_data['sample_options'] = elem_data['options'][:5]  # First 5 options as sample
    
    return additional_data

def clean_text(text: str) -> str:
    """Clean and normalize text content"""
    if not text:
        return ""
    
    # Remove excessive whitespace
    text = ' '.join(text.split())
    
    # Clean up repeated words (like "construct construct construct")
    words = text.split()
    if len(words) > 3:
        cleaned_words = []
        prev_word = ""
        repeat_count = 0
        
        for word in words:
            if word.lower() == prev_word.lower():
                repeat_count += 1
                if repeat_count <= 1:  # Allow max 1 repetition
                    cleaned_words.append(word)
            else:
                cleaned_words.append(word)
                repeat_count = 0
            prev_word = word
        
        text = ' '.join(cleaned_words)
    
    return text.strip()

def clean_and_deduplicate_content(content_items: List[Dict]) -> List[Dict]:
    """Clean and deduplicate content items more aggressively"""
    cleaned_items = []
    seen_content = set()
    seen_interactive_ids = set()
    
    for item in content_items:
        # Handle interactive elements
        if item['type'] == 'interactive':
            item_id = item['index']
            if item_id not in seen_interactive_ids:
                cleaned_items.append(item)
                seen_interactive_ids.add(item_id)
        else:
            # Handle content items
            # Fix: Convert to string before calling strip
            content = str(item.get('content', '')).strip() if item.get('content') is not None else ''
            if len(content) < 3:  # Skip very short content
                continue
                
            # Create signature for deduplication
            signature = f"{item['type']}_{content[:30].lower()}"
            
            if signature not in seen_content:
                cleaned_items.append(item)
                seen_content.add(signature)
    
    return cleaned_items

def flatten_ax_tree_with_hierarchy(node: Dict[str, Any], depth: int = 0) -> List[Dict[str, Any]]:
    """Flatten accessibility tree preserving hierarchy information"""
    result = []
    
    if node:
        # Fix: Convert to string before calling strip
        name = str(node.get('name', '')).strip() if node.get('name') is not None else ''
        value = str(node.get('value', '')).strip() if node.get('value') is not None else ''
        
        node_info = {
            'role': node.get('role', ''),
            'name': name,
            'value': value,
            'description': str(node.get('description', '')).strip() if node.get('description') is not None else '',
            'depth': depth
        }
        
        # Add heading level for headings
        if node_info['role'] == 'heading':
            # Try to infer level from depth or name
            node_info['level'] = min(depth + 1, 6)
        
        if node_info['role'] or node_info['name']:
            result.append(node_info)
        
        # Add children
        children = node.get('children', [])
        for child in children:
            result.extend(flatten_ax_tree_with_hierarchy(child, depth + 1))
    
    return result
