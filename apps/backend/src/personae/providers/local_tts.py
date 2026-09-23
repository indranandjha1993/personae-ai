"""OpenAI-compatible local speech server, e.g. Kokoro-FastAPI.

The endpoint must produce raw mono signed PCM16 at 24 kHz for response_format=pcm.
No automatic cloud fallback: a configured local failure is surfaced to the user.
"""

from collections.abc import AsyncIterator

import httpx

from personae.providers.base import ProviderError, Speaker


class LocalSpeaker:
    def __init__(
        self, base_url: str, model: str, voice: str, api_key: str | None, rate: float
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/",
            timeout=httpx.Timeout(30, connect=5),
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
        )
        self._model = model
        self._voice = voice
        self._rate = rate

    async def say(self, text: str, rate: float | None = None) -> AsyncIterator[bytes]:
        remainder = b""
        try:
            async with self._client.stream(
                "POST",
                "audio/speech",
                json={
                    "model": self._model,
                    "input": text,
                    "voice": self._voice,
                    "response_format": "pcm",
                    "speed": rate or self._rate,
                },
            ) as response:
                if response.is_error:
                    raise ProviderError(
                        f"Local speech server refused the request ({response.status_code})"
                    )
                async for data in response.aiter_bytes(chunk_size=4800):
                    data = remainder + data
                    size = len(data) - len(data) % 2
                    remainder = data[size:]
                    if size:
                        yield data[:size]
            if remainder:
                raise ProviderError("Local speech server returned an incomplete PCM sample")
        except httpx.HTTPError as error:
            raise ProviderError(
                "Local speech server is unavailable; check its connection"
            ) from error

    async def close(self) -> None:
        await self._client.aclose()


class LocalTts:
    def __init__(self, base_url: str, model: str, voice: str, api_key: str | None) -> None:
        self._base_url = base_url
        self._model = model
        self._voice = voice
        self._api_key = api_key

    async def open(self, voice: str, rate: float = 1.0, expressivity: int | None = None) -> Speaker:
        selected = voice.removeprefix("local:") if voice.startswith("local:") else self._voice
        return LocalSpeaker(self._base_url, self._model, selected, self._api_key, rate)

    async def synthesize(self, text: str, voice: str, rate: float = 1.0) -> AsyncIterator[bytes]:
        speaker = await self.open(voice, rate)
        try:
            async for chunk in speaker.say(text):
                yield chunk if isinstance(chunk, bytes) else chunk.pcm
        finally:
            await speaker.close()
