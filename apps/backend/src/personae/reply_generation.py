"""Generate one streamed reply; own and close its token and synthesis tasks."""

import asyncio
import contextlib
import logging
from collections.abc import AsyncGenerator, Callable
from time import perf_counter
from uuid import uuid4

from personae import expression
from personae.conversation_history import History
from personae.packs.models import Character
from personae.protocol import MetricsMessage, ServerMessage, SpeechStartMessage, SpeechTimingMessage
from personae.providers.base import (
    LlmProvider,
    ProviderError,
    Speaker,
)
from personae.sentence_buffer import SentenceBuffer
from personae.speech_events import SpeechChunk
from personae.speech_text import (
    farewell_marked,
    for_speech,
    gesture_marks,
    strip_farewell,
    strip_gesture_marks,
)

logger = logging.getLogger(__name__)

# Bound queued output so a slow consumer cannot buffer an entire reply.
OUTBOUND_BUFFER = 48


def _prompt_for(persona: str, seeing: bool) -> str:
    """Tell her what she can do right now.

    She has no other way to know whether a camera is attached: untold, she
    denies having one even while a frame is in front of her, or guesses.
    """
    if seeing:
        return f"{persona}\n\nThe camera is on: you can see the person you are talking to."
    return f"{persona}\n\nThe camera is off: you cannot see them right now."


class Reply:
    """One answer in production: what is ready to send waits in ``outbound``."""

    def __init__(self, transcript: str, frame: bytes | None) -> None:
        self.transcript = transcript
        self.frame = frame
        self.spoken = ""
        self.id = uuid4().hex
        self.started = perf_counter()
        self.metrics: dict[str, float] = {}

        self.outbound: asyncio.Queue[ServerMessage | None] = asyncio.Queue(maxsize=OUTBOUND_BUFFER)
        self.task: asyncio.Task[None] | None = None


async def produce_reply(
    reply: Reply,
    character: Character,
    llm: LlmProvider,
    history: History,
    open_speaker: Callable[[], asyncio.Task[Speaker]],
) -> None:
    outbound = reply.outbound
    vocabulary = character.expression.gestures

    def mark(name: str) -> None:
        reply.metrics.setdefault(name, (perf_counter() - reply.started) * 1000)

    try:
        speaker = await asyncio.shield(open_speaker())
        # Where a sentence falls in the reply, and whether the one before
        # carried a gesture she chose: the hands should not be busy on
        # every line.
        beat = 0
        after_mark = False

        async def say(text: str) -> None:
            """Synthesise one sentence and hand its audio onward."""
            nonlocal beat, after_mark
            # She marks her own gestures: only she knows that "I'm not
            # sure" wants a shrug. Where she marks nothing, the text is
            # read for a cue, so plain replies still move.
            marked = gesture_marks(text, vocabulary)
            speakable = for_speech(strip_gesture_marks(text, vocabulary))
            if not speakable:
                return
            gesture, emotion = expression.infer(
                speakable, character, requested=marked, beat=beat, after_mark=after_mark
            )
            mark("first_speakable_ms")
            opening = beat == 0
            beat += 1
            after_mark = bool(marked)
            # Sent before the audio, so the movement begins with the
            # sound rather than trailing it, and changes per sentence
            # rather than being held for the whole reply.
            await outbound.put(ServerMessage.expression(gesture=gesture, emotion=emotion))
            # Announced before its audio, so the caption can follow her
            # voice rather than arriving in one block at the end.
            utterance_id = f"{reply.id}:{beat}"
            await outbound.put(SpeechStartMessage(utterance_id=utterance_id))
            await outbound.put(ServerMessage.speaking(speakable))
            # Her pace follows her mood: a shade slower when serious, a
            # shade quicker when amused. Never on the opening line: a pace
            # change can delay the first sound, and the opening line is
            # the one with nothing playing to hide that behind.
            rate = None if opening else character.voice.rate * expression.pace(emotion)
            # Closed explicitly: a barge-in cancels this task, and the
            # speaker must learn at once that the sentence is abandoned,
            # not whenever the generator is collected.
            lines = speaker.say(speakable, rate)
            try:
                async for chunk in lines:
                    if isinstance(chunk, SpeechChunk):
                        if chunk.alignment or chunk.visemes:
                            await outbound.put(
                                SpeechTimingMessage(
                                    utterance_id=utterance_id,
                                    alignment=chunk.alignment,
                                    visemes=chunk.visemes,
                                )
                            )
                        pcm = chunk.pcm
                    else:
                        pcm = chunk
                    if pcm:
                        mark("first_audio_ms")
                        await outbound.put(ServerMessage.audio(pcm))
            finally:
                if isinstance(lines, AsyncGenerator):
                    await lines.aclose()

        async def write(frame: bytes | None) -> None:
            # Read tokens independently while speech is synthesised. Bound the
            # queue so a slow consumer cannot accumulate an unbounded reply.
            pending: asyncio.Queue[str | None] = asyncio.Queue(maxsize=4)

            async def read_text() -> None:
                sentences = SentenceBuffer()
                fragments = llm.respond(
                    _prompt_for(character.persona.prompt, frame is not None),
                    reply.transcript,
                    history.messages(),
                    frame,
                )
                try:
                    async for fragment in fragments:
                        if fragment:
                            mark("first_token_ms")
                        reply.spoken += fragment
                        for sentence in sentences.feed(fragment):
                            await pending.put(sentence)
                    await pending.put(sentences.flush())
                    await pending.put(None)
                finally:
                    if isinstance(fragments, AsyncGenerator):
                        await fragments.aclose()

            async def speak_text() -> None:
                while (text := await pending.get()) is not None:
                    await say(text)

            reader = asyncio.create_task(read_text())
            speaker_task = asyncio.create_task(speak_text())
            try:
                await asyncio.gather(reader, speaker_task)
            finally:
                # gather alone does not cancel a sibling when one fails.
                reader.cancel()
                speaker_task.cancel()
                await asyncio.gather(reader, speaker_task, return_exceptions=True)

        await write(reply.frame)

        if not reply.spoken.strip() and reply.frame is not None:
            # Some endpoints accept an image and then stream no text at
            # all. Losing her sight is better than losing her voice, so
            # the turn is asked again without the picture.
            logger.warning("empty reply for a turn with a camera frame; retrying blind")
            await write(None)

        if not reply.spoken.strip():
            # The model accepted the turn and returned nothing. Saying
            # so beats a silent success the listener can only read as
            # the app having died.
            logger.warning("the model returned an empty reply")
            await outbound.put(ServerMessage.error("she had nothing to say -- try again"))
            return

        ending = farewell_marked(reply.spoken)
        reply.spoken = strip_gesture_marks(strip_farewell(reply.spoken), vocabulary)
        # The caption follows the speech rather than preceding it.
        mark("generation_done_ms")
        await outbound.put(MetricsMessage(reply_id=reply.id, values=reply.metrics))
        logger.info("reply_metrics reply_id=%s values=%s", reply.id, reply.metrics)
        await outbound.put(ServerMessage.reply(reply.spoken))

        # After the audio, so her goodbye is never cut off mid-word.
        if ending:
            await outbound.put(ServerMessage.farewell())
    except asyncio.CancelledError:
        raise
    except ProviderError as error:
        # The provider said why it refused; an expired credential or a
        # rejected request is worth repeating rather than hiding behind
        # a generic failure the listener can do nothing about.
        logger.warning("a provider refused the turn: %s", error)
        await outbound.put(ServerMessage.error(str(error)))
    except Exception:
        # One upstream hiccup ends a turn, not the conversation.
        logger.exception("provider failed during reply")
        await outbound.put(ServerMessage.error("the model could not answer"))
    finally:
        # The end marker is best effort: if the queue is full nobody is
        # reading it, and the reader also treats a finished task with an
        # empty queue as the end.
        with contextlib.suppress(asyncio.QueueFull):
            outbound.put_nowait(None)
