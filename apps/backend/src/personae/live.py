"""A continuous conversation: no push-to-talk, and she can be interrupted."""

import asyncio
import contextlib
import logging
from collections.abc import AsyncGenerator, AsyncIterator

from personae import expression
from personae.conversation import History, Turn
from personae.packs.models import Character
from personae.protocol import ServerMessage
from personae.providers.base import LlmProvider, SttProvider, TtsProvider
from personae.sentences import SentenceBuffer
from personae.speech import farewell_marked, for_speech, strip_farewell

logger = logging.getLogger(__name__)

# Roughly thirty seconds of 16kHz audio. Beyond this the client is producing
# faster than transcription consumes, and the oldest frames are already stale.
MAX_PENDING_AUDIO = 300


def _prompt_for(persona: str, seeing: bool) -> str:
    """Tell her what she can do right now.

    She has no other way to know whether a camera is attached, and without
    being told she denies having one even while a frame is in front of her.
    """
    if not seeing:
        return persona
    return f"{persona}\n\nThe camera is on: you can see the person you are talking to."


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
        self._frame: bytes | None = None

    async def offer(self, pcm: bytes) -> None:
        """Queue captured audio, discarding the oldest if the backlog grows.

        A blocking put would stall the same reader loop that carries interrupts,
        so barge-in would stop working under exactly the load that needs it.
        """
        while self._inbound.qsize() >= MAX_PENDING_AUDIO:
            try:
                self._inbound.get_nowait()
            except asyncio.QueueEmpty:  # pragma: no cover - racing consumer
                break
        self._inbound.put_nowait(pcm)

    def backlog(self) -> int:
        """How many audio frames are waiting to be transcribed."""
        return self._inbound.qsize()

    async def close_input(self) -> None:
        self._inbound.put_nowait(None)

    async def interrupt(self) -> None:
        """Stop whatever she is saying right now."""
        self._interrupted.set()

    def see(self, jpeg: bytes) -> None:
        """Hold a camera still for the next turn.

        Only the most recent frame is kept: by the time she answers, an older
        one no longer shows what is in front of the camera.
        """
        self._frame = jpeg

    async def run(self) -> AsyncGenerator[ServerMessage]:
        async for transcript in self._stt.transcribe(self._audio()):
            if not transcript.strip():
                continue
            self._interrupted.clear()
            yield ServerMessage.transcript(transcript)
            async for message in self._answer(transcript):
                yield message

    async def _answer(self, transcript: str) -> AsyncIterator[ServerMessage]:
        spoken = ""
        # Taken once, so a frame arriving mid-reply belongs to the next turn.
        frame, self._frame = self._frame, None
        # Bounded so synthesis is paced by the client rather than buffering a
        # whole reply's audio in memory.
        outbound: asyncio.Queue[ServerMessage | None] = asyncio.Queue(maxsize=16)

        async def produce() -> None:
            nonlocal spoken
            try:
                voice = self._character.voice
                sentences = SentenceBuffer()
                first = True

                async def say(text: str) -> None:
                    """Synthesise one sentence and hand its audio onward."""
                    nonlocal first
                    speakable = for_speech(text)
                    if not speakable:
                        return
                    if first:
                        # The face should move with the first sound, not with
                        # the last word of the reply.
                        gesture, emotion = expression.infer(speakable, self._character)
                        await outbound.put(
                            ServerMessage.expression(gesture=gesture, emotion=emotion)
                        )
                        first = False
                    # Announced before its audio, so the caption can follow her
                    # voice rather than arriving in one block at the end.
                    await outbound.put(ServerMessage.speaking(speakable))
                    async for chunk in self._tts.synthesize(
                        speakable, voice.provider_voice, voice.rate
                    ):
                        await outbound.put(ServerMessage.audio(chunk))

                # Each sentence is spoken as it arrives, so she starts on the
                # first while the model is still writing the rest.
                async for fragment in self._llm.respond(
                    _prompt_for(self._character.persona.prompt, frame is not None),
                    transcript,
                    self._history.messages(),
                    frame,
                ):
                    spoken += fragment
                    for sentence in sentences.feed(fragment):
                        await say(sentence)

                await say(sentences.flush())

                if not spoken.strip() and frame is not None:
                    # Some endpoints accept an image and then stream no text at
                    # all. Losing her sight is better than losing her voice, so
                    # the turn is asked again without the picture.
                    logger.warning("empty reply for a turn with a camera frame; retrying blind")
                    sentences = SentenceBuffer()
                    async for fragment in self._llm.respond(
                        _prompt_for(self._character.persona.prompt, False),
                        transcript,
                        self._history.messages(),
                        None,
                    ):
                        spoken += fragment
                        for sentence in sentences.feed(fragment):
                            await say(sentence)
                    await say(sentences.flush())

                if not spoken.strip():
                    # The model accepted the turn and returned nothing. Saying
                    # so beats a silent success the listener can only read as
                    # the app having died.
                    logger.warning("the model returned an empty reply")
                    await outbound.put(ServerMessage.error("she had nothing to say -- try again"))
                    return

                ending = farewell_marked(spoken)
                spoken = strip_farewell(spoken)
                # The caption follows the speech rather than preceding it.
                await outbound.put(ServerMessage.reply(spoken))

                # After the audio, so her goodbye is never cut off mid-word.
                if ending:
                    await outbound.put(ServerMessage.farewell())
            except asyncio.CancelledError:
                raise
            except Exception:
                # One upstream hiccup ends a turn, not the conversation.
                logger.exception("provider failed during reply")
                await outbound.put(ServerMessage.error("the model could not answer"))
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
                # A provider failure was already reported to the client; letting
                # it re-raise here would also skip the history write below.
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
            # The whole reply the model produced, not only the part that
            # reached the speaker: a barge-in can cut playback short, and she
            # should remember what she meant to say.
            self._history.add(Turn(user=transcript, assistant=spoken))

    async def _audio(self) -> AsyncIterator[bytes]:
        while (chunk := await self._inbound.get()) is not None:
            yield chunk
