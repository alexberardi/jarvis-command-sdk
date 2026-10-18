# jarvis-command-sdk

Core interfaces for building Jarvis voice assistant packages — commands, agents, device protocols, and device managers.

> **Tip:** Use the [Forge](https://pantry.jarvisautomation.io/forge) to generate packages from natural language — it uses this SDK's auto-generated spec as its system prompt.

## Installation

```bash
pip install jarvis-command-sdk
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

## Logging, LLM and command-center calls

The node runtime injects these backends; without one (tests, Pantry container validation)
they fall back and never raise:

```python
from jarvis_command_sdk import get_logger, llm_chat_text, cc_post

log = get_logger("my_command")          # stdlib logging.getLogger without a backend
text = llm_chat_text("Tell me a joke.")  # str, or None without a backend / on error
resp = cc_post("/api/v0/some/endpoint", {"k": "v"})  # dict, or None
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
| `forge` | `generate_spec()`, `generate_spec_markdown()` |
