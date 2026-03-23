"""IJarvisPromptProvider — Abstract base class for prompt providers.

Prompt providers control how the LLM system prompt is built for voice command
parsing. Each provider targets a specific model family + size + training tier
(e.g., Qwen25MediumUntrained, HermesMediumTrained).

Community providers focus on inference — training methods are omitted from
this SDK interface (the CC's internal interface adds them).
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class IJarvisPromptProvider(ABC):
    """Abstract interface for model-specific prompt construction.

    Implementations provide prompt-building logic for a specific LLM model.
    The PromptProviderFactory discovers providers by scanning
    app/core/prompt_providers/ and matching by the ``name`` property.

    Providers install to the command center (not nodes). They are discovered
    at runtime via pkgutil.walk_packages — no restart needed after install.
    """

    __forge_hints__ = {
        "component_type": "prompt_provider",
        "entry_file": "provider.py",
        "convention_dir": "prompt_providers/{name}/",
        "base_class": "IJarvisPromptProvider",
        "required_methods": [
            "name", "build_system_prompt", "get_capabilities",
        ],
        "tips": [
            "Prompt providers install to the command center, not to nodes",
            "name must be unique — convention: <Family><Size><Tier> (e.g., 'Llama31MediumUntrained')",
            "build_system_prompt() receives node context, timezone, tools, and available commands",
            "get_capabilities() must return size_tier ('small'/'medium'/'large') and training_tier ('untrained'/'trained')",
            "Override parse_response() if your model outputs a non-standard format (XML tags, markdown fences)",
            "Override supports_native_tools to True if the model supports OpenAI-style function calling",
            "Override user_message_suffix for models needing control tokens (e.g., Qwen3 /nothink)",
            "Use shared helpers from the CC's prompt_providers/shared/ package for common prompt sections",
        ],
        "example_import": "from jarvis_command_sdk import IJarvisPromptProvider",
    }

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for factory matching.

        Convention: <Family><Size><Tier>, e.g. 'LlamaSmallUntrained'.
        Matched case-insensitively by PromptProviderFactory.
        """
        ...

    @abstractmethod
    def build_system_prompt(
        self,
        node_context: Dict[str, Any],
        timezone: Optional[str],
        tools: List[Dict[str, Any]],
        available_commands: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Build the complete system prompt for an LLM call.

        Args:
            node_context: Runtime context (room, user, voice_mode, agents, etc.)
            timezone: User's IANA timezone (e.g. 'America/New_York')
            tools: Tool definitions in OpenAI function-calling format
            available_commands: Command flag dicts with command_name,
                allow_direct_answer, keywords, etc.

        Returns:
            Full system prompt string ready for the messages array.
        """
        ...

    @abstractmethod
    def get_capabilities(self) -> Dict[str, Any]:
        """Metadata about this provider for health checks and admin UI.

        Returns:
            Dict with at minimum:
            - 'provider_name': str
            - 'model_family': str
            - 'size_tier': str  ('small' / 'medium' / 'large')
            - 'training_tier': str  ('untrained' / 'trained')
            - 'use_tool_classifier': bool
        """
        ...

    @property
    def use_tool_classifier(self) -> bool:
        """Whether the fastText tool classifier should provide routing hints.

        Untrained providers typically return True (needs help routing).
        Trained providers return False (adapter handles routing).
        """
        return True

    @property
    def supports_native_tools(self) -> bool:
        """Whether to pass tools natively to the LLM proxy.

        When True: tools passed via API 'tools' parameter, tool_calls read
        from structured response.
        When False: tools embedded in system prompt, parsed from text output.
        """
        return False

    @property
    def user_message_suffix(self) -> str:
        """Optional suffix appended to every user message.

        Override for models needing control tokens in the user turn
        (e.g., Qwen3 /nothink to disable chain-of-thought).
        """
        return ""

    def parse_response(self, raw_content: str) -> Optional[str]:
        """Transform raw LLM output into Jarvis JSON format.

        Override to handle model-specific output formats (XML tags,
        markdown fences, trailing commas) and normalize to Jarvis JSON.

        Return the transformed string, or None to pass raw content
        to ToolCallParser as-is.
        """
        return None

    def get_response_format(self) -> Optional[Dict[str, Any]]:
        """Override the default JSON response format schema.

        Return None to use the shared default. Override for model families
        that need a different JSON schema.
        """
        return None

    def build_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Build OpenAI-format tool definitions for native tool calling.

        Override to customize tool schemas for a specific model family.
        Only called when supports_native_tools is True.
        """
        return tools
