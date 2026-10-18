"""Tests for the audio-control backend (helpers return safe defaults without a backend)."""
import logging

import pytest

import jarvis_command_sdk
from jarvis_command_sdk import (
    AudioControlBackend,
    audio_adjust_volume_percent,
    audio_set_muted,
    audio_set_volume_percent,
    audio_speak,
    get_audio_control_backend,
    set_audio_control_backend,
)
import jarvis_command_sdk.audio_control as audio_mod


class _Fake(AudioControlBackend):
    def __init__(self) -> None:
        self.calls: list = []

    def set_volume_percent(self, percent):
        self.calls.append(("set_volume_percent", percent))
        return True

    def adjust_volume_percent(self, delta):
        self.calls.append(("adjust_volume_percent", delta))
        return 60

    def set_muted(self, muted):
        self.calls.append(("set_muted", muted))
        return True

    def speak(self, text):
        self.calls.append(("speak", text))
        return True


class _Raising(AudioControlBackend):
    def set_volume_percent(self, percent):
        raise RuntimeError("audio down")

    def adjust_volume_percent(self, delta):
        raise RuntimeError("audio down")

    def set_muted(self, muted):
        raise RuntimeError("audio down")

    def speak(self, text):
        raise RuntimeError("audio down")


_DEFAULTS = [
    (lambda: audio_set_volume_percent(50), False),
    (lambda: audio_adjust_volume_percent(10), None),
    (lambda: audio_set_muted(True), False),
    (lambda: audio_speak("hello"), False),
]


@pytest.fixture(autouse=True)
def _reset_backend():
    audio_mod._backend = None
    yield
    audio_mod._backend = None


@pytest.mark.parametrize("call,default", _DEFAULTS)
def test_no_backend_returns_default_and_logs(caplog, call, default):
    with caplog.at_level(logging.DEBUG, logger="jarvis_command_sdk.audio_control"):
        assert call() == default
    assert "no audio-control backend" in caplog.text


@pytest.mark.parametrize("call,default", _DEFAULTS)
def test_raising_backend_returns_default_and_logs(caplog, call, default):
    set_audio_control_backend(_Raising())
    with caplog.at_level(logging.WARNING, logger="jarvis_command_sdk.audio_control"):
        assert call() == default
    assert "audio down" in caplog.text


def test_backend_called_and_values_passed_through():
    b = _Fake()
    set_audio_control_backend(b)
    assert get_audio_control_backend() is b
    assert audio_set_volume_percent(50) is True
    assert audio_adjust_volume_percent(-10) == 60
    assert audio_set_muted(False) is True
    assert audio_speak("Timer done") is True
    assert b.calls == [
        ("set_volume_percent", 50),
        ("adjust_volume_percent", -10),
        ("set_muted", False),
        ("speak", "Timer done"),
    ]


def test_set_none_resets():
    set_audio_control_backend(_Fake())
    set_audio_control_backend(None)
    assert get_audio_control_backend() is None
    assert audio_speak("hi") is False


def test_exported():
    for name in (
        "AudioControlBackend", "set_audio_control_backend", "get_audio_control_backend",
        "audio_set_volume_percent", "audio_adjust_volume_percent",
        "audio_set_muted", "audio_speak",
    ):
        assert name in jarvis_command_sdk.__all__
