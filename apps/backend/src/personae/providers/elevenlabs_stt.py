"""Scribe realtime transcription of the browser's mono PCM16 / 16 kHz stream."""

import asyncio
import base64
import json
from collections.abc import AsyncGenerator, AsyncIterator, Sequence
from contextlib import aclosing
from urllib.parse import urlencode

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, WebSocketException
from websockets.typing import Data

from personae.providers.base import Heard, ProviderError

SESSION_TIMEOUT_SECONDS = 10.0
DRAIN_TIMEOUT_SECONDS = 5.0


class ElevenLabsStt:
    def __init__(
        self,
        api_key: str,
        model: str = "scribe_v2_realtime",
        language: str = "",
        silence_seconds: float = 0.6,
        filter_background_audio: bool = True,
    ) -> None:
        self._api_key = api_key
        self.model = model
        self._language = language
        self._silence_seconds = silence_seconds
        self._filter_background_audio = filter_background_audio

    async def transcribe(
        self, audio: AsyncIterator[bytes], keyterms: Sequence[str] = ()
    ) -> AsyncGenerator[Heard]:
        # Keyterm prompting is a separately billed feature; do not silently
        # enable it merely because a character name was supplied by the caller.
        params = {
            "model_id": self.model,
            "audio_format": "pcm_16000",
            "commit_strategy": "vad",
            "vad_silence_threshold_secs": str(self._silence_seconds),
            "filter_background_audio": str(self._filter_background_audio).lower(),
            "include_timestamps": "false",
        }
        if self._language.strip():
            params["language_code"] = self._language.strip()
        url = "wss://api.elevenlabs.io/v1/speech-to-text/realtime?" + urlencode(params)
        try:
            async with connect(
                url,
                additional_headers={"xi-api-key": self._api_key},
                open_timeout=SESSION_TIMEOUT_SECONDS,
                close_timeout=2,
                max_size=1_048_576,
            ) as connection:
                async with asyncio.timeout(SESSION_TIMEOUT_SECONDS):
                    event = _event(await connection.recv())
                    if event.get("message_type") != "session_started":
                        raise ProviderError("ElevenLabs STT did not start a transcription session.")
                async with aclosing(self._stream(connection, audio)) as stream:
                    async for heard in stream:
                        yield heard
        except (WebSocketException, OSError, TimeoutError) as exc:
            # Do not expose upstream payloads, credentials, or transcripts.
            raise ProviderError("ElevenLabs STT connection failed; please reconnect.") from exc

    async def _stream(
        self, connection: ClientConnection, audio: AsyncIterator[bytes]
    ) -> AsyncGenerator[Heard]:
        pump = asyncio.create_task(_send_audio(connection, audio))
        receive: asyncio.Task[Data] | None = None
        draining = False
        deadline: float | None = None
        try:
            while True:
                if receive is None:
                    receive = asyncio.create_task(connection.recv())
                remaining = (
                    None
                    if deadline is None
                    else max(0.0, deadline - asyncio.get_running_loop().time())
                )
                watched = {receive} if draining else {receive, pump}
                done, _ = await asyncio.wait(
                    watched, timeout=remaining, return_when=asyncio.FIRST_COMPLETED
                )
                if not done:
                    return  # Bounded final drain, including streams containing only silence.
                if not draining and pump in done:
                    pump.result()  # Surface capture/send failures instead of hanging in recv.
                    draining = True
                    deadline = asyncio.get_running_loop().time() + DRAIN_TIMEOUT_SECONDS
                if receive not in done:
                    continue
                try:
                    raw = receive.result()
                except ConnectionClosed:
                    if draining:
                        return
                    raise
                receive = None
                event = _event(raw)
                kind = event.get("message_type")
                if kind not in ("partial_transcript", "committed_transcript"):
                    continue  # Ignore metadata and timestamp duplicates.
                text = event.get("text")
                if not isinstance(text, str):
                    raise ProviderError("ElevenLabs STT returned an invalid transcript.")
                if text.strip():
                    yield Heard(text.strip(), final=kind == "committed_transcript")
        finally:
            tasks = [pump] if receive is None else [pump, receive]
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


def _event(raw: Data) -> dict[str, object]:
    try:
        event = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise ProviderError("ElevenLabs STT returned an invalid message.") from exc
    if not isinstance(event, dict):
        raise ProviderError("ElevenLabs STT returned an invalid message.")
    kind = event.get("message_type", "")
    if kind != "warning" and (
        "error" in event
        or kind
        in (
            "error",
            "auth_error",
            "quota_exceeded",
            "rate_limited",
            "queue_overflow",
            "invalid_request",
            "session_time_limit_exceeded",
            "unaccepted_terms",
            "resource_exhausted",
            "chunk_size_exceeded",
            "insufficient_audio_activity",
            "commit_throttled",
        )
        or (isinstance(kind, str) and kind.endswith("_error"))
    ):
        raise ProviderError("ElevenLabs STT rejected the stream; check API access and quota.")
    return event


async def _send_audio(connection: ClientConnection, audio: AsyncIterator[bytes]) -> None:
    async for chunk in audio:
        if chunk:
            await connection.send(
                json.dumps(
                    {
                        "message_type": "input_audio_chunk",
                        "audio_base_64": base64.b64encode(chunk).decode("ascii"),
                        "sample_rate": 16000,
                        "commit": False,
                    }
                )
            )
    await connection.send(
        json.dumps(
            {
                "message_type": "input_audio_chunk",
                "audio_base_64": "",
                "commit": True,
                "sample_rate": 16000,
            }
        )
    )
