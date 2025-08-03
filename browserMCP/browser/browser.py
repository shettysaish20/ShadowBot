from browserMCP.browser.profile import BrowserProfile
from browserMCP.browser.session import BrowserSession

BrowserConfig = BrowserProfile
BrowserContextConfig = BrowserProfile
Browser = BrowserSession

__all__ = ['BrowserConfig', 'BrowserContextConfig', 'Browser']
