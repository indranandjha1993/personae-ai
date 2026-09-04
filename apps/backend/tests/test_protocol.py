"""The wire protocol is a closed set of typed messages, not free-form dicts."""

from typing import get_args

import pytest
from pydantic import ValidationError

from personae.protocol import ClientMessage, ServerMessage, parse_client_message


def test_parses_an_audio_frame() -> None:
    message = parse_client_message({"type": "audio", "pcm": "AAECAw=="})
    assert message.type == "audio"
    assert message.pcm_bytes() == bytes([0, 1, 2, 3])


def test_parses_a_stop_message() -> None:
    assert parse_client_message({"type": "stop"}).type == "stop"


def test_rejects_an_unknown_message_type() -> None:
    with pytest.raises(ValidationError):
        parse_client_message({"type": "shutdown"})


def test_rejects_audio_without_a_payload() -> None:
    with pytest.raises(ValidationError):
        parse_client_message({"type": "audio"})


def test_rejects_payloads_that_are_not_base64() -> None:
    """Malformed input must fail at the boundary, not deep in the pipeline."""
    with pytest.raises(ValidationError):
        parse_client_message({"type": "audio", "pcm": "not base64!!"})


def test_rejects_oversized_audio_frames() -> None:
    """A frame cap keeps a hostile client from exhausting memory."""
    with pytest.raises(ValidationError):
        parse_client_message({"type": "audio", "pcm": "A" * 200_000})


def test_server_messages_serialise_with_their_discriminator() -> None:
    payload = ServerMessage.transcript("hello").model_dump()
    assert payload == {"type": "transcript", "text": "hello"}


def test_server_audio_is_base64_encoded() -> None:
    payload = ServerMessage.audio(bytes([255, 0, 128])).model_dump()
    assert payload["type"] == "audio"
    assert payload["pcm"] == "/wCA"


def test_server_audio_keeps_its_bytes_for_the_binary_frame() -> None:
    """The socket sends audio raw; base64 is only for a JSON dump."""
    assert ServerMessage.audio(bytes([255, 0, 128])).pcm == bytes([255, 0, 128])


def test_server_expression_carries_gesture_and_emotion() -> None:
    payload = ServerMessage.expression(gesture="idle", emotion="neutral").model_dump()
    assert payload == {"type": "expression", "gesture": "idle", "emotion": "neutral"}


def test_client_message_union_is_exhaustive() -> None:
    """The accepted variants are exactly those declared; nothing else parses."""
    variants = get_args(get_args(ClientMessage)[0])
    assert {member.__name__ for member in variants} == {
        "AudioFrame",
        "StopSignal",
        "InterruptSignal",
        "VisionFrame",
    }


def test_parses_a_camera_frame() -> None:
    message = parse_client_message({"type": "vision", "jpeg": "AAECAw=="})
    assert message.type == "vision"
    assert message.jpeg_bytes() == bytes([0, 1, 2, 3])


def test_rejects_an_oversized_camera_frame() -> None:
    """A still is small; anything large is a mistake or an attack."""
    with pytest.raises(ValidationError):
        parse_client_message({"type": "vision", "jpeg": "A" * 3_000_000})
