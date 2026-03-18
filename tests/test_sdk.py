"""Tests for jarvis-command-sdk core interfaces."""

import pytest

from jarvis_command_sdk import (
    IJarvisCommand,
    CommandResponse,
    JarvisParameter,
    JarvisSecret,
    JarvisPackage,
    IJarvisButton,
    AuthenticationConfig,
    RequestInformation,
    ValidationResult,
    CommandExample,
    CommandAntipattern,
    PreRouteResult,
)


# ── Test fixtures ──────────────────────────────────────────────────────────


class SampleCommand(IJarvisCommand):
    """Minimal concrete command for testing."""

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
        return [
            JarvisSecret("TEST_API_KEY", "API key for testing", "integration", "string"),
        ]

    @property
    def keywords(self):
        return ["test", "sample"]

    def generate_prompt_examples(self):
        return [
            CommandExample("test something", {"query": "something"}, is_primary=True),
        ]

    def generate_adapter_examples(self):
        return self.generate_prompt_examples()

    def run(self, request_info, **kwargs):
        return CommandResponse.success_response({"result": kwargs.get("query")})


# ── CommandResponse tests ──────────────────────────────────────────────────


class TestCommandResponse:
    def test_success_response(self):
        resp = CommandResponse.success_response({"key": "value"})
        assert resp.success is True
        assert resp.context_data == {"key": "value"}
        assert resp.wait_for_input is True

    def test_error_response(self):
        resp = CommandResponse.error_response("something broke")
        assert resp.success is False
        assert resp.error_details == "something broke"
        assert resp.wait_for_input is False

    def test_final_response(self):
        resp = CommandResponse.final_response({"done": True})
        assert resp.success is True
        assert resp.wait_for_input is False

    def test_follow_up_response(self):
        resp = CommandResponse.follow_up_response({"prompt": "continue?"})
        assert resp.success is True
        assert resp.wait_for_input is True

    def test_chunked_response(self):
        resp = CommandResponse.chunked_response("session-1", {"chunk": 1})
        assert resp.is_chunked_response is True
        assert resp.chunk_session_id == "session-1"

    def test_validation_error(self):
        results = [
            ValidationResult(success=False, param_name="query", command_name="test", message="required"),
        ]
        resp = CommandResponse.validation_error(results)
        assert resp.success is False
        assert "_validation_error" in resp.context_data

    def test_error_details_sets_success_false(self):
        resp = CommandResponse(error_details="oops", success=True)
        assert resp.success is False

    def test_actions_as_dicts(self):
        btn = IJarvisButton("Click", "click_action", "primary")
        resp = CommandResponse(actions=[btn])
        dicts = resp.actions_as_dicts()
        assert len(dicts) == 1
        assert dicts[0]["button_text"] == "Click"

    def test_actions_as_dicts_empty(self):
        resp = CommandResponse()
        assert resp.actions_as_dicts() == []


# ── JarvisParameter tests ──────────────────────────────────────────────────


class TestJarvisParameter:
    def test_basic_creation(self):
        p = JarvisParameter("name", "string", required=True, description="A name")
        assert p.name == "name"
        assert p.param_type == "string"
        assert p.required is True

    def test_invalid_type_raises(self):
        with pytest.raises(ValueError, match="not allowed"):
            JarvisParameter("x", "invalid_type")

    def test_validate_string(self):
        p = JarvisParameter("q", "string", required=True)
        assert p.validate("hello") == (True, None)

    def test_validate_wrong_type(self):
        p = JarvisParameter("q", "int", required=True)
        ok, msg = p.validate("not_int")
        assert ok is False

    def test_validate_enum(self):
        p = JarvisParameter("color", "string", enum_values=["red", "blue"])
        assert p.validate("red") == (True, None)
        ok, msg = p.validate("green")
        assert ok is False
        assert "green" in msg

    def test_to_dict(self):
        p = JarvisParameter("q", "string", required=True, description="query")
        d = p.to_dict()
        assert d["name"] == "q"
        assert d["type"] == "string"
        assert d["required"] is True

    def test_array_types(self):
        for t in ["array<string>", "array[datetime]", "datetime[]"]:
            p = JarvisParameter("items", t)
            assert p.validate([1, 2, 3]) == (True, None)

    def test_float_accepts_int(self):
        p = JarvisParameter("val", "float")
        assert p.validate(42) == (True, None)

    def test_refinable(self):
        p = JarvisParameter("q", "string", refinable=True)
        assert p.refinable is True
        d = p.to_dict()
        assert d["refinable"] is True


# ── JarvisSecret tests ──────────────────────────────────────────────────────


class TestJarvisSecret:
    def test_basic_creation(self):
        s = JarvisSecret("KEY", "desc", "integration", "string")
        assert s.key == "KEY"
        assert s.scope == "integration"
        assert s.required is True
        assert s.is_sensitive is True

    def test_invalid_scope(self):
        with pytest.raises(ValueError, match="Scope must be"):
            JarvisSecret("K", "d", "invalid", "string")

    def test_invalid_value_type(self):
        with pytest.raises(ValueError, match="Value Type"):
            JarvisSecret("K", "d", "integration", "float")

    def test_friendly_name(self):
        s = JarvisSecret("K", "d", "node", "string", friendly_name="My Key")
        assert s.friendly_name == "My Key"

    def test_not_sensitive(self):
        s = JarvisSecret("URL", "URL", "integration", "string", is_sensitive=False)
        assert s.is_sensitive is False


# ── AuthenticationConfig tests ─────────────────────────────────────────────


class TestAuthenticationConfig:
    def test_external_oauth(self):
        auth = AuthenticationConfig(
            type="oauth",
            provider="spotify",
            friendly_name="Spotify",
            client_id="abc",
            keys=["access_token"],
            authorize_url="https://accounts.spotify.com/authorize",
            exchange_url="https://accounts.spotify.com/api/token",
            supports_pkce=True,
        )
        d = auth.to_dict()
        assert d["provider"] == "spotify"
        assert d["supports_pkce"] is True
        assert "authorize_url" in d

    def test_local_oauth(self):
        auth = AuthenticationConfig(
            type="oauth",
            provider="home_assistant",
            friendly_name="Home Assistant",
            client_id="jarvis",
            keys=["access_token"],
            authorize_path="/auth/authorize",
            exchange_path="/auth/token",
            discovery_port=8123,
        )
        d = auth.to_dict()
        assert d["discovery_port"] == 8123
        assert "authorize_url" not in d

    def test_to_dict_minimal(self):
        auth = AuthenticationConfig(
            type="oauth", provider="p", friendly_name="P",
            client_id="c", keys=["k"],
        )
        d = auth.to_dict()
        assert set(d.keys()) == {"type", "provider", "friendly_name", "client_id", "keys"}


# ── IJarvisButton tests ───────────────────────────────────────────────────


class TestIJarvisButton:
    def test_to_dict(self):
        btn = IJarvisButton("Send", "send_click", "primary", button_icon="send")
        d = btn.to_dict()
        assert d["button_text"] == "Send"
        assert d["button_icon"] == "send"

    def test_to_dict_no_icon(self):
        btn = IJarvisButton("Cancel", "cancel_click", "destructive")
        d = btn.to_dict()
        assert "button_icon" not in d


# ── JarvisPackage tests ───────────────────────────────────────────────────


class TestJarvisPackage:
    def test_no_version(self):
        p = JarvisPackage("requests")
        assert p.to_pip_spec() == "requests"

    def test_pinned_version(self):
        p = JarvisPackage("httpx", "0.25.1")
        assert p.to_pip_spec() == "httpx==0.25.1"

    def test_constraint_version(self):
        p = JarvisPackage("pydantic", ">=2.0,<3.0")
        assert p.to_pip_spec() == "pydantic>=2.0,<3.0"

    def test_frozen(self):
        p = JarvisPackage("x")
        with pytest.raises(AttributeError):
            p.name = "y"


# ── RequestInformation tests ──────────────────────────────────────────────


class TestRequestInformation:
    def test_basic(self):
        ri = RequestInformation("hello", "conv-1")
        assert ri.voice_command == "hello"
        assert ri.is_validation_response is False

    def test_validation(self):
        ri = RequestInformation("retry", "conv-1", is_validation_response=True, validation_context={"key": "val"})
        assert ri.is_validation_response is True
        assert ri.validation_context == {"key": "val"}


# ── IJarvisCommand tests ──────────────────────────────────────────────────


class TestIJarvisCommand:
    def test_concrete_command(self):
        cmd = SampleCommand()
        assert cmd.command_name == "test_command"
        assert cmd.description == "A test command"
        assert len(cmd.parameters) == 2
        assert len(cmd.required_secrets) == 1
        assert cmd.keywords == ["test", "sample"]

    def test_defaults(self):
        cmd = SampleCommand()
        assert cmd.rules == []
        assert cmd.antipatterns == []
        assert cmd.allow_direct_answer is False
        assert cmd.critical_rules == []
        assert cmd.required_packages == []
        assert cmd.associated_service is None
        assert cmd.authentication is None
        assert cmd.supported_platforms == []

    def test_run(self):
        cmd = SampleCommand()
        ri = RequestInformation("test query", "conv-1")
        resp = cmd.run(ri, query="hello")
        assert resp.success is True
        assert resp.context_data["result"] == "hello"

    def test_validate_call_valid(self):
        cmd = SampleCommand()
        results = cmd.validate_call(query="hello")
        assert all(r.success for r in results) or len(results) == 0

    def test_validate_call_invalid_type(self):
        cmd = SampleCommand()
        results = cmd.validate_call(count="not_int")
        errors = [r for r in results if not r.success]
        assert len(errors) == 1
        assert errors[0].param_name == "count"

    def test_pre_route_default_none(self):
        cmd = SampleCommand()
        assert cmd.pre_route("test") is None

    def test_post_process_passthrough(self):
        cmd = SampleCommand()
        args = {"query": "test"}
        assert cmd.post_process_tool_call(args, "test") == args

    def test_handle_action_cancel(self):
        cmd = SampleCommand()
        resp = cmd.handle_action("cancel_click", {})
        assert resp.success is True
        assert resp.context_data["cancelled"] is True

    def test_handle_action_unknown(self):
        cmd = SampleCommand()
        resp = cmd.handle_action("unknown_action", {})
        assert resp.success is False

    def test_init_data_default(self):
        cmd = SampleCommand()
        assert cmd.init_data() == {"status": "no_init_required"}

    def test_all_possible_secrets_default(self):
        cmd = SampleCommand()
        secrets = cmd.all_possible_secrets
        assert len(secrets) == len(cmd.required_secrets)
        assert secrets[0].key == cmd.required_secrets[0].key

    def test_associated_service_with_auth(self):
        class AuthCmd(SampleCommand):
            @property
            def authentication(self):
                return AuthenticationConfig(
                    type="oauth", provider="test", friendly_name="Test Service",
                    client_id="c", keys=["access_token"],
                )
        cmd = AuthCmd()
        assert cmd.associated_service == "Test Service"


# ── Data class tests ───────────────────────────────────────────────────────


class TestDataClasses:
    def test_pre_route_result(self):
        pr = PreRouteResult(arguments={"key": "val"}, spoken_response="done")
        assert pr.arguments == {"key": "val"}
        assert pr.spoken_response == "done"

    def test_command_example(self):
        ex = CommandExample("turn on lights", {"room": "kitchen"}, is_primary=True)
        assert ex.is_primary is True

    def test_command_antipattern(self):
        ap = CommandAntipattern("other_cmd", "Use this instead")
        assert ap.command_name == "other_cmd"

    def test_validation_result(self):
        vr = ValidationResult(success=False, param_name="p", command_name="c", message="bad")
        assert vr.success is False
