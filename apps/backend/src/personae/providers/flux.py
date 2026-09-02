"""Deepgram Flux: the voice-agent model line.

Flux replaces the endpointing and utterance-end tuning of the older streaming
API with turn detection built into the model itself, so a turn arrives as one
``EndOfTurn`` event carrying the whole transcript rather than a stream of
fragments the caller has to buffer and flush.

Speech recognition is ``/v2/listen``; synthesis is ``/v2/speak``. Both are
English-only, which is the trade for the lower latency.
"""

import asyncio
import logging
from collections.abc import AsyncIterator

from deepgram import AsyncDeepgramClient
from deepgram.speak.v2.types import SpeakV2Flush, SpeakV2Speak

from personae.protocol import PLAYBACK_SAMPLE_RATE
from personae.providers.base import Heard

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


def _supported_speed(rate: float) -> float:
    """Round a requested rate onto the grid Flux accepts."""
    clamped = min(max(rate, _SPEED_MIN), _SPEED_MAX)
    return round(round(clamped / _SPEED_STEP) * _SPEED_STEP, 2)


class FluxStt:
    """Streaming transcription with model-integrated turn detection."""

    def __init__(
        self,
        api_key: str,
        model: str = "flux-general-en",
        eot_threshold: float = DEFAULT_EOT_THRESHOLD,
        eot_timeout_ms: int = DEFAULT_EOT_TIMEOUT_MS,
    ) -> None:
        self._client = AsyncDeepgramClient(api_key=api_key)
        self.model = model
        self._eot_threshold = eot_threshold
        self._eot_timeout_ms = eot_timeout_ms

    async def transcribe(self, audio: AsyncIterator[bytes]) -> AsyncIterator[Heard]:
        async with self._client.listen.v2.connect(
            model=self.model,
            encoding="linear16",
            sample_rate=STT_SAMPLE_RATE,
            eot_threshold=self._eot_threshold,
            eot_timeout_ms=self._eot_timeout_ms,
        ) as connection:
            pump = asyncio.create_task(self._pump(connection, audio))
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
                    if kind not in ("StartOfTurn", "Update", "EndOfTurn"):
                        continue
                    transcript = (getattr(event, "transcript", "") or "").strip()
                    if kind != "EndOfTurn":
                        # Provisional: shown as the listener speaks, so they can
                        # see they are being heard rather than waiting to find
                        # out afterwards.
                        if transcript:
                            yield Heard(transcript, final=False)
                        continue
                    if transcript:
                        yield Heard(transcript, final=True)
            finally:
                pump.cancel()
                await asyncio.gather(pump, return_exceptions=True)

    @staticmethod
    async def _pump(connection: object, audio: AsyncIterator[bytes]) -> None:
        """Forward captured audio for as long as the caller produces it."""
        async for chunk in audio:
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

    async def synthesize(self, text: str, voice: str, rate: float = 1.0) -> AsyncIterator[bytes]:
        async with self._client.speak.v2.connect(
            model=self.voice_for(voice),
            encoding="linear16",
            sample_rate=TTS_SAMPLE_RATE,
            speed=_supported_speed(rate),
        ) as connection:
            await connection.send_speak(SpeakV2Speak(type="Speak", text=text))
            # Without an explicit flush the server waits for more text before
            # it will finish the utterance.
            await connection.send_flush(SpeakV2Flush(type="Flush"))
            async for event in connection:
                # Audio arrives as raw frames; the metadata record that follows
                # marks the end of the utterance.
                if isinstance(event, bytes | bytearray):
                    if event:
                        yield bytes(event)
                    continue
                if getattr(event, "type", None) == "SpeechMetadata":
                    break
