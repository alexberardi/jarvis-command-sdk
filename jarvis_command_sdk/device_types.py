"""The device-type catalogue: what each domain looks like to Jarvis.

device_types.json is the one source for domain icons, control types, UI hints,
standard action names and normalized state fields. The node, the server and the
apps read the same file, so a device manager or protocol translates its backend's
vocabulary into these names rather than the UIs learning each backend's.
"""

import json
from functools import lru_cache
from importlib import resources
from typing import Any


@lru_cache(maxsize=1)
def device_types() -> dict[str, Any]:
    """The whole catalogue: {"version", "domains": {domain: type}, "fallback": type}."""
    return json.loads(resources.files(__package__).joinpath("device_types.json").read_text("utf-8"))


def device_type(domain: str, unit: str | None = None) -> dict[str, Any]:
    """The type for domain (the fallback for an unknown one), with ui_hints for unit applied."""
    catalogue = device_types()
    entry = dict(catalogue["domains"].get(domain, catalogue["fallback"]))
    overlay = entry.pop("ui_hints_by_unit", {}).get(unit or "")
    if overlay:
        entry["ui_hints"] = {**entry["ui_hints"], **overlay}
    return entry
