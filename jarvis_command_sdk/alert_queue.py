"""Alert-queue backend — lets commands read the node's pending agent alerts.

Usage in extracted Pantry packages:
    from jarvis_command_sdk import alerts_flush

    for alert in alerts_flush():   # pending alerts, removed from the queue
        ...

The queue holds the ``Alert`` objects background agents produced; the host owns
it (dedupe, expiry, persistence). ``alerts_pending()`` reads without removing,
``alerts_flush()`` reads and removes, ``alerts_remove(ids)`` removes by
``Alert.id``.

The node runtime registers a backend via ``set_alert_queue_backend()``. When
none is registered (tests, Pantry container validation), or the backend raises,
every helper logs and returns a safe default ([] / 0). They never raise.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Callable, Iterable, TypeVar

from .agent import Alert

_log = logging.getLogger(__name__)

_T = TypeVar("_T")


class AlertQueueBackend(ABC):
    """Abstract backend the node runtime implements."""

    @abstractmethod
    def pending(self) -> list[Alert]: ...

    @abstractmethod
    def flush(self) -> list[Alert]: ...
    # Returns the pending alerts and removes them from the queue.

    @abstractmethod
    def remove(self, ids: list[str]) -> int: ...
    # Removes the alerts with these ids; returns how many were removed.

    @abstractmethod
    def count(self) -> int: ...


# Global backend instance, set by the node runtime at startup.
_backend: AlertQueueBackend | None = None


def set_alert_queue_backend(backend: AlertQueueBackend | None) -> None:
    """Register the alert-queue backend. Called once by the node runtime."""
    global _backend
    _backend = backend


def get_alert_queue_backend() -> AlertQueueBackend | None:
    """Get the current alert-queue backend (for internal use)."""
    return _backend


def _call(op: str, default: _T, fn: Callable[[AlertQueueBackend], _T]) -> _T:
    if _backend is None:
        _log.debug("alerts_%s: no alert-queue backend registered", op)
        return default
    try:
        return fn(_backend)
    except Exception as e:
        _log.warning("alerts_%s: alert-queue backend failed: %s", op, e)
        return default


def alerts_pending() -> list[Alert]:
    """Return the pending alerts without removing them ([] without a backend)."""
    return _call("pending", [], lambda b: b.pending())


def alerts_flush() -> list[Alert]:
    """Return the pending alerts and remove them from the queue."""
    return _call("flush", [], lambda b: b.flush())


def alerts_remove(ids: Iterable[str]) -> int:
    """Remove the alerts with these ids; return how many were removed."""
    ids = list(ids)
    return _call("remove", 0, lambda b: b.remove(ids))


def alerts_count() -> int:
    """Return how many alerts are pending (0 without a backend)."""
    return _call("count", 0, lambda b: b.count())
