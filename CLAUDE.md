# jarvis-command-sdk

Shared interfaces for building Jarvis voice commands, agents, device protocols, and device managers.

## Quick Reference

```bash
# Install (editable, from monorepo)
pip install -e ../jarvis-command-sdk

# Used by jarvis-node-setup and community Pantry packages
```

## Interfaces

| Interface | Module | Purpose |
|-----------|--------|---------|
| `IJarvisCommand` | `command.py` | Voice command (the original plugin type) |
| `IJarvisAgent` | `agent.py` | Background agent (scheduled data collection) |
| `IJarvisDeviceProtocol` | `device_protocol.py` | LAN/cloud device adapter (LIFX, Kasa, etc.) |
| `IJarvisDeviceManager` | `device_manager.py` | Device listing backend (HA, Jarvis Direct) |

## Usage

**Built-in code** (jarvis-node-setup) imports from `core.*`:
```python
from core.ijarvis_command import IJarvisCommand
from core.ijarvis_agent import IJarvisAgent
```

**Community packages** (Pantry bundles) import from the SDK:
```python
from jarvis_command_sdk import IJarvisCommand, CommandResponse, JarvisParameter
from jarvis_command_sdk import IJarvisAgent, AgentSchedule
from jarvis_command_sdk import IJarvisDeviceProtocol, DiscoveredDevice
from jarvis_command_sdk import IJarvisDeviceManager, DeviceManagerDevice
```

## Exports

```python
# Commands
IJarvisCommand, PreRouteResult, CommandExample, CommandAntipattern
CommandResponse, RequestInformation, ValidationResult
IJarvisParameter, JarvisParameter
IJarvisSecret, JarvisSecret
AuthenticationConfig, IJarvisButton, JarvisPackage

# Agents
IJarvisAgent, AgentSchedule, Alert

# Device protocols
IJarvisDeviceProtocol, DiscoveredDevice, DeviceControlResult

# Device managers
IJarvisDeviceManager, DeviceManagerDevice
```

## For Community Package Authors

When building a Pantry package, use SDK imports with a `jarvis_log_client` fallback:

```python
# SDK imports (always available in Pantry container tests)
from jarvis_command_sdk import IJarvisCommand, CommandResponse

# Logging fallback (jarvis_log_client only on actual nodes)
try:
    from jarvis_log_client import JarvisLogger
except ImportError:
    import logging
    class JarvisLogger:
        def __init__(self, **kw): self._log = logging.getLogger(kw.get("service", __name__))
        def info(self, msg, **kw): self._log.info(msg)
        def warning(self, msg, **kw): self._log.warning(msg)
        def error(self, msg, **kw): self._log.error(msg)
        def debug(self, msg, **kw): self._log.debug(msg)
```

## Dependencies

None (pure Python, no external deps).

## Used By

- `jarvis-node-setup` — Node runtime (imports from `core.*` directly, SDK re-exports same classes)
- `jarvis-pantry` — Container tests install the SDK for validation
- Community packages — Import interfaces for commands, agents, protocols, managers
