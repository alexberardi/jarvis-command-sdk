"""Bluetooth audio routing helper for Jarvis commands.

Provides a simple API for commands that play audio (music, podcasts, etc.)
to route playback to a connected Bluetooth speaker/headphones when available,
while leaving TTS/Jarvis voice on the local speaker.

Routing rule (per ``use_node_audio`` flag):

    use_node_audio=False (default)    BT sink if connected, else node speaker
    use_node_audio=True               always the node speaker, even if BT is up

TTS / Jarvis voice should always pass ``use_node_audio=True`` so the assistant
stays audible in the room when a user is wearing headphones for music.

Usage:
    from jarvis_command_sdk import BluetoothAudio

    # Music command — opt into BT when available (default)
    env = BluetoothAudio.playback_env()
    subprocess.Popen(["mpv", "--no-video", url], env=env, ...)

    # TTS / Jarvis voice — always on node speaker
    env = BluetoothAudio.playback_env(use_node_audio=True)

    # Resolve the explicit target sink for callers that pass ``--device=``
    sink = BluetoothAudio.target_sink()         # → None or "bluez_output.XX..."
    sink = BluetoothAudio.target_sink(use_node_audio=True)   # → always None
"""

import os
import subprocess
from dataclasses import dataclass


@dataclass
class BluetoothSinkInfo:
    """Information about a connected Bluetooth audio sink."""
    sink_name: str
    device_name: str = "Unknown"


class BluetoothAudio:
    """Helper for routing audio playback to Bluetooth devices.

    When a Bluetooth speaker or headphones are connected, PulseAudio
    automatically creates a sink named 'bluez_sink.XX_XX_XX_XX_XX_XX.*'.
    This helper detects that sink and provides environment variables to
    route player audio there.

    TTS/Jarvis voice should NOT use this — it stays on the default
    (local) sink so the assistant is always audible from the room speaker.
    """

    @staticmethod
    def get_sink() -> BluetoothSinkInfo | None:
        """Get the first connected Bluetooth audio sink, or None.

        Returns the PulseAudio sink name suitable for use with PULSE_SINK
        environment variable or pactl commands.
        """
        try:
            result = subprocess.run(
                ["pactl", "list", "sinks", "short"],
                capture_output=True, text=True, timeout=5.0,
            )
            if result.returncode != 0:
                return None

            for line in result.stdout.strip().split("\n"):
                if "bluez_sink" in line or "bluez_output" in line:
                    parts = line.split("\t")
                    if len(parts) >= 2:
                        return BluetoothSinkInfo(sink_name=parts[1])
            return None

        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None

    @staticmethod
    def target_sink(use_node_audio: bool = False) -> str | None:
        """Return the explicit target sink name for this playback, or None.

        ``None`` means "use the default sink" — i.e. the node speaker.

        - ``use_node_audio=False`` (default): returns the BT sink name if
          connected, else None.
        - ``use_node_audio=True``: always returns None, forcing the node
          speaker even when a BT device is connected. Use this for TTS
          and any other audio that must stay audible in the room.
        """
        if use_node_audio:
            return None
        sink = BluetoothAudio.get_sink()
        return sink.sink_name if sink else None

    @staticmethod
    def playback_env(use_node_audio: bool = False) -> dict[str, str]:
        """Get an environment dict for subprocess playback.

        Routes via the ``PULSE_SINK`` env var, which the PipeWire pulse
        compatibility layer (and PulseAudio proper) honors as the target
        sink for the spawned process.

        - ``use_node_audio=False`` (default): if a BT sink is connected,
          sets PULSE_SINK to it; otherwise leaves it unset (default sink
          = node speaker).
        - ``use_node_audio=True``: clears any inherited ``PULSE_SINK`` so
          the spawned process always lands on the default sink — useful
          for TTS, which should stay on the room speaker even when the
          user has BT headphones connected.

        Usage:
            # Music — opt into BT when available
            env = BluetoothAudio.playback_env()
            subprocess.Popen(["mpv", "--no-video", url], env=env)

            # TTS — always node speaker
            env = BluetoothAudio.playback_env(use_node_audio=True)
        """
        env = dict(os.environ)
        if use_node_audio:
            env.pop("PULSE_SINK", None)
            return env
        sink = BluetoothAudio.get_sink()
        if sink:
            env["PULSE_SINK"] = sink.sink_name
        return env

    @staticmethod
    def is_available() -> bool:
        """Check if a Bluetooth audio sink is currently connected.

        Independent of ``use_node_audio`` — this only reports physical
        availability of a BT sink, not whether a given playback should
        use it. Callers wanting routing intent should call ``target_sink``
        or ``playback_env`` instead.
        """
        return BluetoothAudio.get_sink() is not None
