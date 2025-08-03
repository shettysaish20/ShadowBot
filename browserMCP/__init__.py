import warnings

# Suppress specific deprecation warnings from FAISS
warnings.filterwarnings('ignore', category=DeprecationWarning, module='faiss.loader')
warnings.filterwarnings('ignore', message='builtin type SwigPyPacked has no __module__ attribute')
warnings.filterwarnings('ignore', message='builtin type SwigPyObject has no __module__ attribute')
warnings.filterwarnings('ignore', message='builtin type swigvarlink has no __module__ attribute')

from browserMCP.agent.logging_config import setup_logging

setup_logging()

from .agent.prompts import SystemPrompt
# from .agent.service import Agent
from .agent.views import ActionModel, ActionResult, AgentHistoryList
from .browser import Browser, BrowserConfig, BrowserContext, BrowserContextConfig, BrowserProfile, BrowserSession
from .controller.service import Controller
from .dom.service import DomService

__all__ = [
	# 'Agent',
	'Browser',
	'BrowserConfig',
	'BrowserSession',
	'BrowserProfile',
	'Controller',
	'DomService',
	'SystemPrompt',
	'ActionResult',
	'ActionModel',
	'AgentHistoryList',
	'BrowserContext',
	'BrowserContextConfig',
]
