"""Tests for the command-center HTTP backend (cc_post returns None without a backend)."""
import logging

import pytest

import jarvis_command_sdk
from jarvis_command_sdk import (
    CCHttpBackend,
    cc_post,
    get_cc_backend,
    set_cc_backend,
)
import jarvis_command_sdk.cc_http as cc_mod


class _Fake(CCHttpBackend):
    def __init__(self, reply=None) -> None:
        self.calls: list = []
        self.reply = {"ok": True} if reply is None else reply

    def post(self, path: str, json: dict):
        self.calls.append((path, json))
        return self.reply


class _Raising(CCHttpBackend):
    def post(self, path: str, json: dict):
        raise ConnectionError("cc unreachable")


@pytest.fixture(autouse=True)
def _reset_backend():
    cc_mod._backend = None
    yield
    cc_mod._backend = None


def test_no_backend_returns_none_and_logs(caplog):
    with caplog.at_level(logging.DEBUG, logger="jarvis_command_sdk.cc_http"):
        assert cc_post("/api/v0/things", {"a": 1}) is None
    assert "no command-center HTTP backend" in caplog.text
    assert "/api/v0/things" in caplog.text


def test_backend_called_and_value_passed_through():
    b = _Fake(reply={"id": 7})
    set_cc_backend(b)
    assert get_cc_backend() is b
    assert cc_post("/api/v0/things", {"a": 1}) == {"id": 7}
    assert b.calls == [("/api/v0/things", {"a": 1})]


def test_raising_backend_returns_none_and_logs(caplog):
    set_cc_backend(_Raising())
    with caplog.at_level(logging.WARNING, logger="jarvis_command_sdk.cc_http"):
        assert cc_post("/p", {}) is None
    assert "cc unreachable" in caplog.text


def test_set_none_resets():
    set_cc_backend(_Fake())
    set_cc_backend(None)
    assert get_cc_backend() is None
    assert cc_post("/p", {}) is None


def test_exported():
    for name in ("CCHttpBackend", "cc_post", "set_cc_backend", "get_cc_backend"):
        assert name in jarvis_command_sdk.__all__
