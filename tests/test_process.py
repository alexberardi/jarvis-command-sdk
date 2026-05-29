"""Tests for jarvis_command_sdk.process.process_alive."""

import os
import subprocess
import sys
import time

import pytest

from jarvis_command_sdk import process_alive


def test_own_process_alive_no_comm() -> None:
    assert process_alive(os.getpid()) is True


def test_own_process_alive_matching_comm() -> None:
    own_comm = _own_comm()
    assert own_comm is not None
    assert process_alive(os.getpid(), expected_comm=own_comm) is True


def test_own_process_wrong_comm_rejected() -> None:
    assert process_alive(os.getpid(), expected_comm="definitely-not-this-binary") is False


def test_nonexistent_pid_returns_false() -> None:
    # PID we're confident doesn't exist. Use a high number; on the off
    # chance it's taken, sleep + retry once with a different number.
    for candidate in (999_999, 888_888):
        if not _pid_exists(candidate):
            assert process_alive(candidate) is False
            assert process_alive(candidate, expected_comm="x") is False
            return
    pytest.skip("could not find a non-existent PID for this test run")


def test_pid_reuse_simulation_with_wrong_comm() -> None:
    """The bug this function exists to prevent.

    Start a short-lived subprocess (the "current daemon" stand-in),
    capture its PID, let it die, then check that an unrelated process
    occupying that PID later doesn't trick a comm-targeted check. In
    practice the test mostly exercises the matched-comm and gone-PID
    branches — true PID reuse within a test run is rare. Either way,
    the contract is: when ``expected_comm`` is set, only the right
    binary at the right PID returns True.
    """
    proc = subprocess.Popen(["sleep", "5"], stdout=subprocess.DEVNULL)
    try:
        # The daemon-stand-in is named "sleep". Verify both branches.
        assert process_alive(proc.pid, expected_comm="sleep") is True
        assert process_alive(proc.pid, expected_comm="go-librespot") is False
    finally:
        proc.terminate()
        proc.wait(timeout=2)

    # After it's gone, both checks must be False.
    # Tiny grace period for the kernel to reap.
    time.sleep(0.05)
    assert process_alive(proc.pid) is False
    assert process_alive(proc.pid, expected_comm="sleep") is False


@pytest.mark.skipif(sys.platform == "darwin", reason="/proc only on Linux")
def test_pid_1_visible_via_proc() -> None:
    """PID 1 is root-owned; os.kill from non-root raises PermissionError.

    The function must handle that as "process exists" rather than
    conflating it with "process gone." Then comm validation via
    /proc/1/comm — which is world-readable — must still work.
    """
    assert process_alive(1) is True
    # comm of PID 1 is typically "systemd" on Linux; just verify the
    # truth path works rather than asserting a specific init name.
    comm = _read_proc_comm(1)
    if comm:
        assert process_alive(1, expected_comm=comm) is True
        assert process_alive(1, expected_comm="not-the-init") is False


def _own_comm() -> str | None:
    if sys.platform == "darwin":
        result = subprocess.run(
            ["ps", "-p", str(os.getpid()), "-o", "comm="],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            return None
        from pathlib import Path
        return Path(result.stdout.strip()).name or None
    return _read_proc_comm(os.getpid())


def _read_proc_comm(pid: int) -> str | None:
    try:
        with open(f"/proc/{pid}/comm") as f:
            return f.read().strip() or None
    except OSError:
        return None


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
