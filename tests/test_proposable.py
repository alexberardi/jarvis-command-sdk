"""Tests for the proposable-action contract:

- ProposableAction / BlastTier dataclasses + validation + wire form
- IJarvisCommand.proposable_actions (opt-in, default []) + get_proposable_actions()
- get_command_schema() advertising proposable_actions to command-center
- JarvisInbox.propose_action() building the server-plane confirm card
"""

import pytest

from jarvis_command_sdk import (
    IJarvisCommand,
    CommandResponse,
    JarvisParameter,
    CommandExample,
    RequestInformation,
    callback,
    ProposableAction,
    BlastTier,
    JarvisInbox,
    InboxBackend,
)
import jarvis_command_sdk.inbox as inbox_module


# ── Fixtures ────────────────────────────────────────────────────────────────


class BaselineCommand(IJarvisCommand):
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


class AddEventCommand(BaselineCommand):
    """A command exposing one proposable @callback — the calendar-add shape."""

    @property
    def command_name(self) -> str:
        return "add_event"

    @property
    def parameters(self):
        return [
            JarvisParameter("title", "string", required=True),
            JarvisParameter("start", "datetime", required=True),
            JarvisParameter("end", "datetime", required=False),
            JarvisParameter("idempotency_key", "string", required=True),
        ]

    @property
    def proposable_actions(self):
        return [
            ProposableAction(
                callback="create_event",
                params=self.parameters,
                card_title="Add to your calendar?",
                confirm_label="Add",
                editable=["title", "start", "end"],
                blast_tier=BlastTier.reversible,
                idempotency_param="idempotency_key",
            )
        ]

    @callback("create_event")
    def create_event(self, data: dict, request_info: RequestInformation) -> CommandResponse:
        return CommandResponse.final_response({"added": True})


class MisdeclaredCommand(BaselineCommand):
    """Declares a proposable action whose callback does not exist — invalid."""

    @property
    def proposable_actions(self):
        return [ProposableAction(callback="does_not_exist")]


class FakeInboxBackend(InboxBackend):
    def __init__(self):
        self.calls = []

    def post_inbox_item(self, command_name, **kwargs):
        self.calls.append({"command_name": command_name, **kwargs})
        return "ok"


@pytest.fixture(autouse=True)
def _reset_backend():
    inbox_module._backend = None
    yield
    inbox_module._backend = None


# ── ProposableAction dataclass ───────────────────────────────────────────────


class TestProposableActionDataclass:
    def test_minimal_construction_defaults(self):
        a = ProposableAction(callback="create_event")
        assert a.callback == "create_event"
        assert a.params == []
        assert a.editable == []
        assert a.blast_tier == BlastTier.reversible
        assert a.confirm_label == "Confirm"
        assert a.idempotency_param is None

    def test_empty_callback_rejected(self):
        with pytest.raises(ValueError, match="callback"):
            ProposableAction(callback="")

    def test_editable_must_be_subset_of_params(self):
        with pytest.raises(ValueError, match="editable"):
            ProposableAction(
                callback="c",
                params=[JarvisParameter("title", "string")],
                editable=["title", "nope"],
            )

    def test_idempotency_param_must_be_a_declared_param(self):
        with pytest.raises(ValueError, match="idempotency_param"):
            ProposableAction(
                callback="c",
                params=[JarvisParameter("title", "string")],
                idempotency_param="missing",
            )

    def test_blast_tier_coerced_from_string(self):
        a = ProposableAction(callback="c", blast_tier="irreversible")
        assert a.blast_tier == BlastTier.irreversible

    def test_to_dict_wire_form(self):
        a = ProposableAction(
            callback="create_event",
            params=[JarvisParameter("title", "string", required=True)],
            card_title="Add?",
            confirm_label="Add",
            editable=["title"],
            blast_tier=BlastTier.reversible,
            idempotency_param=None,
        )
        d = a.to_dict()
        assert d["callback"] == "create_event"
        assert d["card_title"] == "Add?"
        assert d["confirm_label"] == "Add"
        assert d["editable"] == ["title"]
        assert d["blast_tier"] == "reversible"
        assert isinstance(d["params"], list) and d["params"][0]["name"] == "title"


# ── IJarvisCommand opt-in ────────────────────────────────────────────────────


class TestProposableActionsProperty:
    def test_default_is_empty_optin(self):
        assert BaselineCommand().proposable_actions == []
        assert BaselineCommand().get_proposable_actions() == {}

    def test_get_proposable_actions_returns_map(self):
        actions = AddEventCommand().get_proposable_actions()
        assert set(actions.keys()) == {"create_event"}
        assert actions["create_event"].blast_tier == BlastTier.reversible

    def test_misdeclared_callback_raises_at_discovery(self):
        with pytest.raises(ValueError, match="no @callback"):
            MisdeclaredCommand().get_proposable_actions()

    def test_schema_advertises_proposable_actions(self):
        schema = AddEventCommand().get_command_schema()
        assert "proposable_actions" in schema
        assert schema["proposable_actions"][0]["callback"] == "create_event"

    def test_schema_omits_when_none_declared(self):
        assert "proposable_actions" not in BaselineCommand().get_command_schema()


# ── JarvisInbox.propose_action ───────────────────────────────────────────────


class TestProposeAction:
    def test_returns_no_backend_without_backend(self):
        tag = JarvisInbox("appointment_scan").propose_action(
            target_command="add_event", action="create_event",
            params={"title": "Dentist", "idempotency_key": "k1"}, idempotency_key="k1",
        )
        assert tag == "no_backend"

    def test_invalid_when_missing_required_args(self):
        inbox_module._backend = FakeInboxBackend()
        inbox = JarvisInbox("appointment_scan")
        assert inbox.propose_action(target_command="", action="create_event",
                                    params={}, idempotency_key="k1") == "invalid"
        assert inbox.propose_action(target_command="add_event", action="",
                                    params={}, idempotency_key="k1") == "invalid"
        assert inbox.propose_action(target_command="add_event", action="create_event",
                                    params={}, idempotency_key="") == "invalid"

    def test_builds_server_plane_card(self):
        backend = FakeInboxBackend()
        inbox_module._backend = backend
        tag = JarvisInbox("appointment_scan").propose_action(
            target_command="add_event",
            action="create_event",
            params={"title": "Dentist", "start": "2026-08-10T09:00:00", "idempotency_key": "appt:msg-1"},
            idempotency_key="appt:msg-1",
            node_id="node-7",
            title="Add to your calendar?",
            confirm_label="Add",
            editable=["title", "start"],
            user_id=42,
        )
        assert tag == "ok"
        call = backend.calls[0]
        assert call["command_name"] == "appointment_scan"
        assert call["user_id"] == 42
        elements = call["metadata"]["interactive_elements"]
        confirm = next(e for e in elements if e["callback"] == "execute")
        dismiss = next(e for e in elements if e["callback"] == "dismiss")
        # Confirm routes to the single generic server-plane dispatcher.
        assert confirm["command"] == "jarvis.proposable_action"
        assert confirm["target"] == "server"
        meta = confirm["data"]["_action"]
        assert meta["target_command"] == "add_event"
        assert meta["target_callback"] == "create_event"
        assert meta["node_id"] == "node-7"
        assert meta["idempotency_key"] == "appt:msg-1"
        # Declared params ride at the top level so mobile's field-merge injects edits.
        assert confirm["data"]["title"] == "Dentist"
        assert confirm["data"]["start"] == "2026-08-10T09:00:00"
        # Dismiss is inert (no param data, just the key).
        assert dismiss["command"] == "jarvis.proposable_action"
        assert dismiss["data"]["_action"]["idempotency_key"] == "appt:msg-1"


class TestNeverSuggestButton:
    def test_no_suppress_button_without_source_or_descriptor(self):
        backend = FakeInboxBackend()
        inbox_module._backend = backend
        JarvisInbox("appointment_scan").propose_action(
            target_command="add_event", action="create_event",
            params={"title": "x", "idempotency_key": "k1"}, idempotency_key="k1",
        )
        els = backend.calls[0]["metadata"]["interactive_elements"]
        assert not any(e["callback"] == "suppress" for e in els)

    def test_suppress_button_carries_source_and_descriptor(self):
        backend = FakeInboxBackend()
        inbox_module._backend = backend
        JarvisInbox("appointment_scan").propose_action(
            target_command="add_event", action="create_event",
            params={"title": "PR failed", "idempotency_key": "appt:99"}, idempotency_key="appt:99",
            source="notifications@github.com",
            descriptor="CI/build-failure notification from GitHub",
        )
        els = backend.calls[0]["metadata"]["interactive_elements"]
        suppress = next(e for e in els if e["callback"] == "suppress")
        assert suppress["command"] == "jarvis.proposable_action"
        assert suppress["target"] == "server"
        assert suppress["data"]["source"] == "notifications@github.com"
        assert suppress["data"]["descriptor"] == "CI/build-failure notification from GitHub"
        # Carries which command the suppression is about (for the blocklist row).
        assert suppress["data"]["_action"]["target_command"] == "add_event"


class TestEditableFieldTypes:
    def test_field_types_emit_input_type(self):
        backend = FakeInboxBackend()
        inbox_module._backend = backend
        JarvisInbox("appointment_scan").propose_action(
            target_command="add_event", action="create_event",
            params={"title": "Dentist", "start": "2026-08-10T09:00:00", "idempotency_key": "k1"},
            idempotency_key="k1",
            editable=["title", "start"],
            field_types={"start": "datetime"},
        )
        fields = {f["data_key"]: f for f in backend.calls[0]["metadata"]["editable_fields"]}
        # datetime field carries input_type so mobile renders a picker...
        assert fields["start"]["input_type"] == "datetime"
        # ...while an untyped field stays a plain text box (no input_type key).
        assert "input_type" not in fields["title"]
