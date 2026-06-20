"""Coverage/regression tests for jarvis_command_sdk.command.

Targets the method bodies that tests/test_sdk.py leaves uncovered:
schema generation (to_openai_tool_schema, get_command_schema,
get_primary_example, _validate_examples), the OAuth helpers
(needs_auth with an auth config, refresh_token's HTTP path), the
remaining pre_route branches, execute()'s validation-error and
suggested-value paths, and store_auth_values.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from jarvis_command_sdk import (
    AuthenticationConfig,
    AuthStatus,
    CommandAntipattern,
    CommandExample,
    CommandResponse,
    FastPathPattern,
    IJarvisCommand,
    JarvisParameter,
    JarvisSecret,
    PreRouteResult,
    RequestInformation,
    TokenBundle,
    ValidationResult,
)


# ── Test fixtures ──────────────────────────────────────────────────────────


class BaseCommand(IJarvisCommand):
    """Minimal concrete command. Subclasses tweak individual properties."""

    @property
    def command_name(self) -> str:
        return "test_command"

    @property
    def description(self) -> str:
        return "A test command"

    @property
    def parameters(self):
        return [
            JarvisParameter("query", "string", required=True, description="Search query"),
            JarvisParameter("count", "int", required=False, description="Result count"),
        ]

    @property
    def required_secrets(self):
        return [JarvisSecret("TEST_API_KEY", "API key", "integration", "string")]

    @property
    def keywords(self):
        return ["test", "sample"]

    def generate_prompt_examples(self):
        return [CommandExample("test something", {"query": "something"}, is_primary=True)]

    def generate_adapter_examples(self):
        return [
            CommandExample("variant a", {"query": "a"}),
            CommandExample("variant b", {"query": "b"}),
        ]

    def run(self, request_info, **kwargs):
        return CommandResponse.success_response({"result": kwargs.get("query")})


# ── _validate_examples ───────────────────────────────────────────────────────


class TestValidateExamples:
    def test_zero_primaries_ok(self) -> None:
        cmd = BaseCommand()
        # No exception when 0 primaries.
        cmd._validate_examples([CommandExample("x", {}), CommandExample("y", {})])

    def test_one_primary_ok(self) -> None:
        cmd = BaseCommand()
        cmd._validate_examples([CommandExample("x", {}, is_primary=True)])

    def test_multiple_primaries_raises(self) -> None:
        cmd = BaseCommand()
        examples = [
            CommandExample("x", {}, is_primary=True),
            CommandExample("y", {}, is_primary=True),
        ]
        with pytest.raises(ValueError, match="has 2 primary examples"):
            cmd._validate_examples(examples)


# ── to_openai_tool_schema ──────────────────────────────────────────────────


class TestToOpenAIToolSchema:
    def test_basic_shape(self) -> None:
        cmd = BaseCommand()
        schema = cmd.to_openai_tool_schema()
        assert schema["type"] == "function"
        fn = schema["function"]
        assert fn["name"] == "test_command"
        assert fn["description"] == "A test command"
        # Required param surfaces in required list; optional one does not.
        assert fn["parameters"]["required"] == ["query"]
        assert set(fn["parameters"]["properties"]) == {"query", "count"}
        # str → string, int → integer via _TYPE_MAPPING.
        assert fn["parameters"]["properties"]["query"]["type"] == "string"
        assert fn["parameters"]["properties"]["count"]["type"] == "integer"
        # Description is carried through.
        assert fn["parameters"]["properties"]["query"]["description"] == "Search query"
        assert schema["allow_direct_answer"] is False
        assert schema["keywords"] == ["test", "sample"]

    def test_examples_serialized(self) -> None:
        cmd = BaseCommand()
        schema = cmd.to_openai_tool_schema()
        assert schema["examples"] == [
            {
                "voice_command": "test something",
                "expected_parameters": {"query": "something"},
                "is_primary": True,
            }
        ]

    def test_enum_and_options_source_and_refinable(self) -> None:
        class EnumCmd(BaseCommand):
            @property
            def parameters(self):
                return [
                    JarvisParameter(
                        "color",
                        "string",
                        required=True,
                        enum_values=["red", "blue"],
                        refinable=True,
                        options_source="devices:light",
                    )
                ]

        schema = EnumCmd().to_openai_tool_schema()
        prop = schema["function"]["parameters"]["properties"]["color"]
        assert prop["enum"] == ["red", "blue"]
        assert prop["options_source"] == "devices:light"
        assert prop["_refinable"] is True

    def test_array_datetime_items(self) -> None:
        class ArrayCmd(BaseCommand):
            @property
            def parameters(self):
                return [JarvisParameter("dates", "array<datetime>", required=False)]

        prop = ArrayCmd().to_openai_tool_schema()["function"]["parameters"]["properties"]["dates"]
        assert prop["type"] == "array"
        assert prop["items"] == {"type": "string", "format": "date-time"}

    def test_array_date_items(self) -> None:
        class ArrayCmd(BaseCommand):
            @property
            def parameters(self):
                return [JarvisParameter("days", "date[]", required=False)]

        prop = ArrayCmd().to_openai_tool_schema()["function"]["parameters"]["properties"]["days"]
        assert prop["type"] == "array"
        assert prop["items"] == {"type": "string", "format": "date"}

    def test_antipatterns_included(self) -> None:
        class APCmd(BaseCommand):
            @property
            def antipatterns(self):
                return [CommandAntipattern("other_cmd", "use that instead")]

        schema = APCmd().to_openai_tool_schema()
        assert schema["antipatterns"] == [
            {"command_name": "other_cmd", "description": "use that instead"}
        ]

    def test_no_antipatterns_key_when_empty(self) -> None:
        cmd = BaseCommand()
        assert "antipatterns" not in cmd.to_openai_tool_schema()

    def test_multiple_primary_examples_raises(self) -> None:
        class BadCmd(BaseCommand):
            def generate_prompt_examples(self):
                return [
                    CommandExample("a", {}, is_primary=True),
                    CommandExample("b", {}, is_primary=True),
                ]

        with pytest.raises(ValueError, match="primary examples"):
            BadCmd().to_openai_tool_schema()


# ── get_command_schema ─────────────────────────────────────────────────────


class TestGetCommandSchema:
    def test_uses_prompt_examples_by_default(self) -> None:
        cmd = BaseCommand()
        schema = cmd.get_command_schema()
        assert schema["command_name"] == "test_command"
        assert schema["description"] == "A test command"
        assert schema["allow_direct_answer"] is False
        assert schema["keywords"] == ["test", "sample"]
        # Default uses prompt examples (single example).
        assert [e["voice_command"] for e in schema["examples"]] == ["test something"]
        # Parameters serialized via to_dict.
        assert {p["name"] for p in schema["parameters"]} == {"query", "count"}

    def test_uses_adapter_examples_when_requested(self) -> None:
        cmd = BaseCommand()
        schema = cmd.get_command_schema(use_adapter_examples=True)
        assert [e["voice_command"] for e in schema["examples"]] == ["variant a", "variant b"]

    def test_omits_optional_blocks_by_default(self) -> None:
        cmd = BaseCommand()
        schema = cmd.get_command_schema()
        assert "rules" not in schema
        assert "antipatterns" not in schema
        assert "critical_rules" not in schema

    def test_includes_rules_antipatterns_critical(self) -> None:
        class RichCmd(BaseCommand):
            @property
            def rules(self):
                return ["be nice"]

            @property
            def antipatterns(self):
                return [CommandAntipattern("alt", "use alt")]

            @property
            def critical_rules(self):
                return ["never delete"]

        schema = RichCmd().get_command_schema()
        assert schema["rules"] == ["be nice"]
        assert schema["antipatterns"] == [{"command_name": "alt", "description": "use alt"}]
        assert schema["critical_rules"] == ["never delete"]

    def test_validates_examples(self) -> None:
        class BadCmd(BaseCommand):
            def generate_prompt_examples(self):
                return [
                    CommandExample("a", {}, is_primary=True),
                    CommandExample("b", {}, is_primary=True),
                ]

        with pytest.raises(ValueError, match="primary examples"):
            BadCmd().get_command_schema()


# ── get_primary_example ────────────────────────────────────────────────────


class TestGetPrimaryExample:
    def test_returns_marked_primary(self) -> None:
        class Cmd(BaseCommand):
            def generate_prompt_examples(self):
                return [
                    CommandExample("first", {"query": "1"}),
                    CommandExample("the primary", {"query": "p"}, is_primary=True),
                ]

        ex = Cmd().get_primary_example()
        assert ex.voice_command == "the primary"

    def test_falls_back_to_first_when_none_marked(self) -> None:
        class Cmd(BaseCommand):
            def generate_prompt_examples(self):
                return [
                    CommandExample("first", {"query": "1"}),
                    CommandExample("second", {"query": "2"}),
                ]

        ex = Cmd().get_primary_example()
        assert ex.voice_command == "first"

    def test_raises_when_no_examples(self) -> None:
        class Cmd(BaseCommand):
            def generate_prompt_examples(self):
                return []

        with pytest.raises(ValueError, match="has no examples"):
            Cmd().get_primary_example()


# ── needs_auth (with an auth config) ───────────────────────────────────────


def _auth_config(**overrides) -> AuthenticationConfig:
    base = dict(
        type="oauth",
        provider="spotify",
        friendly_name="Spotify",
        client_id="client-123",
        keys=["access_token"],
        exchange_url="https://accounts.spotify.com/api/token",
    )
    base.update(overrides)
    return AuthenticationConfig(**base)


class AuthCommand(BaseCommand):
    @property
    def required_secrets(self):
        return [JarvisSecret("ACCESS_TOKEN", "OAuth access token", "integration", "string")]

    @property
    def authentication(self):
        return _auth_config()


class TestNeedsAuth:
    def test_missing_required_secret_means_needs_auth(self) -> None:
        cmd = AuthCommand()
        assert cmd.needs_auth(secrets={}) is True

    def test_present_secret_no_status_means_no_auth_needed(self) -> None:
        cmd = AuthCommand()
        assert cmd.needs_auth(secrets={"ACCESS_TOKEN": "tok"}) is False

    def test_auth_status_needs_auth_overrides_present_secret(self) -> None:
        cmd = AuthCommand()
        assert (
            cmd.needs_auth(
                secrets={"ACCESS_TOKEN": "tok"},
                auth_status=AuthStatus(needs_auth=True, reason="401"),
            )
            is True
        )

    def test_auth_status_not_needing_auth_returns_false(self) -> None:
        cmd = AuthCommand()
        assert (
            cmd.needs_auth(
                secrets={"ACCESS_TOKEN": "tok"},
                auth_status=AuthStatus(needs_auth=False),
            )
            is False
        )

    def test_optional_secret_missing_does_not_force_auth(self) -> None:
        class OptionalSecretCmd(AuthCommand):
            @property
            def required_secrets(self):
                return [
                    JarvisSecret("ACCESS_TOKEN", "tok", "integration", "string"),
                    JarvisSecret("OPTIONAL", "opt", "integration", "string", required=False),
                ]

        cmd = OptionalSecretCmd()
        # ACCESS_TOKEN present, OPTIONAL missing but not required → False.
        assert cmd.needs_auth(secrets={"ACCESS_TOKEN": "tok"}) is False


# ── refresh_token ──────────────────────────────────────────────────────────


class TestRefreshToken:
    def test_no_authentication_config_returns_none(self) -> None:
        # BaseCommand has no authentication config.
        cmd = BaseCommand()
        assert cmd.refresh_token(refresh_token="r") is None

    def test_no_exchange_url_returns_none(self) -> None:
        class NoUrlCmd(BaseCommand):
            @property
            def authentication(self):
                return _auth_config(exchange_url=None)

        assert NoUrlCmd().refresh_token(refresh_token="r") is None

    def test_successful_refresh_builds_request_and_returns_bundle(self) -> None:
        cmd = AuthCommand()

        response_body = json.dumps(
            {
                "access_token": "new-access",
                "refresh_token": "new-refresh",
                "expires_in": 3600,
                "scope": "read",
            }
        ).encode()

        fake_resp = MagicMock()
        fake_resp.read.return_value = response_body
        fake_resp.__enter__.return_value = fake_resp
        fake_resp.__exit__.return_value = False

        with patch("jarvis_command_sdk.command.urlopen", return_value=fake_resp) as mock_urlopen:
            bundle = cmd.refresh_token(refresh_token="old-refresh", client_secret="sekret")

        assert isinstance(bundle, TokenBundle)
        assert bundle.access_token == "new-access"
        assert bundle.refresh_token == "new-refresh"
        assert bundle.expires_in == 3600
        assert bundle.raw["scope"] == "read"

        # Verify the request was built correctly.
        assert mock_urlopen.call_count == 1
        req = mock_urlopen.call_args.args[0]
        assert req.full_url == "https://accounts.spotify.com/api/token"
        body = req.data.decode()
        assert "grant_type=refresh_token" in body
        assert "refresh_token=old-refresh" in body
        assert "client_id=client-123" in body
        assert "client_secret=sekret" in body
        # Form-encoded content type.
        headers = {k.lower(): v for k, v in req.headers.items()}
        assert headers["content-type"] == "application/x-www-form-urlencoded"
        # Timeout forwarded.
        assert mock_urlopen.call_args.kwargs["timeout"] == 15.0

    def test_omits_client_secret_when_not_provided(self) -> None:
        cmd = AuthCommand()
        fake_resp = MagicMock()
        fake_resp.read.return_value = json.dumps({"access_token": "a"}).encode()
        fake_resp.__enter__.return_value = fake_resp
        fake_resp.__exit__.return_value = False

        with patch("jarvis_command_sdk.command.urlopen", return_value=fake_resp) as mock_urlopen:
            cmd.refresh_token(refresh_token="r", timeout_seconds=5.0)

        body = mock_urlopen.call_args.args[0].data.decode()
        assert "client_secret" not in body
        assert mock_urlopen.call_args.kwargs["timeout"] == 5.0

    def test_falls_back_to_provided_refresh_token_when_absent_in_response(self) -> None:
        cmd = AuthCommand()
        fake_resp = MagicMock()
        # Response without a refresh_token field.
        fake_resp.read.return_value = json.dumps({"access_token": "a", "expires_in": 60}).encode()
        fake_resp.__enter__.return_value = fake_resp
        fake_resp.__exit__.return_value = False

        with patch("jarvis_command_sdk.command.urlopen", return_value=fake_resp):
            bundle = cmd.refresh_token(refresh_token="original-refresh")

        assert bundle is not None
        assert bundle.refresh_token == "original-refresh"

    def test_http_error_returns_none(self) -> None:
        cmd = AuthCommand()
        with patch(
            "jarvis_command_sdk.command.urlopen", side_effect=OSError("connection refused")
        ):
            assert cmd.refresh_token(refresh_token="r") is None

    def test_invalid_json_returns_none(self) -> None:
        cmd = AuthCommand()
        fake_resp = MagicMock()
        fake_resp.read.return_value = b"not json"
        fake_resp.__enter__.return_value = fake_resp
        fake_resp.__exit__.return_value = False
        with patch("jarvis_command_sdk.command.urlopen", return_value=fake_resp):
            assert cmd.refresh_token(refresh_token="r") is None


# ── pre_route remaining branches ───────────────────────────────────────────


class TestPreRouteBranches:
    def test_regex_no_match_continues(self) -> None:
        class FastCmd(BaseCommand):
            @property
            def fast_path_patterns(self):
                return [
                    FastPathPattern(
                        id="p.nomatch",
                        description="d",
                        example="e",
                        regex=r"^never_matches$",
                        handler="_h",
                    )
                ]

            def _h(self, match, voice_command):
                return PreRouteResult(arguments={}, spoken_response="x")

        # Regex won't match → falls through to None (line 463 continue).
        assert FastCmd().pre_route("anything else") is None

    def test_missing_handler_method_continues(self) -> None:
        class FastCmd(BaseCommand):
            @property
            def fast_path_patterns(self):
                return [
                    FastPathPattern(
                        id="p.missing",
                        description="d",
                        example="e",
                        regex=r".*",
                        handler="_does_not_exist",
                    )
                ]

        # getattr returns None → continue (lines 464-466), falls through.
        assert FastCmd().pre_route("anything") is None


# ── store_auth_values (default no-op) ──────────────────────────────────────


class TestStoreAuthValues:
    def test_default_is_noop(self) -> None:
        cmd = BaseCommand()
        # Default impl is a pass; should not raise and returns None.
        assert cmd.store_auth_values({"ACCESS_TOKEN": "tok", "_base_url": "http://x"}) is None


# ── execute(): validation-error + suggested-value paths ────────────────────


class TestExecuteValidationPaths:
    def test_validation_error_returns_response_not_run(self) -> None:
        class ValidatingCmd(BaseCommand):
            def validate_call(self, **kwargs):
                return [
                    ValidationResult(
                        success=False,
                        param_name="query",
                        command_name="test_command",
                        message="bad value",
                        valid_values=["a", "b"],
                    )
                ]

            def run(self, request_info, **kwargs):  # pragma: no cover - must not run
                raise AssertionError("run() should not be called on validation error")

        cmd = ValidatingCmd()
        ri = RequestInformation(voice_command="test", conversation_id="c")
        resp = cmd.execute(ri, query="hello")
        assert resp.success is False
        assert resp.context_data["_validation_error"] is True
        assert resp.context_data["errors"][0]["param"] == "query"

    def test_suggested_value_applied_before_run(self) -> None:
        class CorrectingCmd(BaseCommand):
            def validate_call(self, **kwargs):
                # A successful result that suggests a corrected value.
                return [
                    ValidationResult(
                        success=True,
                        param_name="query",
                        command_name="test_command",
                        suggested_value="corrected",
                    )
                ]

            def run(self, request_info, **kwargs):
                return CommandResponse.success_response({"result": kwargs["query"]})

        cmd = CorrectingCmd()
        ri = RequestInformation(voice_command="test", conversation_id="c")
        resp = cmd.execute(ri, query="original")
        assert resp.success is True
        # The suggested_value replaced the original kwarg before run().
        assert resp.context_data["result"] == "corrected"

    def test_no_suggested_value_keeps_original(self) -> None:
        cmd = BaseCommand()
        ri = RequestInformation(voice_command="test", conversation_id="c")
        resp = cmd.execute(ri, query="original")
        assert resp.success is True
        assert resp.context_data["result"] == "original"
