import json
from typing import Dict, List, Any, Optional
import hashlib

async def get_comprehensive_page_markdown(browser_session) -> str:
    """Create comprehensive markdown with all content + interactive elements with IDs"""
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
        
        # Extract interactive elements with their IDs
        interactive_elements = extract_interactive_elements_with_ids(structured_result)
        
    finally:
        # Restore original viewport
        browser_session.browser_profile.viewport_expansion = original_viewport
    
    # Get accessibility tree for content structure
    ax_tree = await page.accessibility.snapshot(interesting_only=True)
    
    # Get enhanced DOM data for better matching
    dom_data = await page.evaluate("""
        () => {
            const result = {
                headings: [],
                links: [],
                text_elements: [],
                sections: []
            };
            
            // Extract headings with position
            document.querySelectorAll('h1,h2,h3,h4,h5,h6').forEach((heading, index) => {
                const rect = heading.getBoundingClientRect();
                result.headings.push({
                    text: heading.textContent.trim(),
                    level: parseInt(heading.tagName.slice(1)),
                    x: rect.x,
                    y: rect.y,
                    index: index
                });
            });
            
            // Extract links with position for matching
            document.querySelectorAll('a').forEach((link, index) => {
                const rect = link.getBoundingClientRect();
                result.links.push({
                    text: link.textContent.trim(),
                    href: link.href,
                    x: rect.x,
                    y: rect.y,
                    index: index
                });
            });
            
            // Extract text elements for content
            document.querySelectorAll('p, div, span').forEach((elem, index) => {
                const text = elem.textContent?.trim();
                const rect = elem.getBoundingClientRect();
                if (text && text.length > 10 && rect.width > 0 && rect.height > 0) {
                    result.text_elements.push({
                        text: text.slice(0, 200), // Limit length
                        tag: elem.tagName.toLowerCase(),
                        x: rect.x,
                        y: rect.y,
                        index: index
                    });
                }
            });
            
            return result;
        }
    """)
    
    # Convert to comprehensive markdown
    markdown = create_comprehensive_markdown(ax_tree, interactive_elements, dom_data)
    return markdown

def extract_interactive_elements_with_ids(structured_result) -> Dict[str, List]:
    """Extract interactive elements with IDs from structured output"""
    interactive_map = {}
    
    # Parse the structured JSON result
    if hasattr(structured_result, 'model_dump'):
        data = structured_result.model_dump()
    else:
        data = structured_result
    
    # Extract navigation elements
    for nav_item in data.get('nav', []):
        interactive_map[nav_item['index']] = {
            'type': 'nav',
            'text': nav_item['desc'],
            'action': nav_item['action'],
            'index': nav_item['index']
        }
    
    # Extract form elements
    for form_item in data.get('forms', []):
        interactive_map[form_item['index']] = {
            'type': 'form',
            'text': form_item['desc'],
            'action': form_item['action'],
            'index': form_item['index'],
            'options': form_item.get('options')  # For dropdowns
        }
    
    # Extract button elements
    for button_item in data.get('buttons', []):
        interactive_map[button_item['index']] = {
            'type': 'button',
            'text': button_item['desc'],
            'action': button_item['action'],
            'index': button_item['index']
        }
    
    return interactive_map

def find_interactive_element_by_text(text: str, interactive_elements: Dict, threshold: float = 0.7) -> Optional[Dict]:
    """Find interactive element that matches given text"""
    if not text:
        return None
    
    text = text.strip().lower()
    best_match = None
    best_score = 0
    
    for element_id, element in interactive_elements.items():
        element_text = element['text'].lower().strip()
        
        # Exact match
        if text == element_text:
            return element
        
        # Partial match - text contains element text or vice versa
        if text in element_text or element_text in text:
            score = min(len(text), len(element_text)) / max(len(text), len(element_text))
            if score > best_score and score >= threshold:
                best_score = score
                best_match = element
    
    return best_match

def create_comprehensive_markdown(ax_tree: Dict, interactive_elements: Dict, dom_data: Dict) -> str:
    """Create comprehensive markdown with content + interactive elements (no IDs for clean reading)"""
    markdown_lines = []
    current_section = ""
    
    # Flatten accessibility tree
    nodes = flatten_ax_tree(ax_tree)
    
    # Filter out noise elements
    filtered_nodes = filter_noise_elements(nodes)
    
    for node in filtered_nodes:
        role = node['role']
        name = node['name']
        value = node['value']
        depth = node['depth']
        
        if not name and not value:
            continue
        
        # Skip navigation/footer/pagination content
        if is_noise_content(name):
            continue
        
        # Track current section
        if role == 'heading':
            current_section = name
        
        # Process different node types
        if role == 'heading':
            # Find heading level from DOM
            heading_match = None
            for h in dom_data['headings']:
                if h['text'].lower().strip() == name.lower().strip():
                    heading_match = h
                    break
            
            level = heading_match['level'] if heading_match else min(depth + 1, 6)
            markdown_lines.append(f"\n{'#' * level} {name}\n")
            
        elif role == 'link':
            # Try to find matching interactive element
            interactive = find_interactive_element_by_text(name, interactive_elements)
            
            if interactive:
                # Found interactive element - no ID, just clean link
                markdown_lines.append(f"[{name}](#)")
            else:
                # Regular link - try to find href from DOM
                link_match = None
                for link in dom_data['links']:
                    if link['text'].lower().strip() == name.lower().strip():
                        link_match = link
                        break
                
                href = link_match['href'] if link_match else "#"
                markdown_lines.append(f"[{name}]({href})")
        
        elif role == 'button':
            # Try to find matching interactive element
            interactive = find_interactive_element_by_text(name, interactive_elements)
            
            if interactive:
                markdown_lines.append(f"**[Button: {name}]**")
            else:
                markdown_lines.append(f"**[Button: {name}]**")
        
        elif role in ['textbox', 'searchbox']:
            # Try to find matching form element
            interactive = find_interactive_element_by_text(name, interactive_elements)
            
            if interactive:
                markdown_lines.append(f"**Input: {name}**")
            else:
                markdown_lines.append(f"**Input: {name}**")
        
        elif role == 'combobox':
            # Try to find matching dropdown
            interactive = find_interactive_element_by_text(name, interactive_elements)
            
            if interactive:
                options_text = ""
                if interactive.get('options'):
                    num_options = len(interactive['options'])
                    options_text = f" ({num_options} options)"
                markdown_lines.append(f"**Dropdown: {name}**{options_text}")
            else:
                markdown_lines.append(f"**Dropdown: {name}**")
        
        elif role == 'checkbox':
            status = "[x]" if value == "true" else "[ ]"
            # Try to find matching interactive element
            interactive = find_interactive_element_by_text(name, interactive_elements)
            
            if interactive:
                markdown_lines.append(f"{status} {name}")
            else:
                markdown_lines.append(f"{status} {name}")
        
        elif role == 'radio':
            status = "(*)" if value == "true" else "( )"
            interactive = find_interactive_element_by_text(name, interactive_elements)
            
            if interactive:
                markdown_lines.append(f"{status} {name}")
            else:
                markdown_lines.append(f"{status} {name}")
        
        elif role in ['list', 'listbox']:
            if name:
                markdown_lines.append(f"\n**{name}:**")
        
        elif role == 'listitem':
            if name:
                markdown_lines.append(f"- {name}")
        
        elif role == 'text' and name:
            # Regular text content - clean up repetitions
            cleaned_name = clean_repeated_text(name)
            if len(cleaned_name) > 100:
                markdown_lines.append(f"\n{cleaned_name}\n")
            else:
                markdown_lines.append(cleaned_name)
        
        elif role == 'paragraph' and name:
            cleaned_name = clean_repeated_text(name)
            markdown_lines.append(f"\n{cleaned_name}\n")
        
        elif name:
            # Fallback for other content
            cleaned_name = clean_repeated_text(name)
            markdown_lines.append(cleaned_name)
    
    # Add any unmatched interactive elements at the end (without IDs)
    unmatched_elements = find_unmatched_interactive_elements(interactive_elements, markdown_lines)
    if unmatched_elements:
        markdown_lines.append("\n\n## Additional Interactive Elements\n")
        for element in unmatched_elements:
            if element['type'] == 'form':
                if element.get('options'):
                    num_options = len(element['options'])
                    markdown_lines.append(f"**{element['action'].replace('_', ' ').title()}: {element['text']}** ({num_options} options)")
                else:
                    markdown_lines.append(f"**{element['action'].replace('_', ' ').title()}: {element['text']}**")
            else:
                markdown_lines.append(f"**{element['type'].title()}: {element['text']}**")
    
    return format_comprehensive_markdown(markdown_lines)

def find_unmatched_interactive_elements(interactive_elements: Dict, markdown_lines: List[str]) -> List[Dict]:
    """Find interactive elements that weren't included in the markdown (updated for no-ID matching)"""
    markdown_text = ' '.join(markdown_lines).lower()
    unmatched = []
    
    for element_id, element in interactive_elements.items():
        # Check if element text appears in markdown (no ID checking anymore)
        element_text = element['text'].lower().strip()
        if element_text and element_text not in markdown_text:
            unmatched.append(element)
    
    return unmatched

def clean_repeated_text(text: str) -> str:
    """Clean up repeated words in text"""
    if not text:
        return text
        
    words = text.split()
    if len(words) <= 3:
        return text
    
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
    
    return ' '.join(cleaned_words)

def format_comprehensive_markdown(markdown_lines: List[str]) -> str:
    """Format the final comprehensive markdown with post-processing cleanup"""
    result = []
    
    for i, line in enumerate(markdown_lines):
        if not line.strip():
            continue
            
        if line.startswith('#'):
            # Headings get extra spacing
            if i > 0 and result and not result[-1].endswith('\n\n'):
                result.append('\n')
            result.append(line)
            if i < len(markdown_lines) - 1:
                result.append('\n')
        elif line.startswith('\n'):
            result.append(line)
        else:
            if result and not result[-1].endswith('\n'):
                result.append(' ')
            result.append(line)
    
    # Final cleanup - remove any remaining pagination at the end
    final_result = ''.join(result).strip()
    
    # Split into lines and remove pagination lines
    lines = final_result.split('\n')
    cleaned_lines = []
    
    for line in lines:
        if is_pagination_content(line.strip()):
            continue
        cleaned_lines.append(line)
    
    return '\n'.join(cleaned_lines).strip()

def flatten_ax_tree(node: Dict[str, Any], depth: int = 0) -> List[Dict[str, Any]]:
    """Flatten accessibility tree into a list of nodes with depth info"""
    result = []
    
    if node:
        node_info = {
            'role': node.get('role', ''),
            'name': node.get('name', '').strip(),
            'value': node.get('value', ''),
            'description': node.get('description', ''),
            'depth': depth
        }
        if node_info['role'] or node_info['name']:
            result.append(node_info)
        
        children = node.get('children', [])
        for child in children:
            result.extend(flatten_ax_tree(child, depth + 1))
    
    return result

def filter_noise_elements(nodes: List[Dict]) -> List[Dict]:
    """Filter out common noise elements like navigation, pagination, ads"""
    filtered = []
    
    for node in nodes:
        role = node['role']
        name = node['name'].lower() if node['name'] else ''
        
        # Skip navigation elements
        if role in ['navigation', 'banner', 'contentinfo', 'complementary']:
            continue
            
        # Skip if it looks like pagination (long sequences of numbers)
        if is_pagination_content(name):
            continue
            
        # Skip common noise patterns
        if any(noise in name for noise in ['cookie', 'advertisement', 'sponsored', 'footer', 'header']):
            continue
            
        filtered.append(node)
    
    return filtered

def is_noise_content(text: str) -> bool:
    """Check if text content is likely noise (pagination, navigation, etc.)"""
    if not text:
        return False
        
    text = text.strip().lower()
    
    # Skip pagination patterns (sequences of numbers)
    if is_pagination_content(text):
        return True
        
    # Skip common noise patterns
    noise_patterns = [
        'continue?', 'press enter', 'type \'exit\'',
        'cookie', 'privacy policy', 'terms of service',
        'advertisement', 'sponsored', 'ad choices',
        'footer', 'header', 'navigation', 'menu',
        'subscribe', 'newsletter', 'follow us'
    ]
    
    return any(pattern in text for pattern in noise_patterns)

def is_pagination_content(text: str) -> bool:
    """Check if text looks like pagination (long sequences of numbers)"""
    if not text:
        return False
        
    # Split into words and count numeric words
    words = text.split()
    if len(words) < 10:  # Short text, probably not pagination
        return False
        
    numeric_words = sum(1 for word in words if word.isdigit())
    
    # If more than 50% of words are numbers, it's likely pagination (reduced from 70%)
    if numeric_words / len(words) > 0.5:
        return True
    
    # Also check for specific pagination patterns
    # Long sequences of consecutive numbers
    if len(words) > 20 and numeric_words > 15:
        return True
    
    # Check if it's a sequence of numbers (1 2 3 4 5...)
    if len(words) > 10:
        consecutive_numbers = 0
        for i in range(len(words) - 1):
            if words[i].isdigit() and words[i + 1].isdigit():
                if int(words[i + 1]) == int(words[i]) + 1:
                    consecutive_numbers += 1
        
        # If we have many consecutive numbers, it's pagination
        if consecutive_numbers > 8:
            return True
    
    return False
