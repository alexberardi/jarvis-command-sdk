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
    "invalid"     — the backend rejected the arguments
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

The node runtime registers the real backend via set_inbox_backend().
When no backend is registered (e.g., in tests), post() returns "no_backend".
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


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
    ) -> str: ...
    # Returns a discriminated tag: "ok" | "no_backend" | "no_cc_url" |
    # "http_error" | "invalid" (see module docstring).


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
    ) -> str:
        """Post an inbox item. Returns a discriminated tag (see module docstring).

        ``interactive_elements`` is merged into ``metadata["interactive_elements"]``
        (the caller's metadata dict is not mutated; an empty list is treated as
        None). All other fields pass through to the backend verbatim. Returns
        "no_backend" when no backend is registered — never raises.
        """
        if _backend is None:
            return "no_backend"
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
        )
