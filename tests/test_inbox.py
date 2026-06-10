"""Tests for JarvisInbox — the inbox-posting facade and backend injection."""

import pytest

from jarvis_command_sdk import JarvisInbox, InboxBackend, set_inbox_backend, get_inbox_backend
from jarvis_command_sdk import inbox as inbox_module


# ── Test fixtures ──────────────────────────────────────────────────────────


class FakeInboxBackend(InboxBackend):
    """Records every post_inbox_item call and returns a configurable tag."""

    def __init__(self, tag: str = "ok"):
        self.tag = tag
        self.calls = []

    def post_inbox_item(
        self,
        command_name,
        *,
        title,
        summary="",
        body="",
        category="general",
        metadata=None,
        user_id=None,
        create_push_notification=False,
        target_type="household",
    ):
        self.calls.append(
            {
                "command_name": command_name,
                "title": title,
                "summary": summary,
                "body": body,
                "category": category,
                "metadata": metadata,
                "user_id": user_id,
                "create_push_notification": create_push_notification,
                "target_type": target_type,
            }
        )
        return self.tag


@pytest.fixture(autouse=True)
def reset_backend():
    """Isolate the module-level backend between tests."""
    inbox_module._backend = None
    yield
    inbox_module._backend = None


# ── No-backend behavior ────────────────────────────────────────────────────


class TestNoBackend:
    def test_post_returns_no_backend_tag(self):
        assert JarvisInbox("email").post(title="hello") == "no_backend"

    def test_post_never_raises_with_full_kwargs(self):
        tag = JarvisInbox("email").post(
            title="t",
            summary="s",
            body="b",
            category="interactive_list",
            metadata={"type": "interactive_list"},
            interactive_elements=[{"id": "x", "label": "X", "command": "email", "callback": "cb", "data": {}}],
            user_id=42,
            create_push_notification=True,
            target_type="user",
        )
        assert tag == "no_backend"

    def test_get_inbox_backend_returns_none(self):
        assert get_inbox_backend() is None


# ── Backend registration ───────────────────────────────────────────────────


class TestBackendRegistration:
    def test_set_and_get_backend(self):
        backend = FakeInboxBackend()
        set_inbox_backend(backend)
        assert get_inbox_backend() is backend

    def test_backend_tag_returned_verbatim(self):
        set_inbox_backend(FakeInboxBackend(tag="http_error"))
        assert JarvisInbox("email").post(title="t") == "http_error"


# ── Field passthrough ──────────────────────────────────────────────────────


class TestFieldPassthrough:
    def test_all_fields_pass_through_verbatim(self):
        backend = FakeInboxBackend()
        set_inbox_backend(backend)
        metadata = {"type": "interactive_list", "version": 1}
        tag = JarvisInbox("email").post(
            title="Inbox triage — 3 unread",
            summary="Tap to review",
            body="1. a\n2. b\n3. c",
            category="interactive_list",
            metadata=metadata,
            user_id=42,
            create_push_notification=True,
            target_type="user",
        )
        assert tag == "ok"
        assert backend.calls == [
            {
                "command_name": "email",
                "title": "Inbox triage — 3 unread",
                "summary": "Tap to review",
                "body": "1. a\n2. b\n3. c",
                "category": "interactive_list",
                "metadata": {"type": "interactive_list", "version": 1},
                "user_id": 42,
                "create_push_notification": True,
                "target_type": "user",
            }
        ]

    def test_defaults_forwarded(self):
        backend = FakeInboxBackend()
        set_inbox_backend(backend)
        JarvisInbox("email").post(title="t")
        call = backend.calls[0]
        assert call["summary"] == ""
        assert call["body"] == ""
        assert call["category"] == "general"
        assert call["metadata"] is None
        assert call["user_id"] is None
        assert call["create_push_notification"] is False
        assert call["target_type"] == "household"

    def test_command_name_forwarded(self):
        backend = FakeInboxBackend()
        set_inbox_backend(backend)
        JarvisInbox("export_shopping_list").post(title="t")
        assert backend.calls[0]["command_name"] == "export_shopping_list"


# ── Interactive element merge ──────────────────────────────────────────────


class TestElementMerge:
    ELEMENTS = [
        {
            "id": "send-abc",
            "label": "Send reply",
            "kind": "send",
            "command": "email",
            "callback": "send_draft_reply",
            "data": {"message_id": "abc"},
            "navigation_type": "stack",
        },
        {
            "id": "ignore-abc",
            "label": "Ignore",
            "command": "email",
            "callback": "dismiss_draft",
            "data": {"message_id": "abc"},
        },
    ]

    def test_elements_merge_into_existing_metadata(self):
        backend = FakeInboxBackend()
        set_inbox_backend(backend)
        JarvisInbox("email").post(title="t", metadata={"foo": "bar"}, interactive_elements=self.ELEMENTS)
        assert backend.calls[0]["metadata"] == {"foo": "bar", "interactive_elements": self.ELEMENTS}

    def test_elements_create_metadata_when_none(self):
        backend = FakeInboxBackend()
        set_inbox_backend(backend)
        JarvisInbox("email").post(title="t", interactive_elements=self.ELEMENTS)
        assert backend.calls[0]["metadata"] == {"interactive_elements": self.ELEMENTS}

    def test_callers_metadata_dict_not_mutated(self):
        backend = FakeInboxBackend()
        set_inbox_backend(backend)
        metadata = {"foo": "bar"}
        JarvisInbox("email").post(title="t", metadata=metadata, interactive_elements=self.ELEMENTS)
        assert metadata == {"foo": "bar"}

    def test_empty_elements_list_treated_as_none(self):
        backend = FakeInboxBackend()
        set_inbox_backend(backend)
        JarvisInbox("email").post(title="t", metadata={"foo": "bar"}, interactive_elements=[])
        assert backend.calls[0]["metadata"] == {"foo": "bar"}
