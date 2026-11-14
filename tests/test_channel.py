"""Channel: the calls a chat-service channel's daemon makes, over a fake command-center."""

from __future__ import annotations

import asyncio
import base64

import pytest

import jarvis_command_sdk.cc_http as cc_mod
from jarvis_command_sdk import (
    CCHttpBackend,
    Channel,
    ChannelImage,
    ChannelReply,
    CommandReply,
    Outgoing,
    split_reply,
)


class _CC(CCHttpBackend):
    def __init__(self, replies: dict) -> None:
        self.replies = replies
        self.calls: list = []

    def post(self, path: str, json: dict):
        self.calls.append((path, json))
        reply = self.replies.get(path.rsplit("/", 1)[1])
        return reply.pop(0) if isinstance(reply, list) else reply


@pytest.fixture
def cc():
    def use(**replies):
        fake = _CC(replies)
        cc_mod._backend = fake
        return fake

    yield use
    cc_mod._backend = None


def test_a_message_gets_the_reply(cc) -> None:
    fake = cc(message={"linked": True, "reply": "Noon."})
    reply = asyncio.run(Channel("discord").message("u1", "dm:9", "when?", [ChannelImage(b"\xff\xd8\xff", "image/jpeg")]))
    assert reply == ChannelReply(linked=True, say="Noon.")
    path, body = fake.calls[0]
    assert path == "/api/v0/node/channels/discord/message"
    assert body == {"external_user_id": "u1", "place": "dm:9", "text": "when?",
                    "images": [{"mime": "image/jpeg", "data": base64.b64encode(b"\xff\xd8\xff").decode()}]}


def test_a_stranger_a_failure_and_an_unreachable_jarvis(cc) -> None:
    cc(message={"linked": False})
    assert asyncio.run(Channel("discord").message("u1", "dm:9", "hi")) == ChannelReply(linked=False)
    cc(message={"linked": True, "failed": "I couldn't read that image."})
    assert asyncio.run(Channel("discord").message("u1", "dm:9", "hi")) == ChannelReply(True, "I couldn't read that image.", True)
    cc(message=None)
    assert asyncio.run(Channel("discord").message("u1", "dm:9", "hi")) is None
    cc_mod._backend = None  # no backend at all (a test harness): the same
    assert asyncio.run(Channel("discord").message("u1", "dm:9", "hi")) is None


def test_a_command(cc) -> None:
    fake = cc(command={"text": "Linked.", "private": True})
    assert asyncio.run(Channel("slack").command("U1", "dm:1", "link", code="ABCD2345")) == CommandReply("Linked.", True)
    assert fake.calls[0] == ("/api/v0/node/channels/slack/command",
                             {"external_user_id": "U1", "place": "dm:1", "name": "link", "args": {"code": "ABCD2345"}})
    cc(command=None)
    assert asyncio.run(Channel("slack").command("U1", "dm:1", "status")) is None


def test_the_provider_name_is_checked() -> None:
    for bad in ("", "Discord", "a b", "a/b", "x" * 33):
        with pytest.raises(ValueError):
            Channel(bad)


def test_the_message_call_does_not_block_the_loop(cc) -> None:
    """A turn takes minutes; the daemon's connection must be served meanwhile."""
    import threading

    release = threading.Event()

    class Slow(CCHttpBackend):
        def post(self, path, json):
            release.wait(5)
            return {"linked": True, "reply": "done"}

    cc_mod._backend = Slow()

    async def scenario():
        turn = asyncio.create_task(Channel("discord").message("u1", "dm:9", "hi"))
        await asyncio.sleep(0)  # the loop is free while the turn waits
        assert not turn.done()
        release.set()
        return await turn

    assert asyncio.run(scenario()).say == "done"


def test_deliver_sends_acknowledges_and_offers_a_failed_one_again(cc) -> None:
    one = {"id": "m1", "external_user_id": "u1", "text": "Reminder: bins"}
    two = {"id": "m2", "external_user_id": "u2", "text": "Reminder: vet"}
    fake = cc(outbox=[{"messages": [one, two]}, None, {"messages": [two]}, {"messages": []}])
    sent: list[Outgoing] = []
    fails = {"m2": 1}

    async def send(msg: Outgoing) -> None:
        if fails.get(msg.id):
            fails[msg.id] -= 1
            raise RuntimeError("the service said no")
        sent.append(msg)

    asks = 0

    async def sleep(_: float) -> None:
        nonlocal asks
        asks += 1
        if asks == 4:
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(Channel("discord").deliver(send, sleep=sleep))
    assert [m.id for m in sent] == ["m1", "m2"]
    # The second ask didn't arrive, so its acknowledgement is repeated; then each id is named once.
    assert [body["ack"] for _, body in fake.calls] == [[], ["m1"], ["m1"], ["m2"]]


def test_split_reply() -> None:
    assert split_reply("short", 10) == ["short"]
    assert split_reply("", 10) == [""]
    parts = split_reply("one two three four five six seven", 12)
    assert all(len(p) <= 12 for p in parts) and " ".join(parts) == "one two three four five six seven"
    assert split_reply("first paragraph\n\nsecond paragraph here", 24) == ["first paragraph", "second paragraph here"]
    assert split_reply("x" * 25, 10) == ["x" * 10, "x" * 10, "x" * 5]
