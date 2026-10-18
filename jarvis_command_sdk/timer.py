"""Timer backend — lets commands set and manage the node's timers.

Usage in extracted Pantry packages:
    from jarvis_command_sdk import timer_set, timer_cancel, timer_find_by_label

    timer_id = timer_set(600, label="pasta")
    if timer_id is None:
        ...   # no timer backend — tell the user timers aren't available

The **host** owns the timers: it schedules them, fires them, and speaks the
expiry announcement. Commands never start threads or sleep for a timer; they
call these helpers and return.

A timer dict (``timer_list_active()``, ``timer_get()``) is whatever the host
reports; the SDK passes it through untouched.

The node runtime registers a backend via ``set_timer_backend()``. When none is
registered (tests, Pantry container validation), or the backend raises, every
helper logs and returns a safe default (None / False / [] / 0). They never raise.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, TypeVar

_log = logging.getLogger(__name__)

_T = TypeVar("_T")


class TimerBackend(ABC):
    """Abstract backend the node runtime implements."""

    @abstractmethod
    def set(self, seconds: int, label: str | None = None) -> str | None: ...
    # Starts a timer; returns its id, or None if it could not be set.

    @abstractmethod
    def cancel(self, timer_id: str) -> bool: ...
    # Cancels a timer; False when there is no such timer.

    @abstractmethod
    def list_active(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    def get(self, timer_id: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def find_by_label(self, label: str) -> str | None: ...
    # Returns the id of the active timer with this label, or None.

    @abstractmethod
    def clear_all(self) -> int: ...
    # Cancels every timer; returns how many were cancelled.


# Global backend instance, set by the node runtime at startup.
_backend: TimerBackend | None = None


def set_timer_backend(backend: TimerBackend | None) -> None:
    """Register the timer backend. Called once by the node runtime."""
    global _backend
    _backend = backend


def get_timer_backend() -> TimerBackend | None:
    """Get the current timer backend (for internal use)."""
    return _backend


def _call(op: str, default: _T, fn: Callable[[TimerBackend], _T]) -> _T:
    if _backend is None:
        _log.debug("timer_%s: no timer backend registered", op)
        return default
    try:
        return fn(_backend)
    except Exception as e:
        _log.warning("timer_%s: timer backend failed: %s", op, e)
        return default


def timer_set(seconds: int, label: str | None = None) -> str | None:
    """Start a timer for ``seconds``; return its id, or None."""
    return _call("set", None, lambda b: b.set(seconds, label))


def timer_cancel(timer_id: str) -> bool:
    """Cancel a timer; return True if one was cancelled."""
    return _call("cancel", False, lambda b: b.cancel(timer_id))


def timer_list_active() -> list[dict[str, Any]]:
    """Return the active timers ([] without a backend)."""
    return _call("list_active", [], lambda b: b.list_active())


def timer_get(timer_id: str) -> dict[str, Any] | None:
    """Return one timer, or None."""
    return _call("get", None, lambda b: b.get(timer_id))


def timer_find_by_label(label: str) -> str | None:
    """Return the id of the active timer labelled ``label``, or None."""
    return _call("find_by_label", None, lambda b: b.find_by_label(label))


def timer_clear_all() -> int:
    """Cancel every timer; return how many were cancelled (0 without a backend)."""
    return _call("clear_all", 0, lambda b: b.clear_all())
