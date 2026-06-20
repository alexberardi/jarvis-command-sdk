"""Tests for JarvisStorage — the data/secret persistence facade and backend injection."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Any

import pytest

from jarvis_command_sdk import (
    JarvisStorage,
    StorageBackend,
    get_backend,
    set_backend,
)
from jarvis_command_sdk import context as context_module
from jarvis_command_sdk import storage as storage_module


# ── Test fixtures ──────────────────────────────────────────────────────────


class FakeStorageBackend(StorageBackend):
    """In-memory backend that records every call and stores data/secrets in dicts."""

    def __init__(self) -> None:
        # data[command_name][data_key] = data dict
        self.data: dict[str, dict[str, dict[str, Any]]] = {}
        # secrets[(key, scope, user_id)] = value
        self.secrets: dict[tuple[str, str, int | None], str] = {}
        self.calls: list[tuple[Any, ...]] = []

    def save(
        self,
        command_name: str,
        data_key: str,
        data: dict[str, Any],
        expires_at: datetime | None = None,
    ) -> None:
        self.calls.append(("save", command_name, data_key, data, expires_at))
        self.data.setdefault(command_name, {})[data_key] = data

    def get(self, command_name: str, data_key: str) -> dict[str, Any] | None:
        self.calls.append(("get", command_name, data_key))
        return self.data.get(command_name, {}).get(data_key)

    def get_all(self, command_name: str) -> list[dict[str, Any]]:
        self.calls.append(("get_all", command_name))
        return list(self.data.get(command_name, {}).values())

    def delete(self, command_name: str, data_key: str) -> bool:
        self.calls.append(("delete", command_name, data_key))
        bucket = self.data.get(command_name, {})
        if data_key in bucket:
            del bucket[data_key]
            return True
        return False

    def delete_all(self, command_name: str) -> int:
        self.calls.append(("delete_all", command_name))
        bucket = self.data.get(command_name, {})
        count = len(bucket)
        self.data[command_name] = {}
        return count

    def get_secret(self, key: str, scope: str, user_id: int | None = None) -> str | None:
        self.calls.append(("get_secret", key, scope, user_id))
        return self.secrets.get((key, scope, user_id))

    def set_secret(
        self,
        key: str,
        value: str,
        scope: str,
        value_type: str = "string",
        user_id: int | None = None,
    ) -> None:
        self.calls.append(("set_secret", key, value, scope, value_type, user_id))
        self.secrets[(key, scope, user_id)] = value

    def delete_secret(self, key: str, scope: str, user_id: int | None = None) -> None:
        self.calls.append(("delete_secret", key, scope, user_id))
        self.secrets.pop((key, scope, user_id), None)


@pytest.fixture(autouse=True)
def reset_backend() -> Iterator[None]:
    """Isolate the module-level backend and user context between tests."""
    storage_module._backend = None
    context_module.set_current_user_id(None)
    yield
    storage_module._backend = None
    context_module.set_current_user_id(None)


# ── Backend registration ───────────────────────────────────────────────────


class TestBackendRegistration:
    def test_get_backend_returns_none_by_default(self) -> None:
        assert get_backend() is None

    def test_set_and_get_backend(self) -> None:
        backend = FakeStorageBackend()
        set_backend(backend)
        assert get_backend() is backend
        assert storage_module._backend is backend


# ── No-backend safe defaults ───────────────────────────────────────────────


class TestNoBackendDefaults:
    def test_save_is_noop(self) -> None:
        # No backend installed; should silently return None without raising.
        assert JarvisStorage("bluetooth").save("k", {"a": 1}) is None

    def test_get_returns_none(self) -> None:
        assert JarvisStorage("bluetooth").get("k") is None

    def test_get_all_returns_empty_list(self) -> None:
        assert JarvisStorage("bluetooth").get_all() == []

    def test_delete_returns_false(self) -> None:
        assert JarvisStorage("bluetooth").delete("k") is False

    def test_delete_all_returns_zero(self) -> None:
        assert JarvisStorage("bluetooth").delete_all() == 0

    def test_get_secret_returns_none(self) -> None:
        assert JarvisStorage("bluetooth").get_secret("URL") is None

    def test_set_secret_is_noop(self) -> None:
        assert JarvisStorage("bluetooth").set_secret("URL", "http://x") is None

    def test_delete_secret_is_noop(self) -> None:
        assert JarvisStorage("bluetooth").delete_secret("URL") is None


# ── Command-data proxying ──────────────────────────────────────────────────


class TestCommandDataProxy:
    def test_save_round_trips_through_backend(self) -> None:
        backend = FakeStorageBackend()
        set_backend(backend)
        storage = JarvisStorage("bluetooth")
        storage.save("device_mac", {"name": "JBL", "role": "source"})
        assert backend.data["bluetooth"]["device_mac"] == {"name": "JBL", "role": "source"}
        # command_name is injected from the facade; expires_at defaults to None.
        assert backend.calls[0] == (
            "save",
            "bluetooth",
            "device_mac",
            {"name": "JBL", "role": "source"},
            None,
        )

    def test_save_forwards_expires_at(self) -> None:
        backend = FakeStorageBackend()
        set_backend(backend)
        expires = datetime(2030, 1, 1, 12, 0, 0)
        JarvisStorage("bluetooth").save("k", {"v": 1}, expires_at=expires)
        assert backend.calls[0] == ("save", "bluetooth", "k", {"v": 1}, expires)

    def test_get_returns_stored_value(self) -> None:
        backend = FakeStorageBackend()
        set_backend(backend)
        storage = JarvisStorage("bluetooth")
        storage.save("device_mac", {"name": "JBL"})
        assert storage.get("device_mac") == {"name": "JBL"}

    def test_get_missing_key_returns_none(self) -> None:
        backend = FakeStorageBackend()
        set_backend(backend)
        assert JarvisStorage("bluetooth").get("nope") is None

    def test_get_all_returns_every_record_for_command(self) -> None:
        backend = FakeStorageBackend()
        set_backend(backend)
        storage = JarvisStorage("bluetooth")
        storage.save("a", {"v": 1})
        storage.save("b", {"v": 2})
        # Records for a different command must not leak in.
        JarvisStorage("other").save("c", {"v": 3})
        result = storage.get_all()
        assert {"v": 1} in result
        assert {"v": 2} in result
        assert {"v": 3} not in result
        assert len(result) == 2

    def test_delete_existing_returns_true_and_removes(self) -> None:
        backend = FakeStorageBackend()
        set_backend(backend)
        storage = JarvisStorage("bluetooth")
        storage.save("k", {"v": 1})
        assert storage.delete("k") is True
        assert storage.get("k") is None

    def test_delete_missing_returns_false(self) -> None:
        backend = FakeStorageBackend()
        set_backend(backend)
        assert JarvisStorage("bluetooth").delete("nope") is False

    def test_delete_all_returns_count(self) -> None:
        backend = FakeStorageBackend()
        set_backend(backend)
        storage = JarvisStorage("bluetooth")
        storage.save("a", {"v": 1})
        storage.save("b", {"v": 2})
        assert storage.delete_all() == 2
        assert storage.get_all() == []


# ── Secret proxying & scope resolution ─────────────────────────────────────


class TestSecretProxy:
    def test_set_and_get_secret_default_scope(self) -> None:
        backend = FakeStorageBackend()
        set_backend(backend)
        storage = JarvisStorage("music")  # default scope "integration"
        storage.set_secret("MUSIC_URL", "http://ma", value_type="string")
        # Stored under the default "integration" scope, user_id None.
        assert backend.secrets[("MUSIC_URL", "integration", None)] == "http://ma"
        assert storage.get_secret("MUSIC_URL") == "http://ma"

    def test_default_secret_scope_is_integration(self) -> None:
        backend = FakeStorageBackend()
        set_backend(backend)
        JarvisStorage("music").get_secret("URL")
        # get_secret records (key, scope, user_id)
        assert backend.calls[-1] == ("get_secret", "URL", "integration", None)

    def test_custom_default_scope_used_when_not_overridden(self) -> None:
        backend = FakeStorageBackend()
        set_backend(backend)
        JarvisStorage("music", secret_scope="household").get_secret("URL")
        assert backend.calls[-1] == ("get_secret", "URL", "household", None)

    def test_explicit_scope_overrides_default(self) -> None:
        backend = FakeStorageBackend()
        set_backend(backend)
        JarvisStorage("music", secret_scope="household").get_secret("URL", scope="integration")
        assert backend.calls[-1] == ("get_secret", "URL", "integration", None)

    def test_set_secret_forwards_value_type_and_scope(self) -> None:
        backend = FakeStorageBackend()
        set_backend(backend)
        JarvisStorage("music").set_secret("PORT", "8080", scope="household", value_type="int")
        assert backend.calls[-1] == ("set_secret", "PORT", "8080", "household", "int", None)

    def test_set_secret_default_value_type_is_string(self) -> None:
        backend = FakeStorageBackend()
        set_backend(backend)
        JarvisStorage("music").set_secret("KEY", "val")
        assert backend.calls[-1] == ("set_secret", "KEY", "val", "integration", "string", None)

    def test_delete_secret_proxies(self) -> None:
        backend = FakeStorageBackend()
        set_backend(backend)
        storage = JarvisStorage("music")
        storage.set_secret("KEY", "val")
        storage.delete_secret("KEY")
        assert backend.secrets.get(("KEY", "integration", None)) is None
        assert backend.calls[-1] == ("delete_secret", "KEY", "integration", None)

    def test_delete_secret_with_explicit_scope(self) -> None:
        backend = FakeStorageBackend()
        set_backend(backend)
        JarvisStorage("music").delete_secret("KEY", scope="household")
        assert backend.calls[-1] == ("delete_secret", "KEY", "household", None)


# ── User-scoped secrets pull user_id from the request context ──────────────


class TestUserScopedSecrets:
    def test_user_scope_resolves_user_id_from_context(self) -> None:
        backend = FakeStorageBackend()
        set_backend(backend)
        context_module.set_current_user_id(42)
        storage = JarvisStorage("music")
        storage.set_secret("TOKEN", "abc", scope="user")
        # user_id 42 threaded through from the context var.
        assert backend.calls[-1] == ("set_secret", "TOKEN", "abc", "user", "string", 42)
        assert storage.get_secret("TOKEN", scope="user") == "abc"
        assert backend.calls[-1] == ("get_secret", "TOKEN", "user", 42)

    def test_user_scope_with_no_context_user_id_is_none(self) -> None:
        backend = FakeStorageBackend()
        set_backend(backend)
        # No user set in context -> user_id resolves to None.
        JarvisStorage("music").get_secret("TOKEN", scope="user")
        assert backend.calls[-1] == ("get_secret", "TOKEN", "user", None)

    def test_non_user_scope_does_not_resolve_user_id(self) -> None:
        backend = FakeStorageBackend()
        set_backend(backend)
        context_module.set_current_user_id(99)
        # Even with a context user, non-"user" scopes pass user_id=None.
        JarvisStorage("music").get_secret("KEY", scope="integration")
        assert backend.calls[-1] == ("get_secret", "KEY", "integration", None)

    def test_user_scope_delete_threads_user_id(self) -> None:
        backend = FakeStorageBackend()
        set_backend(backend)
        context_module.set_current_user_id(7)
        JarvisStorage("music").delete_secret("TOKEN", scope="user")
        assert backend.calls[-1] == ("delete_secret", "TOKEN", "user", 7)
