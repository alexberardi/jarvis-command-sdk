"""Context-provider capability — typed plan-time queries a command answers.

Phone-calls PRD (cross-agent-context): context enters at PLAN time via the
node's generic context handler; the provider stays node-side so credentials
never leave the LAN edge.
"""

import pytest

from jarvis_command_sdk import ContextOperation, ContextResult
from jarvis_command_sdk.command import CommandExample, CommandResponse, IJarvisCommand


AVAILABILITY = ContextOperation(
    name="availability",
    description="Free/busy windows in a date range",
    params_schema={
        "start": {"type": "string", "required": True, "description": "ISO date"},
        "end": {"type": "string", "required": True, "description": "ISO date"},
        "granularity": {"type": "string", "required": False, "description": "…"},
    },
)


class _Provider(IJarvisCommand):
    """Minimal command declaring one context op."""

    @property
    def command_name(self) -> str:
        return "calendar"

    @property
    def description(self) -> str:
        return "test"

    def generate_prompt_examples(self):
        return [CommandExample("check availability", {}, is_primary=True)]

    def generate_adapter_examples(self):
        return self.generate_prompt_examples()

    @property
    def parameters(self):
        return []

    @property
    def required_secrets(self):
        return []

    @property
    def keywords(self):
        return ["calendar"]

    def run(self, request_info, **kwargs):  # pragma: no cover - unused
        return CommandResponse.success_response({})

    @property
    def context_operations(self):
        return [AVAILABILITY]

    def execute_context_operation(self, operation, params):
        if operation != "availability":
            return ContextResult.failed(f"unknown op {operation}")
        return ContextResult(data={"busy": [], "free": ["Thu 14:00-17:00"]})


class _Plain(_Provider):
    """Command with no context capability (the default for every command)."""

    @property
    def context_operations(self):
        return IJarvisCommand.context_operations.fget(self)

    def execute_context_operation(self, operation, params):
        return IJarvisCommand.execute_context_operation(self, operation, params)


class TestDeclaration:
    def test_default_is_no_operations(self):
        assert _Plain().context_operations == []

    def test_declared_operation_serializes(self):
        d = _Provider().context_operations[0].to_dict()
        assert d["name"] == "availability"
        assert d["params_schema"]["start"]["required"] is True


class TestParamValidation:
    def test_missing_required_params_reported(self):
        assert AVAILABILITY.missing_required({"start": "2026-07-20"}) == ["end"]

    def test_optional_params_not_required(self):
        assert AVAILABILITY.missing_required(
            {"start": "2026-07-20", "end": "2026-07-27"}
        ) == []


class TestExecution:
    def test_provider_answers(self):
        r = _Provider().execute_context_operation(
            "availability", {"start": "a", "end": "b"}
        )
        assert r.ok and r.data["free"] == ["Thu 14:00-17:00"]
        assert r.to_dict() == {
            "ok": True,
            "data": {"free": ["Thu 14:00-17:00"], "busy": []},
            "error": None,
        }

    def test_unknown_op_fails_without_raising(self):
        r = _Provider().execute_context_operation("nope", {})
        assert not r.ok and "unknown op" in r.error

    def test_default_implementation_fails_honestly(self):
        r = _Plain().execute_context_operation("availability", {})
        assert not r.ok
        assert "does not implement" in r.error

    def test_failed_helper_carries_no_data(self):
        r = ContextResult.failed("calendar unreachable")
        assert r.to_dict() == {"ok": False, "data": {}, "error": "calendar unreachable"}
