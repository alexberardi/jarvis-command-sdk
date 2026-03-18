"""Jarvis Command SDK - Core interfaces for building voice commands.

Usage:
    from jarvis_command_sdk import IJarvisCommand, CommandResponse, JarvisParameter
"""

from .command import (
    IJarvisCommand,
    PreRouteResult,
    CommandExample,
    CommandAntipattern,
)
from .parameter import IJarvisParameter, JarvisParameter
from .secret import IJarvisSecret, JarvisSecret
from .authentication import AuthenticationConfig
from .button import IJarvisButton
from .package import JarvisPackage
from .response import CommandResponse
from .request import RequestInformation
from .validation import ValidationResult
from .agent import IJarvisAgent, AgentSchedule, Alert
from .device_protocol import IJarvisDeviceProtocol, DiscoveredDevice, DeviceControlResult
from .device_manager import IJarvisDeviceManager, DeviceManagerDevice

__all__ = [
    # Command interface
    "IJarvisCommand",
    "PreRouteResult",
    "CommandExample",
    "CommandAntipattern",
    # Parameters
    "IJarvisParameter",
    "JarvisParameter",
    # Secrets
    "IJarvisSecret",
    "JarvisSecret",
    # Authentication
    "AuthenticationConfig",
    # Buttons
    "IJarvisButton",
    # Packages
    "JarvisPackage",
    # Response
    "CommandResponse",
    # Request
    "RequestInformation",
    # Validation
    "ValidationResult",
    # Agent interface
    "IJarvisAgent",
    "AgentSchedule",
    "Alert",
    # Device protocol interface
    "IJarvisDeviceProtocol",
    "DiscoveredDevice",
    "DeviceControlResult",
    # Device manager interface
    "IJarvisDeviceManager",
    "DeviceManagerDevice",
]

__version__ = "0.1.0"
