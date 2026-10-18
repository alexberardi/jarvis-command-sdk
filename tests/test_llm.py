"""Tests for the LLM backend (llm_chat_text returns None without a backend)."""
import logging

import pytest

import jarvis_command_sdk
from jarvis_command_sdk import (
    LLMBackend,
    get_llm_backend,
    llm_chat_text,
    set_llm_backend,
)
import jarvis_command_sdk.llm as llm_mod


class _Fake(LLMBackend):
    def __init__(self, reply="a joke") -> None:
        self.prompts: list = []
        self.reply = reply

    def chat_text(self, prompt: str):
        self.prompts.append(prompt)
        return self.reply


class _Raising(LLMBackend):
    def chat_text(self, prompt: str):
        raise RuntimeError("llm down")


@pytest.fixture(autouse=True)
def _reset_backend():
    llm_mod._backend = None
    yield
    llm_mod._backend = None


def test_no_backend_returns_none_and_logs(caplog):
    with caplog.at_level(logging.DEBUG, logger="jarvis_command_sdk.llm"):
        assert llm_chat_text("tell me a joke") is None
    assert "no LLM backend" in caplog.text


def test_backend_called_and_value_passed_through():
    b = _Fake()
    set_llm_backend(b)
    assert get_llm_backend() is b
    assert llm_chat_text("tell me a joke") == "a joke"
    assert b.prompts == ["tell me a joke"]


def test_backend_none_reply_passed_through():
    set_llm_backend(_Fake(reply=None))
    assert llm_chat_text("p") is None


def test_raising_backend_returns_none_and_logs(caplog):
    set_llm_backend(_Raising())
    with caplog.at_level(logging.WARNING, logger="jarvis_command_sdk.llm"):
        assert llm_chat_text("p") is None
    assert "llm down" in caplog.text


def test_set_none_resets():
    set_llm_backend(_Fake())
    set_llm_backend(None)
    assert get_llm_backend() is None
    assert llm_chat_text("p") is None


def test_exported():
    for name in ("LLMBackend", "llm_chat_text", "set_llm_backend", "get_llm_backend"):
        assert name in jarvis_command_sdk.__all__
