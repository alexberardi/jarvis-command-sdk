# jarvis-command-sdk

Core interfaces for building Jarvis voice assistant packages — commands, agents, device protocols, and device managers.

> **Tip:** Use the [Forge](https://pantry.jarvisautomation.io/forge) to generate packages from natural language — it uses this SDK's auto-generated spec as its system prompt.

## Installation

The SDK is not published on PyPI; install it from this repository:

```bash
pip install git+https://github.com/alexberardi/jarvis-command-sdk.git
```

To pin a specific commit:

```bash
pip install git+https://github.com/alexberardi/jarvis-command-sdk.git@<commit-sha>
```

Contributors (editable install, with dev extras):

```bash
pip install -e ".[dev]"
```

## Usage

```python
from jarvis_command_sdk import (
    IJarvisCommand,
    CommandResponse,
    CommandExample,
    JarvisParameter,
    JarvisSecret,
    RequestInformation,
)


class GetStockPriceCommand(IJarvisCommand):
    @property
    def command_name(self) -> str:
        return "get_stock_price"

    @property
    def description(self) -> str:
        return "Get real-time stock prices by ticker symbol"

    @property
    def parameters(self):
        return [
            JarvisParameter("ticker", "string", required=True, description="Stock ticker symbol"),
        ]

    @property
    def required_secrets(self):
        return [
            JarvisSecret("FINNHUB_API_KEY", "Finnhub API key", "integration", "string"),
        ]

    @property
    def keywords(self):
        return ["stock", "price", "ticker", "market"]

    def generate_prompt_examples(self):
        return [
            CommandExample("what's Apple's stock price", {"ticker": "AAPL"}, is_primary=True),
            CommandExample("check Tesla stock", {"ticker": "TSLA"}),
        ]

    def generate_adapter_examples(self):
        return self.generate_prompt_examples()

    def run(self, request_info, **kwargs):
        ticker = kwargs["ticker"]
        # Fetch stock price using your API...
        return CommandResponse.success_response({"ticker": ticker, "price": 150.00})
```

## Image parameters (photos from mobile chat)

A command can take the photos a user attached in mobile chat. Declare a parameter with
`param_type="image"` (`"array<image>"` is an accepted alias with the same meaning).
`run()` then receives **a list of `JarvisImage`**, always a list even for one photo, in
the order the user attached them: at most 4 photos, each at most 2 MiB.

```python
from jarvis_command_sdk import (
    IJarvisCommand, CommandResponse, CommandExample, JarvisParameter, JarvisImage,
)

class IdentifyPlantCommand(IJarvisCommand):
    command_name = "identify_plant"
    description = "Identify a plant from a photo the user attached"
    keywords = ["plant", "identify"]
    required_secrets = []

    @property
    def parameters(self):
        return [JarvisParameter("photos", "image", required=True, description="Photos of the plant.")]

    def generate_prompt_examples(self):
        return [CommandExample("what plant is this?", {"photos": [1]}, is_primary=True)]

    def generate_adapter_examples(self):
        return self.generate_prompt_examples()

    def run(self, request_info, **kwargs):
        photos: list[JarvisImage] = kwargs["photos"]   # always a list, attach order
        first = photos[0]
        species = my_vision_api(first.as_data_url())   # or first.data / first.save("/tmp/plant")
        return CommandResponse.success_response(
            {"species": species, "photo": f"{first.width}x{first.height} {first.mime}"}
        )
```

`JarvisImage`: `.data` (bytes), `.mime` (`image/jpeg` | `image/png` | `image/webp`,
sniffed from the bytes, never trusted from the wire), `.size_bytes`, `.width` / `.height`
(read from the file header with no Pillow needed; `None` if unparseable; the stored
dimensions, before any EXIF rotation), `.save(path)` (adds `.jpg`/`.png`/`.webp` when the
path has no extension, returns the path), `.as_base64()`, `.as_data_url()`, `.to_pil()`
(needs Pillow: add `JarvisPackage("Pillow")` to `required_packages`). `repr()` never
includes the bytes, so logging an image is safe.

Photos only arrive from mobile chat; a voice request never carries any. If the model calls
the command without photos (or with photo numbers the server could not resolve), `execute()`
returns a validation error and `run()` is not called. Bad input (more than 4, over 2 MiB,
not JPEG/PNG/WebP) is rejected the same way.

## Inbox items with images or video

`JarvisInbox(...).post()` returns a string tag (`"ok"`, or a failure tag), never raises, and can
carry attachments: bytes or a file path, plus the mime type.

```python
from jarvis_command_sdk import Attachment, JarvisInbox

tag = JarvisInbox("comfyui").post(
    title="Your picture is ready",
    attachments=[
        Attachment(path="/tmp/out.png", mime="image/png"),          # filename defaults to "out.png"
        Attachment(data=video_bytes, mime="video/mp4", filename="clip.mp4"),
    ],
    create_push_notification=True,
    target_type="user", user_id=request_info.user_id,
)
```

The SDK checks them before the upload, against jarvisd's defaults: `image/png`, `image/jpeg`,
`image/webp`, `image/gif`, `video/mp4` and `video/webm` (the bytes must match the mime; no SVG),
at most 25 MiB per file and 50 MiB per item. The failure tags are `"attachment_type"`,
`"attachment_too_large"` and `"invalid"` (a missing file, or both or neither of `data`/`path`).
A node that predates attachments returns `"attachments_unsupported"`. jarvisd's caps are
settings and the server has the last word: if a cap was lowered, the upload fails at the server
and you get the backend's failure tag (such as `"http_error"`).

## Logging, LLM and command-center calls

The node runtime injects these backends; without one (tests, Pantry container validation)
they fall back and never raise:

```python
from jarvis_command_sdk import get_logger, llm_chat_text, cc_post

log = get_logger("my_command")          # stdlib logging.getLogger without a backend
text = llm_chat_text("Tell me a joke.")  # str, or None without a backend / on error
resp = cc_post("/api/v0/some/endpoint", {"k": "v"})  # dict, or None
```

## Timers, volume, alerts and calling other commands

Also injected by the node runtime, and also never raising (safe default without a backend):

```python
from jarvis_command_sdk import (
    timer_set, timer_find_by_label, timer_cancel,
    audio_adjust_volume_percent, audio_speak,
    alerts_flush, invoke_command,
)

timer_id = timer_set(600, label="pasta")   # id, or None; the node fires and speaks it
if (tid := timer_find_by_label("pasta")):
    timer_cancel(tid)                      # True / False
level = audio_adjust_volume_percent(+10)   # new level 0-100, or None
audio_speak("Volume up.")                  # True / False
alerts = alerts_flush()                    # list[Alert], removed from the queue
resp = invoke_command("get_weather", request_info, city="Boston")  # CommandResponse, or None
```

## What's Included

| Module | Classes |
|--------|---------|
| `command` | `IJarvisCommand`, `PreRouteResult`, `CommandExample`, `CommandAntipattern` |
| `parameter` | `IJarvisParameter`, `JarvisParameter` |
| `image` | `JarvisImage`, `ImageValidationError`, `coerce_images` |
| `secret` | `IJarvisSecret`, `JarvisSecret` |
| `authentication` | `AuthenticationConfig` |
| `button` | `IJarvisButton` |
| `package` | `JarvisPackage` |
| `response` | `CommandResponse` |
| `request` | `RequestInformation` |
| `validation` | `ValidationResult` |
| `agent` | `IJarvisAgent`, `AgentSchedule`, `Alert` |
| `device_protocol` | `IJarvisDeviceProtocol`, `DiscoveredDevice`, `DeviceControlResult` |
| `device_manager` | `IJarvisDeviceManager`, `DeviceManagerDevice` |
| `logger` | `LoggerBackend`, `get_logger`, `set_logger_backend`, `get_logger_backend` |
| `llm` | `LLMBackend`, `llm_chat_text`, `set_llm_backend`, `get_llm_backend` |
| `cc_http` | `CCHttpBackend`, `cc_post`, `set_cc_backend`, `get_cc_backend` |
| `timer` | `TimerBackend`, `timer_set`, `timer_cancel`, `timer_list_active`, `timer_get`, `timer_find_by_label`, `timer_clear_all`, `set_timer_backend`, `get_timer_backend` |
| `audio_control` | `AudioControlBackend`, `audio_set_volume_percent`, `audio_adjust_volume_percent`, `audio_set_muted`, `audio_speak`, `set_audio_control_backend`, `get_audio_control_backend` |
| `alert_queue` | `AlertQueueBackend`, `alerts_pending`, `alerts_flush`, `alerts_remove`, `alerts_count`, `set_alert_queue_backend`, `get_alert_queue_backend` |
| `command_invoker` | `CommandInvokerBackend`, `invoke_command`, `set_command_invoker_backend`, `get_command_invoker_backend` |
| `forge` | `generate_spec()`, `generate_spec_markdown()` |
