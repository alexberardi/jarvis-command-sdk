"""Household home_context: the RequestInformation field (commands), the ContextVar
(agents), and the home_location convenience — the generic replacement for a
per-command location secret / a jcc round-trip.
"""
from jarvis_command_sdk import (
    RequestInformation,
    get_home_context,
    home_location,
    set_home_context,
)


def test_request_information_home_context_defaults_none():
    r = RequestInformation(voice_command="x", conversation_id="c")
    assert r.home_context is None  # absent when CC didn't inject one → command falls back


def test_request_information_carries_home_context():
    r = RequestInformation(voice_command="x", conversation_id="c",
                           home_context={"location": "Springfield, IL 62704"})
    assert r.home_context["location"] == "Springfield, IL 62704"


def test_home_context_contextvar_for_agents():
    set_home_context({"location": "Miami, FL"})
    try:
        assert get_home_context() == {"location": "Miami, FL"}
    finally:
        set_home_context(None)
    assert get_home_context() is None


def test_home_location_helper():
    assert home_location({"location": "Chicago, IL"}) == "Chicago, IL"
    assert home_location(None) is None
    assert home_location({}, "fallback") == "fallback"
    assert home_location({"location": ""}, "fallback") == "fallback"   # blank → fallback, not ""
