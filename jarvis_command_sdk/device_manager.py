"""IJarvisDeviceManager — Interface for device listing backends.

A DeviceManager collects the full list of devices from a backend
(Home Assistant, Jarvis Direct, etc.) and returns them in a normalized format.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from .authentication import AuthenticationConfig
from .secret import IJarvisSecret


@dataclass
class DeviceManagerDevice:
    """Normalized device returned by any device manager."""

    name: str
    domain: str
    entity_id: str
    is_controllable: bool = True
    manufacturer: str | None = None
    model: str | None = None
    protocol: str | None = None
    local_ip: str | None = None
    mac_address: str | None = None
    cloud_id: str | None = None
    device_class: str | None = None
    source: str = "direct"
    area: str | None = None
    state: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class IJarvisDeviceManager(ABC):
    """Interface for device listing backends.

    A DeviceManager collects the full list of controllable devices from a
    backend (Home Assistant, Jarvis Direct, etc.) and returns them in a
    normalized format. The mobile app displays these in the Devices tab.
    """

    __forge_hints__ = {
        "component_type": "device_manager",
        "entry_file": "manager.py",
        "convention_dir": "device_managers/{name}/",
        "base_class": "IJarvisDeviceManager",
        "required_methods": [
            "name", "friendly_name", "description", "collect_devices",
        ],
        "tips": [
            "name should be short and lowercase (e.g., 'home_assistant', 'jarvis_direct')",
            "friendly_name is shown in the mobile settings UI",
            "can_edit_devices controls whether the mobile app shows edit UI for the device list",
            "collect_devices() should return all devices from this backend in normalized format",
        ],
        "example_import": "from jarvis_command_sdk import IJarvisDeviceManager, DeviceManagerDevice, JarvisSecret",
    }

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier (e.g., 'home_assistant', 'jarvis_direct')."""
        ...

    @property
    @abstractmethod
    def friendly_name(self) -> str:
        """Human-readable display name."""
        ...

    @property
    def description(self) -> str:
        """Short description for mobile settings UI."""
        return ""

    @property
    @abstractmethod
    def can_edit_devices(self) -> bool:
        """Whether mobile should show an edit UI for the device list."""
        ...

    @property
    def required_secrets(self) -> list[IJarvisSecret]:
        """Secrets needed for this manager to function."""
        return []

    @property
    def authentication(self) -> AuthenticationConfig | None:
        """OAuth or other auth config, if any."""
        return None

    @abstractmethod
    async def collect_devices(self) -> list[DeviceManagerDevice]:
        """Collect the full device list from this backend."""
        ...
