"""Audio-control backend — lets commands change the node's volume and speak.

Usage in extracted Pantry packages:
    from jarvis_command_sdk import audio_adjust_volume_percent, audio_speak

    level = audio_adjust_volume_percent(+10)
    if level is None:
        ...   # no audio backend, or it failed
    audio_speak("Volume up.")

The node runtime registers a backend via ``set_audio_control_backend()``. When
none is registered (tests, Pantry container validation), or the backend raises,
every helper logs and returns a safe default (False / None). They never raise.
Percentages are 0–100; clamping is the host's job.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Callable, TypeVar

_log = logging.getLogger(__name__)

_T = TypeVar("_T")


class AudioControlBackend(ABC):
    """Abstract backend the node runtime implements."""

    @abstractmethod
    def set_volume_percent(self, percent: int) -> bool: ...

    @abstractmethod
    def adjust_volume_percent(self, delta: int) -> int | None: ...
    # Moves the volume by ``delta`` points; returns the new level, or None.

    @abstractmethod
    def set_muted(self, muted: bool) -> bool: ...

    @abstractmethod
    def speak(self, text: str) -> bool: ...
    # Speaks ``text`` through the node's TTS; True once it was queued/played.


# Global backend instance, set by the node runtime at startup.
_backend: AudioControlBackend | None = None


def set_audio_control_backend(backend: AudioControlBackend | None) -> None:
    """Register the audio-control backend. Called once by the node runtime."""
    global _backend
    _backend = backend


def get_audio_control_backend() -> AudioControlBackend | None:
    """Get the current audio-control backend (for internal use)."""
    return _backend


def _call(op: str, default: _T, fn: Callable[[AudioControlBackend], _T]) -> _T:
    if _backend is None:
        _log.debug("audio_%s: no audio-control backend registered", op)
        return default
    try:
        return fn(_backend)
    except Exception as e:
        _log.warning("audio_%s: audio-control backend failed: %s", op, e)
        return default


def audio_set_volume_percent(percent: int) -> bool:
    """Set the node's volume to ``percent`` (0–100); True on success."""
    return _call("set_volume_percent", False, lambda b: b.set_volume_percent(percent))


def audio_adjust_volume_percent(delta: int) -> int | None:
    """Move the volume by ``delta`` points; return the new level, or None."""
    return _call("adjust_volume_percent", None, lambda b: b.adjust_volume_percent(delta))


def audio_set_muted(muted: bool) -> bool:
    """Mute or unmute the node; True on success."""
    return _call("set_muted", False, lambda b: b.set_muted(muted))


def audio_speak(text: str) -> bool:
    """Speak ``text`` on the node; True on success."""
    return _call("speak", False, lambda b: b.speak(text))
