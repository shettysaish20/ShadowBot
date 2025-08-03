"""
Telemetry for Browser Use.
"""

from browserMCP.telemetry.service import ProductTelemetry
from browserMCP.telemetry.views import BaseTelemetryEvent, ControllerRegisteredFunctionsTelemetryEvent

__all__ = ['BaseTelemetryEvent', 'ControllerRegisteredFunctionsTelemetryEvent', 'ProductTelemetry']
