"""Cancellation must not poison the next turn or leave event readers behind."""

import asyncio
from collections.abc import AsyncIterator, Sequence

from personae.conversation_history import Message
from personae.live_session import LiveSession
from personae.protocol import ServerMessage
from personae.providers.base import Speaker
from personae.providers.mock import MockLlm, MockStt, MockTts
from tests.test_live_session import _character


async def test_cancelled_reply_does_not_cancel_shared_voice_connection() -> None:
    opening = asyncio.Event()
    release = asyncio.Event()

    class DelayedTts(MockTts):
        async def open(
            self, voice: str, rate: float = 1.0, expressivity: int | None = None
        ) -> Speaker:
            opening.set()
            await release.wait()
            return await super().open(voice, rate, expressivity)

    session = LiveSession(_character(), MockStt(), MockLlm(), DelayedTts(1))
    first = session._start("first")
    await opening.wait()
    assert first.task is not None
    first.task.cancel()
    await asyncio.gather(first.task, return_exceptions=True)
    release.set()
    second = session._start("second")
    assert second.task is not None
    await asyncio.wait_for(second.task, 1)
    messages = []
    while not second.outbound.empty():
        messages.append(second.outbound.get_nowait())
    assert any(getattr(message, "type", "") == "reply" for message in messages)
    await session._release()


async def test_failed_voice_connection_is_retried_next_turn() -> None:
    class RetryTts(MockTts):
        attempts = 0

        async def open(
            self, voice: str, rate: float = 1.0, expressivity: int | None = None
        ) -> Speaker:
            self.attempts += 1
            if self.attempts == 1:
                raise ConnectionError("temporary failure")
            return await super().open(voice, rate, expressivity)

    tts = RetryTts(1)
    session = LiveSession(_character(), MockStt(), MockLlm(), tts)
    for text in ("first", "second"):
        reply = session._start(text)
        assert reply.task is not None
        await asyncio.wait_for(reply.task, 1)
    assert tts.attempts == 2
    await session._release()


async def test_cancelled_stream_releases_all_owned_tasks() -> None:
    class WaitingLlm:
        async def respond(
            self,
            system_prompt: str,
            transcript: str,
            history: Sequence[Message] = (),
            image: bytes | None = None,
        ) -> AsyncIterator[str]:
            await asyncio.Event().wait()
            yield ""

    before = asyncio.all_tasks()
    session = LiveSession(_character(), MockStt(), WaitingLlm(), MockTts())
    reply = session._start("hello")
    stream = session._stream(reply, asyncio.Queue())

    async def consume() -> ServerMessage:
        return await anext(stream)

    consumer = asyncio.create_task(consume())
    for _ in range(10):
        await asyncio.sleep(0)
    consumer.cancel()
    await asyncio.gather(consumer, return_exceptions=True)
    await stream.aclose()
    await session._release()
    assert not (asyncio.all_tasks() - before)


async def test_noisy_room_does_not_interrupt_for_recognized_background_speech() -> None:
    from personae.providers.base import Heard
    from tests.test_live_session import ScriptedStt

    class BackgroundStt(ScriptedStt):
        async def transcribe(
            self, audio: AsyncIterator[bytes], keyterms: Sequence[str] = ()
        ) -> AsyncIterator[Heard]:
            yield Heard("Hello", final=True)
            await asyncio.sleep(0.01)
            yield Heard("Television dialogue", final=True)

    class SlowReply(MockLlm):
        async def respond(
            self,
            system_prompt: str,
            transcript: str,
            history: Sequence[Message] = (),
            image: bytes | None = None,
        ) -> AsyncIterator[str]:
            await asyncio.sleep(0.03)
            yield "One complete answer."

    session = LiveSession(
        _character(), BackgroundStt([]), SlowReply(), MockTts(1), allow_voice_interruption=False
    )
    messages = [message async for message in session.run()]
    assert not any(message.model_dump()["type"] == "interrupted" for message in messages)
    assert sum(message.model_dump()["type"] == "reply" for message in messages) == 1
