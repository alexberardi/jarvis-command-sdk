"""JarvisInbox — Facade for posting inbox items (push + phone UI) from commands.

Provides a clean interface for commands to post inbox items (the entries shown
in the mobile app's inbox, optionally with a push notification) without directly
depending on node internals (clients.rest_client, service discovery).

Usage in extracted Pantry packages:
    from jarvis_command_sdk import JarvisInbox

    inbox = JarvisInbox("email")
    tag = inbox.post(
        title="Inbox triage — 12 unread",
        summary="Tap to review",
        body="Plain-text fallback listing",
        category="interactive_list",   # e.g. InteractiveList.CATEGORY
        metadata=payload.to_dict(),    # e.g. InteractiveList(...).to_dict()
        create_push_notification=True,
        target_type="user",
        user_id=42,
    )
    if tag != "ok":
        ...  # map the failure tag to a spoken response

Discriminated return tags (strings, never exceptions):
    "ok"          — the item was posted
    "no_backend"  — no backend registered (tests, container validation)
    "no_cc_url"   — service discovery returned no command-center URL
    "http_error"  — the POST to command-center failed
    "invalid"     — the backend rejected the arguments, or an attachment is
                    malformed (both or neither of data/path, missing file)
    "attachment_type"         — an attachment's mime is not allowed, or its
                                bytes are not that type
    "attachment_too_large"    — a file is over ATTACHMENT_MAX_FILE_BYTES, or
                                all of them over ATTACHMENT_MAX_ITEM_BYTES
    "attachments_unsupported" — attachments were given but the node's backend
                                predates them (no ``attachments`` parameter)
Backends may return additional implementation-specific failure tags
(e.g. "import_error"); treat any tag other than "ok" as a failure.

Interactive elements (the ``interactive_elements`` kwarg) are buttons rendered
by the mobile InboxDetail screen. They are merged into
``metadata["interactive_elements"]`` — the command-center endpoint has no
separate field; mobile reads ``item.metadata.interactive_elements``. Each
element is a dict:

    {
        "id": "send-abc123",             # unique within the item
        "label": "Send reply",           # button text
        "sublabel": "...",               # optional secondary text
        "kind": "send",                  # optional render hint
        "command": "email",              # command that owns the callback
        "callback": "send_draft_reply",  # @callback name to invoke
        "data": {...},                   # opaque dict passed to the callback
        "navigation_type": "stack",      # optional: "stack" (poll + inline
                                         # result) | "new_notification"
                                         # (fire-and-forget; the default)
    }

Attachments (the ``attachments`` kwarg) are images or videos shown with the
item: a list of :class:`Attachment`, each either bytes or a file path, plus its
mime type. The SDK checks them against jarvisd's default caps and types before
the backend sees them (see docs/decisions/2026-10-18-inbox-attachments-sdk.md);
jarvisd stays authoritative, since its caps are settings and can be lowered:

    from jarvis_command_sdk import Attachment

    tag = inbox.post(
        title="Your picture is ready",
        attachments=[Attachment(path="/tmp/out.png", mime="image/png")],
    )

The node runtime registers the real backend via set_inbox_backend().
When no backend is registered (e.g., in tests), post() returns "no_backend".
"""

from __future__ import annotations

import inspect
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

# jarvisd's defaults (jarvis-server internal/modules/notifications: the
# inbox.attachment_max_file_bytes / inbox.attachment_max_item_bytes settings and
# the allowed types). The server is authoritative; these catch the common
# mistakes before an upload.
ATTACHMENT_MAX_FILE_BYTES = 25 << 20
ATTACHMENT_MAX_ITEM_BYTES = 50 << 20
ATTACHMENT_MIME_TYPES: tuple[str, ...] = (
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
    "video/mp4",
    "video/webm",
)

# ISO-BMFF brands that are not MP4 video (HEIF/AVIF stills, QuickTime).
_NON_MP4_BRANDS = (b"heic", b"heix", b"avif", b"qt  ")


@dataclass(frozen=True)
class Attachment:
    """A file attached to an inbox item: exactly one of ``data`` or ``path``.

    ``filename`` defaults to the path's basename. ``size`` stats a path rather
    than reading it. Construction never raises; :func:`validate_attachments`
    (called by :meth:`JarvisInbox.post`) reports a malformed one as "invalid".
    """

    data: bytes | None = field(default=None, repr=False)
    path: str | os.PathLike[str] | None = None
    mime: str = ""
    filename: str = ""

    def __post_init__(self) -> None:
        if not self.filename and self.path is not None:
            object.__setattr__(self, "filename", os.path.basename(os.fspath(self.path)))

    @property
    def size(self) -> int:
        """Size in bytes (``os.stat`` for a path). Raises OSError for a missing path."""
        if self.data is not None:
            return len(self.data)
        return os.stat(self.path).st_size  # type: ignore[arg-type]

    def read_bytes(self) -> bytes:
        """The content: ``data``, or the file read from ``path``."""
        if self.data is not None:
            return self.data
        with open(self.path, "rb") as f:  # type: ignore[arg-type]
            return f.read()

    def _head(self, n: int = 16) -> bytes:
        if self.data is not None:
            return self.data[:n]
        with open(self.path, "rb") as f:  # type: ignore[arg-type]
            return f.read(n)


def _sniff_matches(mime: str, head: bytes) -> bool:
    if mime == "image/png":
        return head.startswith(b"\x89PNG")
    if mime == "image/jpeg":
        return head.startswith(b"\xff\xd8\xff")
    if mime == "image/gif":
        return head.startswith(b"GIF8")
    if mime == "image/webp":
        return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    if mime == "video/mp4":
        return head[4:8] == b"ftyp" and len(head) >= 12 and head[8:12] not in _NON_MP4_BRANDS
    if mime == "video/webm":
        return head.startswith(b"\x1a\x45\xdf\xa3")
    return False


def validate_attachments(attachments: Any) -> str | None:
    """Check attachments against jarvisd's default caps and types.

    Returns None when they are fine (an empty list or None included), else a
    failure tag: "invalid", "attachment_type" or "attachment_too_large" (see
    the module docstring). Never raises.
    """
    if not attachments:
        return None
    if not isinstance(attachments, (list, tuple)):
        return "invalid"
    total = 0
    for att in attachments:
        if not isinstance(att, Attachment) or (att.data is None) == (att.path is None):
            return "invalid"
        if att.data is not None and not isinstance(att.data, (bytes, bytearray)):
            return "invalid"
        try:
            if att.path is not None and not os.path.isfile(att.path):
                return "invalid"
            mime = (att.mime or "").strip().lower()
            if mime not in ATTACHMENT_MIME_TYPES or not _sniff_matches(mime, att._head()):
                return "attachment_type"
            size = att.size
        except (OSError, TypeError, ValueError):
            return "invalid"
        if size > ATTACHMENT_MAX_FILE_BYTES:
            return "attachment_too_large"
        total += size
    if total > ATTACHMENT_MAX_ITEM_BYTES:
        return "attachment_too_large"
    return None


def _accepts_attachments(backend: InboxBackend) -> bool:
    """Whether the backend's post_inbox_item takes ``attachments`` (or **kwargs)."""
    try:
        params = inspect.signature(backend.post_inbox_item).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(
        p.name == "attachments" or p.kind is inspect.Parameter.VAR_KEYWORD for p in params
    )


class InboxBackend(ABC):
    """Abstract backend that the node runtime implements."""

    @abstractmethod
    def post_inbox_item(
        self,
        command_name: str,
        *,
        title: str,
        summary: str = "",
        body: str = "",
        category: str = "general",
        metadata: dict[str, Any] | None = None,
        user_id: int | None = None,
        create_push_notification: bool = False,
        target_type: str = "household",
        attachments: list[Attachment] | None = None,
    ) -> str: ...
    # Returns a discriminated tag: "ok" | "no_backend" | "no_cc_url" |
    # "http_error" | "invalid" (see module docstring).
    #
    # ``attachments`` is passed only when non-empty, already checked by
    # validate_attachments(). The backend uploads each one
    # (POST {cc}/api/v0/node/inbox-attachment, raw body, Content-Type: mime)
    # and sends the returned ids as "attachment_ids" on the inbox-item POST.
    # A backend without this parameter keeps working for posts without
    # attachments; posts with them return "attachments_unsupported".


# Global backend instance, set by the node runtime at startup
_backend: InboxBackend | None = None


def set_inbox_backend(backend: InboxBackend) -> None:
    """Register the inbox backend. Called once by the node runtime."""
    global _backend
    _backend = backend


def get_inbox_backend() -> InboxBackend | None:
    """Get the current inbox backend (for internal use)."""
    return _backend


class JarvisInbox:
    """Per-command facade for posting inbox items.

    Args:
        command_name: The command posting the item (e.g., "email").
    """

    def __init__(self, command_name: str) -> None:
        self._command_name = command_name

    def post(
        self,
        *,
        title: str,
        summary: str = "",
        body: str = "",
        category: str = "general",
        metadata: dict[str, Any] | None = None,
        interactive_elements: list[dict[str, Any]] | None = None,
        user_id: int | None = None,
        create_push_notification: bool = False,
        target_type: str = "household",
        attachments: list[Attachment] | None = None,
    ) -> str:
        """Post an inbox item. Returns a discriminated tag (see module docstring).

        ``interactive_elements`` is merged into ``metadata["interactive_elements"]``
        (the caller's metadata dict is not mutated; an empty list is treated as
        None). ``attachments`` are validated (:func:`validate_attachments`) and
        passed to the backend only when non-empty. All other fields pass
        through to the backend verbatim. Returns "no_backend" when no backend
        is registered — never raises.
        """
        if _backend is None:
            return "no_backend"
        extra: dict[str, Any] = {}
        if attachments:
            tag = validate_attachments(attachments)
            if tag is not None:
                return tag
            if not _accepts_attachments(_backend):
                return "attachments_unsupported"
            extra["attachments"] = list(attachments)
        if interactive_elements:
            metadata = {**(metadata or {}), "interactive_elements": interactive_elements}
        return _backend.post_inbox_item(
            self._command_name,
            title=title,
            summary=summary,
            body=body,
            category=category,
            metadata=metadata,
            user_id=user_id,
            create_push_notification=create_push_notification,
            target_type=target_type,
            **extra,
        )

    def propose_action(
        self,
        *,
        target_command: str,
        action: str,
        params: dict[str, Any],
        idempotency_key: str,
        node_id: str | None = None,
        title: str | None = None,
        summary: str = "",
        body: str = "",
        confirm_label: str = "Confirm",
        dismiss_label: str = "Dismiss",
        editable: list[str] | None = None,
        field_types: dict[str, str] | None = None,
        blast_tier: str = "reversible",
        source: str | None = None,
        descriptor: str | None = None,
        user_id: int | None = None,
        target_type: str = "user",
        create_push_notification: bool = True,
    ) -> str:
        """Propose that ``target_command.action`` be run — a tap-to-confirm card.

        This is the generic "any agent proposes any command" entry point. The
        agent names a *target* command + a proposable ``action`` (its
        ``@callback`` name) + the ``params`` to run it with; on Confirm the card
        routes to command-center's single generic server-plane dispatcher
        (``jarvis.proposable_action.execute``), which validates the proposal
        against the target command's declared :class:`ProposableAction` (opt-in +
        typed params + blast tier + idempotency) and then runs the ``@callback``
        on the node. The proposing agent need not own the target command.

        ``idempotency_key`` is required: a stable handle (e.g.
        ``f"appt:{message_id}"``) so a re-scan / double-tap / retry never
        double-writes. It rides into the target command's params under the
        action's ``idempotency_param``.

        Returns the same discriminated tags as :meth:`post` plus ``"invalid"``
        when required arguments are missing. Never raises. NOTE: this is a card
        builder — the authoritative opt-in and param validation happen
        server-side at the dispatcher, so a card for a non-proposable action is
        posted but refused (with a visible failure) on tap.
        """
        if not target_command or not action or not idempotency_key:
            return "invalid"
        if not isinstance(params, dict):
            return "invalid"

        editable = editable or []
        str_params = {k: _wire_value(v) for k, v in params.items()}
        action_meta = {
            "target_command": target_command,
            "target_callback": action,
            "node_id": node_id,
            "idempotency_key": idempotency_key,
            "blast_tier": blast_tier,
        }
        elements = [
            {
                "id": f"confirm-{idempotency_key}",
                "label": confirm_label,
                "kind": "confirm",
                "command": "jarvis.proposable_action",
                "callback": "execute",
                "target": "server",
                # `_action` is control metadata the mobile field-merge never
                # touches (it only overwrites keys named by an editable field);
                # the declared params ride at the top level so user edits merge.
                "data": {"_action": action_meta, **str_params},
                "navigation_type": "new_notification",
            },
            {
                "id": f"dismiss-{idempotency_key}",
                "label": dismiss_label,
                "kind": "dismiss",
                "command": "jarvis.proposable_action",
                "callback": "dismiss",
                "target": "server",
                "data": {"_action": {"idempotency_key": idempotency_key}},
                "navigation_type": "new_notification",
            },
        ]

        # "Never suggest this" — opts the user out of future look-alikes. Routes
        # to the suppress handler, which records a blocklist entry from the
        # deterministic ``source`` (a hard key, e.g. the sender) AND the
        # ``descriptor`` (a semantic example injected into the detector's prompt).
        # Only offered when the proposer supplies something to key the block on.
        if source or descriptor:
            elements.append(
                {
                    "id": f"suppress-{idempotency_key}",
                    "label": "Never suggest this",
                    "kind": "suppress",
                    "command": "jarvis.proposable_action",
                    "callback": "suppress",
                    "target": "server",
                    "data": {
                        "_action": {
                            "target_command": target_command,
                            "idempotency_key": idempotency_key,
                        },
                        "source": source or "",
                        "descriptor": descriptor or "",
                    },
                    "navigation_type": "new_notification",
                }
            )

        metadata: dict[str, Any] = {}
        if editable:
            # Forward-compatible editable-field hints (additive; older renderers
            # ignore them and the card still confirms with the parsed values).
            # ``input_type`` (from field_types) lets mobile pick a widget — e.g.
            # "datetime" → a date/time picker — falling back to a text box when
            # absent or unrecognised.
            ftypes = field_types or {}
            fields: list[dict[str, Any]] = []
            for k in editable:
                if k not in str_params:
                    continue
                field: dict[str, Any] = {
                    "data_key": k,
                    "label": k,
                    "initial": str_params.get(k, ""),
                }
                if ftypes.get(k):
                    field["input_type"] = ftypes[k]
                fields.append(field)
            metadata["editable_fields"] = fields

        return self.post(
            title=title or "",
            summary=summary,
            body=body,
            category="proposable_action",
            metadata=metadata or None,
            interactive_elements=elements,
            user_id=user_id,
            create_push_notification=create_push_notification,
            target_type=target_type,
        )


def _wire_value(value: Any) -> Any:
    """Coerce a param value to a JSON/wire-friendly form for the card data.

    datetimes/dates → ISO 8601 strings; primitives pass through; everything
    else is stringified. Keeps the confirm card's ``data`` serialisable.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return isoformat()
    return str(value)
