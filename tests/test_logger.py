"""Tests for the logger backend (get_logger falls back to stdlib logging)."""
import logging

import pytest

import jarvis_command_sdk
from jarvis_command_sdk import (
    LoggerBackend,
    get_logger,
    get_logger_backend,
    set_logger_backend,
)
import jarvis_command_sdk.logger as logger_mod


class _FakeLogger:
    def __init__(self, name: str) -> None:
        self.name = name
        self.lines: list = []

    def info(self, msg, *args, **kwargs):
        self.lines.append(msg)


class _Fake(LoggerBackend):
    def __init__(self) -> None:
        self.names: list = []

    def get_logger(self, name: str):
        self.names.append(name)
        return _FakeLogger(name)


class _Raising(LoggerBackend):
    def get_logger(self, name: str):
        raise RuntimeError("boom")


@pytest.fixture(autouse=True)
def _reset_backend():
    logger_mod._backend = None
    yield
    logger_mod._backend = None


def test_no_backend_returns_stdlib_logger():
    log = get_logger("my_cmd")
    assert isinstance(log, logging.Logger)
    assert log.name == "my_cmd"


def test_backend_called_and_value_passed_through():
    b = _Fake()
    set_logger_backend(b)
    assert get_logger_backend() is b
    log = get_logger("weather")
    assert isinstance(log, _FakeLogger)
    assert log.name == "weather"
    assert b.names == ["weather"]


def test_raising_backend_falls_back_to_stdlib(caplog):
    set_logger_backend(_Raising())
    with caplog.at_level(logging.WARNING, logger="jarvis_command_sdk.logger"):
        log = get_logger("x")
    assert isinstance(log, logging.Logger)
    assert log.name == "x"
    assert "boom" in caplog.text


def test_backend_returning_none_falls_back_to_stdlib():
    class _NoneBackend(LoggerBackend):
        def get_logger(self, name: str):
            return None

    set_logger_backend(_NoneBackend())
    assert isinstance(get_logger("y"), logging.Logger)


def test_set_none_resets():
    set_logger_backend(_Fake())
    set_logger_backend(None)
    assert get_logger_backend() is None
    assert isinstance(get_logger("z"), logging.Logger)


def test_exported():
    for name in ("LoggerBackend", "get_logger", "set_logger_backend", "get_logger_backend"):
        assert name in jarvis_command_sdk.__all__
