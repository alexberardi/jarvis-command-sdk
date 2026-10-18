"""Tests for the alert-queue backend (helpers return safe defaults without a backend)."""
import logging

import pytest

import jarvis_command_sdk
from jarvis_command_sdk import (
    Alert,
    AlertQueueBackend,
    alerts_count,
    alerts_flush,
    alerts_pending,
    alerts_remove,
    get_alert_queue_backend,
    set_alert_queue_backend,
)
import jarvis_command_sdk.alert_queue as aq_mod

_ALERT = Alert(source_agent="news", title="Storm", summary="Storm warning tonight")


class _Fake(AlertQueueBackend):
    def __init__(self) -> None:
        self.calls: list = []

    def pending(self):
        self.calls.append(("pending",))
        return [_ALERT]

    def flush(self):
        self.calls.append(("flush",))
        return [_ALERT]

    def remove(self, ids):
        self.calls.append(("remove", ids))
        return len(ids)

    def count(self):
        self.calls.append(("count",))
        return 1


class _Raising(AlertQueueBackend):
    def pending(self):
        raise RuntimeError("queue down")

    def flush(self):
        raise RuntimeError("queue down")

    def remove(self, ids):
        raise RuntimeError("queue down")

    def count(self):
        raise RuntimeError("queue down")


_DEFAULTS = [
    (lambda: alerts_pending(), []),
    (lambda: alerts_flush(), []),
    (lambda: alerts_remove(["a"]), 0),
    (lambda: alerts_count(), 0),
]


@pytest.fixture(autouse=True)
def _reset_backend():
    aq_mod._backend = None
    yield
    aq_mod._backend = None


@pytest.mark.parametrize("call,default", _DEFAULTS)
def test_no_backend_returns_default_and_logs(caplog, call, default):
    with caplog.at_level(logging.DEBUG, logger="jarvis_command_sdk.alert_queue"):
        assert call() == default
    assert "no alert-queue backend" in caplog.text


@pytest.mark.parametrize("call,default", _DEFAULTS)
def test_raising_backend_returns_default_and_logs(caplog, call, default):
    set_alert_queue_backend(_Raising())
    with caplog.at_level(logging.WARNING, logger="jarvis_command_sdk.alert_queue"):
        assert call() == default
    assert "queue down" in caplog.text


def test_backend_called_and_values_passed_through():
    b = _Fake()
    set_alert_queue_backend(b)
    assert get_alert_queue_backend() is b
    assert alerts_pending() == [_ALERT]
    assert alerts_flush() == [_ALERT]
    assert alerts_count() == 1
    assert alerts_remove(["a", "b"]) == 2
    assert b.calls == [("pending",), ("flush",), ("count",), ("remove", ["a", "b"])]


def test_remove_materializes_iterables():
    b = _Fake()
    set_alert_queue_backend(b)
    assert alerts_remove(i for i in ("a", "b")) == 2
    assert b.calls == [("remove", ["a", "b"])]


def test_set_none_resets():
    set_alert_queue_backend(_Fake())
    set_alert_queue_backend(None)
    assert get_alert_queue_backend() is None
    assert alerts_count() == 0


def test_exported():
    for name in (
        "AlertQueueBackend", "set_alert_queue_backend", "get_alert_queue_backend",
        "alerts_pending", "alerts_flush", "alerts_remove", "alerts_count",
    ):
        assert name in jarvis_command_sdk.__all__
