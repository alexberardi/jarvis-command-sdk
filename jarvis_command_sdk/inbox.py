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
