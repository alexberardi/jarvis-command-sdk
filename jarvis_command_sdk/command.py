"""Core command interface for the Jarvis voice assistant.

This module defines IJarvisCommand — the single base class for every voice
command, whether shipped with a node, installed via Pantry, or built by a
third party. Everything runtime needs (param validation, secret enforcement,
OAuth refresh, schema generation) lives on this class; hosts supply secrets
and auth-status as inputs, not via node-local globals.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Callable, TYPE_CHECKING
from dataclasses import dataclass
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .auth import AuthStatus, MissingSecretsError, TokenBundle
from .authentication import AuthenticationConfig
from .field_spec import FieldSpec
from .parameter import IJarvisParameter
from .record_summary import DataBrowserMode, RecordSummary
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
class FastPathPattern:
    """A declarative regex pattern that bypasses the LLM.

    Surfaced to the mobile app so users can inspect and disable individual
    patterns when they conflict with another package's claims. The default
    `IJarvisCommand.pre_route()` impl iterates declared patterns, skips any
    in `disabled_pattern_ids`, regex-matches each, and dispatches to the
    named handler method. Commands with parsing too complex for a single
    regex should override `pre_route()` directly and honor the disabled set
    in their own logic — they can still declare patterns here as metadata
    so the inspect UI shows them.

    Pattern ID must be stable across package versions (don't derive it from
    the regex string) so a user's "disabled" toggle survives package updates.
    """

    __forge_hints__ = {
        "role": "Declares a regex this command can fast-path without the LLM",
        "tips": [
            "id must be stable across package versions, e.g. 'weather.current' or 'timer.set'",
            "description and example are shown in the mobile inspect/toggle UI",
            "regex is substring-searched in the raw transcript (case-insensitive); anchor with ^ for start-only match",
            "handler is the method name on the command (signature: handler(self, match: re.Match, voice_command: str) -> PreRouteResult | None)",
            "regex/handler may be omitted if the command overrides pre_route() and only declares patterns for inspect-UI display",
        ],
    }

    id: str
    description: str
    example: str
    regex: str | None = None
    handler: str | None = None


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


def callback(name: str):
    """Mark a method as a named interactive-notification callback.

    Decorated methods are dispatched by the node runtime when a tappable
    element in a rich inbox item is activated in the mobile app. The flow:
    mobile tap -> POST to command-center -> CC publishes job_id over MQTT ->
    node fetches the full {command, callback, data} payload over authenticated
    HTTPS -> node looks up the command and calls the method bound to ``name``.

    Decorated methods receive ``(data: dict, request_info: RequestInformation)``
    and must return a CommandResponse (the runtime turns it into a follow-up
    inbox item, same plumbing as ``handle_action``).

    Names are unique per command. Use ``IJarvisCommand.get_callbacks()`` to
    introspect what's registered on an instance.
    """
    if not isinstance(name, str) or not name:
        raise ValueError("@callback requires a non-empty string name")

    def decorator(func: Callable[..., "CommandResponse"]) -> Callable[..., "CommandResponse"]:
        func.__jarvis_callback_name__ = name  # type: ignore[attr-defined]
        return func

    return decorator


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
            "Optionally declare fast_path_patterns (list of FastPathPattern) to opt into LLM-bypass for deterministic phrasings; the default pre_route() iterates patterns and dispatches to the named handler method",
            "Decorate methods with @callback('name') to expose them as interactive-notification callbacks (tapped from rich inbox items in the mobile app); signature is (self, data: dict, request_info: RequestInformation) -> CommandResponse",
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

    # ── Mobile command-data browser ───────────────────────────────────────
    # See PRD: mobile/command-data browser. These let mobile render a
    # structured form over rows the command persists via JarvisStorage.

    @property
    def data_browser_storage_name(self) -> str:
        """The `command_data.command_name` value under which this command's
        records live.

        Defaults to `command_name`. Override when the JarvisStorage key
        diverges from the LLM-facing command_name — e.g. `ReminderCommand`
        has command_name="reminder" but persists rows under "set_reminder"
        for historical reasons.

        The mobile browser displays records under `command_name`; the node
        uses this property to resolve which JarvisStorage rows belong to
        which command.
        """
        return self.command_name

    @property
    def data_browser_mode(self) -> DataBrowserMode:
        """Whether this command's stored data appears in the mobile browser.

        - "enabled"  (default): list, view detail, edit, delete are all on.
        - "disabled": not shown at all. The node filters before serialising
          so disabled data never crosses the wire.
        - "readonly": list + view detail, no edit, no delete. Reserved for
          future mobile support — older mobile builds that don't recognise
          the value hide the section, so commands shipping `readonly`
          aren't accidentally exposed as fully editable.

        Wire format is a plain string so new modes can ship without breaking
        older command-center or mobile builds. Only "disabled" is filtered
        node-side; unknown values pass through and mobile decides how to
        render.

        Override to opt out of the browser:
            @property
            def data_browser_mode(self) -> DataBrowserMode:
                return "disabled"
        """
        return "enabled"

    def editable_fields(self) -> List[FieldSpec]:
        """Schema for the records this command persists.

        Returned list drives the mobile form: each FieldSpec maps to one row
        (text input, datetime picker, enum dropdown, etc.). Empty list means
        the command opts out of the structured editor — the browser will
        still list rows but render them as read-only JSON.

        Default: empty.

        Implementations should match the keys present in the dicts the
        command stores via JarvisStorage. Fields the command computes
        internally (e.g. counters, timestamps) are usually marked
        editable=False so mobile shows them but doesn't allow edits.
        """
        return []

    def display_summary(self, record: dict) -> RecordSummary:
        """Title + subtitle + icon for one row of `record` in the list view.

        Default: title is the first string field in `record`, subtitle is
        None, icon is a generic "information-outline". Commands should
        override to give meaningful list rows (e.g. a reminder uses its
        `text` as the title and the human-formatted `due_at` as the
        subtitle).

        `record` is the raw dict the command saved via JarvisStorage. The
        function must be tolerant of partial/legacy records (missing keys
        from earlier schema versions): use `.get(...)` with sensible
        fallbacks, never raise.
        """
        title = next(
            (str(v) for v in record.values() if isinstance(v, str) and v),
            self.command_name,
        )
        return RecordSummary(title=title)

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

    @property
    def fast_path_patterns(self) -> List[FastPathPattern]:
        """Declarative regex patterns this command claims for the LLM-bypass fast path.

        Patterns are surfaced to the mobile app for inspection and per-pattern
        disabling. The default `pre_route()` implementation iterates these
        patterns, skips any in `disabled_pattern_ids`, regex-matches against
        the voice command, and dispatches to the pattern's `handler` method.

        Commands with custom parsing should override `pre_route()` directly
        but should still declare patterns here as metadata (with `regex=None`
        and `handler=None`) so the mobile inspect UI can show and disable them.

        Returns:
            List of FastPathPattern (default: empty — no fast-path coverage).
        """
        return []

    def pre_route(
        self,
        voice_command: str,
        *,
        disabled_pattern_ids: "set[str] | frozenset[str]" = frozenset(),
    ) -> PreRouteResult | None:
        """Deterministic matching -- bypass the command center entirely.

        Default impl: iterates `fast_path_patterns`, skips any whose `id` is
        in `disabled_pattern_ids`, searches each pattern's regex in the voice
        command (case-insensitive, substring match — anchor with `^` for
        start-of-string), and dispatches to the declared handler method on
        this command.

        Override to claim short/unambiguous utterances that don't fit the
        declarative pattern shape (e.g. multi-step parsers like time
        durations). Overrides must still honor `disabled_pattern_ids` --
        check the set before claiming an utterance for a declared pattern.

        Args:
            voice_command: The raw transcript to match against.
            disabled_pattern_ids: Pattern IDs the user has disabled via the
                mobile inspect UI. The default impl skips matching patterns
                whose `id` is in this set.

        Returns:
            PreRouteResult with arguments for execute(), or None to fall
            through to the normal LLM path.
        """
        for pattern in self.fast_path_patterns:
            if pattern.id in disabled_pattern_ids:
                continue
            if not pattern.regex or not pattern.handler:
                continue
            match = re.search(pattern.regex, voice_command, re.IGNORECASE)
            if not match:
                continue
            handler_fn = getattr(self, pattern.handler, None)
            if handler_fn is None:
                continue
            result = handler_fn(match, voice_command)
            if result is not None:
                return result
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

    def get_callbacks(self) -> Dict[str, Callable[..., CommandResponse]]:
        """Return ``{callback_name: bound_method}`` for methods decorated with ``@callback``.

        Walks the class MRO most-derived-first and collects methods carrying
        the ``__jarvis_callback_name__`` marker. Subclass overrides win (a
        subclass method with the same callback name shadows the parent's).

        Inspects each class's ``__dict__`` directly rather than walking
        ``dir(self)`` so that subclass-defined property getters aren't
        invoked as a side-effect of introspection.

        Raises ``ValueError`` if a single class declares two methods with
        the same callback name — that's a programming bug, not a runtime
        condition.

        Returns an empty dict for commands with no decorated callbacks
        (the default for every existing command).
        """
        callbacks: Dict[str, Callable[..., CommandResponse]] = {}
        for klass in type(self).__mro__:
            seen_in_class: set[str] = set()
            for attr_name, attr in vars(klass).items():
                if not callable(attr):
                    continue
                cb_name = getattr(attr, "__jarvis_callback_name__", None)
                if cb_name is None:
                    continue
                if cb_name in seen_in_class:
                    raise ValueError(
                        f"Command '{type(self).__name__}' declares multiple "
                        f"@callback methods with name '{cb_name}' in class "
                        f"{klass.__name__}"
                    )
                seen_in_class.add(cb_name)
                if cb_name in callbacks:
                    continue  # already claimed by a more-derived class
                callbacks[cb_name] = getattr(self, attr_name)
        return callbacks

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

    # ── Execute (concrete) ────────────────────────────────────────────

    def execute(
        self,
        request_info: RequestInformation,
        *,
        secrets: Dict[str, str] | None = None,
        **kwargs: Any,
    ) -> CommandResponse:
        """Validated entry point. Hosts should call this, not `run()` directly.

        Pipeline:
        1. If `secrets` is provided, assert all required secrets are present
           (raises MissingSecretsError). If it's None, the check is skipped —
           the command is trusted to manage its own lookups.
        2. Required-param presence check (raises ValueError on omissions).
        3. `validate_call(**kwargs)` — value-level validation, returning a
           CommandResponse.validation_error() if any fail.
        4. Apply any auto-corrections (`suggested_value`) back into kwargs.
        5. Delegate to `run()`, forwarding `secrets` only when it was given.

        Args:
            request_info: Request metadata (voice command, conversation id, user id).
            secrets: Dict of secret-key → value, built by the host from its
                secret store. Pass None when the caller explicitly wants to
                skip secret enforcement (tests, dev-mode).
            **kwargs: Command parameters.
        """
        if secrets is not None:
            missing = [
                s.key for s in self.required_secrets
                if s.required and not secrets.get(s.key)
            ]
            if missing:
                raise MissingSecretsError(missing)

        missing_params = [
            p.name for p in self.parameters
            if p.required and kwargs.get(p.name) is None
        ]
        if missing_params:
            raise ValueError(
                f"Missing required params: {', '.join(missing_params)}",
            )

        results = self.validate_call(**kwargs)
        errors = [r for r in results if not r.success]
        if errors:
            return CommandResponse.validation_error(errors)
        for r in results:
            if r.suggested_value is not None:
                kwargs[r.param_name] = r.suggested_value

        if secrets is not None:
            return self.run(request_info, secrets=secrets, **kwargs)
        return self.run(request_info, **kwargs)

    # ── OAuth helpers (concrete) ───────────────────────────────────────

    def needs_auth(
        self,
        *,
        secrets: Dict[str, str],
        auth_status: AuthStatus | None = None,
    ) -> bool:
        """Whether this command needs the user to (re)-authenticate.

        Pure check: takes the current secrets map and an optional AuthStatus
        (host-supplied; e.g. set when a prior request returned 401). Commands
        with no `authentication` config return False.
        """
        if not self.authentication:
            return False
        for s in self.required_secrets:
            if s.required and not secrets.get(s.key):
                return True
        if auth_status is not None and auth_status.needs_auth:
            return True
        return False

    def refresh_token(
        self,
        *,
        refresh_token: str,
        client_secret: str | None = None,
        timeout_seconds: float = 15.0,
    ) -> TokenBundle | None:
        """Standard OAuth2 `refresh_token` grant.

        Returns a TokenBundle on success (caller persists). Returns None if
        this command has no authentication config or the refresh HTTP call
        fails. Commands with non-standard refresh flows should override this.
        """
        auth = self.authentication
        if not auth or not auth.exchange_url:
            return None

        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": auth.client_id,
        }
        if client_secret:
            payload["client_secret"] = client_secret

        try:
            req = Request(
                auth.exchange_url,
                data=urlencode(payload).encode(),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            with urlopen(req, timeout=timeout_seconds) as resp:
                data = json.loads(resp.read().decode())
        except Exception:
            return None

        return TokenBundle(
            access_token=data.get("access_token"),
            refresh_token=data.get("refresh_token", refresh_token),
            expires_in=data.get("expires_in"),
            raw=data,
        )

    # ── Abstract method ───────────────────────────────────────────────

    @abstractmethod
    def run(self, request_info: RequestInformation, **kwargs) -> CommandResponse:
        """
        Execute the command with request information and parameters.

        Called by `execute()` after validation. Hosts that want secret
        enforcement should go through `execute()`, which will pass a
        `secrets` kwarg if it was provided.

        Args:
            request_info: Information about the request from JCC.
            **kwargs: Parameters + (optionally) a `secrets` dict.

        Returns:
            CommandResponse object.
        """
        pass
