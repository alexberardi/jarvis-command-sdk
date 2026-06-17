"""Tests for ReferenceableItem and CommandResponse.with_items().

These power the voice follow-up flow ("mark those as read", "send me #3"):
a list-surfacing command returns items alongside its spoken message; the node
remembers ref_id->owner and the command-center re-injects them so the LLM can
resolve references and call act_on_items().
"""

import pytest

from jarvis_command_sdk import CommandResponse, ReferenceableItem


# ── ReferenceableItem ────────────────────────────────────────────────────────


def test_minimal_item_defaults_attrs_and_actions():
    item = ReferenceableItem(ref_id="eml_1", label="email from ABC")
    assert item.ref_id == "eml_1"
    assert item.label == "email from ABC"
    assert item.attrs == {}
    assert item.actions == []


def test_to_dict_roundtrips_all_fields():
    item = ReferenceableItem(
        ref_id="eml_1",
        label="email from ABC — 'Invoice #42'",
        attrs={"sender": "abc@x.com", "subject": "Invoice #42"},
        actions=["mark_read", "draft_reply"],
    )
    assert item.to_dict() == {
        "ref_id": "eml_1",
        "label": "email from ABC — 'Invoice #42'",
        "attrs": {"sender": "abc@x.com", "subject": "Invoice #42"},
        "actions": ["mark_read", "draft_reply"],
    }


def test_to_dict_copies_mutable_fields():
    """to_dict() must not alias the live attrs/actions (wire isolation)."""
    attrs = {"sender": "abc@x.com"}
    actions = ["mark_read"]
    item = ReferenceableItem(ref_id="eml_1", label="x", attrs=attrs, actions=actions)
    d = item.to_dict()
    d["attrs"]["sender"] = "mutated"
    d["actions"].append("delete")
    assert item.attrs == {"sender": "abc@x.com"}
    assert item.actions == ["mark_read"]


@pytest.mark.parametrize("bad_ref", ["", "   ", None])
def test_blank_ref_id_rejected(bad_ref):
    with pytest.raises(ValueError, match="ref_id"):
        ReferenceableItem(ref_id=bad_ref, label="x")


@pytest.mark.parametrize("bad_label", ["", "   ", None])
def test_blank_label_rejected(bad_label):
    with pytest.raises(ValueError, match="label"):
        ReferenceableItem(ref_id="eml_1", label=bad_label)


# ── CommandResponse.with_items() ─────────────────────────────────────────────


def test_with_items_sets_message_and_items():
    items = [
        ReferenceableItem(ref_id="eml_1", label="from ABC", actions=["mark_read"]),
        ReferenceableItem(ref_id="eml_2", label="from Dana", actions=["mark_read"]),
    ]
    resp = CommandResponse.with_items(message="You have 2 unread emails.", items=items)

    assert resp.success is True
    assert resp.wait_for_input is True
    assert resp.context_data["message"] == "You have 2 unread emails."
    assert resp.referenceable_items == items


def test_with_items_preserves_extra_context_data():
    resp = CommandResponse.with_items(
        message="You have 1 email.",
        items=[ReferenceableItem(ref_id="eml_1", label="from ABC")],
        context_data={"unread_count": 1},
    )
    assert resp.context_data["unread_count"] == 1
    assert resp.context_data["message"] == "You have 1 email."


def test_with_items_does_not_mutate_caller_context_data():
    ctx = {"unread_count": 1}
    CommandResponse.with_items(
        message="hi", items=[ReferenceableItem(ref_id="e", label="l")], context_data=ctx
    )
    assert "message" not in ctx  # caller's dict untouched


def test_referenceable_items_as_dicts():
    resp = CommandResponse.with_items(
        message="x",
        items=[
            ReferenceableItem(ref_id="eml_1", label="from ABC", actions=["mark_read"]),
        ],
    )
    assert resp.referenceable_items_as_dicts() == [
        {"ref_id": "eml_1", "label": "from ABC", "attrs": {}, "actions": ["mark_read"]},
    ]


def test_default_response_has_no_referenceable_items():
    """Back-compat: existing commands never set the field."""
    resp = CommandResponse.success_response(context_data={"message": "ok"})
    assert resp.referenceable_items is None
    assert resp.referenceable_items_as_dicts() == []
