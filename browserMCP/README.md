@software{browser_use2024,
  author = {Müller, Magnus and Žunič, Gregor},
  title = {Browser Use: Enable AI to control your browser},
  year = {2024},
  publisher = {GitHub},
  url = {https://github.com/browser-use/browser-use}
}

All browser automation related code is copied from browser-use.

Here are the available options:

{"click_element_by_index": {"index": 44}}
{"input_text": {"index": 45, "text": "myusername"}}
{"go_back": {}}
{"scroll_down": {"amount": 500}}
{"scroll_up": {"amount": 500}}
{"open_tab": {"url": "https://example.com"}}
{"close_tab": {"page_id": 1}}
{"switch_tab": {"page_id": 1}}
{"save_pdf": {}}
{"extract_content": {"goal": "extract all emails", "should_strip_link_urls": true}}
{"drag_drop": {
    "element_source": "xpath_or_css_selector",
    "element_target": "xpath_or_css_selector",
    "element_source_offset": null,
    "element_target_offset": null,
    "coord_source_x": null,
    "coord_source_y": null,
    "coord_target_x": null,
    "coord_target_y": null,
    "steps": 10,
    "delay_ms": 5
}}
{"send_keys": {"keys": "Enter"}}
{"scroll_to_text": {"text": "Some visible text"}}

click_element_by_index: Click a button, link, etc. by its index.
input_text: Type text into an input or textarea by its index.
go_back: Go back in browser history.
scroll_down / scroll_up: Scroll the page by a pixel amount.
open_tab: Open a new tab with a given URL.
close_tab: Close a tab by its page ID.
switch_tab: Switch to a tab by its page ID.
save_pdf: Save the current page as a PDF.
extract_content: Extract structured content from the page.
drag_drop: Drag and drop between elements or coordinates.
send_keys: Send special keys (e.g., Enter, Escape, Ctrl+T).
scroll_to_text: Scroll to a specific visible text on the page.