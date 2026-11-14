"""IJarvisDaemon: the contract a node's daemon supervisor relies on."""

from __future__ import annotations

import asyncio

import pytest

from jarvis_command_sdk import IJarvisDaemon
from jarvis_command_sdk.forge import INTERFACE_CLASSES


class Listener(IJarvisDaemon):
    def __init__(self) -> None:
        self.closed = False

    @property
    def name(self) -> str:
        return "listener"

    @property
    def description(self) -> str:
        return "Holds a connection."

    @property
    def required_secrets(self):
        return []

    async def run(self) -> None:
        try:
            await asyncio.Event().wait()
        finally:
            self.closed = True


def test_run_is_required() -> None:
    class NoRun(IJarvisDaemon):
        name = "x"
        description = "x"
        required_secrets = []

    with pytest.raises(TypeError):
        NoRun()  # type: ignore[abstract]


def test_run_stays_up_until_cancelled_and_cleans_up() -> None:
    async def scenario() -> Listener:
        d = Listener()
        task = asyncio.create_task(d.run())
        await asyncio.sleep(0)
        assert not task.done()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return d

    assert asyncio.run(scenario()).closed


def test_forge_knows_the_daemon_component() -> None:
    assert IJarvisDaemon in INTERFACE_CLASSES
    hints = IJarvisDaemon.__forge_hints__
    assert hints["component_type"] == "daemon" and hints["convention_dir"] == "daemons/{name}/"
