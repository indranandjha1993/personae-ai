"""Only explicitly configured voices can be selected by a browser."""

import pytest

from personae.settings import Settings
from personae.voices import voice_choices


def test_no_keys_only_advertises_demo() -> None:
    choices = voice_choices(Settings())
    assert list(choices) == ["default"]
    assert choices["default"].mode == "mock"


def test_local_voices_are_independent_of_persona() -> None:
    settings = Settings(
        local_tts_base_url="http://localhost:8880/v1", local_tts_voices=("af_heart", "af_bella")
    )
    choices = voice_choices(settings)
    assert choices["local:af_bella"].voice == "local:af_bella"
    assert choices["local:af_bella"].settings.tts_provider == "local"
    assert choices["local:af_bella"].mode == "local"
    assert "elevenlabs:default" not in choices


async def test_local_tts_streams_pcm_without_cloud_key(monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    import httpx

    from personae.providers.local_tts import LocalTts

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.url.path == "/v1/audio/speech"
        assert body["voice"] == "af_bella"
        assert body["response_format"] == "pcm"
        assert "authorization" not in request.headers
        return httpx.Response(200, content=b"\x01\x00\x02\x00")

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handler)),
    )
    speaker = await LocalTts("http://localhost:8880/v1", "kokoro", "af_heart", None).open(
        "local:af_bella"
    )
    try:
        chunks = [chunk async for chunk in speaker.say("Hi")]
    finally:
        await speaker.close()
    assert b"".join(chunk for chunk in chunks if isinstance(chunk, bytes)) == b"\x01\x00\x02\x00"


def test_voice_endpoint_contains_only_public_metadata() -> None:
    from fastapi.testclient import TestClient

    from personae.main import create_app

    with TestClient(create_app()) as client:
        response = client.get("/voices")
    assert response.status_code == 200
    assert response.json() == {
        "voices": [
            {"id": "default", "label": "Demo tone", "mode": "mock"},
        ]
    }


def test_unknown_voice_is_rejected_before_session() -> None:
    from fastapi.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect

    from personae.main import create_app

    with (
        TestClient(create_app()) as client,
        pytest.raises(WebSocketDisconnect) as error,
        client.websocket_connect("/ws/live/bundled/seed?voice=unconfigured"),
    ):
        pass
    assert error.value.code == 4400


@pytest.mark.parametrize(("status", "body"), [(503, b"busy"), (200, b"\x01")])
async def test_local_tts_surfaces_failures(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    body: bytes,
) -> None:
    import httpx

    from personae.providers.base import ProviderError
    from personae.providers.local_tts import LocalTts

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(
            **kwargs, transport=httpx.MockTransport(lambda _: httpx.Response(status, content=body))
        ),
    )
    speaker = await LocalTts("http://localhost:8880/v1", "kokoro", "af_heart", None).open("default")
    try:
        with pytest.raises(ProviderError):
            _ = [chunk async for chunk in speaker.say("Hello")]
    finally:
        await speaker.close()
