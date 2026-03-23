"""Core command interface for the Jarvis voice assistant.

This module defines the abstract IJarvisCommand interface that all voice commands
must implement. The SDK version contains only the pure interface — node-specific
behavior (secret validation, auth checks, token refresh) is added by the
JarvisCommandBase in jarvis-node-setup/core/.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, TYPE_CHECKING
from dataclasses import dataclass

from .authentication import AuthenticationConfig
from .parameter import IJarvisParameter
from .secret import IJarvisSecret
from .request import RequestInformation
from .response import CommandResponse
from .validation import ValidationResult

if TYPE_CHECKING:
    from .package import JarvisPackage


@dataclass
class PreRouteResult:
    """Result from a command's pre_route() method.

    arguments: kwargs to pass directly to execute().
    spoken_response: optional override for the spoken TTS message.
        If None, the CommandResponse.context_data["message"] is used.
    """
    arguments: Dict[str, Any]
    spoken_response: str | None = None


@dataclass
class CommandExample:
    """Represents a voice command example with expected parameters.

    Used to teach the LLM how to parse voice input into tool calls.
    """

    __forge_hints__ = {
        "role": "Maps a voice utterance to expected parameter extraction",
        "tips": [
            "voice_command: natural language (e.g., 'what's the weather in Boston')",
            "expected_parameters: dict of param_name → extracted value (e.g., {'city': 'Boston'})",
            "is_primary=True for the most representative example (shown first in prompts)",
        ],
    }

    voice_command: str
    expected_parameters: Dict[str, Any]
    is_primary: bool = False


@dataclass
class CommandAntipattern:
    """Represents a command anti-pattern for tool disambiguation"""
    command_name: str
    description: str


class IJarvisCommand(ABC):
    """Abstract interface for Jarvis voice commands.

    Command authors implement this interface to create new voice commands.
    The SDK provides the pure interface — runtime behavior (secret validation,
    auth management, schema generation) is handled by the node runtime.
    """

    __forge_hints__ = {
        "component_type": "command",
        "entry_file": "command.py",
        "convention_dir": "commands/{name}/",
        "base_class": "IJarvisCommand",
        "required_methods": [
            "command_name", "description", "parameters", "required_secrets",
            "keywords", "run", "generate_prompt_examples", "generate_adapter_examples",
        ],
        "tips": [
            "command_name must be snake_case and unique across all installed commands",
            "run() must return a CommandResponse — never raise exceptions to the caller",
            "context_data['message'] is what gets spoken aloud by the TTS engine",
            "generate_prompt_examples() should return 3-5 concise examples for LLM tool registration",
            "generate_adapter_examples() should return 10-20 varied examples for adapter fine-tuning",
            "Use JarvisParameter for each parameter — the LLM extracts these from voice input",
            "Use JarvisSecret for API keys or config — secrets are stored encrypted on the node",
            "Keywords help fuzzy-match voice commands to this command during routing",
            "Override setup_guide to return Markdown with step-by-step instructions for getting API keys or enabling integrations — shown in the mobile app",
        ],
        "example_import": "from jarvis_command_sdk import IJarvisCommand, CommandResponse, JarvisParameter, JarvisSecret, CommandExample, RequestInformation",
    }

    @property
    @abstractmethod
    def command_name(self) -> str:
        """Unique identifier for this command (e.g. 'turn_on_lights', 'check_door_status')"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what this command does"""
        pass

    @abstractmethod
    def generate_prompt_examples(self) -> List[CommandExample]:
        """Generate concise examples for prompt/tool registration"""
        pass

    @abstractmethod
    def generate_adapter_examples(self) -> List[CommandExample]:
        """Generate larger, varied examples for adapter training"""
        pass

    @property
    @abstractmethod
    def parameters(self) -> List[IJarvisParameter]:
        """List of parameters this command accepts"""
        pass

    @property
    @abstractmethod
    def required_secrets(self) -> List[IJarvisSecret]:
        pass

    @property
    def all_possible_secrets(self) -> List[IJarvisSecret]:
        """All secrets this command could ever need, across all config variants.

        Used by install_command.py to seed the DB upfront.
        Default: delegates to required_secrets (backward compatible).
        Override when required_secrets is config-dependent.
        """
        return self.required_secrets

    @property
    @abstractmethod
    def keywords(self) -> List[str]:
        """List of keywords that can be used to identify this command (for fuzzy matching)"""
        pass

    @property
    def rules(self) -> List[str]:
        """Optional list of general rules for this command"""
        return []

    @property
    def antipatterns(self) -> List[CommandAntipattern]:
        """Optional list of anti-patterns that point to other commands"""
        return []

    @property
    def allow_direct_answer(self) -> bool:
        """Whether the model may respond directly without calling the tool."""
        return False

    @property
    def critical_rules(self) -> List[str]:
        """Optional list of critical rules that must be followed for this command"""
        return []

    @property
    def required_packages(self) -> List["JarvisPackage"]:
        """
        Python packages this command requires.

        Override to declare pip dependencies for this command.
        Packages are installed on first use and written to custom-requirements.txt.

        Returns:
            List of JarvisPackage declaring pip dependencies
        """
        return []

    @property
    def associated_service(self) -> str | None:
        """Logical service grouping for the mobile settings UI.

        Commands sharing the same associated_service are grouped together
        in the mobile app's settings screen (e.g., "Home Assistant", "OpenWeather").

        When a command has authentication, the auth provider's friendly_name is
        used as the default group. Override this for commands that share config
        but don't have OAuth (e.g., weather, web search).

        Returns:
            Display name for the service group, or None to remain ungrouped
        """
        if self.authentication:
            return self.authentication.friendly_name
        return None

    @property
    def setup_guide(self) -> str | None:
        """Markdown guide for setting up this command's secrets/integrations.

        Rendered in the mobile app when the user taps "Setup Help" on the
        command's settings section. Use this to walk non-technical users
        through getting API keys, enabling integrations, etc.

        Supports full GitHub-flavored Markdown (headings, links, numbered
        steps, images, code blocks). Keep it concise and action-oriented.

        Returns:
            Markdown string, or None for no guide.
        """
        return None

    @property
    def authentication(self) -> AuthenticationConfig | None:
        """Declare OAuth config for commands that need external auth.

        Override to return an AuthenticationConfig describing the OAuth flow.
        Commands sharing a provider (e.g., all HA commands return provider="home_assistant")
        share auth state -- once one command stores the secrets, all see them.

        Returns:
            AuthenticationConfig or None if no external auth needed
        """
        return None

    @property
    def supported_platforms(self) -> List[str]:
        """Platforms this command supports (empty = all).

        Override to restrict to specific platforms, e.g. ["darwin"] for macOS-only.
        """
        return []

    def validate_call(self, **kwargs: Any) -> list[ValidationResult]:
        """Validate parameter values before execution.

        Default: loops parameters, calls param.validate() on each.
        Override for cross-param or context-dependent validation
        (e.g., entity_id checked against HA data).
        """
        results: list[ValidationResult] = []
        for param in self.parameters:
            value = kwargs.get(param.name)
            if value is None:
                continue  # Missing params handled by _validate_params
            is_valid, error_msg = param.validate(value)
            if not is_valid:
                results.append(ValidationResult(
                    success=False,
                    param_name=param.name,
                    command_name=self.command_name,
                    message=error_msg,
                    valid_values=param.enum_values,
                ))
        return results

    def pre_route(self, voice_command: str) -> PreRouteResult | None:
        """Deterministic matching -- bypass the command center entirely.

        Override to claim short/unambiguous utterances that don't need LLM
        inference (e.g. "pause", "skip", "volume 50").

        Returns:
            PreRouteResult with arguments for execute(), or None to fall
            through to the normal LLM path.
        """
        return None

    def post_process_tool_call(self, args: Dict[str, Any], voice_command: str) -> Dict[str, Any]:
        """Fix up LLM tool-call arguments before execution.

        Called after the LLM produces a tool call but before execute().
        Override to patch common LLM mistakes (e.g. missing query field).

        Returns:
            The (possibly modified) arguments dict.
        """
        return args

    def handle_action(self, action_name: str, context: Dict[str, Any]) -> CommandResponse:
        """Handle an interactive action triggered by a button tap in the mobile app.

        Called when the user taps an action button (e.g. Send, Cancel) on a
        response that included actions. Override to implement action handling.

        The base implementation handles ``cancel_click`` automatically so that
        individual commands don't need to re-implement cancellation.

        Args:
            action_name: The action identifier (e.g. "send_click", "cancel_click").
            context: Context data from the original response (e.g. draft contents).

        Returns:
            CommandResponse with the result of the action.
        """
        if action_name == "cancel_click":
            return CommandResponse.final_response(
                context_data={"cancelled": True, "message": "Cancelled."}
            )
        return CommandResponse.error_response(
            error_details=f"Action '{action_name}' is not supported by {self.command_name}."
        )

    def store_auth_values(self, values: dict[str, str]) -> None:
        """Called when auth tokens are delivered from mobile via config push.

        Override to process and store the received auth values as secrets.
        For example, an HA command might create a long-lived access token
        from the short-lived OAuth token, then store HA URLs and the LLAT.

        Args:
            values: Dict of auth values. Keys match AuthenticationConfig.keys,
                    plus "_base_url" if discovery was used.
        """
        pass

    def init_data(self) -> Dict[str, Any]:
        """
        Optional initialization hook. Called manually on first install.

        Override to sync data on first install:
        - Register devices with Command Center
        - Fetch initial state from external services
        - Set up integrations

        Returns:
            Dict with initialization results (for logging/display)

        Usage:
            python scripts/init_data.py --command <command_name>
        """
        return {"status": "no_init_required"}

    # ── Schema generation ───────────────────────────────────────────────
    # These build tool/command schemas for LLM registration. Defined here
    # (not on the node runtime) so both built-in and Pantry commands work.

    _TYPE_MAPPING: Dict[str, str] = {
        "str": "string", "string": "string",
        "int": "integer", "integer": "integer",
        "float": "number", "number": "number",
        "bool": "boolean", "boolean": "boolean",
        "list": "array", "array": "array",
        "dict": "object",
        "datetime": "string", "date": "string", "time": "string",
        "array[datetime]": "array", "array[date]": "array",
        "array<datetime>": "array", "array<date>": "array",
        "datetime[]": "array", "date[]": "array",
        "enum": "string",
    }

    def _validate_examples(self, examples: List["CommandExample"]) -> None:
        primary_count = sum(1 for ex in examples if ex.is_primary)
        if primary_count > 1:
            raise ValueError(
                f"Command '{self.command_name}' has {primary_count} primary examples. "
                "Only 0 or 1 allowed."
            )

    def to_openai_tool_schema(self, date_context: Any = None) -> Dict[str, Any]:
        """Convert this command to OpenAI function/tool calling schema format."""
        examples = self.generate_prompt_examples()
        self._validate_examples(examples)

        properties: Dict[str, Any] = {}
        required_params: List[str] = []

        for param in self.parameters:
            json_type = self._TYPE_MAPPING.get(param.param_type, "string")
            param_schema: Dict[str, Any] = {"type": json_type}

            if param.description:
                param_schema["description"] = param.description
            if param.enum_values:
                param_schema["enum"] = param.enum_values

            # Handle array types
            if param.param_type.startswith("array") or param.param_type.endswith("[]"):
                param_schema["type"] = "array"
                if "datetime" in param.param_type:
                    param_schema["items"] = {"type": "string", "format": "date-time"}
                elif "date" in param.param_type:
                    param_schema["items"] = {"type": "string", "format": "date"}

            if getattr(param, "refinable", False):
                param_schema["_refinable"] = True

            properties[param.name] = param_schema
            if param.required:
                required_params.append(param.name)

        tool_schema: Dict[str, Any] = {
            "type": "function",
            "function": {
                "name": self.command_name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required_params,
                },
            },
            "allow_direct_answer": self.allow_direct_answer,
            "keywords": self.keywords,
            "examples": [
                {
                    "voice_command": ex.voice_command,
                    "expected_parameters": ex.expected_parameters,
                    "is_primary": ex.is_primary,
                }
                for ex in examples
            ],
        }

        if self.antipatterns:
            tool_schema["antipatterns"] = [
                {"command_name": ap.command_name, "description": ap.description}
                for ap in self.antipatterns
            ]

        return tool_schema

    def get_command_schema(self, date_context: Any = None, use_adapter_examples: bool = False) -> Dict[str, Any]:
        """Generate the command schema for the LLM."""
        examples = self.generate_adapter_examples() if use_adapter_examples else self.generate_prompt_examples()
        self._validate_examples(examples)

        schema: Dict[str, Any] = {
            "command_name": self.command_name,
            "description": self.description,
            "allow_direct_answer": self.allow_direct_answer,
            "examples": [
                {
                    "voice_command": ex.voice_command,
                    "expected_parameters": ex.expected_parameters,
                    "is_primary": ex.is_primary,
                }
                for ex in examples
            ],
            "keywords": self.keywords,
            "parameters": [param.to_dict() for param in self.parameters],
        }

        if self.rules:
            schema["rules"] = self.rules
        if self.antipatterns:
            schema["antipatterns"] = [
                {"command_name": ap.command_name, "description": ap.description}
                for ap in self.antipatterns
            ]
        if self.critical_rules:
            schema["critical_rules"] = self.critical_rules

        return schema

    def get_primary_example(self, date_context: Any = None) -> "CommandExample":
        """Get the primary example for command inference (or first if none marked primary)."""
        examples = self.generate_prompt_examples()
        self._validate_examples(examples)
        primary = [ex for ex in examples if ex.is_primary]
        if primary:
            return primary[0]
        if examples:
            return examples[0]
        raise ValueError(f"Command '{self.command_name}' has no examples")

    # ── Abstract method ───────────────────────────────────────────────

    @abstractmethod
    def run(self, request_info: RequestInformation, **kwargs) -> CommandResponse:
        """
        Execute the command with request information and parameters

        Args:
            request_info: Information about the request from JCC
            **kwargs: Additional parameters for the command

        Returns:
            CommandResponse object with:
            - context_data: Raw data for the server to use in generating response
            - success: Whether the command succeeded
            - error_details: Any error information
            - wait_for_input: Whether to wait for follow-up questions
        """
        pass
