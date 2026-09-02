"""A continuous conversation: no push-to-talk, and she can be interrupted."""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator

from personae import expression
from personae.conversation import History, Turn
from personae.packs.models import Character
from personae.protocol import ServerMessage
from personae.providers.base import LlmProvider, SttProvider, TtsProvider

logger = logging.getLogger(__name__)


class LiveSession:
    """Listens continuously, answers each utterance, and yields when cut off.

    A reply is produced inside a cancellable task so that speaking over it stops
    it at once. Whatever she had said by then is kept, so her next answer does
    not refer to words the listener never heard.
    """

    def __init__(
        self,
        character: Character,
        stt: SttProvider,
        llm: LlmProvider,
        tts: TtsProvider,
        history: History | None = None,
    ) -> None:
        self._character = character
        self._stt = stt
        self._llm = llm
        self._tts = tts
        self._history = history or History()
        self._inbound: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._interrupted = asyncio.Event()

    async def offer(self, pcm: bytes) -> None:
        await self._inbound.put(pcm)

    async def close_input(self) -> None:
        await self._inbound.put(None)

    async def interrupt(self) -> None:
        """Stop whatever she is saying right now."""
        self._interrupted.set()

    async def run(self) -> AsyncIterator[ServerMessage]:
        async for transcript in self._stt.transcribe(self._audio()):
            if not transcript.strip():
                continue
            self._interrupted.clear()
            yield ServerMessage.transcript(transcript)
            async for message in self._answer(transcript):
                yield message

    async def _answer(self, transcript: str) -> AsyncIterator[ServerMessage]:
        spoken = ""
        outbound: asyncio.Queue[ServerMessage | None] = asyncio.Queue()

        async def produce() -> None:
            nonlocal spoken
            try:
                async for fragment in self._llm.respond(
                    self._character.persona.prompt, transcript, self._history.messages()
                ):
                    spoken += fragment
                await outbound.put(ServerMessage.reply(spoken))

                gesture, emotion = expression.infer(spoken, self._character)
                await outbound.put(ServerMessage.expression(gesture=gesture, emotion=emotion))

                voice = self._character.voice
                async for chunk in self._tts.synthesize(spoken, voice.provider_voice, voice.rate):
                    await outbound.put(ServerMessage.audio(chunk))
            finally:
                await outbound.put(None)

        producer = asyncio.create_task(produce())
        waiter = asyncio.create_task(self._interrupted.wait())

        try:
            while True:
                nxt = asyncio.create_task(outbound.get())
                done, _ = await asyncio.wait({nxt, waiter}, return_when=asyncio.FIRST_COMPLETED)
                if waiter in done:
                    nxt.cancel()
                    yield ServerMessage.interrupted()
                    break
                message = nxt.result()
                if message is None:
                    break
                yield message
        finally:
            producer.cancel()
            waiter.cancel()
            for task in (producer, waiter):
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            # Kept even when cut off: this is what she actually said aloud.
            self._history.add(Turn(user=transcript, assistant=spoken))

    async def _audio(self) -> AsyncIterator[bytes]:
        while (chunk := await self._inbound.get()) is not None:
            yield chunk
