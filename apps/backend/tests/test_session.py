"""The WebSocket session drives the full pipeline for one character."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from personae.main import create_app

SPEECH = "AQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyAhIiMkJSYnKCkqKywtLi8w" * 4


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as test_client:
        yield test_client


def _collect(socket: object, limit: int = 40) -> list[dict[str, object]]:
    """Drain messages up to and including the terminal 'done'."""
    messages: list[dict[str, object]] = []
    for _ in range(limit):
        message = socket.receive_json()  # type: ignore[attr-defined]
        messages.append(message)
        if message["type"] == "done":
            break
    return messages


def test_rejects_an_unknown_character(client: TestClient) -> None:
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/ws/session/bundled/nope") as socket,
    ):
        socket.receive_json()


def test_speech_produces_transcript_reply_expression_and_audio(client: TestClient) -> None:
    with client.websocket_connect("/ws/session/bundled/seed") as socket:
        socket.send_json({"type": "audio", "pcm": SPEECH})
        socket.send_json({"type": "stop"})
        kinds = [message["type"] for message in _collect(socket)]

    assert kinds.count("transcript") == 1
    assert "reply" in kinds
    assert "expression" in kinds
    assert "audio" in kinds
    assert kinds[-1] == "done"


def test_expression_is_drawn_from_the_character_vocabulary(client: TestClient) -> None:
    """The backend must never emit a cue the frontend cannot perform."""
    with client.websocket_connect("/ws/session/bundled/seed") as socket:
        socket.send_json({"type": "audio", "pcm": SPEECH})
        socket.send_json({"type": "stop"})
        messages = _collect(socket)

    expression = next(m for m in messages if m["type"] == "expression")
    assert expression["gesture"] in {"idle", "gesture-explain", "gesture-point", "gesture-consider"}
    assert expression["emotion"] in {"neutral", "amused", "focused", "alert"}


def test_malformed_message_yields_an_error_not_a_crash(client: TestClient) -> None:
    with client.websocket_connect("/ws/session/bundled/seed") as socket:
        socket.receive_json()  # ready
        socket.send_json({"type": "audio", "pcm": "not base64!!"})
        message = socket.receive_json()
    assert message["type"] == "error"


def test_non_json_payload_is_rejected_cleanly(client: TestClient) -> None:
    with client.websocket_connect("/ws/session/bundled/seed") as socket:
        socket.receive_json()  # ready
        socket.send_text("<not json>")
        message = socket.receive_json()
    assert message["type"] == "error"


def test_silence_produces_no_transcript(client: TestClient) -> None:
    with client.websocket_connect("/ws/session/bundled/seed") as socket:
        socket.send_json({"type": "audio", "pcm": "AAAAAAAAAAAAAAAAAAAAAA=="})
        socket.send_json({"type": "stop"})
        kinds = [message["type"] for message in _collect(socket)]
    assert "transcript" not in kinds
    assert kinds[-1] == "done"


def test_session_announces_the_audio_format_before_sending_audio(client: TestClient) -> None:
    """The client must not have to hardcode the sample rate.

    Playing the samples at the wrong rate shifts pitch and speed, and a
    constant duplicated across two languages will eventually disagree.
    """
    with client.websocket_connect("/ws/session/bundled/seed") as socket:
        first = socket.receive_json()
    assert first == {"type": "ready", "sample_rate": 24000, "channels": 1}
