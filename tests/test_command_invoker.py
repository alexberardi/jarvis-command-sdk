"""Tests for the command-invoker backend (invoke_command returns None without a backend)."""
import logging

import pytest

import jarvis_command_sdk
from jarvis_command_sdk import (
    CommandInvokerBackend,
    CommandResponse,
    RequestInformation,
    get_command_invoker_backend,
    invoke_command,
    set_command_invoker_backend,
)
import jarvis_command_sdk.command_invoker as ci_mod

_REQ = RequestInformation(voice_command="what's the weather", conversation_id="c1")
_RESP = CommandResponse.success_response(context_data={"temp": 70})


class _Fake(CommandInvokerBackend):
    def __init__(self, reply=_RESP) -> None:
        self.calls: list = []
        self.reply = reply

    def invoke(self, name, request_info, /, **args):
        self.calls.append((name, request_info, args))
        return self.reply


class _Raising(CommandInvokerBackend):
    def invoke(self, name, request_info, /, **args):
        raise RuntimeError("invoker down")


@pytest.fixture(autouse=True)
def _reset_backend():
    ci_mod._backend = None
    yield
    ci_mod._backend = None


def test_no_backend_returns_none_and_logs(caplog):
    with caplog.at_level(logging.DEBUG, logger="jarvis_command_sdk.command_invoker"):
        assert invoke_command("get_weather", _REQ, city="Boston") is None
    assert "no command-invoker backend" in caplog.text


def test_backend_called_and_value_passed_through():
    b = _Fake()
    set_command_invoker_backend(b)
    assert get_command_invoker_backend() is b
    assert invoke_command("get_weather", _REQ, city="Boston", days=2) is _RESP
    assert b.calls == [("get_weather", _REQ, {"city": "Boston", "days": 2})]


def test_args_named_like_the_positionals_pass_through():
    b = _Fake()
    set_command_invoker_backend(b)
    invoke_command("set_timer", _REQ, name="pasta", request_info="x")
    assert b.calls == [("set_timer", _REQ, {"name": "pasta", "request_info": "x"})]


def test_backend_none_reply_passed_through():
    set_command_invoker_backend(_Fake(reply=None))
    assert invoke_command("get_weather", _REQ) is None


def test_raising_backend_returns_none_and_logs(caplog):
    set_command_invoker_backend(_Raising())
    with caplog.at_level(logging.WARNING, logger="jarvis_command_sdk.command_invoker"):
        assert invoke_command("get_weather", _REQ) is None
    assert "invoker down" in caplog.text
    assert "get_weather" in caplog.text


def test_set_none_resets():
    set_command_invoker_backend(_Fake())
    set_command_invoker_backend(None)
    assert get_command_invoker_backend() is None
    assert invoke_command("get_weather", _REQ) is None


def test_exported():
    for name in (
        "CommandInvokerBackend", "invoke_command",
        "set_command_invoker_backend", "get_command_invoker_backend",
    ):
        assert name in jarvis_command_sdk.__all__
