"""Tests for the command-data browser SDK additions: FieldSpec, RecordSummary,
DataBrowserMode, and the IJarvisCommand methods that surface them."""

from __future__ import annotations

import pytest

from jarvis_command_sdk import (
    CommandExample,
    CommandResponse,
    DataBrowserMode,
    FieldSpec,
    IJarvisCommand,
    RecordSummary,
)


# ── Test fixtures ──────────────────────────────────────────────────────────


class _MinimalCommand(IJarvisCommand):
    """Bare-bones command that doesn't override any browser methods."""

    @property
    def command_name(self) -> str:
        return "minimal"

    @property
    def description(self) -> str:
        return "A minimal command"

    @property
    def parameters(self):
        return []

    @property
    def required_secrets(self):
        return []

    @property
    def keywords(self):
        return ["minimal"]

    def generate_prompt_examples(self):
        return [CommandExample("do it", {}, is_primary=True)]

    def generate_adapter_examples(self):
        return self.generate_prompt_examples()

    def run(self, request_info, **kwargs):
        return CommandResponse.success_response({})


class _ReminderLikeCommand(_MinimalCommand):
    """Overrides browser methods like the real ReminderCommand pilot does."""

    @property
    def command_name(self) -> str:
        return "set_reminder"

    def editable_fields(self):
        return [
            FieldSpec("reminder_id", "id", label="ID", editable=False),
            FieldSpec("text", "string", label="What", required=True),
            FieldSpec("due_at", "datetime", label="When", required=True),
            FieldSpec(
                "recurrence",
                "enum",
                label="Repeat",
                enum_values=["daily", "weekdays", "weekly"],
            ),
        ]

    def display_summary(self, record):
        return RecordSummary(
            title=record["text"],
            subtitle=record.get("due_at"),
            icon="bell",
        )


class _OptedOutCommand(_MinimalCommand):
    @property
    def data_browser_mode(self) -> DataBrowserMode:
        return "disabled"


# ── FieldSpec tests ─────────────────────────────────────────────────────────


class TestFieldSpec:
    def test_minimal_creation(self):
        spec = FieldSpec("name", "string")
        assert spec.name == "name"
        assert spec.type == "string"
        assert spec.editable is True
        assert spec.required is False
        assert spec.label is None
        assert spec.enum_values is None

    def test_to_dict_strips_defaults(self):
        spec = FieldSpec("name", "string")
        d = spec.to_dict()
        # Only required (non-default) keys present
        assert d == {"name": "name", "type": "string"}

    def test_to_dict_includes_overrides(self):
        spec = FieldSpec(
            "due_at",
            "datetime",
            label="When",
            required=True,
            editable=False,
            description="When the reminder fires",
            placeholder="YYYY-MM-DD HH:MM",
        )
        d = spec.to_dict()
        assert d["label"] == "When"
        assert d["required"] is True
        assert d["editable"] is False
        assert d["description"] == "When the reminder fires"
        assert d["placeholder"] == "YYYY-MM-DD HH:MM"

    def test_enum_values_round_trip(self):
        spec = FieldSpec("color", "enum", enum_values=["red", "blue"])
        d = spec.to_dict()
        assert d["enum_values"] == ["red", "blue"]
        parsed = FieldSpec.from_dict(d)
        assert parsed.enum_values == ["red", "blue"]

    def test_array_item_type(self):
        spec = FieldSpec("tags", "array", item_type="string")
        d = spec.to_dict()
        assert d["item_type"] == "string"
        parsed = FieldSpec.from_dict(d)
        assert parsed.item_type == "string"

    def test_nested_object_fields(self):
        spec = FieldSpec(
            "address",
            "object",
            fields=[
                FieldSpec("street", "string"),
                FieldSpec("zip", "string"),
            ],
        )
        d = spec.to_dict()
        assert len(d["fields"]) == 2
        assert d["fields"][0] == {"name": "street", "type": "string"}

        parsed = FieldSpec.from_dict(d)
        assert parsed.fields is not None
        assert len(parsed.fields) == 2
        assert parsed.fields[1].name == "zip"

    def test_array_of_objects_reuses_fields(self):
        # Documented dual-meaning: for array of objects, `fields` describes
        # the element schema.
        spec = FieldSpec(
            "stops",
            "array",
            item_type="object",
            fields=[FieldSpec("address", "string"), FieldSpec("time", "time")],
        )
        d = spec.to_dict()
        assert d["item_type"] == "object"
        assert len(d["fields"]) == 2

    def test_from_dict_ignores_unknown_keys(self):
        # Forward-compat: a newer SDK might add `min_value`. Older parse
        # should drop it cleanly, not raise.
        d = {
            "name": "score",
            "type": "int",
            "min_value": 0,
            "max_value": 100,
            "some_future_key": {"nested": True},
        }
        spec = FieldSpec.from_dict(d)
        assert spec.name == "score"
        assert spec.type == "int"

    def test_from_dict_requires_name_and_type(self):
        with pytest.raises(KeyError):
            FieldSpec.from_dict({"name": "x"})
        with pytest.raises(KeyError):
            FieldSpec.from_dict({"type": "string"})

    def test_unknown_type_string_is_preserved(self):
        # Forward-compat: a future type like "phone_number" should round-trip.
        spec = FieldSpec("phone", "phone_number")
        d = spec.to_dict()
        parsed = FieldSpec.from_dict(d)
        assert parsed.type == "phone_number"


# ── RecordSummary tests ─────────────────────────────────────────────────────


class TestRecordSummary:
    def test_minimal(self):
        summary = RecordSummary(title="Buy milk")
        assert summary.title == "Buy milk"
        assert summary.subtitle is None
        assert summary.icon == "information-outline"

    def test_with_subtitle_and_icon(self):
        summary = RecordSummary(
            title="Buy milk", subtitle="6 PM tomorrow", icon="bell"
        )
        d = summary.to_dict()
        assert d["title"] == "Buy milk"
        assert d["subtitle"] == "6 PM tomorrow"
        assert d["icon"] == "bell"

    def test_to_dict_preserves_none_subtitle(self):
        summary = RecordSummary(title="Buy milk")
        d = summary.to_dict()
        assert d["subtitle"] is None


# ── IJarvisCommand defaults ────────────────────────────────────────────────


class TestCommandBrowserDefaults:
    def test_default_mode_is_enabled(self):
        cmd = _MinimalCommand()
        assert cmd.data_browser_mode == "enabled"

    def test_default_editable_fields_is_empty(self):
        cmd = _MinimalCommand()
        assert cmd.editable_fields() == []

    def test_default_display_summary_uses_first_string_value(self):
        cmd = _MinimalCommand()
        summary = cmd.display_summary(
            {"id": 1, "name": "Alice", "count": 5}
        )
        assert summary.title == "Alice"
        assert summary.subtitle is None
        assert summary.icon == "information-outline"

    def test_default_display_summary_falls_back_to_command_name(self):
        cmd = _MinimalCommand()
        # No string values at all in the record
        summary = cmd.display_summary({"count": 42, "flag": True})
        assert summary.title == "minimal"

    def test_default_display_summary_skips_empty_strings(self):
        cmd = _MinimalCommand()
        summary = cmd.display_summary({"a": "", "b": "real"})
        assert summary.title == "real"


# ── IJarvisCommand overrides (pilot) ────────────────────────────────────────


class TestCommandBrowserOverrides:
    def test_reminder_like_schema(self):
        cmd = _ReminderLikeCommand()
        fields = cmd.editable_fields()
        names = [f.name for f in fields]
        assert names == ["reminder_id", "text", "due_at", "recurrence"]

        id_field = fields[0]
        assert id_field.editable is False
        assert id_field.type == "id"

        recurrence = fields[3]
        assert recurrence.enum_values == ["daily", "weekdays", "weekly"]

    def test_reminder_like_display_summary(self):
        cmd = _ReminderLikeCommand()
        summary = cmd.display_summary(
            {"text": "Take out trash", "due_at": "2026-06-04T18:00:00Z"}
        )
        assert summary.title == "Take out trash"
        assert summary.subtitle == "2026-06-04T18:00:00Z"
        assert summary.icon == "bell"

    def test_opt_out(self):
        cmd = _OptedOutCommand()
        assert cmd.data_browser_mode == "disabled"
