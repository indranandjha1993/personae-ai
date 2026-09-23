"""Timing boundaries must reject invalid provider data and preserve audio."""

import base64

import pytest
from pydantic import ValidationError

from personae.providers.elevenlabs import parse_chunk
from personae.speech_events import VisemeCue


def test_alignment_is_timing_not_phonemes() -> None:
    chunk = parse_chunk(
        {
            "audio_base64": base64.b64encode(b"\x01\x00").decode(),
            "alignment": {
                "characters": ["h", "i"],
                "character_start_times_seconds": [0, 0.1],
                "character_end_times_seconds": [0.1, 0.2],
            },
        }
    )
    assert chunk.pcm == b"\x01\x00"
    assert chunk.alignment[1].start == 0.1
    assert chunk.visemes == ()


def test_invalid_alignment_is_rejected() -> None:
    with pytest.raises(ValueError, match="zip"):
        parse_chunk(
            {
                "audio_base64": "",
                "alignment": {
                    "characters": ["a"],
                    "character_start_times_seconds": [],
                    "character_end_times_seconds": [0.1],
                },
            }
        )
    with pytest.raises(ValidationError):
        VisemeCue(start=1, end=0, value="aa")
    with pytest.raises(ValidationError):
        VisemeCue(start=float("nan"), end=1, value="aa")


async def test_streams_audio_and_alignment_without_exposing_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json

    import httpx

    from personae.providers.elevenlabs import ElevenLabsTts
    from personae.speech_events import SpeechChunk

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["xi-api-key"] == "test-key"
        assert request.url.params["output_format"] == "pcm_24000"
        assert json.loads(request.content)["text"] == "Hello."
        # Odd transport boundaries must not corrupt signed 16-bit samples.
        return httpx.Response(
            200,
            content="\n".join(
                [
                    json.dumps({"audio_base64": base64.b64encode(b"\x01").decode()}),
                    json.dumps({"audio_base64": base64.b64encode(b"\x00\x02\x00").decode()}),
                ]
            ),
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handler)),
    )
    provider = ElevenLabsTts("test-key", "test-model", "default-voice")
    speaker = await provider.open("elevenlabs:pack-voice")
    try:
        chunks = [chunk async for chunk in speaker.say("Hello.")]
    finally:
        await speaker.close()
    assert all(isinstance(chunk, SpeechChunk) for chunk in chunks)
    assert (
        b"".join(chunk.pcm for chunk in chunks if isinstance(chunk, SpeechChunk))
        == b"\x01\x00\x02\x00"
    )
    assert requests[0].url.path == "/v1/text-to-speech/pack-voice/stream/with-timestamps"


async def test_reports_elevenlabs_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    from personae.providers.base import ProviderError
    from personae.providers.elevenlabs import ElevenLabsTts

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(
            **kwargs, transport=httpx.MockTransport(lambda request: httpx.Response(401))
        ),
    )
    speaker = await ElevenLabsTts("test-key", "test-model", "voice").open("deepgram-voice")
    try:
        with pytest.raises(ProviderError, match="HTTP 401"):
            _ = [chunk async for chunk in speaker.say("Hello.")]
    finally:
        await speaker.close()
