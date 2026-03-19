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

## What's Included

| Module | Classes |
|--------|---------|
| `command` | `IJarvisCommand`, `PreRouteResult`, `CommandExample`, `CommandAntipattern` |
| `parameter` | `IJarvisParameter`, `JarvisParameter` |
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
| `forge` | `generate_spec()`, `generate_spec_markdown()` |
