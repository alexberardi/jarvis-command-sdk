"""Command-invoker backend — lets a command run another installed command.

Usage in extracted Pantry packages:
    from jarvis_command_sdk import invoke_command

    resp = invoke_command("get_weather", request_info, city="Boston")
    if resp is None:
        ...   # no backend, unknown command, or it failed

The host looks the command up, resolves its secrets, and runs it with
``request_info`` and ``args``; callers never pass or see secrets.

The node runtime registers a backend via ``set_command_invoker_backend()``.
When none is registered (tests, Pantry container validation), or the backend
raises, ``invoke_command()`` logs and returns None. It never raises.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from .request import RequestInformation
from .response import CommandResponse

_log = logging.getLogger(__name__)


class CommandInvokerBackend(ABC):
    """Abstract backend the node runtime implements."""

    @abstractmethod
    def invoke(
        self, name: str, request_info: RequestInformation, /, **args: Any
    ) -> CommandResponse | None: ...
    # Runs command ``name`` with ``args``; returns its response, or None when
    # there is no such command.


# Global backend instance, set by the node runtime at startup.
_backend: CommandInvokerBackend | None = None


def set_command_invoker_backend(backend: CommandInvokerBackend | None) -> None:
    """Register the command-invoker backend. Called once by the node runtime."""
    global _backend
    _backend = backend


def get_command_invoker_backend() -> CommandInvokerBackend | None:
    """Get the current command-invoker backend (for internal use)."""
    return _backend


def invoke_command(
    name: str, request_info: RequestInformation, /, **args: Any
) -> CommandResponse | None:
    """Run the installed command ``name`` with ``args``; return its response or None."""
    if _backend is None:
        _log.debug("invoke_command %s: no command-invoker backend registered", name)
        return None
    try:
        return _backend.invoke(name, request_info, **args)
    except Exception as e:
        _log.warning("invoke_command %s: command-invoker backend failed: %s", name, e)
        return None
