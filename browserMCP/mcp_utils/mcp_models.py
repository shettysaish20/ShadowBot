from typing import Optional, List, Dict, Any
from pydantic import BaseModel

# ============ OUTPUT MODELS ============

class ElementInfo(BaseModel):
    index: int
    desc: str  
    action: str
    options: Optional[List[Dict[str, Any]]] = None
    
    class Config:
        # Exclude None values from JSON output
        exclude_none = True

class FormGroup(BaseModel):
    """Represents a group of form elements that belong together"""
    id: str  # Form ID or generated ID
    name: str  # Form name or description
    elements: List[ElementInfo]
    
    class Config:
        exclude_none = True

class ContextItem(BaseModel):
    text: str
    type: str  # h1, h2, h3, label, etc.
    
    class Config:
        exclude_none = True

class StructuredElementsOutput(BaseModel):
    success: bool
    elements: List[Dict[str, Any]] = []  # Single linear list in reading order
    total: int
    error: Optional[str] = None
    
    class Config:
        exclude_none = True

class SuccessOutput(BaseModel):
    success: bool
    error: Optional[str] = None

class SnapshotOutput(BaseModel):
    success: bool
    elements: Optional[str] = None
    screenshot_path: Optional[str] = None  # ✅ File path instead of base64
    screenshot_info: Optional[str] = None  # ✅ Descriptive info
    error: Optional[str] = None

class ScreenshotOutput(BaseModel):
    success: bool
    screenshot_path: Optional[str] = None  # ✅ Now clearly a file path
    screenshot_info: Optional[str] = None  # ✅ Additional metadata
    error: Optional[str] = None

class ElementsOutput(BaseModel):
    success: bool
    elements: Optional[str] = None
    error: Optional[str] = None

class ActionResultOutput(BaseModel):
    success: bool
    content: Optional[str] = None
    error: Optional[str] = None
    is_done: Optional[bool] = None

# ============ INPUT MODELS ============

class SnapshotInputAction(BaseModel):
    include_screenshot: Optional[bool] = False

class ScreenshotInputAction(BaseModel):
    full_page: Optional[bool] = False

class InteractiveElementsInputAction(BaseModel):
    """Input for getting only truly interactive elements"""
    strict_mode: Optional[bool] = True  # If True, only get essential actionable elements
    viewport_mode: Optional[str] = "visible"  # "visible" (viewport=0) or "all" (viewport=-1)
    structured_output: Optional[bool] = True  # If True, return structured categorized output
