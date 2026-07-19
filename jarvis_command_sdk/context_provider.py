"""Context-provider capability — typed context queries a command can answer.

A command that holds live data (calendar events, device state, inventories)
can declare *context operations*: typed, read-only queries that server-side
planners (jarvis-command-center) invoke at PLAN time over the node's generic
context MQTT handler. First consumer: the phone-call plan-draft step asking
the calendar command for ``availability`` so the confirm card carries a real
constraint envelope instead of a fill-me-in placeholder.

Design rules (phone-calls PRD, cross-agent-context section):
- Plan-time only. Context ops are never exposed as live tools inside a
  phone call or any other untrusted-counterparty loop.
- The provider stays node-side: credentials remain node-stored user
  secrets; the node is the LAN edge.
- Read-only by contract. An op must not mutate command state; mutations
  belong to commands/callbacks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class ContextOperation:
    """One typed context query a command can answer.

    params_schema is a flat {param_name: {"type": str, "required": bool,
    "description": str}} mapping — deliberately simpler than JSON Schema;
    the node runtime validates required params before dispatching.
    """

    name: str
    description: str
    params_schema: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "params_schema": self.params_schema,
        }

    def missing_required(self, params: Dict[str, Any]) -> list[str]:
        """Names of required params absent from ``params``."""
        return [
            name
            for name, spec in self.params_schema.items()
            if spec.get("required") and name not in params
        ]


@dataclass
class ContextResult:
    """What a context operation returns to the server-side planner.

    ``data`` is op-specific and must be JSON-serializable — it crosses MQTT
    to command-center. ``error`` set means the op could not be answered
    (upstream unreachable, not configured); planners degrade gracefully
    rather than blocking, so an error is never fatal to the caller.
    """

    data: Dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    def to_dict(self) -> Dict[str, Any]:
        return {"ok": self.ok, "data": self.data, "error": self.error}

    @classmethod
    def failed(cls, error: str) -> "ContextResult":
        return cls(data={}, error=error)
