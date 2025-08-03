# execute_step.py - SIMPLIFIED (or can be removed since executor.py handles everything)

import uuid
from utils.utils import log_step, log_error
from action.executor import run_user_code
from agent.agentSession import ExecutionSnapshot
import asyncio

# This file can be removed entirely since executor.py handles code execution properly
# Keeping minimal version for backward compatibility

async def execute_step(step_id, code_variants, ctx, session, multi_mcp):
    """Simple wrapper around executor.run_user_code - can be removed"""
    
    # Just call executor directly
    executor_input = {
        "code_variants": code_variants  # CODE_1, CODE_2, etc.
    }
    
    result = await run_user_code(
        executor_input,
        multi_mcp,
        ctx.session_id,
        ctx.get_inputs([])  # Get inputs from context
    )
    
    # Handle session tracking if needed
    if session:
        session.add_execution_snapshot(
            ExecutionSnapshot(
                run_id=str(uuid.uuid4()),
                step_id=step_id,
                variant_used=result.get("code_results", {}).get("successful_variant", ""),
                code=str(code_variants),
                status=result.get("status", "error"),
                result=result.get("result"),
                error=result.get("error"),
                execution_time=result.get("total_time", ""),
                total_time=result.get("total_time", ""),
            )
        )
    
    return result
