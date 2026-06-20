"""Tests for jarvis_command_sdk.settings.UserSettings.

UserSettings is a thin read-only facade over JarvisStorage that:
- uppercases the prefix and builds {PREFIX}_{NAME} secret keys (_key),
- exposes get() with a default-on-missing/empty fallback,
- exposes is_enabled() with truthy-string parsing and a default fallback,
- exposes get_int() with int parsing and a default-on-failure/missing fallback.

These tests patch the JarvisStorage symbol imported into the settings module so
the underlying get_secret returns controlled values, then assert the facade's
return values and the key it asks for.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from jarvis_command_sdk import UserSettings


def _settings_with_secret(value: object, prefix: str = "reminder", scope: str = "integration"):
    """Build a UserSettings whose backing storage.get_secret returns ``value``.

    Returns (settings, fake_storage, storage_cls_mock) so callers can assert on
    both the facade behavior and how JarvisStorage / get_secret were invoked.
    """
    fake_storage = MagicMock()
    fake_storage.get_secret.return_value = value
    storage_cls = MagicMock(return_value=fake_storage)
    with patch("jarvis_command_sdk.settings.JarvisStorage", storage_cls):
        settings = UserSettings(prefix, scope=scope)
    return settings, fake_storage, storage_cls


class TestInitAndKey:
    def test_init_uppercases_prefix_and_builds_storage(self) -> None:
        # Lines 34-35: prefix uppercased, JarvisStorage constructed with
        # the raw prefix and secret_scope kwarg.
        _, _, storage_cls = _settings_with_secret(None, prefix="reminder", scope="user")
        storage_cls.assert_called_once_with("reminder", secret_scope="user")

    def test_default_scope_is_integration(self) -> None:
        _, _, storage_cls = _settings_with_secret(None, prefix="weather")
        storage_cls.assert_called_once_with("weather", secret_scope="integration")

    def test_key_builds_upper_snake_key(self) -> None:
        # Line 39: f"{self._prefix}_{name.upper()}".
        settings, _, _ = _settings_with_secret(None, prefix="reminder")
        assert settings._key("push_notifications") == "REMINDER_PUSH_NOTIFICATIONS"

    def test_key_uppercases_mixed_case_name(self) -> None:
        settings, _, _ = _settings_with_secret(None, prefix="Reminder")
        assert settings._key("Preferred_Theme") == "REMINDER_PREFERRED_THEME"


class TestGet:
    def test_get_returns_stored_value(self) -> None:
        # Line 48 + 51: value present -> returned as-is.
        settings, storage, _ = _settings_with_secret("dark", prefix="reminder")
        assert settings.get("preferred_theme") == "dark"
        storage.get_secret.assert_called_once_with("REMINDER_PREFERRED_THEME")

    def test_get_none_returns_default(self) -> None:
        # Lines 49-50: None -> default.
        settings, _, _ = _settings_with_secret(None)
        assert settings.get("preferred_theme", default="light") == "light"

    def test_get_empty_string_returns_default(self) -> None:
        # Line 49 (empty branch) -> 50.
        settings, _, _ = _settings_with_secret("")
        assert settings.get("preferred_theme", default="light") == "light"

    def test_get_missing_default_is_none(self) -> None:
        settings, _, _ = _settings_with_secret(None)
        assert settings.get("preferred_theme") is None


class TestIsEnabled:
    def test_true_strings_are_truthy(self) -> None:
        # Line 66: truthy parsing, case/whitespace-insensitive.
        for raw in ("true", "TRUE", "1", "yes", "ON", "  On  "):
            settings, _, _ = _settings_with_secret(raw)
            assert settings.is_enabled("push") is True, raw

    def test_false_strings_are_not_enabled(self) -> None:
        for raw in ("false", "0", "no", "off", "nope", "2"):
            settings, _, _ = _settings_with_secret(raw)
            assert settings.is_enabled("push") is False, raw

    def test_none_returns_default(self) -> None:
        # Lines 63-65: None -> default.
        settings, _, _ = _settings_with_secret(None)
        assert settings.is_enabled("push") is False
        assert settings.is_enabled("push", default=True) is True

    def test_empty_string_returns_default(self) -> None:
        settings, _, _ = _settings_with_secret("")
        assert settings.is_enabled("push", default=True) is True

    def test_is_enabled_uses_built_key(self) -> None:
        settings, storage, _ = _settings_with_secret("true", prefix="reminder")
        assert settings.is_enabled("push_notifications") is True
        storage.get_secret.assert_called_once_with("REMINDER_PUSH_NOTIFICATIONS")


class TestGetInt:
    def test_valid_int_parsed(self) -> None:
        # Lines 75 + 78-79: parse success.
        settings, _, _ = _settings_with_secret("42")
        assert settings.get_int("retry_count") == 42

    def test_negative_int_parsed(self) -> None:
        settings, _, _ = _settings_with_secret("-7")
        assert settings.get_int("offset") == -7

    def test_none_returns_default(self) -> None:
        # Lines 76-77: None -> default.
        settings, _, _ = _settings_with_secret(None)
        assert settings.get_int("retry_count", default=5) == 5

    def test_empty_string_returns_default(self) -> None:
        settings, _, _ = _settings_with_secret("")
        assert settings.get_int("retry_count", default=3) == 3

    def test_bad_int_returns_default(self) -> None:
        # Lines 80-81: ValueError on int("abc") -> default.
        settings, _, _ = _settings_with_secret("abc")
        assert settings.get_int("retry_count", default=9) == 9

    def test_bad_int_default_zero(self) -> None:
        settings, _, _ = _settings_with_secret("not-a-number")
        assert settings.get_int("retry_count") == 0

    def test_float_string_returns_default(self) -> None:
        # int("1.5") raises ValueError -> default branch.
        settings, _, _ = _settings_with_secret("1.5")
        assert settings.get_int("retry_count", default=11) == 11
