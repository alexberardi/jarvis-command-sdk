"""JarvisSignals — facade for emitting Signals to the Signal Bus.

The PRODUCER side of the generic Signal Bus (the consumer side is a command's
``proposable_actions`` + ``listening_signal_types``). A producer — a background
agent, a command, or any node code — emits a self-describing Signal (presence,
device state, a detected event, ...). Command-center renders live Signals into
ambient context and reasons over them to propose actions. Mirrors JarvisInbox:
the SDK provides the interface, the node runtime injects the backend via
``set_signals_backend()``.

Usage in extracted Pantry packages:
    from jarvis_command_sdk import JarvisSignals

    signals = JarvisSignals("presence_agent")   # source_agent = who's emitting
    tag = signals.emit(
        kind="presence.seen", source_key="presence:alex",
        summary="Alex is home", facts={"user": "alex"}, ttl_seconds=900,
    )
    if tag != "ok":
        ...   # any tag other than "ok" is a failure (never an exception)

Discriminated return tags (strings, never exceptions):
    "ok"          — accepted by command-center
    "no_backend"  — no backend registered (tests / container validation)
    "no_cc_url"   — service discovery returned no command-center URL
    "http_error"  — the POST to command-center failed
    "invalid"     — missing required kind/source_key, or the backend rejected it

OPEN vs DIRECTED: omit ``command`` for an open Signal (the situation matcher
picks which command, if any, fits); set ``command`` to name a command to propose
directly (bounded to what the node advertises, always a tap-to-confirm card).

The node runtime registers the real backend via ``set_signals_backend()``; when
none is registered (e.g. tests) ``emit()`` returns "no_backend" and never raises.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class SignalsBackend(ABC):
    """Abstract backend the node runtime implements (POSTs to /api/v0/signals)."""

    @abstractmethod
    def emit_signal(self, payload: dict[str, Any]) -> str: ...
    # Returns a discriminated tag: "ok" | "no_cc_url" | "http_error" | "invalid".


# Global backend instance, set by the node runtime at startup.
_backend: SignalsBackend | None = None


def set_signals_backend(backend: SignalsBackend | None) -> None:
    """Register the signals backend. Called once by the node runtime."""
    global _backend
    _backend = backend


def get_signals_backend() -> SignalsBackend | None:
    """Get the current signals backend (for internal use)."""
    return _backend


class JarvisSignals:
    """Per-producer facade for emitting Signals.

    Args:
        source_agent: identifies the producer (agent/command name); used by
            command-center for audit + rate-limit bucketing.
    """

    def __init__(self, source_agent: str) -> None:
        self._source_agent = source_agent

    def emit(
        self,
        *,
        kind: str,
        source_key: str,
        summary: str | None = None,
        facts: dict[str, Any] | None = None,
        subject: str | None = None,
        scope: dict[str, Any] | None = None,
        ttl_seconds: int | None = None,
        cacheable: bool = False,
        salience: float | None = None,
        command: str | None = None,
    ) -> str:
        """Emit a Signal. ``kind`` + ``source_key`` are required. Returns a
        discriminated tag (see module docstring); never raises."""
        if not kind or not source_key:
            return "invalid"
        if _backend is None:
            return "no_backend"

        signal: dict[str, Any] = {
            "kind": kind,
            "source_key": source_key,
            "cacheable": bool(cacheable),
            "source_agent": self._source_agent,
        }
        if subject is not None:
            signal["subject"] = subject
        if summary is not None:
            signal["summary"] = summary
        if scope is not None:
            signal["scope"] = scope
        if ttl_seconds is not None:
            signal["ttl_seconds"] = ttl_seconds
        if salience is not None:
            signal["salience"] = salience

        payload: dict[str, Any] = {"signal": signal, "data": facts}
        if command:
            payload["command"] = command
        return _backend.emit_signal(payload)

    def emit_presence(
        self,
        *,
        user_id: int,
        state: str = "home",
        room: str | None = None,
        node_id: str | None = None,
        name: str | None = None,
        ttl_seconds: int = 900,
    ) -> str:
        """Convenience: emit a presence Signal for a user.

        ``state="home"`` → ``presence.seen``; anything else → ``presence.left``.
        Keyed on ``presence:{user_id}`` so a person is one row that upserts.
        """
        scope: dict[str, Any] = {"user_id": user_id}
        if node_id:
            scope["node_id"] = node_id
        if room:
            scope["room"] = room
        kind = "presence.seen" if state == "home" else "presence.left"
        who = name or "Someone"
        summary = f"{who} is home" if state == "home" else f"{who} is {state}"
        return self.emit(
            kind=kind,
            source_key=f"presence:{user_id}",
            summary=summary,
            facts={"user": user_id, "state": state, "room": room},
            scope=scope,
            ttl_seconds=ttl_seconds,
        )
