"""Live sessions: continuous listening, barge-in, and remembered turns."""

import asyncio
from collections.abc import AsyncIterator, Sequence

from personae.conversation import Message
from personae.live import LiveSession
from personae.packs.loader import load_packs
from personae.packs.models import Character
from personae.protocol import ServerMessage


def _character() -> Character:
    from personae.main import REPO_ROOT

    return load_packs([REPO_ROOT / "packs" / "bundled"]).get("bundled/seed")


class ScriptedStt:
    """Emits a transcript per utterance the caller feeds it."""

    def __init__(self, utterances: list[str]) -> None:
        self._utterances = utterances

    def transcribe(self, audio: AsyncIterator[bytes]) -> AsyncIterator[str]:
        async def run() -> AsyncIterator[str]:
            index = 0
            async for _ in audio:
                if index < len(self._utterances):
                    yield self._utterances[index]
                    index += 1

        return run()


class SlowLlm:
    """Streams slowly, so a barge-in can land mid-reply."""

    def __init__(self, fragments: list[str], delay: float = 0.05) -> None:
        self.fragments = fragments
        self.delay = delay
        self.seen_history: list[Sequence[Message]] = []

    def respond(
        self, system_prompt: str, transcript: str, history: Sequence[Message] = ()
    ) -> AsyncIterator[str]:
        self.seen_history.append(list(history))

        async def run() -> AsyncIterator[str]:
            for fragment in self.fragments:
                await asyncio.sleep(self.delay)
                yield fragment

        return run()


class SilentTts:
    def synthesize(self, text: str, voice: str, rate: float = 1.0) -> AsyncIterator[bytes]:
        async def run() -> AsyncIterator[bytes]:
            for _ in range(10):
                await asyncio.sleep(0.02)
                yield b"\x00\x00"

        return run()


async def _drain(session: LiveSession, limit: int = 60) -> list[ServerMessage]:
    out: list[ServerMessage] = []
    async for message in session.run():
        out.append(message)
        if len(out) >= limit:
            break
    return out


async def test_answers_an_utterance_without_an_explicit_stop() -> None:
    """Live mode ends a turn on silence, not on a button."""
    session = LiveSession(
        _character(), ScriptedStt(["hello"]), SlowLlm(["hi ", "there"], 0.0), SilentTts()
    )
    await session.offer(b"\x10\x20" * 40)
    await session.close_input()
    kinds = [m.model_dump()["type"] for m in await _drain(session)]
    assert "transcript" in kinds
    assert "reply" in kinds
    assert "audio" in kinds


async def test_barge_in_stops_the_reply_in_flight() -> None:
    llm = SlowLlm(["one ", "two ", "three ", "four ", "five"], 0.05)
    session = LiveSession(_character(), ScriptedStt(["hello"]), llm, SilentTts())
    await session.offer(b"\x10\x20" * 40)

    async def interrupt() -> None:
        await asyncio.sleep(0.06)
        await session.interrupt()
        await session.close_input()

    asyncio.create_task(interrupt())
    messages = await _drain(session)
    kinds = [m.model_dump()["type"] for m in messages]
    assert "interrupted" in kinds, kinds


async def test_an_interrupted_reply_is_remembered_as_spoken() -> None:
    """Her next answer must not reference words the listener never heard."""
    llm = SlowLlm(["the first part ", "the second part"], 0.05)
    session = LiveSession(_character(), ScriptedStt(["a", "b"]), llm, SilentTts())
    await session.offer(b"\x10\x20" * 40)

    async def interrupt_then_speak() -> None:
        await asyncio.sleep(0.06)
        await session.interrupt()
        await session.offer(b"\x30\x40" * 40)
        await asyncio.sleep(0.2)
        await session.close_input()

    asyncio.create_task(interrupt_then_speak())
    await _drain(session)

    assert len(llm.seen_history) >= 2, "the second turn never ran"
    remembered = "".join(m["content"] for m in llm.seen_history[1])
    assert "the first part" in remembered
    assert "the second part" not in remembered
