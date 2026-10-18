"""Tests for the timer backend (helpers return safe defaults without a backend)."""
import logging

import pytest

import jarvis_command_sdk
from jarvis_command_sdk import (
    TimerBackend,
    get_timer_backend,
    set_timer_backend,
    timer_cancel,
    timer_clear_all,
    timer_find_by_label,
    timer_get,
    timer_list_active,
    timer_set,
)
import jarvis_command_sdk.timer as timer_mod

_TIMER = {"timer_id": "t1", "label": "pasta", "duration_seconds": 600, "remaining_seconds": 590}


class _Fake(TimerBackend):
    def __init__(self) -> None:
        self.calls: list = []

    def set(self, seconds, label=None):
        self.calls.append(("set", seconds, label))
        return "t1"

    def cancel(self, timer_id):
        self.calls.append(("cancel", timer_id))
        return True

    def list_active(self):
        self.calls.append(("list_active",))
        return [_TIMER]

    def get(self, timer_id):
        self.calls.append(("get", timer_id))
        return _TIMER

    def find_by_label(self, label):
        self.calls.append(("find_by_label", label))
        return "t1"

    def clear_all(self):
        self.calls.append(("clear_all",))
        return 2


class _Raising(TimerBackend):
    def set(self, seconds, label=None):
        raise RuntimeError("timer down")

    def cancel(self, timer_id):
        raise RuntimeError("timer down")

    def list_active(self):
        raise RuntimeError("timer down")

    def get(self, timer_id):
        raise RuntimeError("timer down")

    def find_by_label(self, label):
        raise RuntimeError("timer down")

    def clear_all(self):
        raise RuntimeError("timer down")


_DEFAULTS = [
    (lambda: timer_set(60, "eggs"), None),
    (lambda: timer_cancel("t1"), False),
    (lambda: timer_list_active(), []),
    (lambda: timer_get("t1"), None),
    (lambda: timer_find_by_label("eggs"), None),
    (lambda: timer_clear_all(), 0),
]


@pytest.fixture(autouse=True)
def _reset_backend():
    timer_mod._backend = None
    yield
    timer_mod._backend = None


@pytest.mark.parametrize("call,default", _DEFAULTS)
def test_no_backend_returns_default_and_logs(caplog, call, default):
    with caplog.at_level(logging.DEBUG, logger="jarvis_command_sdk.timer"):
        assert call() == default
    assert "no timer backend" in caplog.text


@pytest.mark.parametrize("call,default", _DEFAULTS)
def test_raising_backend_returns_default_and_logs(caplog, call, default):
    set_timer_backend(_Raising())
    with caplog.at_level(logging.WARNING, logger="jarvis_command_sdk.timer"):
        assert call() == default
    assert "timer down" in caplog.text


def test_backend_called_and_values_passed_through():
    b = _Fake()
    set_timer_backend(b)
    assert get_timer_backend() is b
    assert timer_set(600, "pasta") == "t1"
    assert timer_set(30) == "t1"
    assert timer_cancel("t1") is True
    assert timer_list_active() == [_TIMER]
    assert timer_get("t1") == _TIMER
    assert timer_find_by_label("pasta") == "t1"
    assert timer_clear_all() == 2
    assert b.calls == [
        ("set", 600, "pasta"),
        ("set", 30, None),
        ("cancel", "t1"),
        ("list_active",),
        ("get", "t1"),
        ("find_by_label", "pasta"),
        ("clear_all",),
    ]


def test_list_active_returns_a_new_list_each_call():
    timer_list_active().append("x")
    assert timer_list_active() == []


def test_set_none_resets():
    set_timer_backend(_Fake())
    set_timer_backend(None)
    assert get_timer_backend() is None
    assert timer_set(60) is None


def test_exported():
    for name in (
        "TimerBackend", "set_timer_backend", "get_timer_backend",
        "timer_set", "timer_cancel", "timer_list_active", "timer_get",
        "timer_find_by_label", "timer_clear_all",
    ):
        assert name in jarvis_command_sdk.__all__
