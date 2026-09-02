"""The live WebSocket endpoint, end to end."""

import base64
from collections.abc import AsyncIterator, Iterator

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
        # Audio now precedes the caption, so collecting stops at the reply
        # rather than at the first sound.
        if message["type"] in {"done", "reply", "error"}:
            break
    return messages


def test_rejects_an_unknown_character(client: TestClient) -> None:
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/ws/live/bundled/nope") as socket,
    ):
        socket.receive_json()


def test_speech_produces_transcript_reply_expression_and_audio(client: TestClient) -> None:
    with client.websocket_connect("/ws/live/bundled/seed") as socket:
        socket.receive_json()  # ready
        socket.send_json({"type": "audio", "pcm": SPEECH})
        socket.send_json({"type": "stop"})
        kinds = [message["type"] for message in _collect(socket)]

    assert kinds.count("transcript") == 1
    assert "reply" in kinds
    assert "expression" in kinds
    assert "audio" in kinds


def test_expression_is_drawn_from_the_character_vocabulary(client: TestClient) -> None:
    """The backend must never emit a cue the frontend cannot perform."""
    with client.websocket_connect("/ws/live/bundled/seed") as socket:
        socket.receive_json()  # ready
        socket.send_json({"type": "audio", "pcm": SPEECH})
        socket.send_json({"type": "stop"})
        messages = _collect(socket)

    expression = next(m for m in messages if m["type"] == "expression")
    assert expression["gesture"] in {"idle", "gesture-explain", "gesture-point", "gesture-consider"}
    assert expression["emotion"] in {"neutral", "amused", "focused", "alert"}


def test_malformed_message_yields_an_error_not_a_crash(client: TestClient) -> None:
    with client.websocket_connect("/ws/live/bundled/seed") as socket:
        socket.receive_json()  # ready
        socket.send_json({"type": "audio", "pcm": "not base64!!"})
        message = socket.receive_json()
    assert message["type"] == "error"


def test_non_json_payload_is_rejected_cleanly(client: TestClient) -> None:
    with client.websocket_connect("/ws/live/bundled/seed") as socket:
        socket.receive_json()  # ready
        socket.send_text("<not json>")
        message = socket.receive_json()
    assert message["type"] == "error"


def test_silence_produces_no_transcript(client: TestClient) -> None:
    """Nothing is sent back at all, so a malformed frame is used as a probe."""
    with client.websocket_connect("/ws/live/bundled/seed") as socket:
        socket.receive_json()  # ready
        socket.send_json({"type": "audio", "pcm": "AAAAAAAAAAAAAAAAAAAAAA=="})
        # If silence had produced a transcript it would arrive before this.
        socket.send_text("<not json>")
        assert socket.receive_json()["type"] == "error"


def test_session_announces_the_audio_format_before_sending_audio(client: TestClient) -> None:
    """The client must not have to hardcode the sample rate.

    Playing the samples at the wrong rate shifts pitch and speed, and a
    constant duplicated across two languages will eventually disagree.
    """
    with client.websocket_connect("/ws/live/bundled/seed") as socket:
        first = socket.receive_json()
    assert first == {"type": "ready", "sample_rate": 24000, "channels": 1}


def test_a_camera_frame_reaches_the_reply(client: TestClient) -> None:
    """Vision must work in push-to-talk too, not only in live mode."""
    frame = base64.b64encode(b"\xff\xd8jpeg").decode()
    with client.websocket_connect("/ws/live/bundled/seed") as socket:
        socket.receive_json()  # ready
        socket.send_json({"type": "vision", "jpeg": frame})
        socket.send_json({"type": "audio", "pcm": SPEECH})
        socket.send_json({"type": "stop"})
        messages = _collect(socket)

    reply = next(m for m in messages if m["type"] == "reply")
    # The stand-in reports what it was shown, so the frame is observable.
    assert "frame" in str(reply["text"])


def test_a_vision_frame_does_not_end_the_turn(client: TestClient) -> None:
    """Anything that is not audio used to be treated as 'stop'."""
    frame = base64.b64encode(b"\xff\xd8jpeg").decode()
    with client.websocket_connect("/ws/live/bundled/seed") as socket:
        socket.receive_json()
        socket.send_json({"type": "vision", "jpeg": frame})
        socket.send_json({"type": "audio", "pcm": SPEECH})
        socket.send_json({"type": "stop"})
        kinds = [m["type"] for m in _collect(socket)]
    assert "transcript" in kinds


def test_a_disconnect_releases_the_session(client: TestClient) -> None:
    """An unhandled disconnect used to leave the session and its STT socket
    waiting for input that would never arrive."""
    with client.websocket_connect("/ws/live/bundled/seed") as socket:
        socket.receive_json()  # ready
        socket.send_json({"type": "audio", "pcm": SPEECH})
    # Reconnecting proves the server did not wedge on the abandoned session.
    with client.websocket_connect("/ws/live/bundled/seed") as socket:
        assert socket.receive_json()["type"] == "ready"


async def test_a_provider_failure_is_reported_not_fatal() -> None:
    """A transient model error must not kill the conversation silently."""
    from personae.live import LiveSession
    from personae.main import REPO_ROOT
    from personae.packs.loader import load_packs
    from personae.providers.mock import MockStt, MockTts

    class FailingLlm:
        def respond(self, *args: object, **kwargs: object) -> AsyncIterator[str]:
            async def boom() -> AsyncIterator[str]:
                # An empty yield first makes this a generator without leaving
                # unreachable code after the raise.
                for _ in ():
                    yield ""
                raise RuntimeError("upstream is down")

            return boom()

    character = load_packs([REPO_ROOT / "packs" / "bundled"]).get("bundled/seed")
    session = LiveSession(character, MockStt(), FailingLlm(), MockTts())
    await session.offer(base64.b64decode(SPEECH))
    await session.close_input()

    kinds = [message.model_dump()["type"] async for message in session.run()]
    assert "error" in kinds
