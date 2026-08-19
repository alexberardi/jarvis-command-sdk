from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class RequestInformation:
    """
    Information about the request received from the Jarvis Command Center

    This object contains details about the voice command and any additional
    context that was provided when the command was selected.

    is_pre_routed signals that the call came from the node-side fast path
    (regex match, no LLM). When True, the command should pre-compose its
    spoken response into context_data["message"] — there's no LLM downstream
    to turn structured data into a sentence. Commands that don't speak
    (background timers, etc.) can ignore this flag.

    home_context carries household-level info command-center injected (v1:
    {"location": <locality>}), so a command can read e.g. the household's
    location without a duplicated secret or an HTTP round-trip. None when CC
    didn't inject one (unset household / older CC) — the command falls back to
    its own secret. A plain dict so new keys are additive across SDK versions.
    """
    voice_command: str
    conversation_id: str
    is_validation_response: bool = False
    validation_context: Optional[Dict[str, Any]] = None
    user_id: Optional[int] = None
    is_pre_routed: bool = False
    home_context: Optional[Dict[str, Any]] = None
