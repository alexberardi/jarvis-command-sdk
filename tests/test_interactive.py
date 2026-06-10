"""Tests for the Interactive List v1 payload builders (interactive.py)."""

from __future__ import annotations

import json

import pytest

from jarvis_command_sdk import (
    InteractiveAction,
    InteractiveList,
    InteractiveRow,
    InteractiveRowAction,
    InteractiveSection,
    RequiresRecordField,
)


# ── Test fixtures ──────────────────────────────────────────────────────────


WALMART_PATTERN = r"/ip/(?:[^/]+/)?(\d{5,})"


def _walmart_row(key: str = "milk", label: str = "milk") -> InteractiveRow:
    """The contract's reference row: gate + 2 webview_pick actions + stepper."""
    return InteractiveRow(
        key=key,
        label=label,
        control="checkbox_stepper",
        default_selected=True,
        default_quantity=2,
        disabled_caption="No Walmart match",
        requires_record_field=RequiresRecordField(
            command_name="export_shopping_list",
            field="walmart_item_id",
            field_label="ID",
        ),
        row_actions=[
            InteractiveRowAction(
                label="Find ID",
                start_url="https://www.walmart.com/search?q={label}",
                pattern=WALMART_PATTERN,
                save_command_name="export_shopping_list",
                save_field="walmart_item_id",
            ),
            InteractiveRowAction(
                label="View",
                start_url="https://www.walmart.com/ip/{value}",
                pattern=WALMART_PATTERN,
                save_command_name="export_shopping_list",
                save_field="walmart_item_id",
            ),
        ],
    )


def _payload(**overrides) -> InteractiveList:
    kwargs: dict = dict(
        command_name="export_shopping_list",
        sections=[InteractiveSection(rows=[_walmart_row()], title="Regulars")],
        actions=[InteractiveAction(label="Export {n} items", callback="export_selected", style="primary")],
        title_override="Shopping list — 7 items",
        empty_text="Nothing to export",
        context={"provider": "walmart"},
    )
    kwargs.update(overrides)
    return InteractiveList(**kwargs)


def _rows(n: int) -> list[InteractiveRow]:
    return [InteractiveRow(key=f"row-{i}", label=f"Row {i}") for i in range(n)]


# ── Happy path ───────────────────────────────────────────────────────────────


class TestHappyPath:
    def test_full_payload_matches_contract_shape(self):
        d = _payload().to_dict()
        assert d == {
            "type": "interactive_list",
            "version": 1,
            "command_name": "export_shopping_list",
            "title_override": "Shopping list — 7 items",
            "empty_text": "Nothing to export",
            "context": {"provider": "walmart"},
            "sections": [
                {
                    "title": "Regulars",
                    "rows": [
                        {
                            "key": "milk",
                            "label": "milk",
                            "control": "checkbox_stepper",
                            "default": {"selected": True, "quantity": 2},
                            "disabled_caption": "No Walmart match",
                            "requires_record_field": {
                                "command_name": "export_shopping_list",
                                "field": "walmart_item_id",
                                "field_label": "ID",
                            },
                            "row_actions": [
                                {
                                    "label": "Find ID",
                                    "type": "webview_pick",
                                    "start_url": "https://www.walmart.com/search?q={label}",
                                    "pattern": WALMART_PATTERN,
                                    "save": {
                                        "command_name": "export_shopping_list",
                                        "field": "walmart_item_id",
                                    },
                                },
                                {
                                    "label": "View",
                                    "type": "webview_pick",
                                    "start_url": "https://www.walmart.com/ip/{value}",
                                    "pattern": WALMART_PATTERN,
                                    "save": {
                                        "command_name": "export_shopping_list",
                                        "field": "walmart_item_id",
                                    },
                                },
                            ],
                        }
                    ],
                }
            ],
            "actions": [
                {"label": "Export {n} items", "callback": "export_selected", "style": "primary"},
            ],
        }

    def test_payload_round_trips_through_json(self):
        d = _payload().to_dict()
        assert json.loads(json.dumps(d)) == d

    def test_class_constants(self):
        assert InteractiveList.CATEGORY == "interactive_list"
        assert InteractiveList.VERSION == 1

    def test_caption_emitted_when_set(self):
        row = InteractiveRow(key="k", label="L", caption="static caption")
        assert row.to_dict()["caption"] == "static caption"

    def test_empty_section_renders_rows_key(self):
        # Producers ship one untitled empty section so empty_text renders.
        payload = InteractiveList(
            command_name="cmd",
            sections=[InteractiveSection(rows=[])],
            actions=[InteractiveAction(label="OK", callback="ok")],
        )
        assert payload.to_dict()["sections"] == [{"rows": []}]


# ── Validation: InteractiveList ──────────────────────────────────────────────


class TestListValidation:
    def test_empty_command_name(self):
        with pytest.raises(ValueError, match="command_name"):
            _payload(command_name="")

    def test_zero_sections(self):
        with pytest.raises(ValueError, match="sections"):
            _payload(sections=[])

    def test_more_than_six_sections(self):
        sections = [InteractiveSection(rows=[]) for _ in range(7)]
        with pytest.raises(ValueError, match="sections.*1\\.\\.6"):
            _payload(sections=sections)

    def test_more_than_100_total_rows(self):
        sections = [
            InteractiveSection(rows=_rows(51), title="A"),
            InteractiveSection(
                rows=[InteractiveRow(key=f"b-{i}", label=f"B {i}") for i in range(50)],
                title="B",
            ),
        ]
        with pytest.raises(ValueError, match="100 rows total"):
            _payload(sections=sections)

    def test_exactly_100_rows_allowed(self):
        payload = _payload(sections=[InteractiveSection(rows=_rows(100))])
        assert len(payload.to_dict()["sections"][0]["rows"]) == 100

    def test_zero_actions(self):
        with pytest.raises(ValueError, match="actions"):
            _payload(actions=[])

    def test_more_than_six_actions(self):
        actions = [InteractiveAction(label=f"A{i}", callback=f"cb_{i}") for i in range(7)]
        with pytest.raises(ValueError, match="actions.*1\\.\\.6"):
            _payload(actions=actions)

    def test_duplicate_row_keys_across_sections(self):
        sections = [
            InteractiveSection(rows=[InteractiveRow(key="milk", label="milk")], title="Regulars"),
            InteractiveSection(rows=[InteractiveRow(key="milk", label="milk again")], title="One-offs"),
        ]
        with pytest.raises(ValueError, match="duplicate row key 'milk'"):
            _payload(sections=sections)

    def test_duplicate_row_keys_within_section(self):
        sections = [InteractiveSection(rows=[InteractiveRow(key="x", label="a"), InteractiveRow(key="x", label="b")])]
        with pytest.raises(ValueError, match="duplicate row key 'x'"):
            _payload(sections=sections)


# ── Validation: InteractiveRow ───────────────────────────────────────────────


class TestRowValidation:
    def test_empty_key(self):
        with pytest.raises(ValueError, match="'key'"):
            InteractiveRow(key="", label="milk")

    def test_empty_label(self):
        with pytest.raises(ValueError, match="'milk'.*'label'"):
            InteractiveRow(key="milk", label="")

    def test_label_over_120_chars(self):
        with pytest.raises(ValueError, match="'milk'.*'label'.*120"):
            InteractiveRow(key="milk", label="x" * 121)

    def test_label_exactly_120_chars_allowed(self):
        InteractiveRow(key="milk", label="x" * 120)

    def test_caption_over_200_chars(self):
        with pytest.raises(ValueError, match="'milk'.*'caption'.*200"):
            InteractiveRow(key="milk", label="milk", caption="x" * 201)

    def test_disabled_caption_over_200_chars(self):
        with pytest.raises(ValueError, match="'milk'.*'disabled_caption'.*200"):
            InteractiveRow(key="milk", label="milk", disabled_caption="x" * 201)

    def test_bad_control(self):
        with pytest.raises(ValueError, match="'milk'.*'control'.*'radio'"):
            InteractiveRow(key="milk", label="milk", control="radio")

    def test_quantity_below_range(self):
        with pytest.raises(ValueError, match="'milk'.*'default_quantity'.*1\\.\\.99"):
            InteractiveRow(key="milk", label="milk", control="checkbox_stepper", default_quantity=0)

    def test_quantity_above_range(self):
        with pytest.raises(ValueError, match="'milk'.*'default_quantity'.*1\\.\\.99"):
            InteractiveRow(key="milk", label="milk", control="checkbox_stepper", default_quantity=100)

    def test_quantity_bounds_allowed(self):
        InteractiveRow(key="a", label="a", control="checkbox_stepper", default_quantity=1)
        InteractiveRow(key="b", label="b", control="checkbox_stepper", default_quantity=99)

    def test_more_than_two_row_actions(self):
        action = InteractiveRowAction(
            label="Find",
            start_url="https://example.com/search",
            pattern=WALMART_PATTERN,
            save_command_name="cmd",
            save_field="f",
        )
        with pytest.raises(ValueError, match="'milk'.*row_actions"):
            InteractiveRow(key="milk", label="milk", row_actions=[action, action, action])


# ── Validation: InteractiveRowAction ─────────────────────────────────────────


class TestRowActionValidation:
    def _kwargs(self, **overrides) -> dict:
        kwargs: dict = dict(
            label="Find ID",
            start_url="https://www.walmart.com/search?q={label}",
            pattern=WALMART_PATTERN,
            save_command_name="export_shopping_list",
            save_field="walmart_item_id",
        )
        kwargs.update(overrides)
        return kwargs

    def test_empty_label(self):
        with pytest.raises(ValueError, match="'label'"):
            InteractiveRowAction(**self._kwargs(label=""))

    def test_bad_type(self):
        with pytest.raises(ValueError, match="'type'.*webview_pick"):
            InteractiveRowAction(**self._kwargs(type="deeplink"))

    def test_non_https_start_url(self):
        with pytest.raises(ValueError, match="'start_url'.*https"):
            InteractiveRowAction(**self._kwargs(start_url="http://www.walmart.com/search"))

    def test_pattern_does_not_compile(self):
        with pytest.raises(ValueError, match="'pattern' does not compile"):
            InteractiveRowAction(**self._kwargs(pattern="(unclosed"))

    def test_pattern_without_capture_group(self):
        with pytest.raises(ValueError, match="'pattern'.*capture group"):
            InteractiveRowAction(**self._kwargs(pattern=r"/ip/(?:[^/]+/)?\d{5,}"))

    def test_empty_save_command_name(self):
        with pytest.raises(ValueError, match="'save_command_name'"):
            InteractiveRowAction(**self._kwargs(save_command_name=""))

    def test_empty_save_field(self):
        with pytest.raises(ValueError, match="'save_field'"):
            InteractiveRowAction(**self._kwargs(save_field=""))


# ── Validation: InteractiveAction / RequiresRecordField ─────────────────────


class TestActionValidation:
    def test_empty_label(self):
        with pytest.raises(ValueError, match="'label'"):
            InteractiveAction(label="", callback="go")

    def test_empty_callback(self):
        with pytest.raises(ValueError, match="'Go'.*'callback'"):
            InteractiveAction(label="Go", callback="")

    def test_bad_style(self):
        with pytest.raises(ValueError, match="'Go'.*'style'.*'link'"):
            InteractiveAction(label="Go", callback="go", style="link")

    def test_all_styles_allowed(self):
        for style in ("primary", "secondary", "destructive"):
            assert InteractiveAction(label="Go", callback="go", style=style).to_dict()["style"] == style


class TestRequiresRecordFieldValidation:
    def test_empty_command_name(self):
        with pytest.raises(ValueError, match="'command_name'"):
            RequiresRecordField(command_name="", field="walmart_item_id")

    def test_empty_field(self):
        with pytest.raises(ValueError, match="'field'"):
            RequiresRecordField(command_name="export_shopping_list", field="")


# ── Optional-field omission ──────────────────────────────────────────────────


def _assert_no_none(value) -> None:
    if isinstance(value, dict):
        for v in value.values():
            assert v is not None
            _assert_no_none(v)
    elif isinstance(value, list):
        for v in value:
            _assert_no_none(v)


class TestOptionalOmission:
    def test_minimal_row_omits_absent_optionals(self):
        d = InteractiveRow(key="k", label="Info").to_dict()
        assert d == {"key": "k", "label": "Info", "control": "none", "default": {"selected": False}}

    def test_quantity_omitted_for_control_none(self):
        d = InteractiveRow(key="k", label="L", default_selected=True).to_dict()
        assert d["default"] == {"selected": True}

    def test_quantity_omitted_for_checkbox(self):
        d = InteractiveRow(key="k", label="L", control="checkbox", default_quantity=5).to_dict()
        assert d["default"] == {"selected": False}

    def test_quantity_present_for_checkbox_stepper(self):
        d = InteractiveRow(key="k", label="L", control="checkbox_stepper", default_quantity=5).to_dict()
        assert d["default"] == {"selected": False, "quantity": 5}

    def test_minimal_payload_omits_absent_optionals(self):
        payload = InteractiveList(
            command_name="cmd",
            sections=[InteractiveSection(rows=[InteractiveRow(key="k", label="L")])],
            actions=[InteractiveAction(label="OK", callback="ok")],
        )
        d = payload.to_dict()
        for absent in ("title_override", "empty_text", "context"):
            assert absent not in d
        assert "title" not in d["sections"][0]
        row_d = d["sections"][0]["rows"][0]
        for absent in ("caption", "disabled_caption", "requires_record_field", "row_actions"):
            assert absent not in row_d

    def test_required_keys_always_emitted(self):
        payload = InteractiveList(
            command_name="cmd",
            sections=[InteractiveSection(rows=[])],
            actions=[InteractiveAction(label="OK", callback="ok")],
        )
        d = payload.to_dict()
        assert d["type"] == "interactive_list"
        assert d["version"] == 1
        assert d["command_name"] == "cmd"
        assert "sections" in d and "actions" in d

    def test_field_label_omitted_when_absent(self):
        d = RequiresRecordField(command_name="cmd", field="f").to_dict()
        assert d == {"command_name": "cmd", "field": "f"}

    def test_no_none_values_anywhere(self):
        _assert_no_none(_payload().to_dict())
        _assert_no_none(InteractiveRow(key="k", label="L").to_dict())


# ── Context passthrough ──────────────────────────────────────────────────────


class TestContext:
    def test_context_passed_through_verbatim(self):
        ctx = {"provider": "walmart", "nested": {"ids": [1, 2, 3], "flag": False}}
        d = _payload(context=ctx).to_dict()
        assert d["context"] == ctx
        assert d["context"] is ctx  # not copied or transformed

    def test_empty_context_dict_emitted(self):
        # An explicit {} is not "absent" — it survives to the wire.
        assert _payload(context={}).to_dict()["context"] == {}


# ── Forge spec integration ───────────────────────────────────────────────────


class TestForgeSpec:
    def test_supporting_classes_include_interactive_builders(self):
        from jarvis_command_sdk.forge import generate_spec

        names = set(generate_spec()["supporting_classes"])
        assert {
            "InteractiveList",
            "InteractiveSection",
            "InteractiveRow",
            "InteractiveRowAction",
            "InteractiveAction",
            "RequiresRecordField",
        } <= names

    def test_spec_markdown_mentions_interactive_list(self):
        from jarvis_command_sdk.forge import generate_spec_markdown

        md = generate_spec_markdown()
        assert "InteractiveList" in md
        assert "webview_pick" in md
