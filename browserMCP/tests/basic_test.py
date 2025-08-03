import asyncio
import os
import sys
from typing import Any, List, Dict
from pathlib import Path
import warnings
import logging

if sys.platform == "win32":
	warnings.filterwarnings("ignore", category=ResourceWarning)
	logging.getLogger("asyncio").setLevel(logging.CRITICAL)
	try:
		import asyncio.proactor_events
		asyncio.proactor_events._warn = lambda *a, **k: None
	except Exception:
		pass

	# Suppress unclosed transport warnings
	import asyncio
	asyncio.get_event_loop().set_exception_handler(lambda loop, context: None)

	import asyncio.base_subprocess

	def silent_del(self):
		pass

	asyncio.base_subprocess.BaseSubprocessTransport.__del__ = silent_del
	asyncio.proactor_events._ProactorBasePipeTransport__del__ = silent_del

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from browserMCP.browser import BrowserSession, BrowserProfile
from browserMCP.controller.service import Controller
from browserMCP.controller.registry.views import ActionModel
from browserMCP.dom.service import DomService

# Initial actions to perform
initial_actions = [
	{'open_tab': {'url': 'https://www.google.com'}},
	{'open_tab': {'url': 'https://en.wikipedia.org/wiki/Randomness'}},
	{'scroll_down': {'amount': 1000}},
]

class SimplebrowserMCP:
	def __init__(self):
		self.controller = Controller()
		# Create a browser profile with headless=False
		profile = BrowserProfile(headless=False)
		self.browser_session = BrowserSession(profile=profile)
		self.ActionModel = self.controller.registry.create_action_model()

	async def run_simple_actions(self, actions: List[Dict[str, Dict[str, Any]]]) -> List[ActionModel]:
		"""Convert dictionary-based actions to ActionModel instances and execute them"""
		# Start the browser session first
		await self.browser_session.start()
		
		converted_actions = []
		
		# Convert actions to ActionModel instances
		for action_dict in actions:
			action_name = next(iter(action_dict))
			params = action_dict[action_name]

			# Get the parameter model for this action from registry
			action_info = self.controller.registry.registry.actions[action_name]
			param_model = action_info.param_model

			# Create validated parameters using the appropriate param model
			validated_params = param_model(**params)

			# Create ActionModel instance with the validated parameters
			action_model = self.ActionModel(**{action_name: validated_params})
			converted_actions.append(action_model)

		# Execute the actions
		results = []
		for action in converted_actions:
			try:
				result = await self.controller.act(
					action=action,
					browser_session=self.browser_session,
					page_extraction_llm=None,  # No LLM needed
					sensitive_data=None,
					available_file_paths=None,
					context=None
				)
				results.append(result)
				page = await self.browser_session.get_current_page()
				# import pdb; pdb.set_trace()
				if page is not None:
					dom_service = DomService(page)
					await dom_service.get_clickable_elements(highlight_elements=True)
					print("\nAvailable actions for this page:")
					desc = self.controller.registry.get_prompt_description(page=page)
					if not desc.strip():
						print("  (No actions available for this page)")
					else:
						print(desc)
				await asyncio.sleep(2)  # Add delay between actions
			except Exception as e:
				print(f"Error executing action: {e}")
				results.append(None)

		print("\nAll registered actions:")
		for name, action in self.controller.registry.registry.actions.items():
			print(f"- {name}: {action.description}")

		return results

	async def close(self):
		"""Close browser resources"""
		await self.browser_session.stop()

async def main():
	agent = SimplebrowserMCP()
	try:
		results = await agent.run_simple_actions(initial_actions)
		print("Actions completed:", results)
		print("\nBrowser is still open. Press Enter to close it...")
		# Wait for user input before closing
		input()
	finally:
		await agent.close()

if __name__ == "__main__":
	asyncio.run(main())