"""JarvisStorage — Facade for command data persistence and secrets.

Provides a clean interface for commands to store/retrieve data and secrets
without directly depending on node internals (db.SessionLocal, repositories).

Usage in extracted Pantry packages:
    from jarvis_command_sdk import JarvisStorage

    storage = JarvisStorage("bluetooth")
    storage.save("device_mac", {"name": "JBL", "role": "source"})
    data = storage.get("device_mac")
    all_data = storage.get_all()
    storage.delete("device_mac")

    # Secrets
    url = storage.get_secret("MUSIC_ASSISTANT_URL")
    storage.set_secret("MUSIC_ASSISTANT_URL", "http://...", value_type="string")

The node runtime registers the real backend via JarvisStorage.set_backend().
When no backend is registered (e.g., in tests), methods return safe defaults.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any


class StorageBackend(ABC):
    """Abstract backend that the node runtime implements."""

    # -- Command data --

    @abstractmethod
    def save(
        self,
        command_name: str,
        data_key: str,
        data: dict[str, Any],
        expires_at: datetime | None = None,
    ) -> None: ...

    @abstractmethod
    def get(self, command_name: str, data_key: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def get_all(self, command_name: str) -> list[dict[str, Any]]: ...

    @abstractmethod
    def delete(self, command_name: str, data_key: str) -> bool: ...

    @abstractmethod
    def delete_all(self, command_name: str) -> int: ...

    # -- Secrets --

    @abstractmethod
    def get_secret(self, key: str, scope: str, user_id: int | None = None) -> str | None: ...

    @abstractmethod
    def set_secret(
        self, key: str, value: str, scope: str, value_type: str = "string",
        user_id: int | None = None,
    ) -> None: ...

    @abstractmethod
    def delete_secret(self, key: str, scope: str, user_id: int | None = None) -> None: ...


# Global backend instance, set by the node runtime at startup
_backend: StorageBackend | None = None


def set_backend(backend: StorageBackend) -> None:
    """Register the storage backend. Called once by the node runtime."""
    global _backend
    _backend = backend


def get_backend() -> StorageBackend | None:
    """Get the current storage backend (for internal use)."""
    return _backend


class JarvisStorage:
    """Per-command facade for data persistence and secrets.

    Args:
        command_name: The command that owns the stored data (e.g., "bluetooth").
        secret_scope: Default scope for secret operations (default: "integration").
    """

    def __init__(self, command_name: str, secret_scope: str = "integration") -> None:
        self._command_name = command_name
        self._secret_scope = secret_scope

    # -- Command data --

    def save(
        self,
        key: str,
        data: dict[str, Any],
        expires_at: datetime | None = None,
    ) -> None:
        """Save or update a data record (upsert by key)."""
        if _backend is None:
            return
        _backend.save(self._command_name, key, data, expires_at)

    def get(self, key: str) -> dict[str, Any] | None:
        """Get a data record by key. Returns None if not found or expired."""
        if _backend is None:
            return None
        return _backend.get(self._command_name, key)

    def get_all(self) -> list[dict[str, Any]]:
        """Get all data records for this command."""
        if _backend is None:
            return []
        return _backend.get_all(self._command_name)

    def delete(self, key: str) -> bool:
        """Delete a data record by key."""
        if _backend is None:
            return False
        return _backend.delete(self._command_name, key)

    def delete_all(self) -> int:
        """Delete all data records for this command."""
        if _backend is None:
            return 0
        return _backend.delete_all(self._command_name)

    # -- Secrets --

    def _resolve_user_id(self, scope: str) -> int | None:
        """Get user_id from context when scope is 'user'."""
        if scope == "user":
            from .context import get_current_user_id
            return get_current_user_id()
        return None

    def get_secret(self, key: str, scope: str | None = None) -> str | None:
        """Get a secret value. Uses the instance's default scope if not specified."""
        if _backend is None:
            return None
        resolved_scope = scope or self._secret_scope
        return _backend.get_secret(key, resolved_scope, user_id=self._resolve_user_id(resolved_scope))

    def set_secret(
        self,
        key: str,
        value: str,
        scope: str | None = None,
        value_type: str = "string",
    ) -> None:
        """Set a secret value. Uses the instance's default scope if not specified."""
        if _backend is None:
            return
        resolved_scope = scope or self._secret_scope
        _backend.set_secret(key, value, resolved_scope, value_type, user_id=self._resolve_user_id(resolved_scope))

    def delete_secret(self, key: str, scope: str | None = None) -> None:
        """Delete a secret."""
        if _backend is None:
            return
        resolved_scope = scope or self._secret_scope
        _backend.delete_secret(key, resolved_scope, user_id=self._resolve_user_id(resolved_scope))
