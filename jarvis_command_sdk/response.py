from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from .button import IJarvisButton
    from .validation import ValidationResult


@dataclass
class ReferenceableItem:
    """One item the user was just shown that they can refer back to by voice.

    A list-surfacing command (or agent) returns these alongside its spoken
    message via :meth:`CommandResponse.with_items`. They power follow-up flows
    like "mark those as read", "draft a reply to the one from abc", or "send me
    the full article for 3":

    - ``ref_id`` is the command-owned **stable handle** for the item (a gmail
      message_id, an article url-hash, ...). It is what gets passed back to the
      acting ``@callback`` — never a value the LLM reconstructs from prose.
    - ``label`` is the short human string the model matches descriptive
      references against ("email from ABC — 'Invoice #42'").
    - ``attrs`` are extra matchable facets (sender, subject, source, ...) that
      also ride along to the callback as part of the selected row.
    - ``actions`` names the ``@callback`` methods on the owning command/agent
      that are valid for these items (e.g. ``["mark_read", "draft_reply"]``).

    The node remembers ``ref_id -> owning command`` for the conversation and the
    command-center re-injects a numbered "recently shown" list into the prompt
    each turn, so the model resolves "those" / "#3" / "the one from abc" to the
    right ``ref_id`` and calls the generic ``act_on_items`` tool. Ordinals are
    derived from list position at render time and never stored, so the spoken
    list and the remembered list can't drift.
    """

    __forge_hints__ = {
        "role": "A just-shown item the user can refer back to by voice in a follow-up",
        "constructor": 'ReferenceableItem(ref_id, label, attrs={}, actions=[])',
        "example": (
            'ReferenceableItem(ref_id=msg.id, label=f"email from {msg.sender} — \'{msg.subject}\'", '
            'attrs={"sender": msg.sender, "subject": msg.subject}, actions=["mark_read", "draft_reply"])'
        ),
        "tips": [
            "ref_id must be a STABLE, command-owned handle (gmail message_id, article url-hash) — it is what reaches your @callback",
            "label is what the model matches 'the one from abc' against — make it short and distinctive",
            "actions must name @callback methods on the SAME command/agent; act_on_items dispatches action -> get_callbacks()[action]",
            "Return these via CommandResponse.with_items(message=..., items=[...]) so the spoken message and the remembered list come from one place",
        ],
    }

    ref_id: str
    label: str
    attrs: Dict[str, Any] = field(default_factory=dict)
    actions: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.ref_id or not str(self.ref_id).strip():
            raise ValueError("ReferenceableItem 'ref_id' must be a non-empty string")
        if not self.label or not str(self.label).strip():
            raise ValueError(f"ReferenceableItem '{self.ref_id}': 'label' must be a non-empty string")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ref_id": self.ref_id,
            "label": self.label,
            "attrs": dict(self.attrs or {}),
            "actions": list(self.actions or []),
        }


@dataclass
class CommandResponse:
    """Normalized response structure for all Jarvis commands.

    This object provides a consistent interface for command responses that supports
    conversational flows and context preservation for follow-up questions.

    Note: The server generates the spoken response based on context_data.
    Commands should return raw data only.
    """

    __forge_hints__ = {
        "role": "Return type from run() — carries result data back to the voice pipeline",
        "tips": [
            "context_data['message'] is what gets spoken aloud by TTS",
            "Use CommandResponse.success_response() for happy-path results",
            "Use CommandResponse.error_response() for errors — never raise exceptions",
            "Use CommandResponse.final_response() when no follow-up is expected",
            "Set wait_for_input=True if the command expects a follow-up question",
            "Include structured data in context_data for the LLM to format the spoken response",
            "Use actions=[IJarvisButton(...)] for interactive buttons (Send/Cancel) in mobile UI",
        ],
    }

    # The data found/processed by the command (for server to use in generating response)
    context_data: Optional[Dict[str, Any]] = None

    # Whether the command executed successfully
    success: bool = True

    # Any error details (for later validation handlers)
    error_details: Optional[str] = None

    # Whether Jarvis should wait for follow-up input
    wait_for_input: bool = True

    # Whether to clear conversation history before the next turn
    clear_history: bool = False

    # Command-specific metadata (optional)
    metadata: Optional[Dict[str, Any]] = None

    # Interactive actions (e.g. Send/Cancel buttons for email preview)
    actions: Optional[list[IJarvisButton]] = None

    # Items the user was just shown that they can act on in a follow-up
    # ("mark those as read", "send me #3"). Surfaced via with_items(); the node
    # remembers ref_id->owner and the command-center re-injects them into the
    # prompt so the LLM can resolve references and call act_on_items().
    referenceable_items: Optional[list["ReferenceableItem"]] = None

    # Chunked response support
    is_chunked_response: bool = False
    chunk_session_id: Optional[str] = None

    # Optional callable the voice pipeline invokes after the spoken response
    # has finished and the wake-word duck has been released. Use for media
    # commands (Spotify, Music Assistant, Pandora, ...) that would otherwise
    # start audio playback while the duck is still parking sink-inputs on
    # the null sink, causing the first few seconds of the track to be lost.
    # The handler should do all the synchronous resolution (search, station
    # lookup, transfer-playback, etc.) and return the spoken message in
    # context_data["message"]; the callable does only the final "start the
    # audio now" step. Local-only — never serialized to wire or LLM.
    on_response_complete: Optional[Callable[[], None]] = field(
        default=None, repr=False, compare=False,
    )

    def __post_init__(self) -> None:
        """Validate the response structure"""
        # If there's an error, success should be False
        if self.error_details and self.success:
            self.success = False

    def actions_as_dicts(self) -> list[dict[str, str]]:
        """Serialize actions to plain dicts for the wire format."""
        return [a.to_dict() for a in (self.actions or [])]

    def referenceable_items_as_dicts(self) -> list[Dict[str, Any]]:
        """Serialize referenceable items to plain dicts for the wire format."""
        return [i.to_dict() for i in (self.referenceable_items or [])]

    @classmethod
    def success_response(
        cls,
        context_data: Optional[Dict[str, Any]] = None,
        wait_for_input: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
        on_response_complete: Optional[Callable[[], None]] = None,
    ) -> CommandResponse:
        """Create a successful command response.

        Pass ``on_response_complete`` for media commands (Spotify, MA, Pandora)
        that should defer audio playback until the spoken response is finished
        and the wake-word duck is released — see field docstring above.
        """
        return cls(
            context_data=context_data,
            success=True,
            wait_for_input=wait_for_input,
            metadata=metadata,
            on_response_complete=on_response_complete,
        )

    @classmethod
    def with_items(
        cls,
        message: str,
        items: list["ReferenceableItem"],
        *,
        context_data: Optional[Dict[str, Any]] = None,
        wait_for_input: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CommandResponse:
        """Surface a list the user can act on in a follow-up.

        ``message`` is spoken now (it becomes ``context_data['message']``) and
        ``items`` are remembered for the rest of the conversation so the user
        can say "mark those as read" / "send me #3" / "the one from abc". Both
        come from this one call, so the spoken list and the remembered list
        cannot drift. Each item's ``actions`` must name ``@callback`` methods on
        this command (the generic ``act_on_items`` tool dispatches to them).
        """
        ctx: Dict[str, Any] = dict(context_data or {})
        ctx["message"] = message
        return cls(
            context_data=ctx,
            success=True,
            wait_for_input=wait_for_input,
            metadata=metadata,
            referenceable_items=list(items),
        )

    @classmethod
    def error_response(
        cls,
        error_details: str,
        context_data: Optional[Dict[str, Any]] = None,
        wait_for_input: bool = False
    ) -> CommandResponse:
        """Create an error command response"""
        return cls(
            context_data=context_data,
            success=False,
            error_details=error_details,
            wait_for_input=wait_for_input
        )

    @classmethod
    def follow_up_response(
        cls,
        context_data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> CommandResponse:
        """Create a response that expects follow-up input"""
        return cls(
            context_data=context_data,
            success=True,
            wait_for_input=True,
            metadata=metadata
        )

    @classmethod
    def final_response(
        cls,
        context_data: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> CommandResponse:
        """Create a response that doesn't expect follow-up input"""
        return cls(
            context_data=context_data,
            success=True,
            wait_for_input=False,
            metadata=metadata
        )

    @classmethod
    def chunked_response(
        cls,
        session_id: str,
        context_data: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> CommandResponse:
        """Create a response for chunked content that can be continued"""
        return cls(
            context_data=context_data,
            success=True,
            wait_for_input=True,
            metadata=metadata,
            is_chunked_response=True,
            chunk_session_id=session_id
        )

    @classmethod
    def validation_error(
        cls,
        results: list[ValidationResult],
    ) -> CommandResponse:
        """Create a response indicating parameter validation failure."""
        errors = [r for r in results if not r.success]
        messages = [r.message for r in errors if r.message]
        return cls(
            context_data={
                "_validation_error": True,
                "errors": [
                    {"param": r.param_name, "message": r.message, "valid_values": r.valid_values}
                    for r in errors
                ],
            },
            success=False,
            error_details="\n".join(messages),
            wait_for_input=False,
        )
