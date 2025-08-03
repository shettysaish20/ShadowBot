@mcp.tool()
async def extract_content(input: ExtractContentAction, ctx: Context) -> ActionResultOutput:
    """Extract page content to retrieve specific information"""
    return await execute_controller_action("extract_content", input)


# ============ GOOGLE SHEETS ACTIONS ============

@mcp.tool()
async def get_sheet_contents(ctx: Context) -> ActionResultOutput:
    """Google Sheets: Get the contents of the entire sheet"""
    return await execute_controller_action("get_sheet_contents", {})

@mcp.tool()
async def select_cell_or_range(input: GoogleSheetsRangeAction, ctx: Context) -> ActionResultOutput:
    """Google Sheets: Select a specific cell or range of cells"""
    return await execute_controller_action("select_cell_or_range", input)

@mcp.tool()
async def get_range_contents(input: GoogleSheetsRangeAction, ctx: Context) -> ActionResultOutput:
    """Google Sheets: Get the contents of a specific cell or range"""
    return await execute_controller_action("get_range_contents", input)

@mcp.tool()
async def clear_selected_range(ctx: Context) -> ActionResultOutput:
    """Google Sheets: Clear the currently selected cells"""
    return await execute_controller_action("clear_selected_range", {})

@mcp.tool()
async def input_selected_cell_text(input: GoogleSheetsTextAction, ctx: Context) -> ActionResultOutput:
    """Google Sheets: Input text into the currently selected cell"""
    return await execute_controller_action("input_selected_cell_text", input)

@mcp.tool()
async def update_range_contents(input: GoogleSheetsUpdateAction, ctx: Context) -> ActionResultOutput:
    """Google Sheets: Batch update a range of cells with TSV data"""
    return await execute_controller_action("update_range_contents", input)

@mcp.tool()
async def get_ax_tree(input: GetAxTreeAction, ctx: Context) -> ActionResultOutput:
    """Get the accessibility tree of the page"""
    return await execute_controller_action("get_ax_tree", input)