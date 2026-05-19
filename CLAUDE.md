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
| `JarvisStorage` | `storage.py` | Command data persistence + secrets facade |
| `DateKeys` | `date_keys.py` | Standardized relative date constants |
| `GeocodingHelper` | `geocoding.py` | Fuzzy location → coordinates resolver |

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

# Storage
JarvisStorage, StorageBackend, set_backend, get_backend

# Date keys
DateKeys, ALL_DATE_KEYS

# Geocoding
GeocodingHelper, GeocodingResult
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

## Forge (Auto-Documentation)

The SDK auto-documents itself for the Forge (AI-powered package builder) via:

- **`__forge_hints__`** — Class-level dicts on all interfaces and supporting classes with component type, constructor signatures, tips, and examples
- **`forge.py`** — Runtime introspection module that walks all SDK classes using `inspect` + `get_type_hints` + docstrings + `__forge_hints__` to produce a structured spec
- **`generate_spec()`** → JSON dict (~55KB) with interfaces, supporting classes, manifest schema, file layout, validation rules
- **`generate_spec_markdown()`** → Human-readable Markdown (~550 lines) used as the Forge LLM system prompt

The Pantry serves this via `GET /v1/forge/spec` and uses it to build the Forge system prompt dynamically. When you add a method to an interface or change a type, the Forge spec updates automatically.

```python
from jarvis_command_sdk.forge import generate_spec, generate_spec_markdown
spec = generate_spec()           # JSON dict
markdown = generate_spec_markdown()  # For LLM prompts
```

## Dependencies

None (pure Python, no external deps).

## Used By

- `jarvis-node-setup` — Node runtime (imports from `core.*` directly, SDK re-exports same classes)
- `jarvis-pantry` — Container tests install the SDK for validation; Forge uses `forge.py` for spec generation
- `jarvis-pantry-web` — Forge UI consumes the spec via Pantry API
- Community packages — Import interfaces for commands, agents, protocols, managers

## Invariants & gotchas

1. **Public API is the contract for the entire package ecosystem.** Adding a required method to `IJarvisCommand` is a breaking change that invalidates every community package. Add methods as **optional with defaults** unless the migration story is intentional.
2. **`__forge_hints__` are load-bearing.** They drive the auto-generated Forge spec that powers AI package generation. When you add a new interface or supporting class, add `__forge_hints__` with `component_type`, `constructor_args`, `tips`, and `examples`. The Forge LLM uses this to write correct code.
3. **No external dependencies.** Pure Python. Don't add `httpx`, `pydantic`, or anything else without a real reason — every dep gets shipped to every community package in the sandbox.
4. **`JarvisStorage` is a facade over a backend.** The actual SQLAlchemy + SQLCipher implementation lives on the node side. Community packages get the facade; production swaps in the real backend via `set_backend()` at install time. Don't import the backend directly.
5. **The community-package logger fallback pattern is canonical.** Every package author copies the `try: from jarvis_log_client; except ImportError: stdlib fallback` block (shown above). Don't try to make `jarvis_log_client` an SDK dependency — it's a node-only library.
6. **Spec generation is at import time** when the Pantry calls `GET /v1/forge/spec`. If you do expensive work in `__forge_hints__` (e.g. dynamic imports), the spec endpoint slows. Keep hints declarative.

## Stability

The interfaces are the **public contract** with the community package ecosystem. Stability matters more here than anywhere else in the stack. Treat `IJarvisCommand`, `IJarvisAgent`, `IJarvisDeviceProtocol`, `IJarvisDeviceManager`, and `JarvisStorage` as semver-stable.

When adding new functionality, **prefer optional kwargs and default-implemented base methods** over required new methods. Community packages need a graceful upgrade story.
