"""Tests for JarvisSignals — the producer facade for the Signal Bus."""
import pytest

from jarvis_command_sdk import (
    JarvisSignals,
    SignalsBackend,
    set_signals_backend,
    get_signals_backend,
)
import jarvis_command_sdk.signals as signals_mod


class _Fake(SignalsBackend):
    def __init__(self) -> None:
        self.payloads: list = []

    def emit_signal(self, payload: dict) -> str:
        self.payloads.append(payload)
        return "ok"


@pytest.fixture(autouse=True)
def _reset_backend():
    signals_mod._backend = None
    yield
    signals_mod._backend = None


def test_no_backend_returns_tag():
    assert JarvisSignals("a").emit(kind="k", source_key="s") == "no_backend"


def test_invalid_missing_required():
    set_signals_backend(_Fake())
    assert JarvisSignals("a").emit(kind="", source_key="s") == "invalid"
    assert JarvisSignals("a").emit(kind="k", source_key="") == "invalid"


def test_set_get_backend():
    b = _Fake()
    set_signals_backend(b)
    assert get_signals_backend() is b


def test_emit_open_builds_payload():
    b = _Fake()
    set_signals_backend(b)
    tag = JarvisSignals("presence_agent").emit(
        kind="presence.seen", source_key="presence:1", summary="Alex is home",
        facts={"user": "alex"}, scope={"user_id": 1}, ttl_seconds=900,
    )
    assert tag == "ok"
    p = b.payloads[0]
    assert p["signal"]["kind"] == "presence.seen"
    assert p["signal"]["source_key"] == "presence:1"
    assert p["signal"]["source_agent"] == "presence_agent"   # from the producer name
    assert p["signal"]["ttl_seconds"] == 900
    assert p["signal"]["scope"] == {"user_id": 1}
    assert p["data"] == {"user": "alex"}
    assert "command" not in p                                 # open mode


def test_emit_directed_sets_command():
    b = _Fake()
    set_signals_backend(b)
    JarvisSignals("email").emit(
        kind="appt.detected", source_key="appt:1", command="add_event",
        facts={"title": "Dentist"},
    )
    p = b.payloads[0]
    assert p["command"] == "add_event"
    assert p["data"] == {"title": "Dentist"}


def test_emit_presence_home_and_away():
    b = _Fake()
    set_signals_backend(b)
    JarvisSignals("geo").emit_presence(user_id=7, state="home", node_id="n1", name="Alex")
    JarvisSignals("geo").emit_presence(user_id=7, state="away", name="Alex")
    home, away = b.payloads[0]["signal"], b.payloads[1]["signal"]
    assert home["kind"] == "presence.seen" and home["source_key"] == "presence:7"
    assert home["scope"]["node_id"] == "n1"
    assert away["kind"] == "presence.left"
    assert "away" in away["summary"]
