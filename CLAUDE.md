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
| `IJarvisMusicCommand` | `music.py` | A command that plays audio: reports `PlaybackState`, takes transport controls |
| `IJarvisAgent` | `agent.py` | Background agent (scheduled data collection) |
| `IJarvisDaemon` | `daemon.py` | Long-running daemon: started once, kept running and restarted by the node (a held connection) |
| `IJarvisDeviceProtocol` | `device_protocol.py` | LAN/cloud device adapter (LIFX, Kasa, etc.) |
| `IJarvisDeviceManager` | `device_manager.py` | Device backend (HA, Jarvis Direct): list, plus optional `get_state`/`control` |
| `device_types()` / `device_type()` | `device_types.py` | The device-type catalogue (`device_types.json`): per-domain icon, control type, UI hints, actions, state fields |
| `JarvisStorage` | `storage.py` | Command data persistence + secrets facade |
| `JarvisInbox` | `inbox.py` | Inbox item posting facade (push + phone UI) |
| `LoggerBackend` / `get_logger` | `logger.py` | Node-supplied logger; falls back to `logging.getLogger` |
| `LLMBackend` / `llm_chat_text` | `llm.py` | Ask the node's LLM for a text reply (None without a backend) |
| `CCHttpBackend` / `cc_post` | `cc_http.py` | POST to command-center as the node (None without a backend) |
| `TimerBackend` / `timer_*` | `timer.py` | Set/cancel/list the node's timers; the host fires and speaks them |
| `AudioControlBackend` / `audio_*` | `audio_control.py` | Node volume, mute, and speak |
| `AlertQueueBackend` / `alerts_*` | `alert_queue.py` | Read/flush/remove the node's pending agent `Alert`s |
| `CommandInvokerBackend` / `invoke_command` | `command_invoker.py` | Run another installed command (host resolves its secrets) |
| `DateKeys` | `date_keys.py` | Standardized relative date constants |
| `GeocodingHelper` | `geocoding.py` | Fuzzy location → coordinates resolver |
| `JarvisImage` | `image.py` | A user-attached photo passed to an `image` parameter |

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
JarvisImage, ImageValidationError, coerce_images   # param_type="image" → run() gets list[JarvisImage]
MAX_IMAGES, MAX_IMAGE_BYTES, IMAGE_MIME_TYPES, IMAGE_SCHEMA_MARKER
IJarvisSecret, JarvisSecret   # value_type="user" renders a household-member picker; stored value = selected member's user id (string)
AuthenticationConfig, IJarvisButton, JarvisPackage

# Plan-time context (calendar availability, call_context for phone calls)
ContextOperation, ContextResult
CALL_CONTEXT, CallContextField, TIER_IF_ASKED, TIER_STATE, call_context_operation, call_context_result

# Music commands (jarvis-server docs/agent/PLAYBACK.md)
IJarvisMusicCommand, PlaybackState, PlaybackArtwork, PlaybackBackend, set_playback_backend, get_playback_backend
PLAYBACK_STATES, PLAYBACK_ACTIONS, REPEAT_MODES, ARTWORK_MIME_TYPES, ARTWORK_MAX_BYTES

# Agents
IJarvisAgent, AgentSchedule, Alert
IJarvisDaemon

# Device protocols
IJarvisDeviceProtocol, DiscoveredDevice, DeviceControlResult

# Device managers
IJarvisDeviceManager, DeviceManagerDevice

# Device-type catalogue (device_types.json; jarvisd embeds a copy, keep them identical)
device_types, device_type

# Interactive list payloads (server-driven phone UI)
InteractiveList, InteractiveSection, InteractiveRow
InteractiveRowAction, InteractiveAction, RequiresRecordField

# Storage
JarvisStorage, StorageBackend, set_backend, get_backend

# Inbox
JarvisInbox, InboxBackend, set_inbox_backend, get_inbox_backend
Attachment, validate_attachments   # images/videos on an inbox item (post(attachments=...))
ATTACHMENT_MAX_FILE_BYTES, ATTACHMENT_MAX_ITEM_BYTES, ATTACHMENT_MIME_TYPES

# Signals (producer side of the Signal Bus)
JarvisSignals, SignalsBackend, set_signals_backend, get_signals_backend

# Logger / LLM / command-center HTTP (backends injected by the node runtime)
LoggerBackend, get_logger, set_logger_backend, get_logger_backend
LLMBackend, llm_chat_text, set_llm_backend, get_llm_backend
CCHttpBackend, cc_post, set_cc_backend, get_cc_backend

# Timer / audio control / alert queue / command invoker (backends injected by the node runtime)
TimerBackend, set_timer_backend, get_timer_backend
timer_set, timer_cancel, timer_list_active, timer_get, timer_find_by_label, timer_clear_all
AudioControlBackend, set_audio_control_backend, get_audio_control_backend
audio_set_volume_percent, audio_adjust_volume_percent, audio_set_muted, audio_speak
AlertQueueBackend, set_alert_queue_backend, get_alert_queue_backend
alerts_pending, alerts_flush, alerts_remove, alerts_count
CommandInvokerBackend, invoke_command, set_command_invoker_backend, get_command_invoker_backend

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

## Image parameters

`param_type="image"` (aliases `array<image>`, `array[image]`, `image[]`, all normalized to
`"image"` by `JarvisParameter`) declares a parameter that receives photos the user attached
in mobile chat. `run()` gets `list[JarvisImage]` (`image.py`), always a list, attach order.
See README for the author-facing example.

**Two shapes, one parameter** — keep them straight:

| Where | Shape |
|---|---|
| Tool schema the model sees (`to_openai_tool_schema`, reported by the node's `report_tools`) | `{"type": "array", "items": {"type": "integer", "minimum": 1}, "maxItems": 4, "description": "<author text> Photo numbers: ...", "x-jarvis-type": "image"}` — 1-based photo numbers |
| `get_command_schema()` parameters | `{"type": "image", ...}` (the declared type) |
| `tool_call` arguments delivered to the node (the server swaps numbers for bytes) | `[{"mime": "image/jpeg", "data": "<standard base64>"}, ...]` — ≤ 4, each ≤ 2 MiB decoded |
| `run()` kwargs | `list[JarvisImage]` |

- `IMAGE_SCHEMA_MARKER = "x-jarvis-type"` with value `"image"` is how the server finds image
  properties. Don't rename it without a server change.
- `IJarvisCommand.execute()` does the coercion (`coerce_images`) after the required-param
  check and before `validate_call()`. Failures (too many, too big, bad base64, not
  JPEG/PNG/WebP, or still-unsubstituted integers) return `CommandResponse.validation_error`
  and `run()` is not called. An empty list for a required image param is an error;
  absent optional params are not injected. Coercion is idempotent (JarvisImage passes through).
- Hosts that call `run()` directly skip coercion — call `execute()`.
- The MIME type is sniffed from magic bytes; the wire `mime` is ignored. Base64 longer than
  2 MiB's encoding is rejected before decoding.
- Error messages and `repr(JarvisImage)` never contain image data; keep it that way (node logs
  them).
- `to_pil()` is the only Pillow touchpoint and imports it lazily; the SDK stays dependency-free.

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

**Attachments** (`attachments=[Attachment(...)]`, decision:
`docs/decisions/2026-10-18-inbox-attachments-sdk.md`): each is `Attachment(data=bytes)` or
`Attachment(path=...)` plus `mime` (and an optional `filename`, which defaults to the path's
basename). `post()` checks them with `validate_attachments()` against jarvisd's defaults:
`image/png|jpeg|webp|gif`, `video/mp4|webm`, with magic bytes that match the mime, at most 25 MiB
per file and 50 MiB per item. The failure tags are `"invalid"` (both or neither of data/path,
a missing file), `"attachment_type"` and `"attachment_too_large"`. The facade passes
`attachments=` to the backend **only when the list is non-empty**, so backends written before
attachments keep working. When such a backend gets attachments, `post()` returns
`"attachments_unsupported"` (it checks the signature for `attachments` or `**kwargs`). The
backend contract: upload each file (`POST /api/v0/node/inbox-attachment`, with the raw body and
`Content-Type: mime`), then send the returned ids as `attachment_ids` on the inbox-item POST.

## Logger, LLM and command-center HTTP backends

Same injection pattern again (`logger.py`, `llm.py`, `cc_http.py`): an ABC, a module-level
`_backend`, `set_*_backend(backend | None)` / `get_*_backend()`, and a module function
packages call. The node runtime registers the backends; the functions never raise.

| Function | Backend method | No backend / backend raises |
|---|---|---|
| `get_logger(name)` | `LoggerBackend.get_logger(name)` | `logging.getLogger(name)` (a failure is logged as a warning) |
| `llm_chat_text(prompt) -> str \| None` | `LLMBackend.chat_text(prompt)` | `None`, logged (debug / warning) |
| `cc_post(path, json) -> dict \| None` | `CCHttpBackend.post(path, json)` | `None`, logged (debug / warning) |

The backend method names are the contract the node implements; don't rename them.

```python
from jarvis_command_sdk import get_logger, llm_chat_text

log = get_logger("tell_a_joke")
joke = llm_chat_text("Tell me a short joke.") or "I'm out of jokes."
```

## Timer, audio-control, alert-queue and command-invoker backends

Same pattern (`timer.py`, `audio_control.py`, `alert_queue.py`, `command_invoker.py`).
Each module has a private `_call(op, default, fn)` that does the no-backend / raising-backend
fallback; helpers are prefixed (`timer_`, `audio_`, `alerts_`) so they don't collide in the
package root.

| Function | Backend method | No backend / backend raises |
|---|---|---|
| `timer_set(seconds, label=None) -> str \| None` | `TimerBackend.set` | `None` |
| `timer_cancel(timer_id) -> bool` | `.cancel` | `False` |
| `timer_list_active() -> list[dict]` | `.list_active` | `[]` |
| `timer_get(timer_id) -> dict \| None` | `.get` | `None` |
| `timer_find_by_label(label) -> str \| None` | `.find_by_label` | `None` |
| `timer_clear_all() -> int` | `.clear_all` | `0` |
| `audio_set_volume_percent(percent) -> bool` | `AudioControlBackend.set_volume_percent` | `False` |
| `audio_adjust_volume_percent(delta) -> int \| None` (new level) | `.adjust_volume_percent` | `None` |
| `audio_set_muted(muted) -> bool` | `.set_muted` | `False` |
| `audio_speak(text) -> bool` | `.speak` | `False` |
| `alerts_pending() -> list[Alert]` | `AlertQueueBackend.pending` | `[]` |
| `alerts_flush() -> list[Alert]` (and removes) | `.flush` | `[]` |
| `alerts_remove(ids) -> int` | `.remove(list(ids))` | `0` |
| `alerts_count() -> int` | `.count` | `0` |
| `invoke_command(name, request_info, /, **args) -> CommandResponse \| None` | `CommandInvokerBackend.invoke` | `None` |

- The host owns timers: it schedules, fires and speaks them. Commands never start threads for a timer.
- `invoke_command`'s `name` and `request_info` are positional-only, so a command argument
  called `name` passes through in `**args`. The host resolves the invoked command's secrets.

## Sharing context with phone calls (`call_context`)

When Jarvis plans a phone call, the server asks every command on every node of the household
for context, once, while the plan is made (never during the call): the calendar's
`availability`, and the well-known `call_context` operation. A command that has something a
business might ask for (a loyalty number, a vehicle's VIN, a dental member ID) declares it:

```python
from jarvis_command_sdk import CallContextField, call_context_operation, call_context_result

class DentalPlan(IJarvisCommand):
    @property
    def call_context_description(self) -> str:      # shown to the user under its switch
        return "Your dental plan's member ID, given only if the office asks"

    @property
    def context_operations(self):
        return [call_context_operation()]           # params: business, goal (both optional)

    def execute_context_operation(self, operation, params):
        if "dent" not in (params.get("business") or "").lower():
            return call_context_result([])          # share only what fits this call
        return call_context_result([CallContextField(
            key="dental_member_id", label="Dental member ID", value=self._member_id())])
```

The fields go into the plan's brief, which the user sees and can edit on the confirm card.
`TIER_IF_ASKED` (the default) fields are given only when the business asks and are guarded on
the call; `TIER_STATE` ones may be stated. The user's own saved call details win a key over every
command, and the first command to share a key wins over later ones. The household can switch a
command out with "Share with phone calls" in the app (enforced on the node: a switched-off command
is never asked). Commands on an older SDK declare nothing and are skipped. Read-only, as every
context operation.

## Follow-ups after a call (`offer_after_calls`)

A proposable action can also be offered as a button on a phone call's **Call finished** card.
Set `offer_after_calls` to one sentence saying when it fits a call; nothing else changes:

```python
ProposableAction(
    callback="create_event", params=self.parameters,
    card_title="Add to your calendar?", confirm_label="Add to Calendar",
    offer_after_calls="the call booked an appointment or reservation for a specific date and time",
)
```

After the call, the server's model picks the offered actions that fit the transcript and fills
their params; the server checks every pick (declared params, dates actually said on the call, no
private call details, at most 3) and the user taps to run one through the normal proposable-action
dispatcher. `None` (the default) never offers it; 1-200 chars when set. The wire form carries the
key only when set. Only commands with **Share with phone calls** on are considered. Design:
jarvis-server `docs/cc/phone-followups.md`.

## Music commands (`IJarvisMusicCommand`)

`IJarvisMusicCommand(IJarvisCommand)` (`music.py`) is the source contract of jarvis-server's
playback plan (`docs/agent/PLAYBACK.md`): one now-playing state per node, any provider.

- **Still a regular command.** Hosts find it with `issubclass(cls, IJarvisCommand)`; a host that
  doesn't know the subclass runs it as a plain command.
- **Required:** `playback_binary` (property: the player process, for ducking and takeover),
  `playback_status() -> PlaybackState | None`, `playback_control(action, **args) -> PlaybackState | None`.
  Adding these as abstract is safe because the interface is new; `IJarvisCommand` itself is unchanged.
- **Optional:** `playback_artwork() -> PlaybackArtwork | None` (bytes, JPEG/PNG/WebP, ≤ 2 MiB).
- **Provided:** `report(state=None) -> bool` pushes a change through `PlaybackBackend.report(command_name, state_dict | None)`;
  False without a backend or on any failure, never raises. `takes_over_playback_binary` returns
  `playback_binary`, so hosts that predate the subclass still do takeover.
- **The sync rule:** `playback_status()` reads the player every time; `playback_control()` returns
  the state read back afterwards, never the state asked for.
- **Closed sets:** `PLAYBACK_STATES` (`playing`, `paused`, `idle`), `PLAYBACK_ACTIONS` (`play`, `pause`,
  `next`, `previous`, `seek`, `volume`, `shuffle`, `repeat`, `like`), `REPEAT_MODES`. `PlaybackState`
  raises ValueError outside them and clamps `volume` to 0–100. Field names follow the device
  catalogue's `media_player` type. `to_dict()` omits optional fields that are None. Extending a set
  is a wire change for jarvisd and the apps.

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

## Adding a component type

A component type (`command`, `agent`, `daemon`, `device_protocol`, ...) is named in several repos,
and nothing checks that the lists agree. A type missing from one of them fails quietly: the
Pantry warns "unknown type" and its test harness fails the package, a folder isn't discovered,
or a node installs the package and skips the component. Change them together; `daemon` (0.17.0)
is the worked example.

1. **Here:** the base class with `__forge_hints__`, the export in `__init__.py`, and `forge.py`
   (`INTERFACE_CLASSES`, the manifest's valid component types, the bundle layout, convention
   inference). The Forge's prompt is generated from this, so it needs nothing else.
2. **jarvis-pantry:** `static_analysis.py` (`COMPONENT_TYPE_INFO`), `github_service.py`
   (`dir_types`), `test_harness.py` (`dir_types`, a runner, `_TYPE_RUNNERS`), the component table
   in its `CLAUDE.md`, and the SDK version it runs (`SDK_REF` in `Dockerfile.local`, plus the
   cached test base image). Its "Add a new package type" recipe has the detail.
3. **jarvis-pantry-web:** the type union in `src/api/pantry.ts`, the labels and icons in
   `CommandCard.tsx` and `app/commands/[name]/page.tsx`, the enum in `src/lib/forgeModel.ts`.
4. **The node (jarvis-server):** `internal/agent/packages/manifest.go` (`componentDirs`,
   `conventional`, `NodeTypes`), whatever loads and runs the type under `internal/agent/`, and
   the SDK commit it pins (`SDKRequirement` in `internal/agent/packages/python.go`). The Python
   node (`jarvis-node-setup`) is deprecated and gets no new types.

## Stability

The interfaces are the **public contract** with the community package ecosystem. Stability matters more here than anywhere else in the stack. Treat `IJarvisCommand`, `IJarvisAgent`, `IJarvisDeviceProtocol`, `IJarvisDeviceManager`, and `JarvisStorage` as semver-stable.

When adding new functionality, **prefer optional kwargs and default-implemented base methods** over required new methods. Community packages need a graceful upgrade story.

`JarvisInbox` joins that list as of 0.3.3 — same contract weight as `JarvisStorage`.
