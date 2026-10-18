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


# ── Attachments ────────────────────────────────────────────────────────────

from jarvis_command_sdk import (  # noqa: E402
    ATTACHMENT_MAX_FILE_BYTES,
    ATTACHMENT_MAX_ITEM_BYTES,
    ATTACHMENT_MIME_TYPES,
    Attachment,
    validate_attachments,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
GIF = b"GIF89a" + b"\x00" * 16
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 8
MP4 = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 12
WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 16


class AttachmentBackend(FakeInboxBackend):
    """A backend that takes attachments (the post-#187 node)."""

    def post_inbox_item(self, command_name, *, attachments=None, **kwargs):
        self.calls.append({"command_name": command_name, "attachments": attachments, **kwargs})
        return self.tag


class KwargsBackend(FakeInboxBackend):
    def post_inbox_item(self, command_name, **kwargs):
        self.calls.append({"command_name": command_name, **kwargs})
        return self.tag


def _sparse(path, size, header=PNG):
    with open(path, "wb") as f:
        f.write(header)
        f.truncate(size)
    return path


class TestAttachment:
    def test_caps_match_jarvisd_defaults(self):
        assert ATTACHMENT_MAX_FILE_BYTES == 25 << 20
        assert ATTACHMENT_MAX_ITEM_BYTES == 50 << 20
        assert set(ATTACHMENT_MIME_TYPES) == {
            "image/png", "image/jpeg", "image/webp", "image/gif", "video/mp4", "video/webm",
        }

    def test_bytes_size_and_read(self):
        a = Attachment(data=PNG, mime="image/png", filename="a.png")
        assert a.size == len(PNG)
        assert a.read_bytes() == PNG

    def test_path_size_uses_stat_and_filename_defaults_to_basename(self, tmp_path):
        p = tmp_path / "clip.mp4"
        p.write_bytes(MP4)
        a = Attachment(path=p, mime="video/mp4")
        assert a.filename == "clip.mp4"
        assert a.size == len(MP4)
        assert a.read_bytes() == MP4

    def test_repr_omits_bytes(self):
        assert "\\x89" not in repr(Attachment(data=PNG, mime="image/png"))


class TestValidateAttachments:
    @pytest.mark.parametrize(
        "data,mime",
        [(PNG, "image/png"), (JPEG, "image/jpeg"), (GIF, "image/gif"), (WEBP, "image/webp"),
         (MP4, "video/mp4"), (WEBM, "video/webm"), (PNG, "IMAGE/PNG")],
    )
    def test_accepts_each_allowed_type(self, data, mime):
        assert validate_attachments([Attachment(data=data, mime=mime)]) is None

    def test_empty_and_none_are_valid(self):
        assert validate_attachments([]) is None
        assert validate_attachments(None) is None

    def test_disallowed_mime(self):
        svg = Attachment(data=b"<svg/>", mime="image/svg+xml")
        assert validate_attachments([svg]) == "attachment_type"

    def test_magic_bytes_must_match_mime(self):
        assert validate_attachments([Attachment(data=JPEG, mime="image/png")]) == "attachment_type"

    @pytest.mark.parametrize("brand", [b"heic", b"avif", b"qt  "])
    def test_ftyp_non_mp4_brands_refused(self, brand):
        data = b"\x00\x00\x00\x18ftyp" + brand + b"\x00" * 12
        assert validate_attachments([Attachment(data=data, mime="video/mp4")]) == "attachment_type"

    def test_magic_checked_for_path(self, tmp_path):
        p = tmp_path / "x.png"
        p.write_bytes(GIF)
        assert validate_attachments([Attachment(path=p, mime="image/png")]) == "attachment_type"

    def test_file_over_cap(self, tmp_path):
        p = _sparse(tmp_path / "big.png", ATTACHMENT_MAX_FILE_BYTES + 1)
        assert validate_attachments([Attachment(path=p, mime="image/png")]) == "attachment_too_large"

    def test_file_at_cap_ok(self, tmp_path):
        p = _sparse(tmp_path / "big.png", ATTACHMENT_MAX_FILE_BYTES)
        assert validate_attachments([Attachment(path=p, mime="image/png")]) is None

    def test_total_over_cap(self, tmp_path):
        atts = [
            Attachment(path=_sparse(tmp_path / f"{i}.png", 20 << 20), mime="image/png")
            for i in range(3)
        ]
        assert validate_attachments(atts) == "attachment_too_large"

    @pytest.mark.parametrize(
        "att",
        [
            Attachment(data=PNG, path="x.png", mime="image/png"),
            Attachment(mime="image/png"),
            Attachment(path="/nonexistent/x.png", mime="image/png"),
            "not an attachment",
        ],
    )
    def test_structural_problems_are_invalid(self, att):
        assert validate_attachments([att]) == "invalid"

    def test_not_a_list_is_invalid(self):
        assert validate_attachments(Attachment(data=PNG, mime="image/png")) == "invalid"

    def test_directory_path_is_invalid(self, tmp_path):
        assert validate_attachments([Attachment(path=tmp_path, mime="image/png")]) == "invalid"

    def test_str_data_is_invalid(self):
        assert validate_attachments([Attachment(data="png", mime="image/png")]) == "invalid"


class TestPostWithAttachments:
    def test_legacy_backend_without_attachments_unchanged(self):
        backend = FakeInboxBackend()
        set_inbox_backend(backend)
        assert JarvisInbox("c").post(title="t", attachments=[]) == "ok"
        assert JarvisInbox("c").post(title="t", attachments=None) == "ok"
        assert "attachments" not in backend.calls[0]
        assert len(backend.calls) == 2

    def test_legacy_backend_with_attachments_unsupported(self):
        backend = FakeInboxBackend()
        set_inbox_backend(backend)
        tag = JarvisInbox("c").post(title="t", attachments=[Attachment(data=PNG, mime="image/png")])
        assert tag == "attachments_unsupported"
        assert backend.calls == []

    def test_backend_receives_attachments_verbatim(self):
        backend = AttachmentBackend()
        set_inbox_backend(backend)
        atts = [Attachment(data=PNG, mime="image/png", filename="a.png")]
        assert JarvisInbox("c").post(title="t", attachments=atts) == "ok"
        assert backend.calls[0]["attachments"] == atts
        assert backend.calls[0]["title"] == "t"

    def test_kwargs_backend_receives_attachments(self):
        backend = KwargsBackend()
        set_inbox_backend(backend)
        atts = [Attachment(data=PNG, mime="image/png")]
        assert JarvisInbox("c").post(title="t", attachments=atts) == "ok"
        assert backend.calls[0]["attachments"] == atts

    def test_empty_list_not_forwarded(self):
        backend = AttachmentBackend()
        set_inbox_backend(backend)
        JarvisInbox("c").post(title="t", attachments=[])
        assert backend.calls[0]["attachments"] is None

    def test_invalid_attachments_not_posted(self):
        backend = AttachmentBackend()
        set_inbox_backend(backend)
        tag = JarvisInbox("c").post(title="t", attachments=[Attachment(data=JPEG, mime="image/png")])
        assert tag == "attachment_type"
        assert backend.calls == []

    def test_no_backend_wins(self):
        assert JarvisInbox("c").post(title="t", attachments=[Attachment(mime="x")]) == "no_backend"
