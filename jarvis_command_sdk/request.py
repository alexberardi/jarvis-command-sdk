from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class RequestInformation:
    """
    Information about the request received from the Jarvis Command Center

    This object contains details about the voice command and any additional
    context that was provided when the command was selected.
    """
    voice_command: str
    conversation_id: str
    is_validation_response: bool = False
    validation_context: Optional[Dict[str, Any]] = None
