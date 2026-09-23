"""The model must continue producing while the first sentence synthesises."""

import asyncio
from collections.abc import AsyncIterator, Sequence

from personae.conversation_history import Message
from personae.live_session import LiveSession
from personae.providers.base import SynthesizingSpeaker
from tests.test_live_session import ScriptedStt, _character


async def test_llm_reading_overlaps_synthesis() -> None:
    continued = asyncio.Event()

    class Llm:
        async def respond(
            self,
            system_prompt: str,
            transcript: str,
            history: Sequence[Message] = (),
            image: bytes | None = None,
        ) -> AsyncIterator[str]:
            yield "First sentence. "
            continued.set()
            yield "Second sentence."

    class Tts:
        async def synthesize(
            self, text: str, voice: str, rate: float = 1.0
        ) -> AsyncIterator[bytes]:
            await asyncio.wait_for(continued.wait(), timeout=0.5)
            yield b"\x00\x00"

        async def open(
            self, voice: str, rate: float = 1.0, expressivity: int | None = None
        ) -> SynthesizingSpeaker:
            return SynthesizingSpeaker(self.synthesize, voice, rate)

    session = LiveSession(_character(), ScriptedStt(["hi"]), Llm(), Tts())
    await session.offer(b"\x00\x00")
    await session.close_input()
    messages = [m.model_dump() async for m in session.run()]
    assert not [m for m in messages if m["type"] == "error"]
    assert len([m for m in messages if m["type"] == "audio"]) == 2
    starts = [m["utterance_id"] for m in messages if m["type"] == "speech_start"]
    assert len(set(starts)) == 2
    metrics = next(m["values"] for m in messages if m["type"] == "metrics")
    assert 0 <= metrics["first_token_ms"] <= metrics["first_audio_ms"]
