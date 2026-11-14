"""IJarvisDaemon — Abstract base class for long-running package daemons.

A daemon is started once and kept running by the node: it holds a connection
open (a chat service's gateway, a device bridge's socket) or waits on events,
which a scheduled ``IJarvisAgent`` cannot do. The node runs each daemon in its
own process, restarts it when it stops, and stops it on uninstall.
"""

from abc import ABC, abstractmethod
from typing import List

from .secret import IJarvisSecret


class IJarvisDaemon(ABC):
    """Abstract base class for long-running daemons.

    ``run()`` is awaited once and is expected never to return. The node
    cancels it to stop the daemon (uninstall, shutdown, a changed secret), so
    clean up in ``finally`` or on ``asyncio.CancelledError``. If ``run()``
    returns or raises, the daemon is considered dead and the node restarts it
    after a delay.
    """

    __forge_hints__ = {
        "component_type": "daemon",
        "entry_file": "daemon.py",
        "convention_dir": "daemons/{name}/",
        "base_class": "IJarvisDaemon",
        "required_methods": ["name", "description", "required_secrets", "run"],
        "tips": [
            "run() is awaited once and should run until cancelled — hold your connection or event loop there",
            "Returning or raising from run() means the daemon died; the node restarts it after a delay",
            "The node cancels run() to stop the daemon — release connections in finally",
            "Use IJarvisAgent instead when polling on an interval is enough",
            "Daemons share secrets with commands via the same JarvisSecret system; a changed secret restarts the daemon",
            "A household runs a daemon on one node only — do not assume several copies",
        ],
        "example_import": "from jarvis_command_sdk import IJarvisDaemon, JarvisSecret",
    }

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this daemon."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description."""
        ...

    @property
    @abstractmethod
    def required_secrets(self) -> List[IJarvisSecret]:
        """Secrets this daemon needs to function."""
        ...

    @abstractmethod
    async def run(self) -> None:
        """Run until cancelled."""
        ...
