"""The WebSocket wire protocol.

Every message is a tagged variant validated at the boundary. Nothing untyped
crosses into the pipeline: a client can only send what is declared here, and
anything else is rejected before it reaches application code.
"""

import base64
import binascii
import json
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationError,
    field_serializer,
    field_validator,
)

# 16-bit PCM at 16 kHz is 32 kB per second; this caps a single frame at roughly
# two seconds, which is far above the ~100 ms frames the client actually sends.
MAX_FRAME_BYTES = 64_000

# A downscaled still is well under this; anything larger is a mistake.
MAX_IMAGE_BYTES = 1_500_000

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


class VisionFrame(_Message):
    """A camera still for the model to look at, attached to the next turn."""

    type: Literal["vision"]
    jpeg: str

    @field_validator("jpeg")
    @classmethod
    def _must_be_decodable(cls, value: str) -> str:
        try:
            decoded = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("jpeg must be valid base64") from exc
        if len(decoded) > MAX_IMAGE_BYTES:
            raise ValueError(f"frame exceeds {MAX_IMAGE_BYTES} bytes")
        return value

    def jpeg_bytes(self) -> bytes:
        return base64.b64decode(self.jpeg, validate=True)


class InterruptSignal(_Message):
    """The listener started talking over the reply."""

    type: Literal["interrupt"]


ClientMessage = Annotated[
    AudioFrame | StopSignal | InterruptSignal | VisionFrame,
    Field(discriminator="type"),
]

_client_adapter: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)


def parse_client_message(payload: object) -> ClientMessage:
    """Validate an inbound message, raising ValidationError if it is not one."""
    return _client_adapter.validate_python(payload)


class MalformedMessageError(Exception):
    """An inbound frame was not a valid protocol message."""


def decode(raw: str) -> ClientMessage:
    """Parse one inbound frame.

    Malformed JSON and a well-formed but invalid message surface as the same
    failure, because the client should not be able to tell them apart.
    """
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MalformedMessageError("payload is not valid JSON") from exc
    try:
        return parse_client_message(payload)
    except ValidationError as exc:
        raise MalformedMessageError(str(exc)) from exc


class ServerMessage(_Message):
    """Base for outbound messages, with constructors for each variant."""

    @staticmethod
    def ready(sample_rate: int, channels: int = 1) -> "ReadyMessage":
        return ReadyMessage(type="ready", sample_rate=sample_rate, channels=channels)

    @staticmethod
    def transcript(text: str) -> "TranscriptMessage":
        return TranscriptMessage(type="transcript", text=text)

    @staticmethod
    def hearing(text: str) -> "HearingMessage":
        return HearingMessage(type="hearing", text=text)

    @staticmethod
    def speaking(text: str) -> "SpeakingMessage":
        return SpeakingMessage(type="speaking", text=text)

    @staticmethod
    def reply(text: str) -> "ReplyMessage":
        return ReplyMessage(type="reply", text=text)

    @staticmethod
    def audio(pcm: bytes) -> "AudioMessage":
        return AudioMessage(type="audio", pcm=pcm)

    @staticmethod
    def expression(gesture: str, emotion: str) -> "ExpressionMessage":
        return ExpressionMessage(type="expression", gesture=gesture, emotion=emotion)

    @staticmethod
    def interrupted() -> "InterruptedMessage":
        return InterruptedMessage(type="interrupted")

    @staticmethod
    def farewell() -> "FarewellMessage":
        return FarewellMessage(type="farewell")

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


class HearingMessage(ServerMessage):
    """What the listener is saying, while they are still saying it.

    Provisional and superseded by the next one, so it is shown but never
    acted on.
    """

    type: Literal["hearing"]
    text: str


class SpeakingMessage(ServerMessage):
    """The sentence she is about to say, sent just before its audio."""

    type: Literal["speaking"]
    text: str


class ReplyMessage(ServerMessage):
    type: Literal["reply"]
    text: str


class AudioMessage(ServerMessage):
    """Synthesised speech.

    Sent as a binary frame: a third smaller than base64 in JSON, and the client
    can hand the bytes straight to the audio graph. The base64 form survives
    for anything that dumps the message as JSON.
    """

    type: Literal["audio"]
    pcm: bytes

    @field_serializer("pcm")
    def _as_base64(self, pcm: bytes) -> str:
        return base64.b64encode(pcm).decode("ascii")


class ExpressionMessage(ServerMessage):
    type: Literal["expression"]
    gesture: str
    emotion: str


class InterruptedMessage(ServerMessage):
    """The reply was cut short because the listener started speaking."""

    type: Literal["interrupted"]


class FarewellMessage(ServerMessage):
    """She has said goodbye; the conversation is over once her audio ends."""

    type: Literal["farewell"]


class ErrorMessage(ServerMessage):
    type: Literal["error"]
    detail: str
