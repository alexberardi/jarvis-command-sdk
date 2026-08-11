"""IJarvisCommand.listening_signal_types — the consumer's signal-interest hint."""
from jarvis_command_sdk import IJarvisCommand, CommandResponse, CommandExample


class _Base(IJarvisCommand):
    @property
    def parameters(self):
        return []

    @property
    def keywords(self):
        return []

    @property
    def required_secrets(self):
        return []

    def generate_prompt_examples(self):
        return [CommandExample(voice_command="do it", expected_parameters={}, is_primary=True)]

    def generate_adapter_examples(self):
        return self.generate_prompt_examples()

    def run(self, request_info, **kwargs):
        return CommandResponse.success_response(context_data={})


class _Listening(_Base):
    @property
    def command_name(self) -> str:
        return "listen_cmd"

    @property
    def description(self) -> str:
        return "listens for appt + presence signals"

    @property
    def listening_signal_types(self):
        return ["appt.detected", "presence.transition"]


class _Plain(_Base):
    @property
    def command_name(self) -> str:
        return "plain_cmd"

    @property
    def description(self) -> str:
        return "not signal-specific"


def test_default_is_empty_and_absent_from_schema():
    c = _Plain()
    assert c.listening_signal_types == []
    assert "listening_signal_types" not in c.get_command_schema()


def test_declared_types_ride_the_schema():
    schema = _Listening().get_command_schema()
    assert schema["listening_signal_types"] == ["appt.detected", "presence.transition"]
