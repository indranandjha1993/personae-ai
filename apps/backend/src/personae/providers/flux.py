"""Deepgram Flux: the voice-agent model line.

Flux replaces the endpointing and utterance-end tuning of the older streaming
API with turn detection built into the model itself, so a turn arrives as one
``EndOfTurn`` event carrying the whole transcript rather than a stream of
fragments the caller has to buffer and flush.

Speech recognition is ``/v2/listen``; synthesis is ``/v2/speak``. Both are
English-only, which is the trade for the lower latency.
"""

import asyncio
import contextlib
import logging
import math
from array import array
from collections.abc import AsyncIterator, Sequence

from deepgram import AsyncDeepgramClient
from deepgram.speak.v2.socket_client import AsyncV2SocketClient
from deepgram.speak.v2.types import (
    SpeakV2Configure,
    SpeakV2Flush,
    SpeakV2Interrupt,
    SpeakV2Speak,
)

from personae.protocol import PLAYBACK_SAMPLE_RATE
from personae.providers.base import Heard, ProviderError, Speaker

logger = logging.getLogger(__name__)

STT_SAMPLE_RATE = 16_000
TTS_SAMPLE_RATE = PLAYBACK_SAMPLE_RATE

# How sure the model must be that a turn has ended.
#
# Above Deepgram's 0.7 default: a person gathering their thought mid-sentence
# should not be answered over. The cost is a little more delay before she
# starts, which reads as patience rather than lag.
DEFAULT_EOT_THRESHOLD = 0.8

# How long a silence may run before the turn is closed regardless.
DEFAULT_EOT_TIMEOUT_MS = 5_000

# Flux takes a speaking rate in steps of 0.05 within this range and rejects
# anything else, so a pack's own rate is snapped rather than left to fail
# mid-conversation.
_SPEED_MIN = 0.9
_SPEED_MAX = 1.5
_SPEED_STEP = 0.05

# How long to wait for the server to confirm it has stopped a cut-off
# sentence before giving up on the socket and opening a fresh one.
ABANDON_TIMEOUT_S = 2.0

# Peak loudness, 0 to 1, below which a turn's audio was too quiet to have
# been a voice at a sensible distance from a working microphone.
QUIET_INPUT = 0.02


def _supported_speed(rate: float) -> float:
    """Round a requested rate onto the grid Flux accepts."""
    clamped = min(max(rate, _SPEED_MIN), _SPEED_MAX)
    return round(round(clamped / _SPEED_STEP) * _SPEED_STEP, 2)


class _Level:
    """The loudest frame since last read, so a silent microphone shows in the log."""

    def __init__(self) -> None:
        self.peak = 0.0

    def observe(self, chunk: bytes) -> None:
        samples = array("h")
        samples.frombytes(chunk[: len(chunk) - len(chunk) % 2])
        if not samples:
            return
        rms = math.sqrt(sum(s * s for s in samples) / len(samples)) / 32768.0
        self.peak = max(self.peak, rms)

    def take(self) -> float:
        peak, self.peak = self.peak, 0.0
        return peak


class FluxStt:
    """Streaming transcription with model-integrated turn detection."""

    def __init__(
        self,
        api_key: str,
        model: str = "flux-general-en",
        eot_threshold: float = DEFAULT_EOT_THRESHOLD,
        eot_timeout_ms: int = DEFAULT_EOT_TIMEOUT_MS,
        eager_eot_threshold: float | None = None,
    ) -> None:
        self._client = AsyncDeepgramClient(api_key=api_key)
        self.model = model
        self._eot_threshold = eot_threshold
        self._eot_timeout_ms = eot_timeout_ms
        # When set, Flux also says when a turn has *probably* ended, a beat
        # before it is sure, and retracts if the speaker carries on.
        self._eager_eot_threshold = eager_eot_threshold

    async def transcribe(
        self, audio: AsyncIterator[bytes], keyterms: Sequence[str] = ()
    ) -> AsyncIterator[Heard]:
        level = _Level()
        async with self._client.listen.v2.connect(
            model=self.model,
            encoding="linear16",
            sample_rate=STT_SAMPLE_RATE,
            eot_threshold=self._eot_threshold,
            eot_timeout_ms=self._eot_timeout_ms,
            eager_eot_threshold=self._eager_eot_threshold,
            # Names above all: a general model hears "Wren" as "Ren" or "Ryan"
            # every time until told to expect it.
            keyterm=list(keyterms) or None,
        ) as connection:
            pump = asyncio.create_task(self._pump(connection, audio, level))
            try:
                async for event in connection:
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(
                            "flux %s conf=%s transcript=%r",
                            getattr(event, "event", type(event).__name__),
                            getattr(event, "end_of_turn_confidence", None),
                            getattr(event, "transcript", None),
                        )
                    kind = getattr(event, "event", None)
                    transcript = (getattr(event, "transcript", "") or "").strip()
                    if kind == "EndOfTurn":
                        # One line per turn: how it ended and how loud it was.
                        # A turn closed by the timeout means noise kept the
                        # model unsure the speaker had finished; a quiet peak
                        # means the microphone, not the model, is the problem.
                        peak = level.take()
                        logger.info(
                            "turn: %d words, ended by %s at %.2f, input peak %.3f",
                            len(getattr(event, "words", None) or ()),
                            getattr(event, "trigger", None) or "model",
                            getattr(event, "end_of_turn_confidence", None) or 0.0,
                            peak,
                        )
                        if transcript and peak < QUIET_INPUT:
                            logger.warning(
                                "microphone input is very quiet (peak %.3f): check the "
                                "input device and its level",
                                peak,
                            )
                        if transcript:
                            yield Heard(transcript, final=True)
                    elif kind == "EagerEndOfTurn":
                        # Probably finished: worth starting on an answer, as
                        # long as it can be thrown away.
                        if transcript:
                            yield Heard(transcript, final=False, eager=True)
                    elif kind == "TurnResumed":
                        # They carried on. Whatever was drafted is void even
                        # if there are no new words yet.
                        yield Heard(transcript, final=False, resumed=True)
                    elif kind in ("StartOfTurn", "Update") and transcript:
                        # Provisional: shown as the listener speaks, so they can
                        # see they are being heard rather than waiting to find
                        # out afterwards.
                        yield Heard(transcript, final=False)
            finally:
                pump.cancel()
                await asyncio.gather(pump, return_exceptions=True)

    @staticmethod
    async def _pump(
        connection: object, audio: AsyncIterator[bytes], level: _Level | None = None
    ) -> None:
        """Forward captured audio for as long as the caller produces it."""
        async for chunk in audio:
            if level is not None:
                level.observe(chunk)
            await connection.send_media(chunk)  # type: ignore[attr-defined]
        await connection.send_close_stream()  # type: ignore[attr-defined]


class FluxTts:
    """Streaming synthesis on the Flux voices."""

    def __init__(self, api_key: str, voice: str = "flux-haley-en") -> None:
        self._client = AsyncDeepgramClient(api_key=api_key)
        self._voice = voice

    def voice_for(self, requested: str) -> str:
        """A character's own voice wins; the configured one fills the gap."""
        return requested or self._voice

    async def open(self, voice: str, rate: float = 1.0, expressivity: int | None = None) -> Speaker:
        speaker = FluxSpeaker(
            self._client, self.voice_for(voice), _supported_speed(rate), expressivity
        )
        await speaker.connect()
        return speaker

    async def synthesize(self, text: str, voice: str, rate: float = 1.0) -> AsyncIterator[bytes]:
        """One sentence on a socket of its own, for callers without a session."""
        speaker = await self.open(voice, rate)
        try:
            async for chunk in speaker.say(text):
                yield chunk
        finally:
            await speaker.close()


class FluxSpeaker:
    """One synthesis socket, held for a whole conversation.

    Connecting costs more than a sentence does, so every sentence is a turn on
    the same socket. Cut off mid-sentence, it tells the server to stop and
    clears what was in flight, so the next sentence starts on a clean channel.
    """

    def __init__(
        self,
        client: AsyncDeepgramClient,
        voice: str,
        speed: float,
        expressivity: int | None,
    ) -> None:
        self._client = client
        self._voice = voice
        self._speed = speed
        self._expressivity = expressivity
        self._stack: contextlib.AsyncExitStack | None = None
        self._connection: AsyncV2SocketClient | None = None
        # The speed the socket is currently set to; changed only when a line
        # asks for a different one.
        self._configured_speed = speed
        # Sentences are serialised: the socket carries one turn at a time.
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        stack = contextlib.AsyncExitStack()
        self._connection = await stack.enter_async_context(
            self._client.speak.v2.connect(
                model=self._voice,
                encoding="linear16",
                sample_rate=TTS_SAMPLE_RATE,
                speed=self._speed,
                expressivity=self._expressivity,
            )
        )
        self._stack = stack
        self._configured_speed = self._speed

    async def close(self) -> None:
        stack, self._stack, self._connection = self._stack, None, None
        if stack is not None:
            with contextlib.suppress(Exception):
                await stack.aclose()

    async def say(self, text: str, rate: float | None = None) -> AsyncIterator[bytes]:
        async with self._lock:
            connection = await self._ready()
            # A rate change is a control message ahead of the text, which can
            # delay the first audio. ``None`` leaves the pace as it is, and the
            # session only asks for a change on a line that has the previous
            # line's playback to hide the cost behind.
            try:
                await self._begin(connection, text, rate)
            except Exception as error:
                # A socket that died between sentences is found out here: one
                # fresh socket and one retry before it counts as a failure.
                logger.warning("the voice socket dropped (%s); reconnecting", error)
                await self.close()
                connection = await self._ready()
                await self._begin(connection, text, rate)

            finished = False
            heard_any = False
            retried = False
            try:
                while True:
                    event = await connection.recv()
                    if isinstance(event, bytes | bytearray):
                        if event:
                            heard_any = True
                            yield bytes(event)
                        continue
                    kind = getattr(event, "type", None)
                    if kind == "SpeechMetadata":
                        # The record that follows the last of the audio.
                        finished = True
                        return
                    if kind == "Error":
                        # The server gave up on this line. A socket that has
                        # errored is not trusted again; if nothing of the line
                        # was heard yet it is said once more on a fresh one.
                        description = str(getattr(event, "description", "speech synthesis failed"))
                        await self.close()
                        if heard_any or retried:
                            raise ProviderError(f"the voice failed: {description}")
                        logger.warning(
                            "the voice failed (%s); retrying on a new socket", description
                        )
                        retried = True
                        connection = await self._ready()
                        await self._begin(connection, text, rate)
                        continue
                    if kind == "Warning":
                        logger.warning("flux tts: %s", getattr(event, "description", event))
            finally:
                if not finished:
                    await self._abandon()

    async def _begin(self, connection: AsyncV2SocketClient, text: str, rate: float | None) -> None:
        """Open a turn: the pace if it changed, the text, and the flush."""
        if rate is not None:
            wanted = _supported_speed(rate)
            if wanted != self._configured_speed:
                await connection.send_configure(SpeakV2Configure(type="Configure", speed=wanted))
                self._configured_speed = wanted

        # The trailing space tells the server the sentence is complete, so
        # synthesis starts on the text alone rather than waiting for the
        # Flush, which some network paths deliver noticeably later.
        await connection.send_speak(SpeakV2Speak(type="Speak", text=f"{text} "))
        # Without an explicit flush the server waits for more text before
        # it will finish the utterance.
        await connection.send_flush(SpeakV2Flush(type="Flush"))

    async def _ready(self) -> AsyncV2SocketClient:
        if self._connection is None:
            await self.connect()
        assert self._connection is not None
        return self._connection

    async def _abandon(self) -> None:
        """Stop a sentence nobody will hear and clear its audio off the socket.

        The server's acknowledgement is waited for, so the next sentence is not
        preceded by this one's leftovers; if it does not come in time the
        socket is dropped and reopened on the next sentence.
        """
        connection = self._connection
        if connection is None:
            return
        try:
            await connection.send_interrupt(SpeakV2Interrupt(type="Interrupt"))
            async with asyncio.timeout(ABANDON_TIMEOUT_S):
                while True:
                    event = await connection.recv()
                    if getattr(event, "type", None) in ("SpeechInterrupted", "SpeechMetadata"):
                        return
        except Exception:
            logger.warning("could not stop the voice cleanly; reconnecting on the next line")
            await self.close()
