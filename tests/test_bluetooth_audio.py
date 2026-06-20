"""Tests for jarvis_command_sdk.bluetooth_audio.BluetoothAudio routing helper."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from jarvis_command_sdk import BluetoothAudio, BluetoothSinkInfo

# Representative `pactl list sinks short` output. Columns are tab-separated:
# index  name  driver  sample-spec  state
_BLUEZ_OUTPUT = (
    "0\talsa_output.platform-bcm2835_audio.analog-stereo\tmodule-alsa-card.c\t"
    "s16le 2ch 44100Hz\tSUSPENDED\n"
    "1\tbluez_output.AA_BB_CC_DD_EE_FF.1\tmodule-bluez5-device.c\t"
    "s16le 2ch 44100Hz\tRUNNING"
)

_BLUEZ_SINK_LEGACY = (
    "2\tbluez_sink.11_22_33_44_55_66.a2dp_sink\tmodule-bluez5-device.c\t"
    "s16le 2ch 44100Hz\tRUNNING"
)

_NO_BT = (
    "0\talsa_output.platform-bcm2835_audio.analog-stereo\tmodule-alsa-card.c\t"
    "s16le 2ch 44100Hz\tSUSPENDED\n"
    "1\talsa_output.usb-Generic_USB_Audio.iec958-stereo\tmodule-alsa-card.c\t"
    "s16le 2ch 48000Hz\tSUSPENDED"
)


def _run_result(stdout: str = "", returncode: int = 0) -> MagicMock:
    """Build a stand-in for the subprocess.CompletedProcess returned by run()."""
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    return result


class TestGetSink:
    def test_parses_bluez_output_sink_name(self) -> None:
        with patch(
            "jarvis_command_sdk.bluetooth_audio.subprocess.run",
            return_value=_run_result(_BLUEZ_OUTPUT),
        ) as run:
            sink = BluetoothAudio.get_sink()

        assert isinstance(sink, BluetoothSinkInfo)
        # parts[1] is the sink name column.
        assert sink.sink_name == "bluez_output.AA_BB_CC_DD_EE_FF.1"
        assert sink.device_name == "Unknown"
        # Confirm we actually shelled out to pactl with the expected args.
        run.assert_called_once()
        args, _ = run.call_args
        assert args[0] == ["pactl", "list", "sinks", "short"]

    def test_parses_legacy_bluez_sink_name(self) -> None:
        with patch(
            "jarvis_command_sdk.bluetooth_audio.subprocess.run",
            return_value=_run_result(_BLUEZ_SINK_LEGACY),
        ):
            sink = BluetoothAudio.get_sink()

        assert sink is not None
        assert sink.sink_name == "bluez_sink.11_22_33_44_55_66.a2dp_sink"

    def test_returns_none_when_no_bluetooth_sink(self) -> None:
        with patch(
            "jarvis_command_sdk.bluetooth_audio.subprocess.run",
            return_value=_run_result(_NO_BT),
        ):
            assert BluetoothAudio.get_sink() is None

    def test_returns_none_on_nonzero_returncode(self) -> None:
        with patch(
            "jarvis_command_sdk.bluetooth_audio.subprocess.run",
            return_value=_run_result(_BLUEZ_OUTPUT, returncode=1),
        ):
            assert BluetoothAudio.get_sink() is None

    def test_returns_none_when_pactl_missing(self) -> None:
        with patch(
            "jarvis_command_sdk.bluetooth_audio.subprocess.run",
            side_effect=FileNotFoundError("pactl"),
        ):
            assert BluetoothAudio.get_sink() is None

    def test_returns_none_on_timeout(self) -> None:
        with patch(
            "jarvis_command_sdk.bluetooth_audio.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="pactl", timeout=5.0),
        ):
            assert BluetoothAudio.get_sink() is None

    def test_ignores_malformed_line_without_tab(self) -> None:
        # A matching line that lacks a name column (len(parts) < 2) must be
        # skipped rather than crash or return a bogus sink.
        with patch(
            "jarvis_command_sdk.bluetooth_audio.subprocess.run",
            return_value=_run_result("bluez_output-no-tabs-here"),
        ):
            assert BluetoothAudio.get_sink() is None


class TestTargetSink:
    def test_use_node_audio_true_always_none(self) -> None:
        # Even with a BT sink present, node-audio intent forces the default sink.
        with patch(
            "jarvis_command_sdk.bluetooth_audio.subprocess.run",
            return_value=_run_result(_BLUEZ_OUTPUT),
        ) as run:
            assert BluetoothAudio.target_sink(use_node_audio=True) is None
        # Short-circuits before shelling out to pactl.
        run.assert_not_called()

    def test_default_returns_bt_sink_name(self) -> None:
        with patch.object(
            BluetoothAudio,
            "get_sink",
            return_value=BluetoothSinkInfo(sink_name="bluez_output.AA_BB_CC_DD_EE_FF.1"),
        ):
            assert BluetoothAudio.target_sink() == "bluez_output.AA_BB_CC_DD_EE_FF.1"

    def test_default_returns_none_when_no_sink(self) -> None:
        with patch.object(BluetoothAudio, "get_sink", return_value=None):
            assert BluetoothAudio.target_sink() is None


class TestPlaybackEnv:
    def test_sets_pulse_sink_when_bt_connected(self) -> None:
        base_env = {"PATH": "/usr/bin", "HOME": "/home/pi"}
        with patch.dict(
            "jarvis_command_sdk.bluetooth_audio.os.environ",
            base_env,
            clear=True,
        ), patch.object(
            BluetoothAudio,
            "get_sink",
            return_value=BluetoothSinkInfo(sink_name="bluez_output.AA_BB_CC_DD_EE_FF.1"),
        ):
            env = BluetoothAudio.playback_env()

        assert env["PULSE_SINK"] == "bluez_output.AA_BB_CC_DD_EE_FF.1"
        # Inherited env preserved.
        assert env["PATH"] == "/usr/bin"
        assert env["HOME"] == "/home/pi"

    def test_leaves_pulse_sink_unset_when_no_bt(self) -> None:
        base_env = {"PATH": "/usr/bin"}
        with patch.dict(
            "jarvis_command_sdk.bluetooth_audio.os.environ",
            base_env,
            clear=True,
        ), patch.object(BluetoothAudio, "get_sink", return_value=None):
            env = BluetoothAudio.playback_env()

        assert "PULSE_SINK" not in env
        assert env["PATH"] == "/usr/bin"

    def test_use_node_audio_clears_inherited_pulse_sink(self) -> None:
        # An inherited PULSE_SINK (e.g. from a BT-routed parent) must be
        # stripped so TTS lands on the default node speaker.
        base_env = {"PATH": "/usr/bin", "PULSE_SINK": "bluez_output.stale.1"}
        with patch.dict(
            "jarvis_command_sdk.bluetooth_audio.os.environ",
            base_env,
            clear=True,
        ), patch.object(BluetoothAudio, "get_sink") as get_sink:
            env = BluetoothAudio.playback_env(use_node_audio=True)

        assert "PULSE_SINK" not in env
        assert env["PATH"] == "/usr/bin"
        # Node-audio path short-circuits before touching get_sink.
        get_sink.assert_not_called()

    def test_use_node_audio_no_pulse_sink_to_clear(self) -> None:
        base_env = {"PATH": "/usr/bin"}
        with patch.dict(
            "jarvis_command_sdk.bluetooth_audio.os.environ",
            base_env,
            clear=True,
        ):
            env = BluetoothAudio.playback_env(use_node_audio=True)

        assert "PULSE_SINK" not in env
        assert env["PATH"] == "/usr/bin"

    def test_returns_copy_not_live_environ(self) -> None:
        base_env = {"PATH": "/usr/bin"}
        with patch.dict(
            "jarvis_command_sdk.bluetooth_audio.os.environ",
            base_env,
            clear=True,
        ), patch.object(
            BluetoothAudio,
            "get_sink",
            return_value=BluetoothSinkInfo(sink_name="bluez_output.x.1"),
        ):
            env = BluetoothAudio.playback_env()
            import jarvis_command_sdk.bluetooth_audio as mod

            # The sink is set on the returned copy, never on the global environ.
            assert env["PULSE_SINK"] == "bluez_output.x.1"
            assert "PULSE_SINK" not in mod.os.environ


class TestIsAvailable:
    def test_true_when_sink_present(self) -> None:
        with patch.object(
            BluetoothAudio,
            "get_sink",
            return_value=BluetoothSinkInfo(sink_name="bluez_output.AA.1"),
        ):
            assert BluetoothAudio.is_available() is True

    def test_false_when_no_sink(self) -> None:
        with patch.object(BluetoothAudio, "get_sink", return_value=None):
            assert BluetoothAudio.is_available() is False
