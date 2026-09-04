"""A continuous conversation: no push-to-talk, and she can be interrupted."""

import asyncio
import contextlib
import logging
import re
from collections import deque
from collections.abc import AsyncGenerator, AsyncIterator

from personae import expression
from personae.conversation import History, Turn
from personae.packs.models import Character
from personae.protocol import ServerMessage
from personae.providers.base import (
    Heard,
    LlmProvider,
    ProviderError,
    Speaker,
    SttProvider,
    TtsProvider,
)
from personae.sentences import SentenceBuffer
from personae.speech import (
    farewell_marked,
    for_speech,
    gesture_marks,
    strip_farewell,
    strip_gesture_marks,
)

logger = logging.getLogger(__name__)

# Roughly thirty seconds of 16kHz audio in 80ms frames. Beyond this the client
# is producing faster than transcription consumes, and the oldest frames are
# already stale.
MAX_PENDING_AUDIO = 375

# How far a reply may run ahead of the client hearing it. Bounded so a whole
# reply's audio is never buffered in memory; wide enough that a reply drafted
# before the turn is confirmed has its opening ready the moment it is.
OUTBOUND_BUFFER = 48

# A recogniser socket that drops is reopened this many times in a row before
# the conversation is given up as lost. The microphone audio keeps queueing
# meanwhile, so a brief drop costs nothing that was said.
RECONNECT_ATTEMPTS = 3
RECONNECT_DELAY_S = 0.5

# What the recogniser hears, or the reason it stopped, or the end of input.
Event = Heard | Exception | None


def _prompt_for(persona: str, seeing: bool) -> str:
    """Tell her what she can do right now.

    She has no other way to know whether a camera is attached: untold, she
    denies having one even while a frame is in front of her, or guesses.
    """
    if seeing:
        return f"{persona}\n\nThe camera is on: you can see the person you are talking to."
    return f"{persona}\n\nThe camera is off: you cannot see them right now."


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z']+", text.lower()))


def is_echo(heard: str, spoken: str) -> bool:
    """Whether words heard while she talks are her own voice coming back.

    Echo cancellation is the real defence; this is the guard behind it. A
    fragment made only of words she has just said is taken to be her.
    """
    words = _words(heard)
    return bool(words) and words <= _words(spoken)


class _Reply:
    """One answer in production: what is ready to send waits in ``outbound``."""

    def __init__(self, transcript: str, frame: bytes | None) -> None:
        self.transcript = transcript
        self.frame = frame
        self.spoken = ""
        self.outbound: asyncio.Queue[ServerMessage | None] = asyncio.Queue(maxsize=OUTBOUND_BUFFER)
        self.task: asyncio.Task[None] | None = None


class LiveSession:
    """Listens continuously, answers each utterance, and yields when cut off.

    The recogniser is read on its own task the whole time, so a listener who
    talks over her is heard as they do it, and the socket is never left
    unread. A reply is produced inside a cancellable task so that speaking
    over it stops it at once; whatever she had said by then is kept.
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
        # Set once the end of the input has been consumed: a dropped recogniser
        # is reconnected only while there is audio left to hear.
        self._drained = False
        self._interrupted = asyncio.Event()
        self._frame: bytes | None = None
        self._speaker: asyncio.Task[Speaker] | None = None
        self._draft: _Reply | None = None
        self._retiring: set[asyncio.Task[None]] = set()
        # Heard while a reply was being sent, and to be dealt with after it.
        self._pending: deque[Event] = deque()

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
        # The voice is connected now, alongside the recogniser, so its
        # handshake is paid while the listener is still saying hello rather
        # than inside the silence before the first answer.
        self._voice()
        # Her name is the word a listener says most and a general model hears
        # least reliably, so the recogniser is told to expect it.
        keyterms = (self._character.display_name, *self._character.keyterms)
        events: asyncio.Queue[Event] = asyncio.Queue()
        listener = asyncio.create_task(self._listen(events, keyterms))
        try:
            while True:
                event = await self._next(events)
                if event is None:
                    break
                if isinstance(event, Exception):
                    yield ServerMessage.error("she stopped hearing you -- the connection dropped")
                    break
                heard = event
                text = heard.text.strip()
                if heard.resumed:
                    # They carried on past what looked like the end. Whatever
                    # was drafted answers a sentence they had not finished.
                    self._discard_draft()
                    if text:
                        yield ServerMessage.hearing(text)
                    continue
                if not text:
                    continue
                if heard.eager:
                    # Probably finished. Start the answer now; it is sent only
                    # once the recogniser is sure, and dropped if it was wrong.
                    yield ServerMessage.hearing(text)
                    if self._draft is None or self._draft.transcript != text:
                        self._discard_draft()
                        self._draft = self._start(text)
                    continue
                if not heard.final:
                    # Provisional words go straight to the caption: seeing
                    # themselves transcribed as they speak is what tells the
                    # listener they are being heard, and it costs nothing.
                    yield ServerMessage.hearing(text)
                    continue
                self._interrupted.clear()
                yield ServerMessage.transcript(text)
                reply = self._take_draft(text) or self._start(text)
                async for message in self._stream(reply, events):
                    yield message
        finally:
            self._discard_draft()
            listener.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await listener
            await self._release()

    async def _next(self, events: asyncio.Queue[Event]) -> Event:
        """The next thing heard: first anything set aside during a reply."""
        if self._pending:
            return self._pending.popleft()
        return await events.get()

    async def _listen(self, events: asyncio.Queue[Event], keyterms: tuple[str, ...]) -> None:
        """Feed the recogniser and relay what it hears, for as long as there is input.

        On its own task so nothing heard waits on a reply being sent: an unread
        socket cannot answer the pings that keep it open. A dropped socket is
        reopened, with the microphone audio queueing meanwhile.
        """
        failures = 0
        try:
            while not self._drained:
                try:
                    async for heard in self._stt.transcribe(self._audio(), keyterms):
                        failures = 0
                        await events.put(heard)
                    # The input ran out; the conversation is over.
                    return
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    failures += 1
                    if failures > RECONNECT_ATTEMPTS:
                        logger.exception("the recogniser kept dropping; giving up")
                        await events.put(error)
                        return
                    logger.warning(
                        "the recogniser dropped the connection (%s); reconnecting %d/%d",
                        error,
                        failures,
                        RECONNECT_ATTEMPTS,
                    )
                    await asyncio.sleep(RECONNECT_DELAY_S)
        finally:
            await events.put(None)

    def _voice(self) -> asyncio.Task[Speaker]:
        """The session's speaker, connecting on first use."""
        if self._speaker is None:
            voice = self._character.voice
            self._speaker = asyncio.create_task(
                self._tts.open(voice.provider_voice, voice.rate, voice.expressivity)
            )
        return self._speaker

    def _start(self, transcript: str) -> _Reply:
        # Taken once, so a frame arriving mid-reply belongs to the next turn.
        frame, self._frame = self._frame, None
        reply = _Reply(transcript, frame)
        reply.task = asyncio.create_task(self._produce(reply))
        return reply

    def _take_draft(self, transcript: str) -> _Reply | None:
        """The draft for this turn, if one was started and it still fits.

        The recogniser promises the confirmed transcript matches the tentative
        one; anything else means the draft answered different words.
        """
        draft, self._draft = self._draft, None
        if draft is None:
            return None
        if draft.transcript == transcript:
            return draft
        self._retire(draft)
        return None

    def _discard_draft(self) -> None:
        draft, self._draft = self._draft, None
        if draft is not None:
            self._retire(draft)

    def _retire(self, reply: _Reply) -> None:
        """Abandon a reply nobody will hear, without waiting on it.

        Its task is left to wind down on its own: stopping the voice mid-word
        can take a moment, and the transcription loop must not stall for it.
        """
        # A still that was never looked at belongs to the next turn after all.
        if reply.frame is not None and self._frame is None:
            self._frame = reply.frame
        if reply.task is not None and not reply.task.done():
            reply.task.cancel()
            self._retiring.add(reply.task)
            reply.task.add_done_callback(self._retiring.discard)

    async def _release(self) -> None:
        if self._retiring:
            await asyncio.gather(*self._retiring, return_exceptions=True)
        if self._speaker is None:
            return
        opening, self._speaker = self._speaker, None
        if not opening.done():
            opening.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await (await opening).close()

    async def _produce(self, reply: _Reply) -> None:
        outbound = reply.outbound
        character = self._character
        vocabulary = character.expression.gestures
        try:
            speaker = await self._voice()
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
                opening = beat == 0
                beat += 1
                after_mark = bool(marked)
                # Sent before the audio, so the movement begins with the
                # sound rather than trailing it, and changes per sentence
                # rather than being held for the whole reply.
                await outbound.put(ServerMessage.expression(gesture=gesture, emotion=emotion))
                # Announced before its audio, so the caption can follow her
                # voice rather than arriving in one block at the end.
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
                        await outbound.put(ServerMessage.audio(chunk))
                finally:
                    if isinstance(lines, AsyncGenerator):
                        await lines.aclose()

            async def write(frame: bytes | None) -> None:
                # Each sentence is spoken as it arrives, so she starts on the
                # first while the model is still writing the rest.
                sentences = SentenceBuffer()
                async for fragment in self._llm.respond(
                    _prompt_for(character.persona.prompt, frame is not None),
                    reply.transcript,
                    self._history.messages(),
                    frame,
                ):
                    reply.spoken += fragment
                    for sentence in sentences.feed(fragment):
                        await say(sentence)
                await say(sentences.flush())

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

    async def _stream(
        self, reply: _Reply, events: asyncio.Queue[Event]
    ) -> AsyncIterator[ServerMessage]:
        """Relay a reply as it is produced, until it ends or is cut off.

        Words arriving while she talks are the listener talking over her and
        stop her at once; what was heard is answered once she has stopped.
        """
        outbound = reply.outbound
        producer = reply.task
        assert producer is not None
        waiter = asyncio.create_task(self._interrupted.wait())
        listening = True
        try:
            while True:
                if producer.done() and outbound.empty():
                    break
                nxt = asyncio.create_task(outbound.get())
                ear = asyncio.create_task(self._next(events)) if listening else None
                tasks: set[asyncio.Task[object]] = {nxt, waiter, producer}
                if ear is not None:
                    tasks.add(ear)
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

                cut = waiter in done
                if ear is not None:
                    if ear in done:
                        event = ear.result()
                        if event is None or isinstance(event, Exception):
                            # Nothing more will be heard; noted for after.
                            self._pending.appendleft(event)
                            listening = False
                        elif self._is_barge_in(event, reply):
                            if event.final or event.eager:
                                # A whole turn spoken over her: answered next.
                                self._pending.appendleft(event)
                            else:
                                yield ServerMessage.hearing(event.text.strip())
                            cut = True
                    else:
                        ear.cancel()
                if cut:
                    nxt.cancel()
                    yield ServerMessage.interrupted()
                    break
                if nxt in done:
                    message = nxt.result()
                    if message is None:
                        break
                    yield message
                else:
                    # The producer finished while we waited; go round to drain
                    # whatever it left, or to stop if there is nothing.
                    nxt.cancel()
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
            self._history.add(Turn(user=reply.transcript, assistant=reply.spoken))

    def _is_barge_in(self, heard: Heard, reply: _Reply) -> bool:
        """Whether something heard mid-reply means the listener is talking."""
        text = heard.text.strip()
        if not text:
            return False
        if heard.final or heard.eager:
            return True
        return not is_echo(text, reply.spoken)

    async def _audio(self) -> AsyncIterator[bytes]:
        while (chunk := await self._inbound.get()) is not None:
            yield chunk
        self._drained = True
