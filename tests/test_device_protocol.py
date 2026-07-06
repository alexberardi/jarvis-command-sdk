"""Tests for the IJarvisDeviceProtocol camera stream-source hook."""

import asyncio
import inspect

from jarvis_command_sdk import (
    DeviceControlResult,
    DiscoveredDevice,
    IJarvisDeviceProtocol,
)


class _MinimalProtocol(IJarvisDeviceProtocol):
    """A protocol that implements only the abstract members."""

    @property
    def protocol_name(self) -> str:
        return "minimal"

    @property
    def supported_domains(self) -> list[str]:
        return ["light"]

    async def discover(self, timeout: float = 5.0) -> list[DiscoveredDevice]:
        return []

    async def control(self, ip, action, data=None, **kwargs) -> DeviceControlResult:
        return DeviceControlResult(success=True, entity_id="x", action=action)

    async def get_state(self, ip, **kwargs):
        return {}


def _camera() -> DiscoveredDevice:
    return DiscoveredDevice(
        name="Front Door",
        domain="camera",
        manufacturer="",
        model="",
        protocol="minimal",
        entity_id="front_door",
        cloud_id="enterprises/p/devices/XYZ",
    )


def test_minimal_protocol_instantiates():
    """A protocol overriding only the abstract members must instantiate —
    get_stream_source must NOT be abstract."""
    _MinimalProtocol()


def test_get_stream_source_default_returns_none():
    """The default hook returns None so protocols without camera support are inert."""
    proto = _MinimalProtocol()
    assert asyncio.run(proto.get_stream_source(_camera())) is None


def test_get_stream_source_is_async():
    """The hook is async so implementations can do I/O (e.g. an SDM capability GET)."""
    assert inspect.iscoroutinefunction(IJarvisDeviceProtocol.get_stream_source)


def test_get_stream_source_is_optional_not_required():
    """It must stay off required_methods so every installed protocol keeps loading."""
    assert "get_stream_source" not in IJarvisDeviceProtocol.__forge_hints__["required_methods"]
