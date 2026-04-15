"""Auth primitives: OAuth token bundles and caller-provided auth status.

Kept out of command.py to avoid circular imports and to give hosts (node,
mobile, CLI) a clean type to serialize to/from their own persistence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass
class TokenBundle:
    """Result of an OAuth token exchange or refresh.

    `raw` is the full decoded JSON response so callers can pull provider-
    specific fields (scopes, id_token, etc.) without the SDK having to
    guess at them.
    """

    access_token: str | None
    refresh_token: str | None
    expires_in: int | None
    raw: dict[str, Any] = field(default_factory=dict)

    def expires_at(self, *, now: datetime | None = None) -> datetime | None:
        if self.expires_in is None:
            return None
        base = now or datetime.now(timezone.utc)
        return base + timedelta(seconds=int(self.expires_in))


@dataclass
class AuthStatus:
    """Snapshot of whether a provider currently needs re-auth.

    Hosts that track failed 401s (or similar) hand this to `needs_auth()` so
    the check stays pure — no host-specific DB lookup inside the command.
    """

    needs_auth: bool
    reason: str | None = None


class MissingSecretsError(Exception):
    """Raised by `IJarvisCommand.execute()` when required secrets are absent
    from the `secrets` dict the caller passed in."""

    def __init__(self, missing_secrets: list[str]):
        self.missing_secrets = list(missing_secrets)
        super().__init__(
            f"Missing required secrets: {', '.join(self.missing_secrets)}",
        )
