"""Logger backend — lets the node runtime supply the logger commands use.

Usage in extracted Pantry packages:
    from jarvis_command_sdk import get_logger

    log = get_logger("my_command")
    log.info("hello")

The node runtime registers a backend via ``set_logger_backend()`` (e.g. one
backed by jarvis_log_client). When none is registered (tests, Pantry container
validation), or the backend fails, ``get_logger()`` returns the stdlib
``logging.getLogger(name)``. It never raises.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

_log = logging.getLogger(__name__)


class LoggerBackend(ABC):
    """Abstract backend the node runtime implements."""

    @abstractmethod
    def get_logger(self, name: str) -> Any: ...
    # Returns a logger-like object with debug/info/warning/error/exception.


# Global backend instance, set by the node runtime at startup.
_backend: LoggerBackend | None = None


def set_logger_backend(backend: LoggerBackend | None) -> None:
    """Register the logger backend. Called once by the node runtime."""
    global _backend
    _backend = backend


def get_logger_backend() -> LoggerBackend | None:
    """Get the current logger backend (for internal use)."""
    return _backend


def get_logger(name: str) -> Any:
    """Return a logger for ``name``: the backend's, else ``logging.getLogger(name)``."""
    if _backend is not None:
        try:
            logger = _backend.get_logger(name)
            if logger is not None:
                return logger
        except Exception as e:
            _log.warning("logger backend failed for %r, using stdlib logging: %s", name, e)
    return logging.getLogger(name)
