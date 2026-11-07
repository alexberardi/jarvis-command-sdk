"""Tests for IJarvisMusicCommand, PlaybackState and the playback backend."""
from typing import Any

import pytest

from jarvis_command_sdk import (
    ARTWORK_MAX_BYTES,
    IJarvisCommand,
    IJarvisMusicCommand,
    PlaybackArtwork,
    PlaybackBackend,
    PlaybackState,
    generate_spec,
    get_playback_backend,
    set_playback_backend,
)


class _Radio(IJarvisMusicCommand):
    """A minimal music command over a fake player."""

    def __init__(self) -> None:
        self.playing = True
        self.raise_on_status = False

    command_name = "radio"
    description = "Plays the radio"
    parameters: list = []
    required_secrets: list = []
    keywords = ["radio"]

    def generate_prompt_examples(self):
        return []

    def generate_adapter_examples(self):
        return []

    def run(self, request_info, **kwargs):
        return None

    @property
    def playback_binary(self) -> str:
        return "mpv"

    def playback_status(self):
        if self.raise_on_status:
            raise RuntimeError("player gone")
        if not self.playing:
            return None
        return PlaybackState(state="playing", media_title="Jazz FM", actions=("pause",))

    def playback_control(self, action: str, **args: Any):
        if action == "pause":
            self.playing = False
        return self.playback_status()


class _Backend(PlaybackBackend):
    def __init__(self, fail: bool = False) -> None:
        self.reports: list = []
        self.fail = fail

    def report(self, command_name, state):
        if self.fail:
            raise RuntimeError("node gone")
        self.reports.append((command_name, state))
        return True


@pytest.fixture(autouse=True)
def _no_backend():
    set_playback_backend(None)
    yield
    set_playback_backend(None)


def test_music_command_is_a_regular_command():
    radio = _Radio()
    assert isinstance(radio, IJarvisCommand)
    assert issubclass(_Radio, IJarvisCommand)


def test_playback_methods_are_required():
    class Missing(IJarvisMusicCommand):
        command_name = "x"
        description = "x"
        parameters: list = []
        required_secrets: list = []
        keywords: list = []

        def generate_prompt_examples(self):
            return []

        def generate_adapter_examples(self):
            return []

        def run(self, request_info, **kwargs):
            return None

    with pytest.raises(TypeError):
        Missing()


def test_takeover_name_follows_playback_binary():
    """Sidecars that predate IJarvisMusicCommand read takes_over_playback_binary."""
    assert _Radio().takes_over_playback_binary == "mpv"


def test_artwork_defaults_to_none():
    assert _Radio().playback_artwork() is None


def test_report_without_backend_is_false():
    assert _Radio().report() is False


def test_report_reads_status_when_given_none():
    backend = _Backend()
    set_playback_backend(backend)
    radio = _Radio()

    assert radio.report() is True
    assert backend.reports == [("radio", {
        "state": "playing", "media_title": "Jazz FM", "media_artist": "", "media_album": "",
        "context": "", "actions": ["pause"],
    })]

    radio.playback_control("pause")
    assert radio.report() is True
    assert backend.reports[-1] == ("radio", None)


def test_report_sends_a_given_state():
    backend = _Backend()
    set_playback_backend(backend)
    assert _Radio().report(PlaybackState(state="paused")) is True
    assert backend.reports[-1][1]["state"] == "paused"


def test_report_never_raises():
    set_playback_backend(_Backend(fail=True))
    assert _Radio().report() is False

    set_playback_backend(_Backend())
    radio = _Radio()
    radio.raise_on_status = True
    assert radio.report() is False


def test_backend_registry():
    backend = _Backend()
    set_playback_backend(backend)
    assert get_playback_backend() is backend


def test_state_rejects_unknown_state_and_actions():
    with pytest.raises(ValueError):
        PlaybackState(state="buffering")
    with pytest.raises(ValueError):
        PlaybackState(state="playing", actions=("pause", "rewind"))
    with pytest.raises(ValueError):
        PlaybackState(state="playing", repeat="sometimes")


def test_state_clamps_volume_and_dedupes_actions():
    assert PlaybackState(state="playing", volume=150).volume == 100
    assert PlaybackState(state="playing", volume=-5).volume == 0
    assert PlaybackState(state="playing", actions=["pause", "next", "pause"]).actions == ("pause", "next")


def test_state_to_dict_omits_unset_optionals():
    full = PlaybackState(
        state="playing", media_title="t", media_artist="a", media_album="b", position=12.5,
        duration=200.0, volume=40, actions=("pause", "seek"), shuffle=False, repeat="one",
        liked=True, context="Road trip",
    ).to_dict()
    assert full == {
        "state": "playing", "media_title": "t", "media_artist": "a", "media_album": "b",
        "context": "Road trip", "actions": ["pause", "seek"], "position": 12.5,
        "duration": 200.0, "volume": 40, "shuffle": False, "repeat": "one", "liked": True,
    }
    assert "shuffle" not in PlaybackState(state="idle").to_dict()


def test_artwork_checks_type_and_size():
    art = PlaybackArtwork(data=b"\xff\xd8\xff", mime="image/jpeg")
    assert "\\xff" not in repr(art)
    with pytest.raises(ValueError):
        PlaybackArtwork(data=b"x", mime="image/gif")
    with pytest.raises(ValueError):
        PlaybackArtwork(data=b"x" * (ARTWORK_MAX_BYTES + 1), mime="image/png")


def test_forge_spec_lists_the_music_command():
    text = repr(generate_spec())
    assert "IJarvisMusicCommand" in text
    assert "PlaybackState" in text
