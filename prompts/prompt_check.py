from google import genai
import os
from dotenv import load_dotenv


decision_1 = """
{
  "plan_mode": "initial",
  "planning_strategy": "conservative"
  "original_query": "Find number of BHK variants available in DLF Camelia from local sources.",
  "perception": {
  "entities": ["DLF Camelia", "BHK variants", "local sources"],
  "result_requirement": "Numerical count of distinct BHK configurations in DLF Camelia, based on local data.",
  "original_goal_achieved": false,
  "reasoning": "The query asks for a specific numerical answer derived from local sources about the property configurations in DLF Camelia. This requires accessing and processing local real estate information, which is not immediately available.",
  "local_goal_achieved": false,
  "local_reasoning": "This is the initial query interpretation. No specific actions or data retrieval has occurred yet."
}
}"""

decision_2 = """
{
  "plan_mode": "mid_session",
  "planning_strategy": "conservative"
  "original_query": "Find number of BHK variants available in DLF Camelia from local sources.",
  "current_plan_version": 1,
  "current_plan": [
    "Step 0: Use local RAG to get BHK variants.",
    "Step 1: Extract types from raw text.",
    "Step 2: Summarize answer cleanly."
  ],
  "completed_steps": [],
  "current_step": {
    "index": 0,
    "description": "Use local RAG to find BHK types",
    "execution_result": "None / tool failed",
    "perception_feedback": {
      "entities": [],
      "result_requirement": "Numerical count of distinct BHK configurations in DLF Camelia, based on local data.",
      "original_goal_achieved": false,
      "reasoning": "The first step, intended to retrieve information about BHK types from local sources, failed. Without this initial data, we cannot proceed towards fulfilling the user's request for the number of BHK variants.",
      "local_goal_achieved": false,
      "local_reasoning": "The tool execution did not return any usable information. Therefore, the local goal of identifying BHK types using local RAG was not achieved."
    },
    "status": "failed"
  }
}
"""

perception_1 = """
{
  "snapshot_type": "user_query",
  "raw_input": "Find number of BHK variants available in DLF Camelia from local sources.",
  "memory_excerpt": {},
  "prev_objective": "",
  "prev_confidence": null
}
"""

perecption_2 = """
{
  "snapshot_type": "step_result",
  "step_index": 0,
  "step_description": "Use local RAG to find BHK types",
  "step_result": "None / tool failed",
  "prev_objective": "List of BHK variants",
  "prior_steps": []
}
"""
with open("decision_prompt.txt", "r", encoding="utf-8") as f:
    content = f.read()

prompt = content + decision_1

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)
response = client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=prompt)

raw = response.text.strip()
print(raw)