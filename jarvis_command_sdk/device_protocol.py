"""IJarvisDeviceProtocol — Interface for device family protocol adapters.

Each implementation handles discovery and control for one manufacturer/protocol
(e.g., LIFX LAN, TP-Link Kasa, Govee cloud).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

from .authentication import AuthenticationConfig
from .button import IJarvisButton
from .secret import IJarvisSecret


@dataclass
class DiscoveredDevice:
    """A device found during scanning (LAN or cloud)."""

    name: str
    domain: str
    manufacturer: str
    model: str
    protocol: str
    entity_id: str
    local_ip: str | None = None
    mac_address: str | None = None
    cloud_id: str | None = None
    device_class: str | None = None
    is_controllable: bool = True
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class DeviceControlResult:
    """Result of a device control operation."""

    success: bool
    entity_id: str
    action: str
    error: str | None = None


class IJarvisDeviceProtocol(ABC):
    """Interface for manufacturer-specific device protocols."""

    @property
    @abstractmethod
    def protocol_name(self) -> str:
        """Short protocol identifier (e.g., 'lifx', 'kasa')."""
        ...

    @property
    @abstractmethod
    def supported_domains(self) -> list[str]:
        """HA-style domains this protocol can control."""
        ...

    @property
    def connection_type(self) -> Literal["lan", "cloud", "hybrid"]:
        """How this family connects to devices."""
        return "lan"

    @property
    def required_secrets(self) -> list[IJarvisSecret]:
        """Secrets this family needs to function."""
        return []

    @property
    def friendly_name(self) -> str:
        """Human-readable display name."""
        return self.protocol_name.replace("_", " ").title()

    @property
    def description(self) -> str:
        """Short description for the mobile UI."""
        return ""

    @property
    def authentication(self) -> AuthenticationConfig | None:
        """OAuth or other auth config for this device family."""
        return None

    @property
    def supported_actions(self) -> list[IJarvisButton]:
        """Default device control buttons."""
        return [
            IJarvisButton("Turn On", "turn_on", "primary", "power"),
            IJarvisButton("Turn Off", "turn_off", "secondary", "power-off"),
        ]

    def store_auth_values(self, values: dict[str, str]) -> None:
        """Store auth tokens/values received from OAuth flow."""

    @abstractmethod
    async def discover(self, timeout: float = 5.0) -> list[DiscoveredDevice]:
        """Scan for devices using this protocol."""
        ...

    @abstractmethod
    async def control(
        self,
        ip: str,
        action: str,
        data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> DeviceControlResult:
        """Send a control command to a device."""
        ...

    @abstractmethod
    async def get_state(self, ip: str, **kwargs: Any) -> dict[str, Any] | None:
        """Query current device state."""
        ...
