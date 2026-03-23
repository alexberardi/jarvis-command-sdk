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
from .prompt_provider import IJarvisPromptProvider
from .storage import JarvisStorage, StorageBackend, set_backend, get_backend
from .date_keys import DateKeys, ALL_DATE_KEYS
from .geocoding import GeocodingHelper, GeocodingResult
from .settings import UserSettings
from .forge import generate_spec, generate_spec_markdown

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
    # Prompt provider interface
    "IJarvisPromptProvider",
    # Storage
    "JarvisStorage",
    "StorageBackend",
    "set_backend",
    "get_backend",
    # Date keys
    "DateKeys",
    "ALL_DATE_KEYS",
    # Geocoding
    "GeocodingHelper",
    "GeocodingResult",
    # Settings
    "UserSettings",
    # Forge spec generation
    "generate_spec",
    "generate_spec_markdown",
]

__version__ = "0.1.0"
