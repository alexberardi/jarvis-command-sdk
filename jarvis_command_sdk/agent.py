"""IJarvisAgent — Abstract base class for background agents.

Agents run on a schedule, collecting data and caching results for injection
into voice request context.
"""

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from .secret import IJarvisSecret


_DEFAULT_TTL = timedelta(hours=1)


@dataclass
class AgentSchedule:
    """Schedule configuration for an agent.

    Controls how often the agent's run() method is called.
    """

    __forge_hints__ = {
        "role": "Controls agent execution schedule",
        "tips": [
            "interval_seconds: how often run() is called (e.g., 300 for every 5 minutes)",
            "run_on_startup=True means run immediately when the node starts, then on schedule",
        ],
    }

    interval_seconds: int
    run_on_startup: bool = True


@dataclass
class Alert:
    """A time-sensitive notification produced by a background agent.

    ``created_at`` / ``expires_at`` default to "now" and "now + 1 hour" so
    existing call sites that only pass the four core fields keep working.
    Producers with a real expiry should set ``expires_at`` explicitly.

    ``id`` is a fresh uuid per instance and therefore cannot deduplicate a
    re-emitted alert across runs — set ``dedupe_key`` to a stable identity
    (e.g. an article guid or ``"storm:2026-07-18"``) so downstream queues and
    the server can suppress repeats. ``category`` groups alerts for per-source
    routing preferences; ``target_user_id`` addresses one household member
    (leave ``None`` for household-wide).
    """

    source_agent: str
    title: str
    summary: str
    priority: int = 2  # 1=low, 2=medium, 3=high
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    expires_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc) + _DEFAULT_TTL,
    )
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    dedupe_key: str | None = None
    category: str = "general"
    target_user_id: str | None = None

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.expires_at

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source_agent": self.source_agent,
            "title": self.title,
            "summary": self.summary,
            "priority": self.priority,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "dedupe_key": self.dedupe_key,
            "category": self.category,
            "target_user_id": self.target_user_id,
        }


class IJarvisAgent(ABC):
    """Abstract base class for background agents.

    Agents run on a schedule in the background, collecting data and caching
    results. Their cached data is injected into voice request context so
    commands can reference it. Agents can also produce time-sensitive alerts.
    """

    __forge_hints__ = {
        "component_type": "agent",
        "entry_file": "agent.py",
        "convention_dir": "agents/{name}/",
        "base_class": "IJarvisAgent",
        "required_methods": [
            "name", "description", "schedule", "required_secrets", "run", "get_context_data",
        ],
        "tips": [
            "run() is called on a schedule — use it to fetch/cache external data",
            "get_context_data() returns a dict injected into voice request context for all commands",
            "Use AgentSchedule to set interval_seconds and whether to run_on_startup",
            "get_alerts() can return time-sensitive Alert objects for push notifications",
            "Give every Alert a stable dedupe_key (e.g. an article guid) — the uuid id changes per run, so without one a re-emitted alert notifies again",
            "Agents share secrets with commands via the same JarvisSecret system",
        ],
        "example_import": "from jarvis_command_sdk import IJarvisAgent, AgentSchedule, Alert, JarvisSecret",
    }

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this agent."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description."""
        ...

    @property
    @abstractmethod
    def schedule(self) -> AgentSchedule:
        """When this agent should run."""
        ...

    @property
    @abstractmethod
    def required_secrets(self) -> List[IJarvisSecret]:
        """Secrets this agent needs to function."""
        ...

    @abstractmethod
    async def run(self) -> None:
        """Execute the background task."""
        ...

    @property
    def include_in_context(self) -> bool:
        """Whether to include this agent's data in voice request context."""
        return True

    @abstractmethod
    def get_context_data(self) -> Dict[str, Any]:
        """Return cached data for voice request context."""
        ...

    def get_alerts(self) -> List[Alert]:
        """Return alerts generated by the last run()."""
        return []
