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
from typing import Any, Dict, Iterable


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


# --- call_context: what a command shares with a phone call's plan ------------------------
#
# A well-known operation the server's call plan asks every command that declares it, on every
# node of the household, while the plan is made (never during the call). The fields go into the
# plan's brief, which the user sees on the confirm card and can edit before the call. A command
# says what it shares, for the user, with ``IJarvisCommand.call_context_description``; the
# household can switch a command out of sharing ("Share with phone calls" in the app).

CALL_CONTEXT = "call_context"
"""The well-known context operation a phone call's plan asks for."""

TIER_STATE = "state"
"""A detail the assistant may state on the call when it helps (a preferred hygienist)."""

TIER_IF_ASKED = "if_asked"
"""A detail the assistant gives only when the business asks for it (a member ID)."""


@dataclass
class CallContextField:
    """One detail a command shares with a call plan.

    ``key`` identifies it (the first command to share a key wins, and the user's own saved
    call details win over every command); ``label`` is how the brief names it; ``tier`` is
    ``TIER_IF_ASKED`` (default: given only when asked, and guarded on the call) or
    ``TIER_STATE``.
    """

    key: str
    label: str
    value: str
    tier: str = TIER_IF_ASKED
    category: str = "general"

    def to_dict(self) -> Dict[str, Any]:
        return {"key": self.key, "label": self.label, "value": self.value,
                "tier": self.tier, "category": self.category}


def call_context_operation(description: str = "Details for a phone call made on the user's behalf") -> ContextOperation:
    """The ``call_context`` operation to list in ``context_operations``. Its params are the
    business being called and the call's goal, so a command can share only what fits."""
    return ContextOperation(
        name=CALL_CONTEXT,
        description=description,
        params_schema={
            "business": {"type": "string", "required": False, "description": "The business being called"},
            "goal": {"type": "string", "required": False, "description": "What the call is for"},
        },
    )


def call_context_result(fields: Iterable[CallContextField]) -> ContextResult:
    """The answer to ``call_context``: the fields to share (none is a fine answer)."""
    return ContextResult(data={"fields": [f.to_dict() for f in fields]})
