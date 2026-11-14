"""Channel — what a chat-service package's daemon says to Jarvis.

A channel package (Discord, Slack, ...) is an ``IJarvisDaemon`` that holds the
service's connection and hands Jarvis what people send. Jarvis decides who an
account is (people link theirs in the app), runs the chat turn and answers; the
package says the answer where it was asked. ``Channel`` wraps the three calls,
running the blocking ``cc_post`` in a thread so the daemon's connection keeps
being served while a turn takes its time.

    channel = Channel("discord")
    reply = await channel.message(str(author.id), f"dm:{chan.id}", text)
    if reply is None or not reply.linked:
        return                      # unreachable, or a stranger: say nothing
    for part in split_reply(reply.say, 1900):
        await chan.send(part)
"""

from __future__ import annotations

import asyncio
import base64
import logging
import re
from dataclasses import dataclass
from typing import Awaitable, Callable, Iterable, Sequence

from .cc_http import cc_post

_log = logging.getLogger(__name__)

_PROVIDER = re.compile(r"^[a-z0-9_]{1,32}$")

#: The commands every channel has; how a person types one is the package's.
COMMANDS: tuple[str, ...] = ("link", "new", "node", "voice", "notify", "status")


@dataclass(frozen=True)
class ChannelImage:
    """A photo someone sent: its bytes as the service gave them (JPEG, PNG or WebP)."""

    data: bytes
    mime: str = "image/jpeg"


@dataclass(frozen=True)
class ChannelReply:
    """Jarvis's answer to a message.

    ``linked`` False: the account isn't linked to anyone, so say nothing at all
    (strangers get no answer). Otherwise say ``say``: the reply, or what went
    wrong in words meant for the sender (``failed`` tells the two apart).
    """

    linked: bool
    say: str = ""
    failed: bool = False


@dataclass(frozen=True)
class CommandReply:
    """A command's answer. ``private``: for the asker's eyes only, where the service can."""

    text: str
    private: bool = True


@dataclass(frozen=True)
class Outgoing:
    """Something Jarvis wants said unasked: a reminder, to an account that opted in."""

    id: str
    external_user_id: str
    text: str


class Channel:
    """One chat service's line to Jarvis, from the node its daemon runs on."""

    __forge_hints__ = {
        "role": "The calls a chat-service channel's daemon makes to Jarvis",
        "constructor": "Channel(provider)  # provider: your service's name, [a-z0-9_], e.g. 'discord'",
        "tips": [
            "Use inside an IJarvisDaemon: await channel.message(external_user_id, place, text, images)",
            "reply is None (Jarvis unreachable) or reply.linked is False (a stranger): say nothing",
            "Otherwise send reply.say, split with split_reply(text, your_service_limit)",
            "place is where it was said (a DM, a channel, a thread): one conversation per person and place",
            "Map your service's commands to channel.command(external_user_id, place, name, **args); names are in COMMANDS",
            "Run channel.deliver(send) as a task to send reminders; send raises if it could not",
            "Never mention or ping anyone in what you send, and answer only where you were asked",
        ],
        "example_import": "from jarvis_command_sdk import Channel, ChannelImage, split_reply",
    }

    def __init__(self, provider: str) -> None:
        if not _PROVIDER.match(provider):
            raise ValueError(f"a provider's name is 1-32 of a-z, 0-9 and _, not {provider!r}")
        self.provider = provider

    async def _post(self, route: str, body: dict) -> dict | None:
        resp = await asyncio.to_thread(cc_post, f"/api/v0/node/channels/{self.provider}/{route}", body)
        return resp if isinstance(resp, dict) else None

    async def message(self, external_user_id: str, place: str, text: str = "",
                      images: Sequence[ChannelImage] = ()) -> ChannelReply | None:
        """What an account sent, for Jarvis's answer. It waits for the whole chat turn, which
        can take minutes. None: Jarvis could not be reached."""
        body: dict = {"external_user_id": external_user_id, "place": place, "text": text}
        if images:
            body["images"] = [{"mime": im.mime, "data": base64.b64encode(im.data).decode("ascii")} for im in images]
        resp = await self._post("message", body)
        if resp is None:
            return None
        if not resp.get("linked"):
            return ChannelReply(linked=False)
        if resp.get("failed"):
            return ChannelReply(linked=True, say=str(resp["failed"]), failed=True)
        return ChannelReply(linked=True, say=str(resp.get("reply") or ""))

    async def command(self, external_user_id: str, place: str, name: str, **args: str) -> CommandReply | None:
        """One of COMMANDS, e.g. ``command(uid, place, "link", code="ABCD2345")``. A command
        always has an answer, also for an account that isn't linked. None: Jarvis could not be
        reached."""
        resp = await self._post("command", {"external_user_id": external_user_id, "place": place,
                                            "name": name, "args": args})
        if resp is None or "text" not in resp:
            return None
        return CommandReply(text=str(resp["text"]), private=bool(resp.get("private", True)))

    async def outbox(self, ack: Iterable[str] = ()) -> list[Outgoing]:
        """What Jarvis wants said unasked, after acknowledging the ids already sent. The call
        also tells Jarvis this channel is running, so make it every few seconds (deliver does)."""
        return _outgoing(await self._post("outbox", {"ack": list(ack)}))

    async def deliver(self, send: Callable[[Outgoing], Awaitable[None]], every: float = 5.0,
                      sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:
        """Send reminders for as long as the daemon runs: ask every ``every`` seconds, ``send``
        each message, and acknowledge the ones ``send`` returned from. One it raised on is
        offered again at the next ask. Run it as a task beside the service's connection."""
        sent: list[str] = []
        while True:
            resp = await self._post("outbox", {"ack": sent})
            if resp is not None:
                sent = []  # acknowledged; an ask that didn't arrive repeats them
            for msg in _outgoing(resp):
                try:
                    await send(msg)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    _log.warning("channel %s: a reminder was not sent: %s", self.provider, exc)
                    continue
                sent.append(msg.id)
            await sleep(every)


def _outgoing(resp: dict | None) -> list[Outgoing]:
    out = []
    for m in (resp or {}).get("messages") or []:
        try:
            out.append(Outgoing(id=str(m["id"]), external_user_id=str(m["external_user_id"]), text=str(m["text"])))
        except (KeyError, TypeError):
            continue
    return out


def split_reply(text: str, limit: int) -> list[str]:
    """Cut text into pieces of at most ``limit`` characters for a service with a message
    length limit, preferring paragraph, line and word breaks."""
    if limit < 1:
        raise ValueError("limit must be at least 1")
    out: list[str] = []
    while len(text) > limit:
        window, cut = text[:limit], limit
        for sep in ("\n\n", "\n", " "):
            i = window.rfind(sep)
            if i > limit // 2:
                cut = i
                break
        out.append(text[:cut].rstrip(" \n"))
        text = text[cut:].lstrip(" \n")
    if text or not out:
        out.append(text)
    return out
