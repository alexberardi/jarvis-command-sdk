"""Interactive List payload builders — server-driven phone UI for inbox items.

A command ships an :class:`InteractiveList` payload in an inbox item's
``metadata`` (POSTed to ``{cc}/api/v0/node/inbox-item`` with
``category=InteractiveList.CATEGORY``) and the mobile app renders it on one
generic screen: sections of rows with selection controls, action buttons that
fire ``@callback`` methods carrying the collected state, and standardized
result affordances (open a URL / copy text / show a message / detail list).

All validation happens at construction time (``__post_init__``) so a malformed
payload fails in the producer's tests, not silently on the phone. ``to_dict()``
emits exactly the v1 wire format documented in the SDK CLAUDE.md
("Interactive List payloads (v1)"). Mobile parses permissively — unknown keys
are ignored and absent optionals are defaulted — so the schema can grow
additively without coordinated upgrades.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, ClassVar

# Caps shared with the mobile renderer — the SDK rejects at construction time,
# mobile re-enforces at render time (drop/truncate + one "truncated" notice).
_MAX_SECTIONS = 6
_MAX_TOTAL_ROWS = 100
_MAX_ACTIONS = 6
_MAX_ROW_ACTIONS = 2
_MAX_LABEL_LEN = 120
_MAX_CAPTION_LEN = 200

_CONTROLS = ("none", "checkbox", "checkbox_stepper")
_STYLES = ("primary", "secondary", "destructive")


@dataclass
class RequiresRecordField:
    """Live record gate for a row (the `requires_record_field` primitive).

    At load the mobile app fetches `command_name`'s records via the data
    browser API; the row is enabled iff the record whose key equals the row's
    `key` has a non-empty value for `field`. When met, the row caption becomes
    "{field_label or field}: {value}" (overriding any static caption); when
    unmet, the row renders disabled and shows the row's `disabled_caption`.
    """

    __forge_hints__ = {
        "role": "Gates a row on live record data — enabled iff the row-keyed record has a non-empty value for the field",
        "constructor": "RequiresRecordField(command_name, field, field_label=None)",
        "example": 'RequiresRecordField(command_name="export_shopping_list", field="walmart_item_id", field_label="ID")',
        "tips": [
            "The row is enabled iff the record whose key equals the row's `key` has a non-empty value for `field`",
            "When met, the row caption becomes '{field_label or field}: {value}'; when unmet the row is disabled and shows disabled_caption",
            "Records are re-fetched on every screen load, so the gate reflects live state — no stale inbox snapshots",
            "Pair with a webview_pick row action that saves to the same field so the user can satisfy the gate in place",
        ],
    }

    command_name: str
    field: str
    field_label: str | None = None

    def __post_init__(self) -> None:
        if not self.command_name or not self.command_name.strip():
            raise ValueError("RequiresRecordField 'command_name' must be a non-empty string")
        if not self.field or not self.field.strip():
            raise ValueError("RequiresRecordField 'field' must be a non-empty string")

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"command_name": self.command_name, "field": self.field}
        if self.field_label is not None:
            d["field_label"] = self.field_label
        return d


@dataclass
class InteractiveRowAction:
    """A text button on a row — v1 has exactly one type: ``webview_pick``.

    Opens a WebView at `start_url`; while the user browses, every navigation
    URL is matched against `pattern` (capture group 1 = the detected value).
    On confirm, mobile PATCHes ``{save_field: value}`` onto the record
    (`save_command_name` + row `key`), which satisfies a RequiresRecordField
    gate on the same field.
    """

    __forge_hints__ = {
        "role": "webview_pick row button: user browses a website, a URL regex captures a value, mobile saves it onto the row's record",
        "constructor": 'InteractiveRowAction(label, start_url, pattern, save_command_name, save_field, type="webview_pick")',
        "example": (
            'InteractiveRowAction(label="Find ID", start_url="https://www.walmart.com/search?q={label}", '
            'pattern=r"/ip/(?:[^/]+/)?(\\d{5,})", save_command_name="export_shopping_list", save_field="walmart_item_id")'
        ),
        "tips": [
            "start_url must be https:// and supports two substitutions: {label} (URL-encoded row label, for search seeding) "
            "and {value} (current value of save_field — actions whose start_url uses {value} are hidden until a value exists)",
            "pattern is matched against every URL the WebView navigates to; capture group 1 is the picked value, "
            "so the regex MUST contain at least one capture group",
            "On confirm, mobile PATCHes {save_field: <value>} onto the record (save_command_name + row key) — "
            "pair with a RequiresRecordField gate on the same field so picking a value enables the row",
            "Keep the regex JS-compatible (mobile runs it with new RegExp); avoid Python-only syntax like (?P<name>...)",
            "At most 2 row_actions per row",
        ],
    }

    label: str
    start_url: str
    pattern: str
    save_command_name: str
    save_field: str
    type: str = "webview_pick"

    def __post_init__(self) -> None:
        if not self.label or not self.label.strip():
            raise ValueError("InteractiveRowAction 'label' must be a non-empty string")
        if self.type != "webview_pick":
            raise ValueError(
                f"InteractiveRowAction '{self.label}': 'type' must be 'webview_pick' (the only v1 type), got '{self.type}'"
            )
        if not self.start_url.startswith("https://"):
            raise ValueError(
                f"InteractiveRowAction '{self.label}': 'start_url' must start with 'https://', got '{self.start_url}'"
            )
        try:
            compiled = re.compile(self.pattern)
        except re.error as e:
            raise ValueError(f"InteractiveRowAction '{self.label}': 'pattern' does not compile: {e}") from e
        if compiled.groups < 1:
            raise ValueError(
                f"InteractiveRowAction '{self.label}': 'pattern' must have at least one capture group "
                f"(group 1 is the picked value)"
            )
        if not self.save_command_name or not self.save_command_name.strip():
            raise ValueError(f"InteractiveRowAction '{self.label}': 'save_command_name' must be a non-empty string")
        if not self.save_field or not self.save_field.strip():
            raise ValueError(f"InteractiveRowAction '{self.label}': 'save_field' must be a non-empty string")

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "type": self.type,
            "start_url": self.start_url,
            "pattern": self.pattern,
            "save": {"command_name": self.save_command_name, "field": self.save_field},
        }


@dataclass
class InteractiveRow:
    """One list row: a label with an optional selection control, gate, and buttons.

    `key` is the callback identifier — unique across the whole payload.
    Selected rows arrive in callbacks as ``{key, quantity?}`` (quantity only
    for ``checkbox_stepper`` rows, clamped 1–99 by the renderer).
    """

    __forge_hints__ = {
        "role": "One list row: a label with an optional selection control, record gate, and webview_pick buttons",
        "constructor": (
            'InteractiveRow(key, label, caption=None, control="none", default_selected=False, default_quantity=1, '
            "disabled_caption=None, requires_record_field=None, row_actions=None)"
        ),
        "allowed_controls": ["none", "checkbox", "checkbox_stepper"],
        "example": (
            'InteractiveRow(key="milk", label="milk", control="checkbox_stepper", default_selected=True, '
            'default_quantity=2, disabled_caption="No Walmart match", '
            'requires_record_field=RequiresRecordField("export_shopping_list", "walmart_item_id", field_label="ID"))'
        ),
        "tips": [
            "key is the callback identifier — unique across the whole payload; selected rows arrive as {key, quantity?}",
            "Three controls in v1: 'none' (info row, never selectable), 'checkbox' (toggle), "
            "'checkbox_stepper' (toggle + 1-99 quantity stepper seeded from default_quantity)",
            "quantity is sent in callbacks only for checkbox_stepper rows",
            "requires_record_field gates the row on live record data; when unmet the row renders disabled with disabled_caption",
            "row_actions (max 2) are text buttons; the only v1 type is webview_pick",
            "label max 120 chars, caption/disabled_caption max 200 chars — rejected here, truncated on mobile",
            "All text renders as plain text on mobile — no HTML/markdown",
        ],
    }

    key: str
    label: str
    caption: str | None = None
    control: str = "none"
    default_selected: bool = False
    default_quantity: int = 1
    disabled_caption: str | None = None
    requires_record_field: RequiresRecordField | None = None
    row_actions: list[InteractiveRowAction] | None = None

    def __post_init__(self) -> None:
        if not self.key or not self.key.strip():
            raise ValueError("InteractiveRow 'key' must be a non-empty string")
        if not self.label or not self.label.strip():
            raise ValueError(f"InteractiveRow '{self.key}': 'label' must be a non-empty string")
        if len(self.label) > _MAX_LABEL_LEN:
            raise ValueError(
                f"InteractiveRow '{self.key}': 'label' must be at most {_MAX_LABEL_LEN} characters, got {len(self.label)}"
            )
        if self.caption is not None and len(self.caption) > _MAX_CAPTION_LEN:
            raise ValueError(
                f"InteractiveRow '{self.key}': 'caption' must be at most {_MAX_CAPTION_LEN} characters, got {len(self.caption)}"
            )
        if self.disabled_caption is not None and len(self.disabled_caption) > _MAX_CAPTION_LEN:
            raise ValueError(
                f"InteractiveRow '{self.key}': 'disabled_caption' must be at most {_MAX_CAPTION_LEN} characters, "
                f"got {len(self.disabled_caption)}"
            )
        if self.control not in _CONTROLS:
            raise ValueError(
                f"InteractiveRow '{self.key}': 'control' must be one of {', '.join(_CONTROLS)}, got '{self.control}'"
            )
        if not isinstance(self.default_quantity, int) or isinstance(self.default_quantity, bool) or not (
            1 <= self.default_quantity <= 99
        ):
            raise ValueError(
                f"InteractiveRow '{self.key}': 'default_quantity' must be an int in 1..99, got {self.default_quantity!r}"
            )
        if self.row_actions is not None and len(self.row_actions) > _MAX_ROW_ACTIONS:
            raise ValueError(
                f"InteractiveRow '{self.key}': at most {_MAX_ROW_ACTIONS} 'row_actions' per row, got {len(self.row_actions)}"
            )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"key": self.key, "label": self.label}
        if self.caption is not None:
            d["caption"] = self.caption
        d["control"] = self.control
        default: dict[str, Any] = {"selected": self.default_selected}
        if self.control == "checkbox_stepper":
            default["quantity"] = self.default_quantity
        d["default"] = default
        if self.disabled_caption is not None:
            d["disabled_caption"] = self.disabled_caption
        if self.requires_record_field is not None:
            d["requires_record_field"] = self.requires_record_field.to_dict()
        if self.row_actions is not None:
            d["row_actions"] = [a.to_dict() for a in self.row_actions]
        return d


@dataclass
class InteractiveSection:
    """A titled (or untitled) group of rows inside an InteractiveList."""

    __forge_hints__ = {
        "role": "A titled (or untitled) group of rows inside an InteractiveList",
        "constructor": "InteractiveSection(rows, title=None)",
        "example": 'InteractiveSection(rows=[InteractiveRow(key="milk", label="milk")], title="Regulars")',
        "tips": [
            "title=None renders an untitled flat list",
            "Only ship non-empty sections; a payload whose sections contain zero rows total renders empty_text instead",
            "An InteractiveList holds 1-6 sections with at most 100 rows total",
        ],
    }

    rows: list[InteractiveRow]
    title: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        if self.title is not None:
            d["title"] = self.title
        d["rows"] = [r.to_dict() for r in self.rows]
        return d


@dataclass
class InteractiveAction:
    """A bottom action button — fires a ``@callback`` with the collected selection.

    Every action sends the SAME collected state ``{action, selected, context}``
    to its named callback on the payload's `command_name`; callbacks ignore
    what they don't need.
    """

    __forge_hints__ = {
        "role": "A bottom action button — fires a @callback on the payload's command with the collected selection",
        "constructor": 'InteractiveAction(label, callback, style="primary")',
        "allowed_styles": ["primary", "secondary", "destructive"],
        "example": 'InteractiveAction(label="Export {n} items", callback="export_selected", style="primary")',
        "tips": [
            "{n} in the label substitutes the live selection count on mobile",
            "Every action sends the SAME collected state {action, selected, context} to its named @callback — "
            "callbacks ignore what they don't need",
            "1-2 actions render side by side; 3 or more stack vertically (max 6)",
            "styles: primary (contained), secondary (outlined), destructive (contained with error color)",
        ],
    }

    label: str
    callback: str
    style: str = "primary"

    def __post_init__(self) -> None:
        if not self.label or not self.label.strip():
            raise ValueError("InteractiveAction 'label' must be a non-empty string")
        if not self.callback or not self.callback.strip():
            raise ValueError(f"InteractiveAction '{self.label}': 'callback' must be a non-empty string")
        if self.style not in _STYLES:
            raise ValueError(
                f"InteractiveAction '{self.label}': 'style' must be one of {', '.join(_STYLES)}, got '{self.style}'"
            )

    def to_dict(self) -> dict[str, Any]:
        return {"label": self.label, "callback": self.callback, "style": self.style}


@dataclass
class InteractiveList:
    """The interactive_list v1 payload — ship it in an inbox item's ``metadata``.

    Producers POST an inbox item with ``category=InteractiveList.CATEGORY`` and
    ``metadata=payload.to_dict()``; the command center injects
    ``metadata.node_id`` server-side (never set it yourself). Each action
    button fires a ``@callback`` on `command_name` with
    ``data={action, selected, context}``; the callback's
    ``CommandResponse.context_data`` may carry the result affordances
    `message`, `url`, `text`, and `detail_lines`.
    """

    __forge_hints__ = {
        "role": "Server-driven phone UI: an interactive list payload shipped in an inbox item's metadata",
        "constructor": "InteractiveList(command_name, sections, actions, title_override=None, empty_text=None, context=None)",
        "example": (
            'InteractiveList(command_name="export_shopping_list", '
            'sections=[InteractiveSection(rows=rows, title="Regulars")], '
            'actions=[InteractiveAction(label="Export {n} items", callback="export_selected")], '
            'context={"provider": "walmart"}, empty_text="Nothing to export")'
        ),
        "tips": [
            "POST the payload as the inbox item's metadata with category=InteractiveList.CATEGORY — "
            "mobile routes on the category and renders the generic screen",
            "command_name targets YOUR command: every action button fires a @callback on it with "
            "data={action, selected, context}",
            "Caps (validated here, re-enforced on mobile): max 6 sections, max 100 rows total, max 6 actions, "
            "max 2 row_actions per row, label max 120 chars, captions max 200 chars",
            "context is an opaque dict echoed verbatim in every callback — use it to carry producer state "
            "(e.g. which provider) without a record round-trip",
            "If the list can be empty, ship one untitled empty section and set empty_text — "
            "mobile renders it centered and hides the action bar",
            "Callback results render from CommandResponse.context_data: 'message' (body text), "
            "'url' (auto-open + 'Open link' button), 'text' (monospace block + copy-to-clipboard), "
            "'detail_lines' (checkmarked list of strings). Use at most one of url/text",
            "All strings render as plain text on mobile — no HTML/markdown",
        ],
    }

    CATEGORY: ClassVar[str] = "interactive_list"
    VERSION: ClassVar[int] = 1

    command_name: str
    sections: list[InteractiveSection]
    actions: list[InteractiveAction]
    title_override: str | None = None
    empty_text: str | None = None
    context: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.command_name or not self.command_name.strip():
            raise ValueError("InteractiveList 'command_name' must be a non-empty string")
        if not 1 <= len(self.sections) <= _MAX_SECTIONS:
            raise ValueError(
                f"InteractiveList 'sections' must contain 1..{_MAX_SECTIONS} sections, got {len(self.sections)}"
            )
        if not 1 <= len(self.actions) <= _MAX_ACTIONS:
            raise ValueError(f"InteractiveList 'actions' must contain 1..{_MAX_ACTIONS} actions, got {len(self.actions)}")
        total_rows = sum(len(s.rows) for s in self.sections)
        if total_rows > _MAX_TOTAL_ROWS:
            raise ValueError(
                f"InteractiveList 'sections' must contain at most {_MAX_TOTAL_ROWS} rows total, got {total_rows}"
            )
        seen_keys: set[str] = set()
        for section in self.sections:
            for row in section.rows:
                if row.key in seen_keys:
                    raise ValueError(
                        f"InteractiveList: duplicate row key '{row.key}' — row keys must be unique across all sections"
                    )
                seen_keys.add(row.key)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "type": self.CATEGORY,
            "version": self.VERSION,
            "command_name": self.command_name,
        }
        if self.title_override is not None:
            d["title_override"] = self.title_override
        if self.empty_text is not None:
            d["empty_text"] = self.empty_text
        if self.context is not None:
            d["context"] = self.context
        d["sections"] = [s.to_dict() for s in self.sections]
        d["actions"] = [a.to_dict() for a in self.actions]
        return d
