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
| `JarvisInbox` | `inbox.py` | Inbox item posting facade (push + phone UI) |
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
IJarvisSecret, JarvisSecret   # value_type="user" renders a household-member picker; stored value = selected member's user id (string)
AuthenticationConfig, IJarvisButton, JarvisPackage

# Agents
IJarvisAgent, AgentSchedule, Alert

# Device protocols
IJarvisDeviceProtocol, DiscoveredDevice, DeviceControlResult

# Device managers
IJarvisDeviceManager, DeviceManagerDevice

# Interactive list payloads (server-driven phone UI)
InteractiveList, InteractiveSection, InteractiveRow
InteractiveRowAction, InteractiveAction, RequiresRecordField

# Storage
JarvisStorage, StorageBackend, set_backend, get_backend

# Inbox
JarvisInbox, InboxBackend, set_inbox_backend, get_inbox_backend

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

## Interactive List payloads (v1)

Server-driven phone UI (`interactive.py`): a command POSTs an inbox item
(`{cc}/api/v0/node/inbox-item`) with `category=InteractiveList.CATEGORY`
(`"interactive_list"`) and the payload in `metadata`; the mobile app renders it on one
generic screen. Build payloads with the SDK dataclasses — all validation happens at
construction time (`ValueError` naming the offending field/row key):

```python
from jarvis_command_sdk import (
    InteractiveList, InteractiveSection, InteractiveRow,
    InteractiveRowAction, InteractiveAction, RequiresRecordField,
)

metadata = InteractiveList(
    command_name="export_shopping_list",   # callback + record-API target
    sections=[InteractiveSection(rows=rows, title="Regulars")],
    actions=[InteractiveAction(label="Export {n} items", callback="export_selected")],
    context={"provider": "walmart"},       # opaque, echoed verbatim in callbacks
    empty_text="Nothing to export",
).to_dict()
```

**Wire format** (what `to_dict()` emits — absent optionals are omitted, never null):

```jsonc
{
  "type": "interactive_list",            // == InteractiveList.CATEGORY, always emitted
  "version": 1,                          // == InteractiveList.VERSION; renderer falls back if > 1
  "command_name": "export_shopping_list",
  "title_override": "...",               // optional; fallback: inbox item title
  "empty_text": "...",                   // optional; shown when all sections have zero rows
  "context": { },                        // optional opaque dict, echoed in callbacks
  "sections": [{ "title": "...", "rows": [   // title optional (untitled flat list)
    {
      "key": "milk",                     // unique across the payload; the callback identifier
      "label": "milk",                   // ≤120 chars
      "caption": "...",                  // optional static caption, ≤200
      "control": "checkbox_stepper",     // "none" | "checkbox" | "checkbox_stepper"
      "default": { "selected": true, "quantity": 2 },  // quantity only for checkbox_stepper
      "disabled_caption": "...",         // optional, ≤200; shown when gated off
      "requires_record_field": { "command_name": "...", "field": "...", "field_label": "..." },
      "row_actions": [{                  // ≤2; only v1 type is "webview_pick"
        "label": "Find ID", "type": "webview_pick",
        "start_url": "https://...",      // https only; {label} / {value} substitutions
        "pattern": "/ip/(?:[^/]+/)?(\\d{5,})",  // JS-compatible regex, capture group 1 = value
        "save": { "command_name": "...", "field": "..." }
      }]
    }
  ]}],
  "actions": [                           // 1..6; {n} = live selection count
    { "label": "Export {n} items", "callback": "export_selected", "style": "primary" }
    // style: "primary" | "secondary" | "destructive"
  ]
}
```

**Caps** (validated at construction, re-enforced by the renderer with truncation):
1–6 sections, ≤100 rows total, 1–6 actions, ≤2 row_actions per row, label ≤120 chars,
captions ≤200 chars. All text renders as plain `<Text>` — no HTML/markdown anywhere.

**The three behavioral primitives** (everything else is static rendering):

1. **`requires_record_field`** — live record gate. Mobile fetches the command's records
   at load; the row is enabled iff the record whose key equals the row's `key` has a
   non-empty value for `field` (caption becomes `{field_label ?? field}: {value}`).
   Unmet ⇒ disabled + `disabled_caption`, never selectable.
2. **`webview_pick`** row action — opens a WebView at `start_url` (`{label}` =
   URL-encoded row label, `{value}` = current saved field value; actions whose
   `start_url` uses `{value}` are hidden until one exists). Capture group 1 of
   `pattern` matched against navigation URLs is the picked value; confirming PATCHes
   `{field: value}` onto the record and enables + selects the row.
3. **Result affordances** — the callback's `CommandResponse.context_data` may contain
   `message` (body text), `url` (auto-open + "Open link" button), `text` (selectable
   monospace block + copy-to-clipboard), `detail_lines: [string]` (checkmarked list).
   Convention: at most one of `url`/`text`. Unknown keys ignored.

**Callback request** — every action button sends the same collected state to its
named `@callback` on `command_name`:

```jsonc
{
  "command_name": "export_shopping_list",
  "callback_name": "export_selected",
  "data": {
    "action": "export_selected",
    "selected": [{ "key": "milk", "quantity": 2 }],  // quantity only for checkbox_stepper rows
    "context": { "provider": "walmart" }             // payload.context echoed; {} if absent
  },
  "target_node_id": "<metadata.node_id — CC-injected, never set by producers>"
}
```

Mobile parses payloads **permissively** — unknown keys ignored, absent optionals
defaulted — so the schema can grow additively. Malformed payloads (or `version` > 1)
fall back to the plain inbox detail view; they never crash the app.

## Posting inbox items from packages

`JarvisInbox` (`inbox.py`) follows the `JarvisStorage` backend-injection pattern: the SDK
ships the facade, the node runtime registers the real backend via `set_inbox_backend()`
at startup, and `post()` returns `"no_backend"` (never raises) when nothing is
registered — tests and container validation just work.

```python
from jarvis_command_sdk import JarvisInbox

tag = JarvisInbox("email").post(
    title="Inbox triage — 12 unread",
    summary="Tap to review",
    body="Plain-text fallback listing",         # rendered by clients without the rich view
    category=InteractiveList.CATEGORY,
    metadata=payload.to_dict(),
    interactive_elements=None,                  # optional InboxDetail buttons (see inbox.py docstring)
    create_push_notification=True,
    target_type="user", user_id=request_info.user_id,
)
```

`post()` returns a **discriminated string tag** — `"ok"` | `"no_backend"` | `"no_cc_url"`
| `"http_error"` | `"invalid"` — so callers can map each failure mode to a distinct
spoken response (never a bool, never an exception). `interactive_elements` (a list of
button dicts dispatched to `@callback`s, shape documented in `inbox.py`) is merged into
`metadata["interactive_elements"]`; all other fields pass through verbatim to
`POST {cc}/api/v0/node/inbox-item`. CC injects `metadata.node_id` server-side — never
set it yourself.

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
4. **`JarvisStorage` is a facade over a backend.** The actual SQLAlchemy + SQLCipher implementation lives on the node side. Community packages get the facade; production swaps in the real backend via `set_backend()` at install time. Don't import the backend directly. (`JarvisInbox` follows the same pattern via `set_inbox_backend()`.)
5. **The community-package logger fallback pattern is canonical.** Every package author copies the `try: from jarvis_log_client; except ImportError: stdlib fallback` block (shown above). Don't try to make `jarvis_log_client` an SDK dependency — it's a node-only library.
6. **Spec generation is at import time** when the Pantry calls `GET /v1/forge/spec`. If you do expensive work in `__forge_hints__` (e.g. dynamic imports), the spec endpoint slows. Keep hints declarative.

## Stability

The interfaces are the **public contract** with the community package ecosystem. Stability matters more here than anywhere else in the stack. Treat `IJarvisCommand`, `IJarvisAgent`, `IJarvisDeviceProtocol`, `IJarvisDeviceManager`, and `JarvisStorage` as semver-stable.

When adding new functionality, **prefer optional kwargs and default-implemented base methods** over required new methods. Community packages need a graceful upgrade story.

`JarvisInbox` joins that list as of 0.3.3 — same contract weight as `JarvisStorage`.
