"""UserSettings — helper for checking user-facing toggle settings.

Provides a clean interface for commands and agents to check boolean/string
settings stored in the secrets system. Settings are read-only from the
command's perspective — users configure them via the mobile app.

Usage:
    from jarvis_command_sdk import UserSettings

    settings = UserSettings("reminder")
    if settings.is_enabled("push_notifications"):
        # send push notification

    theme = settings.get("preferred_theme", default="dark")
"""

from __future__ import annotations

from .storage import JarvisStorage


class UserSettings:
    """Read-only access to user-facing settings for a command/agent.

    Settings are stored as secrets (scope: "integration") with a
    naming convention: {prefix}_{setting_name} in UPPER_SNAKE_CASE.

    Args:
        prefix: Command/agent name used as prefix (e.g., "reminder" → "REMINDER_PUSH_NOTIFICATIONS").
        scope: Secret scope (default: "integration").
    """

    def __init__(self, prefix: str, scope: str = "integration") -> None:
        self._prefix = prefix.upper()
        self._storage = JarvisStorage(prefix, secret_scope=scope)

    def _key(self, name: str) -> str:
        """Build the full secret key from a setting name."""
        return f"{self._prefix}_{name.upper()}"

    def get(self, name: str, default: str | None = None) -> str | None:
        """Get a setting value as a string.

        Args:
            name: Setting name (e.g., "push_notifications").
            default: Value to return if not set.
        """
        value = self._storage.get_secret(self._key(name))
        if value is None or value == "":
            return default
        return value

    def is_enabled(self, name: str, default: bool = False) -> bool:
        """Check if a boolean setting is enabled.

        Truthy values: "true", "1", "yes", "on" (case-insensitive).
        Missing or empty values return the default.

        Args:
            name: Setting name (e.g., "push_notifications").
            default: Value to return if not set.
        """
        value = self._storage.get_secret(self._key(name))
        if value is None or value == "":
            return default
        return value.strip().lower() in ("true", "1", "yes", "on")

    def get_int(self, name: str, default: int = 0) -> int:
        """Get a setting value as an integer.

        Args:
            name: Setting name.
            default: Value to return if not set or not a valid integer.
        """
        value = self._storage.get_secret(self._key(name))
        if value is None or value == "":
            return default
        try:
            return int(value)
        except (ValueError, TypeError):
            return default
