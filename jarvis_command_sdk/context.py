"""Thread-safe context for the currently authenticated user + the household's
home context.

The node's command execution service sets these before calling command.execute()
(and the agent scheduler sets home_context before agent.run()). JarvisStorage reads
the user_id when accessing user-scoped secrets; commands/agents read home_context to
get household-level info (location, ...) that command-center injects — so they never
need a duplicated per-command location secret or an HTTP round-trip to jcc.
"""

from contextvars import ContextVar
from typing import Any, Dict, Optional

_current_user_id: ContextVar[int | None] = ContextVar("current_user_id", default=None)

# Household home context — a plain dict (JSON-native, survives SDK version skew;
# new keys are additive and never force a bump). v1 carries {"location": <locality>}.
# None means command-center didn't inject one (unset household / older CC) → the
# consumer falls back to its own secret.
_home_context: ContextVar[Optional[Dict[str, Any]]] = ContextVar("home_context", default=None)


def get_current_user_id() -> int | None:
    """Get the user_id of the currently executing request."""
    return _current_user_id.get()


def set_current_user_id(user_id: int | None) -> None:
    """Set the user_id for the currently executing request."""
    _current_user_id.set(user_id)


def get_home_context() -> Optional[Dict[str, Any]]:
    """The household's injected home context for the current run, or None. Agents
    (which have no RequestInformation) read household info through this."""
    return _home_context.get()


def set_home_context(value: Optional[Dict[str, Any]]) -> None:
    """Set the household home context for the current run (node runtime only)."""
    _home_context.set(value)


def home_location(home_context: Optional[Dict[str, Any]], fallback: Any = None) -> Any:
    """One-liner for consumers: the household ``location`` from a home_context dict,
    or ``fallback`` when absent/empty. Treats "" as absent so a blank setting falls
    through to the caller's own secret."""
    return (home_context or {}).get("location") or fallback
