"""Regression tests for the ``Alert`` dataclass.

``Alert.to_dict`` / ``Alert.is_expired`` shipped broken to prod once: call
sites that passed only the core fields blew up because ``created_at`` /
``expires_at`` had no defaults, and ``to_dict`` must emit JSON-serializable
ISO strings (not raw ``datetime`` objects) for the inbox/notification path.
These tests pin the fixed behavior so it cannot silently regress again.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

from jarvis_command_sdk import Alert


CORE_FIELDS = {
    "source_agent": "weather-agent",
    "title": "Severe storm warning",
    "summary": "High winds expected in the next hour.",
}


class TestAlertConstruction:
    def test_core_fields_only_construct(self) -> None:
        # The original bug: created_at/expires_at had no defaults, so this
        # three-arg call site raised TypeError. Guard against that regression.
        alert = Alert(**CORE_FIELDS)
        assert alert.source_agent == "weather-agent"
        assert alert.title == "Severe storm warning"
        assert alert.summary == "High winds expected in the next hour."

    def test_priority_defaults_to_medium(self) -> None:
        assert Alert(**CORE_FIELDS).priority == 2

    def test_id_defaults_to_unique_uuid_string(self) -> None:
        a = Alert(**CORE_FIELDS)
        b = Alert(**CORE_FIELDS)
        assert isinstance(a.id, str)
        # Parses as a UUID and is unique per instance.
        uuid.UUID(a.id)
        assert a.id != b.id

    def test_timestamps_default_to_aware_utc(self) -> None:
        before = datetime.now(timezone.utc)
        alert = Alert(**CORE_FIELDS)
        after = datetime.now(timezone.utc)

        assert alert.created_at.tzinfo is not None
        assert alert.expires_at.tzinfo is not None
        assert before <= alert.created_at <= after

    def test_default_ttl_is_one_hour(self) -> None:
        alert = Alert(**CORE_FIELDS)
        ttl = alert.expires_at - alert.created_at
        # Two separate default_factory calls; allow tiny scheduling slack.
        assert abs(ttl - timedelta(hours=1)) < timedelta(seconds=1)

    def test_explicit_values_are_preserved(self) -> None:
        created = datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc)
        expires = datetime(2026, 6, 20, 18, 0, tzinfo=timezone.utc)
        alert = Alert(
            source_agent="a",
            title="t",
            summary="s",
            priority=3,
            created_at=created,
            expires_at=expires,
            id="fixed-id",
        )
        assert alert.priority == 3
        assert alert.created_at == created
        assert alert.expires_at == expires
        assert alert.id == "fixed-id"


class TestAlertIsExpired:
    def test_is_expired_is_a_bool_property_not_a_method(self) -> None:
        # Accessing .is_expired must yield a bool, not a bound method
        # (a method object is always truthy and would mask expiry logic).
        assert isinstance(Alert(**CORE_FIELDS).is_expired, bool)

    def test_fresh_alert_with_default_ttl_is_not_expired(self) -> None:
        assert Alert(**CORE_FIELDS).is_expired is False

    def test_past_expiry_is_expired(self) -> None:
        past = datetime.now(timezone.utc) - timedelta(minutes=1)
        alert = Alert(**CORE_FIELDS, expires_at=past)
        assert alert.is_expired is True

    def test_future_expiry_is_not_expired(self) -> None:
        future = datetime.now(timezone.utc) + timedelta(hours=2)
        alert = Alert(**CORE_FIELDS, expires_at=future)
        assert alert.is_expired is False


class TestAlertToDict:
    def test_contains_all_public_fields(self) -> None:
        d = Alert(**CORE_FIELDS).to_dict()
        assert set(d) == {
            "id",
            "source_agent",
            "title",
            "summary",
            "priority",
            "created_at",
            "expires_at",
        }

    def test_timestamps_serialize_as_iso_strings(self) -> None:
        # The regression: to_dict must emit ISO strings, never raw datetimes,
        # so the dict survives json.dumps on the notification/inbox path.
        d = Alert(**CORE_FIELDS).to_dict()
        assert isinstance(d["created_at"], str)
        assert isinstance(d["expires_at"], str)

    def test_output_is_json_serializable(self) -> None:
        payload = json.dumps(Alert(**CORE_FIELDS).to_dict())
        assert isinstance(payload, str)

    def test_iso_strings_round_trip_to_original_datetimes(self) -> None:
        created = datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc)
        expires = datetime(2026, 6, 20, 18, 0, tzinfo=timezone.utc)
        d = Alert(**CORE_FIELDS, created_at=created, expires_at=expires).to_dict()
        assert datetime.fromisoformat(d["created_at"]) == created
        assert datetime.fromisoformat(d["expires_at"]) == expires

    def test_scalar_fields_pass_through_unchanged(self) -> None:
        alert = Alert(**CORE_FIELDS, priority=1, id="abc")
        d = alert.to_dict()
        assert d["id"] == "abc"
        assert d["source_agent"] == "weather-agent"
        assert d["title"] == "Severe storm warning"
        assert d["summary"] == "High winds expected in the next hour."
        assert d["priority"] == 1
