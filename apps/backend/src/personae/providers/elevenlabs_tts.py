"""Sentence-streaming ElevenLabs adapter. Alignment remains character timing.

HTTP streaming suits the pipeline's complete phrases and allows cancellation
without draining a shared vendor socket. A session reuses its HTTP connection pool.
"""

import base64
import binascii
import json
from collections.abc import AsyncIterator
from urllib.parse import quote

import httpx
from pydantic import BaseModel, Field

from personae.providers.base import ProviderError, Speaker
from personae.speech_events import CharacterCue, SpeechChunk


class _Alignment(BaseModel):
    characters: list[str]
    character_start_times_seconds: list[float]
    character_end_times_seconds: list[float]


class _Chunk(BaseModel):
    audio_base64: str = ""
    alignment: _Alignment | None = None
    normalized_alignment: _Alignment | None = None


def parse_chunk(raw: object) -> SpeechChunk:
    data = _Chunk.model_validate(raw)
    alignment = data.normalized_alignment or data.alignment
    cues: tuple[CharacterCue, ...] = ()
    if alignment is not None:
        cues = tuple(
            CharacterCue(text=text, start=start, end=end)
            for text, start, end in zip(
                alignment.characters,
                alignment.character_start_times_seconds,
                alignment.character_end_times_seconds,
                strict=True,
            )
        )
    try:
        pcm = base64.b64decode(data.audio_base64, validate=True)
    except binascii.Error as error:
        raise ValueError("invalid speech audio") from error
    return SpeechChunk(pcm=pcm, alignment=cues)


class _VoiceSettings(BaseModel):
    # v3 accepts discrete stability values; 0.5 is its natural setting.
    stability: float = 0.5
    speed: float = Field(ge=0.7, le=1.2)


class ElevenLabsSpeaker:
    def __init__(self, api_key: str, model: str, voice: str, rate: float) -> None:
        self._client = httpx.AsyncClient(
            base_url="https://api.elevenlabs.io/v1/",
            headers={"xi-api-key": api_key},
            timeout=httpx.Timeout(30, connect=10),
        )
        self._model = model
        self._voice = voice
        self._rate = rate

    async def say(self, text: str, rate: float | None = None) -> AsyncIterator[SpeechChunk]:
        settings = _VoiceSettings(speed=max(0.7, min(1.2, rate or self._rate)))
        remainder = b""
        try:
            async with self._client.stream(
                "POST",
                f"text-to-speech/{quote(self._voice, safe='')}/stream/with-timestamps",
                params={"output_format": "pcm_24000"},
                json={
                    "text": text,
                    "model_id": self._model,
                    "voice_settings": settings.model_dump(),
                },
            ) as response:
                if response.is_error:
                    raise ProviderError(f"ElevenLabs refused speech (HTTP {response.status_code})")
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    chunk = parse_chunk(json.loads(line))
                    pcm = remainder + chunk.pcm
                    size = len(pcm) - len(pcm) % 2
                    remainder = pcm[size:]
                    yield SpeechChunk(pcm[:size], chunk.alignment, chunk.visemes)
            if remainder:
                raise ProviderError("ElevenLabs returned an incomplete PCM sample")
        except (ValueError, httpx.HTTPError) as error:
            raise ProviderError("ElevenLabs speech stream failed") from error

    async def close(self) -> None:
        await self._client.aclose()


class ElevenLabsTts:
    def __init__(self, api_key: str, model: str, default_voice: str) -> None:
        self._api_key = api_key
        self._model = model
        self._default_voice = default_voice

    async def open(self, voice: str, rate: float = 1.0, expressivity: int | None = None) -> Speaker:
        # Explicitly namespaced pack voices override the provider default.
        selected = (
            voice.removeprefix("elevenlabs:")
            if voice.startswith("elevenlabs:")
            else self._default_voice
        )
        if not selected:
            raise ProviderError("Configure an ElevenLabs voice ID")
        return ElevenLabsSpeaker(self._api_key, self._model, selected, rate)

    async def synthesize(self, text: str, voice: str, rate: float = 1.0) -> AsyncIterator[bytes]:
        speaker = await self.open(voice, rate)
        try:
            async for chunk in speaker.say(text):
                yield chunk if isinstance(chunk, bytes) else chunk.pcm
        finally:
            await speaker.close()
