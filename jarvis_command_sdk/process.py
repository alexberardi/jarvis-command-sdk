"""Cross-platform process introspection helpers for command authors.

Custom commands that spawn background daemons (Spotify Connect, MPD
bridges, BT pairing agents, etc.) typically track them via a pidfile —
read the PID on next startup, decide whether to re-spawn. The naive
liveness check ``os.kill(pid, 0)`` is unsafe for that workflow: after a
reboot the kernel may have recycled the PID to an unrelated process
(empirically, often another daemon under the same uid that comes up
earlier in boot), and a bare existence check would incorrectly report
the original daemon as running.

``process_alive`` accepts an ``expected_comm`` so callers can validate
that the process at the pidfile-stored PID is actually their daemon
binary, not whatever else happens to occupy that PID now.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def process_alive(pid: int, expected_comm: str | None = None) -> bool:
    """True if a live process exists at ``pid``, optionally matching ``expected_comm``.

    When ``expected_comm`` is provided, also verifies the running binary's
    name matches — guards against PID-reuse staleness in pidfile-tracked
    daemons. Reads ``/proc/<pid>/comm`` on Linux; falls back to ``ps -p``
    on darwin (and any other platform without ``/proc``).

    ``expected_comm`` is matched against the basename, so ``/usr/bin/foo``
    and ``foo`` both match ``expected_comm="foo"``. Linux's 15-char comm
    truncation applies — long binary names should be passed truncated.
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but is owned by a different uid. Fall through to
        # the comm check — /proc/<pid>/comm is world-readable on Linux,
        # so we can still validate the binary name. When no comm is
        # requested, "exists" is enough.
        pass
    if expected_comm is None:
        return True
    return _pid_comm(pid) == expected_comm


def _pid_comm(pid: int) -> str | None:
    """Return the comm (binary name) of ``pid``, or None if it can't be read."""
    comm_path = Path(f"/proc/{pid}/comm")
    if comm_path.exists():
        try:
            return comm_path.read_text().strip()
        except OSError:
            return None
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "comm="],
            capture_output=True, text=True, timeout=2,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    raw = result.stdout.strip()
    if not raw:
        return None
    return Path(raw).name
