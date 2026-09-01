"""One conversational turn, driven over a WebSocket."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator

from pydantic import ValidationError

from personae import expression
from personae.packs.models import Character
from personae.protocol import AudioFrame, ServerMessage, StopSignal, parse_client_message
from personae.providers.base import LlmProvider, SttProvider, TtsProvider

logger = logging.getLogger(__name__)


class Session:
    """Streams audio in, and transcript, reply, expression, and audio back.

    The transport is injected rather than imported so the pipeline can be
    driven by a test double as easily as by a live WebSocket.
    """

    def __init__(
        self,
        character: Character,
        stt: SttProvider,
        llm: LlmProvider,
        tts: TtsProvider,
    ) -> None:
        self._character = character
        self._stt = stt
        self._llm = llm
        self._tts = tts
        self._inbound: asyncio.Queue[bytes | None] = asyncio.Queue()

    async def offer(self, frame: AudioFrame) -> None:
        await self._inbound.put(frame.pcm_bytes())

    async def close_input(self) -> None:
        await self._inbound.put(None)

    async def run(self) -> AsyncIterator[ServerMessage]:
        """Yield outbound messages until the turn completes."""
        async for transcript in self._stt.transcribe(self._audio()):
            yield ServerMessage.transcript(transcript)

            reply = ""
            async for fragment in self._llm.respond(self._character.persona.prompt, transcript):
                reply += fragment
            yield ServerMessage.reply(reply)

            gesture, emotion = expression.infer(reply, self._character)
            yield ServerMessage.expression(gesture=gesture, emotion=emotion)

            async for chunk in self._tts.synthesize(reply, self._character.voice.provider_voice):
                yield ServerMessage.audio(chunk)

    async def _audio(self) -> AsyncIterator[bytes]:
        while (chunk := await self._inbound.get()) is not None:
            yield chunk


class MalformedMessageError(Exception):
    """An inbound frame was not a valid protocol message."""


def decode(raw: str) -> AudioFrame | StopSignal:
    """Parse one inbound frame.

    Both malformed JSON and a well-formed but invalid message surface as the
    same failure, because the client should not be able to tell them apart.
    """
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MalformedMessageError("payload is not valid JSON") from exc
    try:
        return parse_client_message(payload)
    except ValidationError as exc:
        raise MalformedMessageError(str(exc)) from exc
