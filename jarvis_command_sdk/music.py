"""IJarvisMusicCommand — a command that plays audio and reports what is playing.

A music package subclasses ``IJarvisMusicCommand`` instead of ``IJarvisCommand``. It is still a
regular command (its own parameters, ``run()``, secrets), and every host that loads commands
loads it. On top, it tells the node what it is playing and takes the node's transport controls,
so the display, the mobile app and the built-in "pause the music" commands work for every
provider the same way (jarvis-server docs/agent/PLAYBACK.md).

Usage in extracted Pantry packages:
    from jarvis_command_sdk import IJarvisMusicCommand, PlaybackState

    class RadioCommand(IJarvisMusicCommand):
        @property
        def playback_binary(self) -> str:
            return "mpv"

        def playback_status(self) -> PlaybackState | None:
            if not self._player.running:
                return None
            return PlaybackState(state="playing", media_title=self._station,
                                 actions=("pause", "play", "volume"))

        def playback_control(self, action: str, **args) -> PlaybackState | None:
            if action == "pause":
                self._player.pause()
            ...
            return self.playback_status()   # read back from the player, never assumed

    # when the player changes on its own (a new track, the phone pausing it):
    self.report()

The rule that keeps every screen in sync: ``playback_status()`` reads the player. It never
returns what a control asked for, only what the player says now.

The node runtime registers a backend via ``set_playback_backend()``. With none registered (tests,
Pantry container validation), or a backend that raises, ``report()`` logs and returns False. It
never raises.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from .command import IJarvisCommand

_log = logging.getLogger(__name__)

# The states a source can report (the device catalogue's media_player values).
PLAYBACK_STATES: tuple[str, ...] = ("playing", "paused", "idle")

# The closed set of transport actions. Clients show only the ones a source lists.
PLAYBACK_ACTIONS: tuple[str, ...] = (
    "play", "pause", "next", "previous", "seek", "volume", "shuffle", "repeat", "like",
)

REPEAT_MODES: tuple[str, ...] = ("off", "all", "one")

ARTWORK_MIME_TYPES: tuple[str, ...] = ("image/jpeg", "image/png", "image/webp")
ARTWORK_MAX_BYTES = 2 << 20


@dataclass(frozen=True)
class PlaybackState:
    """What a source is playing, read from its player.

    Field names follow the device catalogue's ``media_player`` type. ``position`` and
    ``duration`` are seconds at the moment of reading; the node stamps the time. ``volume``
    is 0–100 and clamped, never rejected. Optional fields left as None are omitted from
    ``to_dict()``. Construction raises ValueError for a state or action outside the closed
    sets.
    """

    state: str
    media_title: str = ""
    media_artist: str = ""
    media_album: str = ""
    position: float | None = None
    duration: float | None = None
    volume: int | None = None
    actions: tuple[str, ...] = ()
    shuffle: bool | None = None
    repeat: str | None = None
    liked: bool | None = None
    context: str = ""  # "playing from": a playlist, album or station name

    __forge_hints__ = {
        "constructor_args": {
            "state": "'playing' | 'paused' | 'idle'",
            "media_title": "track or station title",
            "media_artist": "artist(s), comma-separated",
            "media_album": "album name",
            "position": "seconds into the track, as read now (None if unknown)",
            "duration": "track length in seconds (None for a stream)",
            "volume": "0-100 (clamped)",
            "actions": "the subset of PLAYBACK_ACTIONS this source supports right now",
            "shuffle": "True/False when the source has shuffle, else None",
            "repeat": "'off' | 'all' | 'one' when the source has repeat, else None",
            "liked": "True/False when the source has a library, else None",
            "context": "what it is playing from, e.g. a playlist name",
        },
        "tips": [
            "Read every field from the player; never echo back what a control asked for",
            "List only the actions that work right now in `actions`; clients hide the rest",
        ],
    }

    def __post_init__(self) -> None:
        if self.state not in PLAYBACK_STATES:
            raise ValueError(f"PlaybackState.state must be one of {PLAYBACK_STATES}, not {self.state!r}")
        actions = tuple(self.actions)
        unknown = [a for a in actions if a not in PLAYBACK_ACTIONS]
        if unknown:
            raise ValueError(f"PlaybackState.actions has unknown actions {unknown}; allowed: {PLAYBACK_ACTIONS}")
        object.__setattr__(self, "actions", tuple(dict.fromkeys(actions)))
        if self.repeat is not None and self.repeat not in REPEAT_MODES:
            raise ValueError(f"PlaybackState.repeat must be one of {REPEAT_MODES} or None, not {self.repeat!r}")
        if self.volume is not None:
            object.__setattr__(self, "volume", max(0, min(100, int(self.volume))))

    def to_dict(self) -> dict[str, Any]:
        """The wire form: strings always, optional fields only when set."""
        out: dict[str, Any] = {
            "state": self.state,
            "media_title": self.media_title,
            "media_artist": self.media_artist,
            "media_album": self.media_album,
            "context": self.context,
            "actions": list(self.actions),
        }
        for key in ("position", "duration", "volume", "shuffle", "repeat", "liked"):
            value = getattr(self, key)
            if value is not None:
                out[key] = value
        return out


@dataclass(frozen=True)
class PlaybackArtwork:
    """The current track's cover image, as bytes. The node serves it; nothing fetches a URL."""

    data: bytes = field(repr=False)
    mime: str

    def __post_init__(self) -> None:
        if self.mime not in ARTWORK_MIME_TYPES:
            raise ValueError(f"PlaybackArtwork.mime must be one of {ARTWORK_MIME_TYPES}, not {self.mime!r}")
        if len(self.data) > ARTWORK_MAX_BYTES:
            raise ValueError(f"PlaybackArtwork is {len(self.data)} bytes; the limit is {ARTWORK_MAX_BYTES}")


class PlaybackBackend(ABC):
    """Abstract backend the node runtime implements."""

    @abstractmethod
    def report(self, command_name: str, state: dict[str, Any] | None) -> bool: ...
    # A source's new state (PlaybackState.to_dict(), or None: stopped); True once taken.


# Global backend instance, set by the node runtime at startup.
_backend: PlaybackBackend | None = None


def set_playback_backend(backend: PlaybackBackend | None) -> None:
    """Register the playback backend. Called once by the node runtime."""
    global _backend
    _backend = backend


def get_playback_backend() -> PlaybackBackend | None:
    """Get the current playback backend (for internal use)."""
    return _backend


class IJarvisMusicCommand(IJarvisCommand):
    """A command that plays audio on the node and reports what is playing.

    Implement everything ``IJarvisCommand`` needs, plus ``playback_binary``,
    ``playback_status()`` and ``playback_control()``. ``playback_artwork()`` is optional.
    Call ``report()`` when the player changes without the node asking (a new track, a pause
    from another app); the node also polls ``playback_status()`` while something plays.
    """

    __forge_hints__ = {
        "component_type": "command",
        "entry_file": "command.py",
        "convention_dir": "commands/{name}/",
        "base_class": "IJarvisMusicCommand",
        "required_methods": [
            "command_name", "description", "parameters", "required_secrets",
            "keywords", "run", "generate_prompt_examples", "generate_adapter_examples",
            "playback_binary", "playback_status", "playback_control",
        ],
        "tips": [
            "Use IJarvisMusicCommand instead of IJarvisCommand for anything that plays audio (music, radio, podcasts)",
            "playback_binary names the player process you run (e.g. 'mpv', 'go-librespot'); the node ducks it while the user talks and stops it when another source plays",
            "playback_status() must read the player every time; return None when nothing plays",
            "playback_control(action, **args) does one action from PLAYBACK_ACTIONS and returns playback_status() read back afterwards",
            "seek passes position (seconds), volume passes volume (0-100); other actions take no args",
            "Call self.report() when the track changes or another app pauses it, so screens update at once",
            "Override playback_artwork() to return PlaybackArtwork(data=..., mime=...) for the current track; never return a URL",
            "Keep search and starting playback in run(); pause, next and volume also come from the built-in transport commands",
        ],
        "example_import": "from jarvis_command_sdk import IJarvisMusicCommand, PlaybackState, PlaybackArtwork, CommandResponse",
    }

    @property
    @abstractmethod
    def playback_binary(self) -> str:
        """The player process this command runs, for ducking and takeover."""

    @property
    def takes_over_playback_binary(self) -> str:
        # Hosts that predate IJarvisMusicCommand read this name for takeover.
        return self.playback_binary

    @abstractmethod
    def playback_status(self) -> PlaybackState | None:
        """What the player is doing now, or None when nothing plays."""

    @abstractmethod
    def playback_control(self, action: str, **args: Any) -> PlaybackState | None:
        """Perform one action from PLAYBACK_ACTIONS; return the state read back afterwards."""

    def playback_artwork(self) -> PlaybackArtwork | None:
        """The current track's cover image, or None (the default)."""
        return None

    def report(self, state: PlaybackState | None = None) -> bool:
        """Tell the node the player changed. With no state, reads playback_status().

        Returns False without a backend or when anything fails; never raises.
        """
        if _backend is None:
            _log.debug("report: no playback backend registered")
            return False
        try:
            current = state if state is not None else self.playback_status()
            return bool(_backend.report(self.command_name, current.to_dict() if current else None))
        except Exception as e:
            _log.warning("report: playback backend failed: %s", e)
            return False
