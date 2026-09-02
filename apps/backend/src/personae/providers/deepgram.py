"""Deepgram speech-to-text and text-to-speech.

Uses the v7 SDK, which is async-native: `listen.v1.connect` and
`speak.v1.connect` are async context managers rather than the callback-based
clients of earlier majors.
"""

import asyncio
import logging
from collections.abc import AsyncIterator

from deepgram import AsyncDeepgramClient
from deepgram.speak.v1.types.speak_v1text import SpeakV1Text

from personae.protocol import PLAYBACK_SAMPLE_RATE

logger = logging.getLogger(__name__)

STT_SAMPLE_RATE = 16_000

# Silence after speech before Deepgram closes a turn. Long enough to survive a
# thinking pause, short enough that a reply does not feel delayed.
ENDPOINTING_MS = 800
UTTERANCE_END_MS = 1000
TTS_SAMPLE_RATE = PLAYBACK_SAMPLE_RATE


class DeepgramStt:
    """Streaming transcription over a live websocket."""

    def __init__(self, api_key: str, model: str = "nova-3") -> None:
        self._client = AsyncDeepgramClient(api_key=api_key)
        self._model = model

    async def transcribe(self, audio: AsyncIterator[bytes]) -> AsyncIterator[str]:
        async with self._client.listen.v1.connect(
            model=self._model,
            encoding="linear16",
            sample_rate=STT_SAMPLE_RATE,
            channels=1,
            punctuate=True,
            # Deepgram decides when a turn has ended, so a live conversation
            # needs no push-to-talk. Interim results arrive first and are
            # discarded; only finalised transcripts are yielded.
            interim_results=True,
            endpointing=ENDPOINTING_MS,
            utterance_end_ms=UTTERANCE_END_MS,
            vad_events=True,
        ) as connection:
            pump = asyncio.create_task(self._pump(connection, audio))
            try:
                async for event in connection:
                    if not _is_final(event):
                        continue
                    text = _transcript_of(event)
                    if text:
                        yield text
            finally:
                # The socket is closing either way; make sure the feeding task
                # does not outlive it and write to a dead connection.
                pump.cancel()
                await asyncio.gather(pump, return_exceptions=True)

    @staticmethod
    async def _pump(connection: object, audio: AsyncIterator[bytes]) -> None:
        """Forward captured audio until the caller stops producing it."""
        async for chunk in audio:
            await connection.send_media(chunk)  # type: ignore[attr-defined]
        await connection.send_close_stream()  # type: ignore[attr-defined]


class DeepgramTts:
    """Streaming speech synthesis."""

    def __init__(self, api_key: str, model: str = "aura-2-asteria-en") -> None:
        self._client = AsyncDeepgramClient(api_key=api_key)
        self._model = model

    async def synthesize(self, text: str, voice: str, rate: float = 1.0) -> AsyncIterator[bytes]:
        # A character's configured voice wins; the constructor default is only
        # a fallback for packs that do not name one.
        async with self._client.speak.v1.connect(
            model=voice or self._model,
            encoding="linear16",
            sample_rate=TTS_SAMPLE_RATE,
            speed=rate,
        ) as connection:
            await connection.send_text(SpeakV1Text(type="Speak", text=text))
            await connection.send_flush()
            await connection.send_close()
            async for message in connection:
                if isinstance(message, bytes):
                    yield message


def _is_final(event: object) -> bool:
    """True for a finalised transcript, false for an interim guess."""
    return bool(getattr(event, "is_final", False) or getattr(event, "speech_final", False))


def _transcript_of(event: object) -> str:
    """Pull the final transcript out of a Deepgram result, if it has one.

    The SDK returns generated model objects rather than plain dicts, and the
    shape differs between message types, so this reads defensively instead of
    asserting a structure.
    """
    channel = getattr(event, "channel", None)
    alternatives = getattr(channel, "alternatives", None) if channel else None
    if not alternatives:
        return ""
    transcript = getattr(alternatives[0], "transcript", "")
    return transcript.strip() if isinstance(transcript, str) else ""
