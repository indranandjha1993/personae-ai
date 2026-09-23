"""A continuous conversation: no push-to-talk, and she can be interrupted."""

import asyncio
import contextlib
import logging
import re
from collections import deque
from collections.abc import AsyncGenerator, AsyncIterator

from personae.conversation_history import History, Turn
from personae.packs.models import Character
from personae.protocol import ServerMessage
from personae.providers.base import (
    Heard,
    LlmProvider,
    Speaker,
    SttProvider,
    TtsProvider,
)
from personae.reply_generation import Reply, produce_reply

logger = logging.getLogger(__name__)

# Roughly thirty seconds of 16kHz audio in 80ms frames. Beyond this the client
# is producing faster than transcription consumes, and the oldest frames are
# already stale.
MAX_PENDING_AUDIO = 375

# A recogniser socket that drops is reopened this many times in a row before
# the conversation is given up as lost. The microphone audio keeps queueing
# meanwhile, so a brief drop costs nothing that was said.
RECONNECT_ATTEMPTS = 3
RECONNECT_DELAY_S = 0.5

# What the recogniser hears, or the reason it stopped, or the end of input.
Event = Heard | Exception | None


def _words(text: str) -> set[str]:
    return set(re.findall(r"[^\W_]+(?:'[^\W_]+)*", text.casefold()))


def is_echo(heard: str, spoken: str) -> bool:
    """Whether words heard while she talks are her own voice coming back.

    Echo cancellation is the real defence; this is the guard behind it. A
    fragment made only of words she has just said is taken to be her.
    """
    words = _words(heard)
    return bool(words) and words <= _words(spoken)


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
        *,
        allow_voice_interruption: bool = True,
    ) -> None:
        self._allow_voice_interruption = allow_voice_interruption
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
        self._draft: Reply | None = None
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
                async with contextlib.aclosing(self._stream(reply, events)) as stream:
                    async for message in stream:
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
        if (
            self._speaker is not None
            and self._speaker.done()
            and (self._speaker.cancelled() or self._speaker.exception() is not None)
        ):
            self._speaker = None
        if self._speaker is None:
            voice = self._character.voice
            self._speaker = asyncio.create_task(
                self._tts.open(voice.provider_voice, voice.rate, voice.expressivity)
            )
        return self._speaker

    def _start(self, transcript: str) -> Reply:
        # Taken once, so a frame arriving mid-reply belongs to the next turn.
        frame, self._frame = self._frame, None
        reply = Reply(transcript, frame)
        reply.task = asyncio.create_task(
            produce_reply(reply, self._character, self._llm, self._history, self._voice)
        )
        return reply

    def _take_draft(self, transcript: str) -> Reply | None:
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

    def _retire(self, reply: Reply) -> None:
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

    async def _stream(
        self, reply: Reply, events: asyncio.Queue[Event]
    ) -> AsyncGenerator[ServerMessage]:
        """Relay a reply as it is produced, until it ends or is cut off.

        Words arriving while she talks are the listener talking over her and
        stop her at once; what was heard is answered once she has stopped.
        """
        outbound = reply.outbound
        producer = reply.task
        assert producer is not None
        waiter = asyncio.create_task(self._interrupted.wait())
        listening = True
        nxt: asyncio.Task[ServerMessage | None] | None = None
        ear: asyncio.Task[Event] | None = None
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
                        with contextlib.suppress(asyncio.CancelledError):
                            await ear
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
            owned = [task for task in (producer, waiter, nxt, ear) if task is not None]
            for task in owned:
                task.cancel()
            for task in owned:
                # A provider failure was already reported to the client; letting
                # it re-raise here would also skip the history write below.
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
            # The whole reply the model produced, not only the part that
            # reached the speaker: a barge-in can cut playback short, and she
            # should remember what she meant to say.
            self._history.add(Turn(user=reply.transcript, assistant=reply.spoken))

    def _is_barge_in(self, heard: Heard, reply: Reply) -> bool:
        """Whether something heard mid-reply means the listener is talking."""
        if not self._allow_voice_interruption:
            return False
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
