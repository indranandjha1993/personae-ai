"""Scribe wire protocol, cancellation, and independent provider selection."""

import asyncio
import base64
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

from personae.providers import elevenlabs_stt as module
from personae.providers.base import Heard, ProviderError
from personae.providers.factory import build_stt
from personae.providers.mock import MockStt
from personae.providers.status import stt_mode
from personae.settings import Settings


class Socket:
    def __init__(self) -> None:
        self.messages: asyncio.Queue[str] = asyncio.Queue()
        self.messages.put_nowait(json.dumps({"message_type": "session_started"}))
        self.sent: list[dict[str, Any]] = []
        self.closed = False
        self.fail_send = False

    async def recv(self) -> str:
        return await self.messages.get()

    async def send(self, data: str) -> None:
        if self.fail_send:
            raise OSError("send failed")
        self.sent.append(json.loads(data))

    def event(self, kind: str, **kwargs: object) -> None:
        self.messages.put_nowait(json.dumps({"message_type": kind, **kwargs}))


@pytest.fixture
def wire(monkeypatch: pytest.MonkeyPatch) -> tuple[Socket, dict[str, Any]]:
    socket = Socket()
    handshake: dict[str, Any] = {}

    @asynccontextmanager
    async def connect(url: str, **kwargs: Any) -> AsyncIterator[Socket]:
        handshake.update(url=url, **kwargs)
        try:
            yield socket
        finally:
            socket.closed = True

    monkeypatch.setattr(module, "connect", connect)
    return socket, handshake


async def endless_audio() -> AsyncIterator[bytes]:
    yield b"\x00\x01" * 160
    await asyncio.Event().wait()


async def test_partial_final_metadata_and_repeated_turns(
    wire: tuple[Socket, dict[str, Any]],
) -> None:
    socket, handshake = wire
    socket.event("partial_transcript", text="wait please")
    socket.event("committed_transcript", text="wait please")
    socket.event("committed_transcript_with_timestamps", text="wait please")
    socket.event("committed_transcript", text="wait please")
    stream = module.ElevenLabsStt("secret", language="en").transcribe(endless_audio())
    assert await anext(stream) == Heard("wait please", final=False)
    assert await anext(stream) == Heard("wait please", final=True)
    # Identical words in separate turns are legitimate; timestamp duplicates aren't.
    assert await anext(stream) == Heard("wait please", final=True)
    await stream.aclose()
    query = parse_qs(urlparse(handshake["url"]).query)
    assert query["audio_format"] == ["pcm_16000"]
    assert query["commit_strategy"] == ["vad"]
    assert query["language_code"] == ["en"]
    assert query["filter_background_audio"] == ["true"]
    assert handshake["additional_headers"] == {"xi-api-key": "secret"}
    assert "secret" not in handshake["url"]
    assert base64.b64decode(socket.sent[0]["audio_base_64"]) == b"\x00\x01" * 160
    assert socket.sent[0]["commit"] is False
    assert socket.closed


@pytest.mark.parametrize("kind", ["auth_error", "quota_exceeded", "rate_limited", "error"])
async def test_provider_errors_close_stream(
    wire: tuple[Socket, dict[str, Any]],
    kind: str,
) -> None:
    socket, _ = wire
    socket.event(kind, error="sensitive upstream detail")
    with pytest.raises(ProviderError, match="check API access") as error:
        await anext(module.ElevenLabsStt("secret").transcribe(endless_audio()))
    assert "sensitive" not in str(error.value)
    assert socket.closed


async def test_send_failure_does_not_hang_in_receive(
    wire: tuple[Socket, dict[str, Any]],
) -> None:
    socket, _ = wire
    socket.fail_send = True
    with pytest.raises(ProviderError, match="connection failed"):
        await asyncio.wait_for(anext(module.ElevenLabsStt("secret").transcribe(endless_audio())), 1)
    assert socket.closed


async def test_cancellation_closes_audio_and_socket(
    wire: tuple[Socket, dict[str, Any]],
) -> None:
    socket, _ = wire
    closed = asyncio.Event()
    started = asyncio.Event()

    async def audio() -> AsyncIterator[bytes]:
        try:
            yield b"\0\0"
            started.set()
            await asyncio.Event().wait()
        finally:
            closed.set()

    task = asyncio.ensure_future(anext(module.ElevenLabsStt("secret").transcribe(audio())))
    await asyncio.wait_for(started.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed.is_set()
    assert socket.closed


async def test_audio_end_commits_and_drains_with_deadline(
    wire: tuple[Socket, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    socket, _ = wire
    monkeypatch.setattr(module, "DRAIN_TIMEOUT_SECONDS", 0.02)

    async def audio() -> AsyncIterator[bytes]:
        yield b"\0\0"
        socket.event("committed_transcript", text="hello")

    results = [heard async for heard in module.ElevenLabsStt("key").transcribe(audio())]
    assert results == [Heard("hello", final=True)]
    assert socket.sent[-1]["commit"] is True
    assert socket.closed


def test_provider_selection_is_independent_of_tts() -> None:
    settings = Settings(stt_provider="elevenlabs", elevenlabs_api_key="key")
    assert isinstance(build_stt(settings), module.ElevenLabsStt)
    assert stt_mode(settings) == "live"
    assert settings.tts_provider == "deepgram"
    assert isinstance(build_stt(Settings(stt_provider="mock", deepgram_api_key="key")), MockStt)
    assert stt_mode(Settings(stt_provider="elevenlabs", deepgram_api_key="key")) == "mock"
    assert isinstance(build_stt(Settings(stt_provider="elevenlabs")), MockStt)


def test_env_selection_and_tuning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERSONAE_STT_PROVIDER", "elevenlabs")
    monkeypatch.setenv("PERSONAE_ELEVENLABS_API_KEY", "key")
    monkeypatch.setenv("PERSONAE_ELEVENLABS_STT_SILENCE_SECONDS", "0.8")
    settings = Settings()
    assert settings.stt_provider == "elevenlabs"
    assert settings.elevenlabs_stt_silence_seconds == 0.8
    assert isinstance(build_stt(settings), module.ElevenLabsStt)


@pytest.mark.parametrize("value", [0, -1, 4])
def test_invalid_silence_duration(value: float) -> None:
    with pytest.raises(ValueError, match="elevenlabs_stt_silence_seconds"):
        Settings(elevenlabs_stt_silence_seconds=value)


@pytest.mark.parametrize("payload", ["not json", "[]", '{"message_type":"partial_transcript"}'])
async def test_malformed_messages_fail_cleanly(
    wire: tuple[Socket, dict[str, Any]],
    payload: str,
) -> None:
    socket, _ = wire
    socket.messages.put_nowait(payload)
    with pytest.raises(ProviderError, match="invalid"):
        await anext(module.ElevenLabsStt("key").transcribe(endless_audio()))
    assert socket.closed


async def test_session_start_has_a_deadline(
    wire: tuple[Socket, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    socket, _ = wire
    socket.messages.get_nowait()
    monkeypatch.setattr(module, "SESSION_TIMEOUT_SECONDS", 0.01)
    with pytest.raises(ProviderError, match="connection failed"):
        await anext(module.ElevenLabsStt("key").transcribe(endless_audio()))
    assert socket.closed


def test_health_uses_selected_stt_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from personae.main import create_app

    monkeypatch.setenv("PERSONAE_STT_PROVIDER", "elevenlabs")
    monkeypatch.setenv("PERSONAE_ELEVENLABS_API_KEY", "key")
    with TestClient(create_app()) as client:
        assert client.get("/health").json()["providers"]["stt"] == "live"


def test_rejection_event_without_error_payload_is_not_ignored() -> None:
    with pytest.raises(ProviderError, match="rejected"):
        module._event('{"message_type":"invalid_request"}')


async def test_closing_after_yield_immediately_stops_audio_pump(
    wire: tuple[Socket, dict[str, Any]],
) -> None:
    socket, _ = wire
    started = asyncio.Event()
    closed = asyncio.Event()

    async def audio() -> AsyncIterator[bytes]:
        try:
            yield b"\0\0"
            started.set()
            await asyncio.Event().wait()
        finally:
            closed.set()

    stream = module.ElevenLabsStt("key").transcribe(audio())
    next_result = asyncio.ensure_future(anext(stream))
    await asyncio.wait_for(started.wait(), 1)
    socket.event("partial_transcript", text="hello")
    assert await next_result == Heard("hello", final=False)
    await stream.aclose()
    assert closed.is_set()
    assert socket.closed
