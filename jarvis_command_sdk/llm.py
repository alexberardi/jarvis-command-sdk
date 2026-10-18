"""LLM backend — lets commands ask the node's LLM for a text reply.

Usage in extracted Pantry packages:
    from jarvis_command_sdk import llm_chat_text

    text = llm_chat_text("Tell me a short joke about cats.")
    if text is None:
        ...   # no LLM available — fall back (canned reply, etc.)

The node runtime registers a backend via ``set_llm_backend()``. When none is
registered (tests, Pantry container validation), or the backend raises,
``llm_chat_text()`` logs and returns None. It never raises.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

_log = logging.getLogger(__name__)


class LLMBackend(ABC):
    """Abstract backend the node runtime implements."""

    @abstractmethod
    def chat_text(self, prompt: str) -> str | None: ...
    # Returns the model's text reply, or None when it has none.


# Global backend instance, set by the node runtime at startup.
_backend: LLMBackend | None = None


def set_llm_backend(backend: LLMBackend | None) -> None:
    """Register the LLM backend. Called once by the node runtime."""
    global _backend
    _backend = backend


def get_llm_backend() -> LLMBackend | None:
    """Get the current LLM backend (for internal use)."""
    return _backend


def llm_chat_text(prompt: str) -> str | None:
    """Send ``prompt`` to the node's LLM and return its text reply, or None."""
    if _backend is None:
        _log.debug("llm_chat_text: no LLM backend registered")
        return None
    try:
        return _backend.chat_text(prompt)
    except Exception as e:
        _log.warning("llm_chat_text: LLM backend failed: %s", e)
        return None
