import os
import sys
import warnings
import logging
import json

if sys.platform == "win32":
    warnings.filterwarnings("ignore", category=ResourceWarning)
    logging.getLogger("asyncio").setLevel(logging.CRITICAL)
    try:
        import asyncio.proactor_events
        asyncio.proactor_events._warn = lambda *a, **k: None
    except Exception:
        pass
    import asyncio.base_subprocess
    def silent_del(self): pass
    asyncio.base_subprocess.BaseSubprocessTransport.__del__ = silent_del
    asyncio.proactor_events._ProactorBasePipeTransport__del__ = silent_del

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from browserMCP.browser import BrowserSession, BrowserProfile
from browserMCP.controller.service import Controller

# logging.getLogger("browser").setLevel(logging.DEBUG)

async def main() -> None:
    profile         = BrowserProfile(
        headless=False,
        allowed_domains=None,
        highlight_elements=True,
        bypass_csp=True,
        viewport_expansion=-1,
        include_dynamic_attributes=True,
    )
    browser_session = BrowserSession(profile=profile)
    controller      = Controller()

    await browser_session.start()
    try:
        # Open Hacker News
        page = await browser_session.create_new_tab("https://www.inkers.ai/")
        await page.wait_for_load_state("domcontentloaded")

        while True:
            # ---- refresh DOM & selector-map via the *public* API ----
            try:
                # 1️⃣ Pull the fresh state (this populates the internal cache)
                state = await browser_session.get_state_summary(
                    cache_clickable_elements_hashes=False
                )


                # 2️⃣ Access the selector-map from the returned summary
                selector_map = state.selector_map
                page         = await browser_session.get_current_page()

                # import pdb; pdb.set_trace()

                # print("DEBUG current url:", page.url)
                # print("DEBUG selector_map size:", len(selector_map))
            except Exception as exc:
                print("‼️ get_state_summary() failed:", exc)
                import traceback; traceback.print_exc()
                break
            # ----------------------------------------------------------------

            # ---------- what the LLM receives ----------
            # print("\nAvailable actions for this page (schema):")
            # print(controller.registry.get_prompt_description(page=page))

            print("\nAvailable clickable/input elements (LLM format):")
            print(state.element_tree.clickable_elements_to_string(include_attributes=["id", "name", "placeholder", "type"])[:200])
            # import pdb; pdb.set_trace()

            print("\nExamples you can try (copy-paste):")
            print('  {"click_element_by_index": {"index": 44}}')
            print('  {"input_text": {"index": 45, "text": "myusername"}}')
            print('  {"go_back": {}}')
            print('  {"scroll_down": {"amount": 500}}')

            # import pdb; pdb.set_trace()

            user = input(
                '\nPaste LLM JSON (e.g. {"click_element_by_index": {"index": 27}}) '
                'or press Enter to quit:\n> '
            ).strip()
            if not user:
                break

            # ---------- parse / validate ----------
            try:
                llm = json.loads(user)
                if not (isinstance(llm, dict) and len(llm) == 1):
                    raise ValueError("must be single-key JSON")
                action_name, params = next(iter(llm.items()))
                reg_action  = controller.registry.registry.actions[action_name]
                param_model = reg_action.param_model
                validated   = param_model(**params)
                ActModel    = controller.registry.create_action_model(page=page)
                action_obj  = ActModel(**{action_name: validated})
            except Exception as exc:
                print("❌ invalid input:", exc)
                continue
            # --------------------------------------

            # ---------- execute ----------
            try:
                result = await controller.act(
                    action          = action_obj,
                    browser_session = browser_session,
                    page_extraction_llm=None
                )
                print("✅ result:", result)
                page = await browser_session.get_current_page()
                await page.wait_for_load_state("domcontentloaded")
            except Exception as exc:
                print("❌ controller error:", exc)
            # --------------------------------------

    finally:
        input("\n✋  Press Enter to close the browser...")
        await browser_session.stop()

if __name__ == "__main__":
    asyncio.run(main())
