"""Schema spec for command-data browser fields.

A FieldSpec describes one editable (or read-only) field inside a record stored
by a command via JarvisStorage. Commands declare a list of FieldSpecs via
IJarvisCommand.editable_fields(); the mobile app uses these to render a
structured form instead of a raw JSON tree.

The wire format is intentionally permissive: `type` is a free-form string
(not an Enum) so new field types can ship in the SDK and become available to
older command-center / mobile builds without coordinated upgrades. Mobile
falls back to a text input for unrecognised types.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class FieldSpec:
    """One field in a command-data record's editable schema.

    Attributes:
        name: JSON key in the stored record (e.g. "due_at").
        type: Widget hint. Initial vocabulary:
            "string", "text", "int", "float", "bool", "enum", "datetime",
            "date", "time", "duration", "array", "object", "id", "user_ref".
            Unknown values render as a plain text input on mobile.
        label: Display label; if None, mobile falls back to `name`.
        description: Helper text rendered under the field.
        editable: When False the field renders as a read-only display row.
            The record's primary key (`data_key`) is always treated as
            non-editable by the node regardless of this flag.
        create_only: When True the field is settable while CREATING a new
            record but read-only when editing an existing one. Use for fields
            that pin a record's identity/scope at birth and must not change
            afterwards — e.g. a medication's `scope` (personal vs household),
            which decides ownership and would re-expose a private record if
            re-scoped later. `create_only` fields are typically also
            `editable=False` (so the edit form leaves them read-only); the
            create form and the node's create op honour them, the update op
            ignores them.
        required: Whether the field must be present after edit. The mobile
            form enforces presence; the node treats this advisorily and
            relies on the command's own validation for hard rejection.
        enum_values: Allowed values when type="enum" (string-only for now).
        item_type: Element type when type="array".
        fields: Nested schema. Used for type="object" and also for
            type="array" + item_type="object" (one nested schema for the
            element). When both are present, this list describes the
            object's fields.
        placeholder: Optional hint shown in empty inputs on mobile.
    """

    name: str
    type: str
    label: str | None = None
    description: str | None = None
    editable: bool = True
    required: bool = False
    enum_values: list[str] | None = None
    item_type: str | None = None
    fields: list["FieldSpec"] | None = None
    placeholder: str | None = None
    create_only: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialise for the MQTT/REST wire format.

        Only includes non-default values so the payload stays compact and
        additions stay additive (consumers ignore unknown keys; absent keys
        get the FieldSpec.from_dict() default).
        """
        d: dict[str, Any] = {"name": self.name, "type": self.type}
        if self.label is not None:
            d["label"] = self.label
        if self.description is not None:
            d["description"] = self.description
        if not self.editable:
            d["editable"] = False
        if self.create_only:
            d["create_only"] = True
        if self.required:
            d["required"] = True
        if self.enum_values is not None:
            d["enum_values"] = list(self.enum_values)
        if self.item_type is not None:
            d["item_type"] = self.item_type
        if self.fields is not None:
            d["fields"] = [f.to_dict() for f in self.fields]
        if self.placeholder is not None:
            d["placeholder"] = self.placeholder
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "FieldSpec":
        """Parse from the wire format, ignoring unknown keys.

        Unknown keys are dropped so a future SDK that adds e.g. `min_value`
        can ship spec dicts that older code still parses successfully.
        """
        nested_raw = d.get("fields")
        nested = [cls.from_dict(f) for f in nested_raw] if nested_raw else None
        enum_raw = d.get("enum_values")
        return cls(
            name=d["name"],
            type=d["type"],
            label=d.get("label"),
            description=d.get("description"),
            editable=d.get("editable", True),
            required=d.get("required", False),
            create_only=d.get("create_only", False),
            enum_values=list(enum_raw) if enum_raw is not None else None,
            item_type=d.get("item_type"),
            fields=nested,
            placeholder=d.get("placeholder"),
        )
