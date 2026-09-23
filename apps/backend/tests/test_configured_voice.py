"""Session voices come only from the selected provider configuration."""

import pytest

from personae.settings import Settings


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


@pytest.mark.parametrize(
    ("provider", "expected"),
    [
        ("deepgram", "aura-2-thalia-en"),
        ("elevenlabs", "elevenlabs:chosen"),
        ("local", "local:af_bella"),
        ("mock", ""),
    ],
)
def test_provider_voice_wins_over_pack(provider: str, expected: str) -> None:
    from personae.main import REPO_ROOT
    from personae.packs.loader import load_packs
    from personae.voices import configured_voice

    settings = Settings.model_validate(
        {
            "tts_provider": provider,
            "deepgram_tts_voice": "aura-2-thalia-en",
            "elevenlabs_tts_voice": "chosen",
            "local_tts_voice": "af_bella",
        }
    )
    character = load_packs([REPO_ROOT / "packs/bundled"]).get("bundled/seed")
    original = character.voice.provider_voice
    resolved = configured_voice(character, settings)
    assert resolved.voice.provider_voice == expected
    assert character.voice.provider_voice == original
    assert resolved.voice.rate == character.voice.rate
    assert resolved.persona == character.persona


def test_session_uses_env_voice_even_when_pack_names_another_family(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi.testclient import TestClient

    from personae import main
    from personae.packs.models import Character
    from personae.providers.mock import MockStt, MockTts
    from personae.voices import configured_voice

    captured: list[str] = []

    def resolve(character: Character, settings: Settings) -> Character:
        resolved = configured_voice(character, settings)
        captured.append(resolved.voice.provider_voice)
        return resolved

    monkeypatch.setenv("PERSONAE_DEEPGRAM_TTS_VOICE", "aura-2-thalia-en")
    monkeypatch.setattr(main, "configured_voice", resolve)
    monkeypatch.setattr(main, "build_stt", lambda _: MockStt())
    monkeypatch.setattr(main, "build_tts", lambda _: MockTts())
    with (
        TestClient(main.create_app()) as client,
        client.websocket_connect("/ws/live/bundled/seed") as socket,
    ):
        assert socket.receive_json()["type"] == "ready"
    assert captured == ["aura-2-thalia-en"]
