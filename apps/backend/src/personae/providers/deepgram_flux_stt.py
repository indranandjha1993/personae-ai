"""Deepgram Flux streaming speech-to-text with model-integrated turn detection."""

import asyncio
import logging
import math
from array import array
from collections.abc import AsyncIterator, Sequence

from deepgram import AsyncDeepgramClient

from personae.providers.base import Heard

logger = logging.getLogger(__name__)


STT_SAMPLE_RATE = 16_000


DEFAULT_EOT_THRESHOLD = 0.8


DEFAULT_EOT_TIMEOUT_MS = 5_000


QUIET_INPUT = 0.02


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
