"""Tests for the @callback decorator and IJarvisCommand.get_callbacks()."""

import pytest

from jarvis_command_sdk import (
    IJarvisCommand,
    CommandResponse,
    JarvisParameter,
    JarvisSecret,
    CommandExample,
    RequestInformation,
    callback,
)


# ── Fixtures ───────────────────────────────────────────────────────────────


class BaselineCommand(IJarvisCommand):
    """No callbacks declared — establishes the back-compat baseline."""

    @property
    def command_name(self) -> str:
        return "baseline"

    @property
    def description(self) -> str:
        return "Baseline"

    @property
    def parameters(self):
        return [JarvisParameter("q", "string", required=True)]

    @property
    def required_secrets(self):
        return []

    @property
    def keywords(self):
        return []

    def generate_prompt_examples(self):
        return [CommandExample("hi", {"q": "x"}, is_primary=True)]

    def generate_adapter_examples(self):
        return self.generate_prompt_examples()

    def run(self, request_info, **kwargs):
        return CommandResponse.success_response({"q": kwargs.get("q")})


class MovieKnowledgeCommand(BaselineCommand):
    """Realistic shape — one command, several @callback methods."""

    @property
    def command_name(self) -> str:
        return "movie_knowledge"

    @callback("expand_actor")
    def expand_actor(self, data: dict, request_info: RequestInformation) -> CommandResponse:
        return CommandResponse.final_response(
            {"actor_id": data.get("actor_id"), "kind": "actor"}
        )

    @callback("expand_director")
    def expand_director(self, data: dict, request_info: RequestInformation) -> CommandResponse:
        return CommandResponse.final_response(
            {"director_id": data.get("director_id"), "kind": "director"}
        )


# ── Decorator tests ────────────────────────────────────────────────────────


class TestCallbackDecorator:
    def test_marks_method_with_callback_name(self):
        @callback("foo")
        def fn(self, data, request_info):
            return None

        assert getattr(fn, "__jarvis_callback_name__") == "foo"

    def test_returns_original_function(self):
        def fn(self, data, request_info):
            return "ok"

        decorated = callback("bar")(fn)
        assert decorated is fn

    def test_rejects_empty_name(self):
        with pytest.raises(ValueError, match="non-empty string name"):
            callback("")

    def test_rejects_non_string_name(self):
        with pytest.raises(ValueError, match="non-empty string name"):
            callback(None)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="non-empty string name"):
            callback(123)  # type: ignore[arg-type]


# ── get_callbacks() tests ──────────────────────────────────────────────────


class TestGetCallbacks:
    def test_empty_when_no_decorators(self):
        """Back-compat: every existing command must return {} by default."""
        cmd = BaselineCommand()
        assert cmd.get_callbacks() == {}

    def test_returns_decorated_methods_by_name(self):
        cmd = MovieKnowledgeCommand()
        callbacks = cmd.get_callbacks()
        assert set(callbacks.keys()) == {"expand_actor", "expand_director"}

    def test_returned_method_is_invocable(self):
        cmd = MovieKnowledgeCommand()
        ri = RequestInformation(voice_command="cb:expand_actor", conversation_id="c-1")
        resp = cmd.get_callbacks()["expand_actor"]({"actor_id": "nm0000158"}, ri)
        assert resp.success is True
        assert resp.context_data["actor_id"] == "nm0000158"
        assert resp.context_data["kind"] == "actor"

    def test_returned_method_is_bound_to_instance(self):
        """Calling the returned callable should not require passing self."""
        cmd = MovieKnowledgeCommand()
        director_fn = cmd.get_callbacks()["expand_director"]
        ri = RequestInformation(voice_command="cb:expand_director", conversation_id="c-1")
        # Two positional args (data, request_info) — no self.
        resp = director_fn({"director_id": "nm0000033"}, ri)
        assert resp.context_data["director_id"] == "nm0000033"

    def test_inherits_callbacks_from_parent(self):
        class WithExtra(MovieKnowledgeCommand):
            @callback("expand_similar")
            def expand_similar(self, data, request_info):
                return CommandResponse.final_response({"kind": "similar"})

        cmd = WithExtra()
        assert set(cmd.get_callbacks().keys()) == {
            "expand_actor", "expand_director", "expand_similar",
        }

    def test_subclass_override_wins(self):
        """Subclass redefining a callback name shadows the parent's method."""
        class Overridden(MovieKnowledgeCommand):
            @callback("expand_actor")
            def expand_actor(self, data, request_info):
                return CommandResponse.final_response({"kind": "overridden"})

        cmd = Overridden()
        ri = RequestInformation(voice_command="x", conversation_id="c")
        resp = cmd.get_callbacks()["expand_actor"]({}, ri)
        assert resp.context_data["kind"] == "overridden"

    def test_does_not_invoke_property_getters(self):
        """Property getters with side effects must not fire during introspection."""
        side_effect_log: list[str] = []

        class WithSideEffectProperty(BaselineCommand):
            @property
            def dangerous(self) -> str:
                side_effect_log.append("invoked")
                raise RuntimeError("getter should never run during introspection")

            @callback("safe")
            def safe(self, data, request_info):
                return CommandResponse.final_response({})

        cmd = WithSideEffectProperty()
        callbacks = cmd.get_callbacks()
        assert "safe" in callbacks
        assert side_effect_log == []

    def test_duplicate_callback_name_in_same_class_raises(self):
        class Duped(BaselineCommand):
            @callback("dup")
            def a(self, data, request_info):
                return CommandResponse.final_response({})

            @callback("dup")
            def b(self, data, request_info):
                return CommandResponse.final_response({})

        cmd = Duped()
        with pytest.raises(ValueError, match="multiple @callback methods"):
            cmd.get_callbacks()

    def test_handle_action_still_works(self):
        """Back-compat: introducing @callback must not disturb handle_action."""
        cmd = MovieKnowledgeCommand()
        resp = cmd.handle_action("cancel_click", {})
        assert resp.success is True
        assert resp.context_data["cancelled"] is True
