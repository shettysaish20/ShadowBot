# flow.py – SIMPLIFIED Output Chain System

import networkx as nx
import asyncio
from agentLoop.contextManager import ExecutionContextManager
from typing import Optional, Union, Any, Dict
from agentLoop.agents import AgentRunner
from utils.utils import log_step, log_error
from agentLoop.visualizer import ExecutionVisualizer
from rich.console import Console
from pathlib import Path
from action.executor import run_user_code

class AgentLoop4:
    def __init__(self, multi_mcp, strategy="conservative"):
        self.multi_mcp = multi_mcp
        self.strategy = strategy
        self.agent_runner = AgentRunner(multi_mcp)
        self._conversation_turn = 0

    async def run(self, query, file_manifest, uploaded_files, context: Optional[ExecutionContextManager] = None):
        """Run planning + execution. If an existing context is supplied, extend the current session.

        Args:
            query: User's new query / follow-up
            file_manifest: Current file manifest
            uploaded_files: Files just uploaded (optional per turn)
            context: Existing ExecutionContextManager (continuation) or None (new session)
        Returns:
            ExecutionContextManager (existing or newly created) updated with new nodes
        """
        self._conversation_turn += 1
        is_continuation = context is not None

        # Phase 1: (Re)Profile only newly provided files (simple approach)
        # Phase 1: File Profiling (if files exist)
        file_profiles = {}
        if uploaded_files:
            file_list_text = "\n".join([f"- File {i+1}: {Path(f).name} (full path: {f})" for i, f in enumerate(uploaded_files)])
            
            grounded_instruction = f"""Profile and summarize each file's structure, columns, content type.

            IMPORTANT: Use these EXACT file names in your response:
            {file_list_text}

            Profile each file separately and return details."""

            file_result = await self.agent_runner.run_agent(
                "DistillerAgent",
                {
                    "task": "profile_files",
                    "files": uploaded_files,
                    "instruction": grounded_instruction,
                    "writes": ["file_profiles"]
                }
            )
            if file_result["success"]:
                file_profiles = file_result["output"]

        # Phase 2: Planning (initial vs mid_session)
        planner_input = {
            "original_query": query,
            "planning_strategy": self.strategy,
            "file_manifest": file_manifest,
            "file_profiles": file_profiles,
            "mode": "mid_session" if is_continuation else "initial",
            "conversation_turn": self._conversation_turn
        }
        if is_continuation and context is not None:
            # Provide existing plan graph + used IDs + recent queries for context
            existing_nodes = [n for n in context.plan_graph.nodes if n != "ROOT"]
            planner_input["existing_plan_graph"] = {
                "nodes": [
                    {
                        "id": n,
                        "agent": context.plan_graph.nodes[n].get("agent"),
                        "description": context.plan_graph.nodes[n].get("description"),
                        "reads": context.plan_graph.nodes[n].get("reads", []),
                        "writes": context.plan_graph.nodes[n].get("writes", []),
                        "status": context.plan_graph.nodes[n].get("status")
                    } for n in existing_nodes
                ],
                "edges": [
                    {"source": u, "target": v} for u, v in context.plan_graph.edges() if u != "ROOT" or v != "ROOT"
                ]
            }
            planner_input["used_step_ids"] = existing_nodes
            planner_input["previous_queries"] = context.plan_graph.graph.get("queries", [])

        plan_result = await self.agent_runner.run_agent("PlannerAgent", planner_input)

        if not plan_result["success"]:
            raise RuntimeError(f"Planning failed: {plan_result['error']}")

        if 'plan_graph' not in plan_result['output']:
            raise RuntimeError(f"PlannerAgent output missing 'plan_graph' key")
        
        plan_graph = plan_result["output"]["plan_graph"]

        if not is_continuation:
            # Phase 3: Create new context
            context = ExecutionContextManager(
                plan_graph,
                session_id="",  # auto-generate inside constructor when falsy
                original_query=query,
                file_manifest=file_manifest
            )
            context.set_multi_mcp(self.multi_mcp)
            context.plan_graph.graph.setdefault("queries", []).append({
                "turn": self._conversation_turn,
                "query": query
            })

            # Store initial files in output chain
            if file_profiles:
                context.plan_graph.graph['output_chain']['file_profiles'] = file_profiles

            # Store uploaded files directly
            for file_info in file_manifest:
                context.plan_graph.graph['output_chain'][file_info['name']] = file_info['path']
        else:
            # Phase 3b: Append new plan to existing context
            self._append_new_plan(context, plan_graph, query)
            context.plan_graph.graph.setdefault("queries", []).append({
                "turn": self._conversation_turn,
                "query": query
            })
            # Merge new file profiles (namespace safe)
            if file_profiles:
                context.plan_graph.graph['output_chain'][f"file_profiles_turn_{self._conversation_turn}"] = file_profiles

        # Phase 4: Execute with simple output chaining
        await self._execute_dag(context)
        return context

    def _append_new_plan(self, context: ExecutionContextManager, new_plan_graph: dict, query: str):
        """Append nodes/edges from a new plan_graph into existing session graph.
        Ensures unique IDs and preserves existing node statuses.
        """
        existing_ids = set(context.plan_graph.nodes())
        # Determine next numeric index for fallback
        def next_id_generator():
            # Extract numeric parts like T001
            max_num = 0
            for nid in existing_ids:
                try:
                    if nid.startswith('T'):
                        num = int(''.join(ch for ch in nid[1:] if ch.isdigit()))
                        max_num = max(max_num, num)
                except Exception:
                    continue
            while True:
                max_num += 1
                yield f"T{max_num:03d}"
        id_gen = next_id_generator()

        id_map = {}
        for node in new_plan_graph.get("nodes", []):
            nid = node["id"]
            if nid in existing_ids:
                new_id = next(id_gen)
                id_map[nid] = new_id
                nid = new_id
            else:
                id_map[node["id"]] = node["id"]
            # Remove any attributes we explicitly set to avoid duplicate kwargs
            sanitized = {k: v for k, v in node.items() if k not in {'id','status','output','error','cost','start_time','end_time','execution_time'}}
            # Use provided status if present else pending
            node_status = node.get('status','pending')
            context.plan_graph.add_node(
                nid,
                **sanitized,
                status=node_status,
                output=None, error=None, cost=0.0,
                start_time=None, end_time=None, execution_time=0.0
            )
        # Add edges
        for edge in new_plan_graph.get("edges", []):
            src = id_map.get(edge.get("source"), edge.get("source"))
            tgt = id_map.get(edge.get("target"), edge.get("target"))
            # Only add if both in graph
            if src in context.plan_graph.nodes and tgt in context.plan_graph.nodes:
                context.plan_graph.add_edge(src, tgt)
        # Update graph original_query to most recent query for prompt context
        context.plan_graph.graph['original_query'] = query
        log_step(f"🔗 Appended {len(new_plan_graph.get('nodes', []))} new nodes (turn {self._conversation_turn})", symbol="➕")

    async def _execute_dag(self, context: ExecutionContextManager):
        """Execute DAG with simple output chaining"""
        visualizer = ExecutionVisualizer(context)
        console = Console()
        
        MAX_CONCURRENT_AGENTS = 4
        max_iterations = 20
        iteration = 0

        while not context.all_done() and iteration < max_iterations:
            iteration += 1
            console.print(visualizer.get_layout())

            # Watchdog: auto-fail steps running too long
            stuck = context.get_running_over(90)
            if stuck:
                for s in stuck:
                    if context.plan_graph.nodes[s]['status'] == 'running':
                        context.mark_failed(s, error='watchdog_timeout')
            
            ready_steps = context.get_ready_steps()
            if not ready_steps:
                if any(context.plan_graph.nodes[n]['status'] == 'failed' 
                       for n in context.plan_graph.nodes):
                    break
                await asyncio.sleep(0.3)
                continue

            # Rate limiting
            batch_size = min(len(ready_steps), MAX_CONCURRENT_AGENTS)
            current_batch = ready_steps[:batch_size]
            
            print(f"🚀 Executing batch: {current_batch}")

            # Mark running
            for step_id in current_batch:
                context.mark_running(step_id)
            
            # Execute batch
            tasks = [self._execute_step(step_id, context) for step_id in current_batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results - SIMPLE!
            for step_id, result in zip(current_batch, results):
                if isinstance(result, Exception):
                    context.mark_failed(step_id, str(result))
                    continue
                if not isinstance(result, dict):
                    context.mark_failed(step_id, f"Unexpected result type: {type(result)}")
                    continue
                if result.get("success"):
                    await context.mark_done(step_id, result.get("output"))
                else:
                    context.mark_failed(step_id, result.get("error"))

            if len(ready_steps) > batch_size:
                await asyncio.sleep(5)

    async def _execute_step(self, step_id, context: ExecutionContextManager):
        """SIMPLE: Execute step with direct output passing and code execution"""
        step_data = context.get_step_data(step_id)
        agent_type = step_data["agent"]
        
        # SIMPLE: Get raw outputs from previous steps
        inputs = context.get_inputs(step_data.get("reads", []))
        
        # Build agent input
        def build_agent_input(instruction=None, previous_output=None):
            return {
                "step_id": step_id,
                "agent_prompt": instruction or step_data.get("agent_prompt", step_data["description"]),
                "reads": step_data.get("reads", []),
                "writes": step_data.get("writes", []),
                "inputs": inputs,  # Direct output passing!
                "original_query": context.plan_graph.graph['original_query'],
                "session_context": {
                    "session_id": context.plan_graph.graph['session_id'],
                    "file_manifest": context.plan_graph.graph['file_manifest']
                },
                **({"previous_output": previous_output} if previous_output else {})
            }

        # Execute first iteration
        agent_input = build_agent_input()
        result = await self.agent_runner.run_agent(agent_type, agent_input)
        
        # NEW: Handle code execution if agent returned code variants
        if result["success"] and "code" in result["output"]:
            log_step(f"🔧 {step_id}: Agent returned code variants, executing...", symbol="⚙️")
            
            # Prepare executor input
            executor_input = {
                "code_variants": result["output"]["code"],  # CODE_1, CODE_2, etc.
            }
            
            # Execute code variants sequentially until one succeeds
            try:
                execution_result = await run_user_code(
                    executor_input, 
                    self.multi_mcp, 
                    context.plan_graph.graph['session_id'] or "default_session",
                    inputs  # Pass inputs to code execution
                )
                
                # Handle execution results
                if execution_result["status"] == "success":
                    log_step(f"✅ {step_id}: Code execution succeeded", symbol="🎉")
                    
                    # Extract the actual result from code execution
                    code_output = execution_result.get("code_results", {}).get("result", {})
                    
                    # Combine agent output with code execution results
                    combined_output = {
                        **result["output"].get("output", {}),  # Agent's direct output
                        **code_output  # Code execution results
                    }
                    
                    # Update result with combined output
                    result["output"] = combined_output
                    
                elif execution_result["status"] == "partial_failure":
                    log_step(f"⚠️ {step_id}: Code execution partial failure", symbol="⚠️")
                    
                    # Try to extract any successful results
                    code_output = execution_result.get("code_results", {}).get("result", {})
                    if code_output:
                        combined_output = {
                            **result["output"].get("output", {}),
                            **code_output
                        }
                        result["output"] = combined_output
                    else:
                        # Mark as failed
                        result["success"] = False
                        result["error"] = f"Code execution failed: {execution_result.get('error', 'Unknown error')}"
                        
                else:
                    log_step(f"❌ {step_id}: Code execution failed", symbol="🚨")
                    result["success"] = False
                    result["error"] = f"Code execution failed: {execution_result.get('error', 'Unknown error')}"
                    
            except Exception as e:
                log_step(f"💥 {step_id}: Code execution exception: {e}", symbol="❌")
                result["success"] = False
                result["error"] = f"Code execution exception: {str(e)}"
        
        # Handle call_self if needed
        if result["success"] and result["output"].get("call_self"):
            log_step(f"🔄 CALL_SELF triggered for {step_id}", symbol="🔄")
            
            # Second iteration with previous output
            second_input = build_agent_input(
                instruction=result["output"].get("next_instruction", "Continue"),
                previous_output=result["output"]
            )
            
            second_result = await self.agent_runner.run_agent(agent_type, second_input)
            
            # Handle code execution for second iteration too
            if second_result["success"] and "code" in second_result["output"]:
                log_step(f"🔧 {step_id}: Second iteration returned code variants", symbol="⚙️")
                
                executor_input = {
                    "code_variants": second_result["output"]["code"],
                }
                
                try:
                    execution_result = await run_user_code(
                        executor_input,
                        self.multi_mcp,
                        context.plan_graph.graph['session_id'] or "default_session",
                        inputs
                    )
                    
                    if execution_result["status"] == "success":
                        code_output = execution_result.get("code_results", {}).get("result", {})
                        combined_output = {
                            **second_result["output"].get("output", {}),
                            **code_output
                        }
                        second_result["output"] = combined_output
                    else:
                        second_result["success"] = False
                        second_result["error"] = f"Code execution failed: {execution_result.get('error')}"
                        
                except Exception as e:
                    second_result["success"] = False
                    second_result["error"] = f"Code execution exception: {str(e)}"
            
            # Store iteration data
            step_data['iterations'] = [
                {"iteration": 1, "output": result["output"]},
                {"iteration": 2, "output": second_result["output"] if second_result["success"] else None}
            ]
            step_data['call_self_used'] = True
            
            return second_result if second_result["success"] else result
        
        ## FIXED: Check for the code bug in ClarificationAgent
        if result["success"] and "clarification_request" in result["output"]:
            log_step(f"🤔 {step_id}: Clarification needed", symbol="❓")
            
            # Get user input
            clarification = result["output"].get("clarification_request",{"message": "Please elaborate on your query!"})
            user_response = await self._get_user_input(clarification["message"])
            
            # CREATE the actual node output (ClarificationAgent doesn't do this)
            result["output"] = {
                "user_choice": user_response,
                "clarification_provided": clarification["message"]
            }
            # Mark as successful
            result["success"] = True
        
        return result
    
    async def _get_user_input(self, message):
        """Get query from user"""
        log_step(message, symbol="❓")
        return input().strip()

