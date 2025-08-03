from browserMCP.browser.profile import BrowserProfile
from browserMCP.browser.session import BrowserSession

Browser = BrowserSession
BrowserConfig = BrowserProfile
BrowserContext = BrowserSession
BrowserContextConfig = BrowserProfile

__all__ = ['Browser', 'BrowserConfig', 'BrowserContext', 'BrowserContextConfig']
