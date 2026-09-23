"""Deepgram Aura streaming text-to-speech."""

from collections.abc import AsyncIterator

from deepgram import AsyncDeepgramClient
from deepgram.speak.v1.types.speak_v1text import SpeakV1Text

from personae.protocol import PLAYBACK_SAMPLE_RATE
from personae.providers.base import Speaker, SynthesizingSpeaker

TTS_SAMPLE_RATE = PLAYBACK_SAMPLE_RATE


class DeepgramTts:
    """Streaming speech synthesis."""

    def __init__(self, api_key: str, voice: str = "aura-2-thalia-en") -> None:
        self._client = AsyncDeepgramClient(api_key=api_key)
        self._voice = voice

    def voice_for(self, requested: str) -> str:
        """A character's own voice wins; the configured one fills the gap."""
        return requested or self._voice

    async def open(self, voice: str, rate: float = 1.0, expressivity: int | None = None) -> Speaker:
        # Aura connects per utterance; expressivity is a Flux control.
        return SynthesizingSpeaker(self.synthesize, self.voice_for(voice), rate)

    async def synthesize(self, text: str, voice: str, rate: float = 1.0) -> AsyncIterator[bytes]:
        # A character's configured voice wins; the constructor default is only
        # a fallback for packs that do not name one.
        async with self._client.speak.v1.connect(
            model=self.voice_for(voice),
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
