"""The WebSocket wire protocol.

Every message is a tagged variant validated at the boundary. Nothing untyped
crosses into the pipeline: a client can only send what is declared here, and
anything else is rejected before it reaches application code.
"""

import base64
import binascii
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

# 16-bit PCM at 16 kHz is 32 kB per second; this caps a single frame at roughly
# two seconds, which is far above the ~100 ms frames the client actually sends.
MAX_FRAME_BYTES = 64_000

# Sample rate of the audio streamed back to clients. Providers synthesise at
# this rate, and the client is told it on connect rather than assuming it.
PLAYBACK_SAMPLE_RATE = 24_000


class _Message(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class AudioFrame(_Message):
    """Captured microphone audio, base64-encoded for JSON transport."""

    type: Literal["audio"]
    pcm: str

    @field_validator("pcm")
    @classmethod
    def _must_be_decodable(cls, value: str) -> str:
        try:
            decoded = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("pcm must be valid base64") from exc
        if len(decoded) > MAX_FRAME_BYTES:
            raise ValueError(f"frame exceeds {MAX_FRAME_BYTES} bytes")
        return value

    def pcm_bytes(self) -> bytes:
        return base64.b64decode(self.pcm, validate=True)


class StopSignal(_Message):
    """The client has finished speaking."""

    type: Literal["stop"]


class InterruptSignal(_Message):
    """The listener started talking over the reply."""

    type: Literal["interrupt"]


ClientMessage = Annotated[AudioFrame | StopSignal | InterruptSignal, Field(discriminator="type")]

_client_adapter: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)


def parse_client_message(payload: object) -> ClientMessage:
    """Validate an inbound message, raising ValidationError if it is not one."""
    return _client_adapter.validate_python(payload)


class ServerMessage(_Message):
    """Base for outbound messages, with constructors for each variant."""

    @staticmethod
    def ready(sample_rate: int, channels: int = 1) -> "ReadyMessage":
        return ReadyMessage(type="ready", sample_rate=sample_rate, channels=channels)

    @staticmethod
    def transcript(text: str) -> "TranscriptMessage":
        return TranscriptMessage(type="transcript", text=text)

    @staticmethod
    def reply(text: str) -> "ReplyMessage":
        return ReplyMessage(type="reply", text=text)

    @staticmethod
    def audio(pcm: bytes) -> "AudioMessage":
        return AudioMessage(type="audio", pcm=base64.b64encode(pcm).decode("ascii"))

    @staticmethod
    def expression(gesture: str, emotion: str) -> "ExpressionMessage":
        return ExpressionMessage(type="expression", gesture=gesture, emotion=emotion)

    @staticmethod
    def interrupted() -> "InterruptedMessage":
        return InterruptedMessage(type="interrupted")

    @staticmethod
    def error(detail: str) -> "ErrorMessage":
        return ErrorMessage(type="error", detail=detail)


class ReadyMessage(ServerMessage):
    """Sent once on connect, describing the audio the client will receive."""

    type: Literal["ready"]
    sample_rate: int
    channels: int


class TranscriptMessage(ServerMessage):
    type: Literal["transcript"]
    text: str


class ReplyMessage(ServerMessage):
    type: Literal["reply"]
    text: str


class AudioMessage(ServerMessage):
    type: Literal["audio"]
    pcm: str


class ExpressionMessage(ServerMessage):
    type: Literal["expression"]
    gesture: str
    emotion: str


class InterruptedMessage(ServerMessage):
    """The reply was cut short because the listener started speaking."""

    type: Literal["interrupted"]


class ErrorMessage(ServerMessage):
    type: Literal["error"]
    detail: str
