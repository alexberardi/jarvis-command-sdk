"""Command-center HTTP backend — lets commands POST to command-center.

Usage in extracted Pantry packages:
    from jarvis_command_sdk import cc_post

    resp = cc_post("/api/v0/some/endpoint", {"key": "value"})
    if resp is None:
        ...   # no backend, or the request failed

The node runtime registers a backend via ``set_cc_backend()`` that resolves the
command-center URL and authenticates as the node. When none is registered
(tests, Pantry container validation), or the backend raises, ``cc_post()``
logs and returns None. It never raises.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

_log = logging.getLogger(__name__)


class CCHttpBackend(ABC):
    """Abstract backend the node runtime implements."""

    @abstractmethod
    def post(self, path: str, json: dict[str, Any]) -> dict[str, Any] | None: ...
    # POSTs ``json`` to command-center at ``path``; returns the decoded JSON
    # response, or None on failure.


# Global backend instance, set by the node runtime at startup.
_backend: CCHttpBackend | None = None


def set_cc_backend(backend: CCHttpBackend | None) -> None:
    """Register the command-center HTTP backend. Called once by the node runtime."""
    global _backend
    _backend = backend


def get_cc_backend() -> CCHttpBackend | None:
    """Get the current command-center HTTP backend (for internal use)."""
    return _backend


def cc_post(path: str, json: dict[str, Any]) -> dict[str, Any] | None:
    """POST ``json`` to command-center at ``path``; return the response or None."""
    if _backend is None:
        _log.debug("cc_post %s: no command-center HTTP backend registered", path)
        return None
    try:
        return _backend.post(path, json)
    except Exception as e:
        _log.warning("cc_post %s: command-center HTTP backend failed: %s", path, e)
        return None
