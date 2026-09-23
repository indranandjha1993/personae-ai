"""Deepgram Nova streaming speech-to-text and utterance assembly."""

import asyncio
from collections.abc import AsyncIterator, Sequence

from deepgram import AsyncDeepgramClient

from personae.providers.base import Heard

STT_SAMPLE_RATE = 16_000


KEEPALIVE_INTERVAL_S = 5.0


class DeepgramStt:
    """Streaming transcription over a live websocket."""

    def __init__(
        self,
        api_key: str,
        model: str = "nova-3",
        language: str = "en",
        endpointing_ms: int = 800,
        utterance_end_ms: int = 1000,
    ) -> None:
        self._client = AsyncDeepgramClient(api_key=api_key)
        self.model = model
        self.language = language
        self._endpointing_ms = endpointing_ms
        self._utterance_end_ms = utterance_end_ms

    async def transcribe(
        self, audio: AsyncIterator[bytes], keyterms: Sequence[str] = ()
    ) -> AsyncIterator[Heard]:
        async with self._client.listen.v1.connect(
            model=self.model,
            encoding="linear16",
            sample_rate=STT_SAMPLE_RATE,
            channels=1,
            language=self.language,
            punctuate=True,
            # Only nova-3 takes keyterms; nova-2 has a different mechanism and
            # rejects this one at the socket.
            keyterm=list(keyterms) if keyterms and self.model.startswith("nova-3") else None,
            # Deepgram decides when a turn has ended, so a live conversation
            # needs no push-to-talk. Interim results arrive first and are
            # shown as provisional, so the listener sees they are being heard.
            interim_results=True,
            endpointing=self._endpointing_ms,
            utterance_end_ms=self._utterance_end_ms,
            vad_events=True,
        ) as connection:
            pump = asyncio.create_task(self._pump(connection, audio))
            buffer = UtteranceBuffer()
            try:
                async for event in connection:
                    # Deepgram signals the end of speech separately from the
                    # end of a transcription fragment.
                    if type(event).__name__.endswith("UtteranceEnd"):
                        pending = buffer.flush()
                        if pending:
                            yield Heard(pending, final=True)
                        continue
                    utterance = buffer.take(event)
                    if utterance:
                        yield Heard(utterance, final=True)
                        continue
                    # Not a finished turn, but words worth showing while they
                    # are still being spoken.
                    interim = _transcript_of(event)
                    if interim and not getattr(event, "is_final", False):
                        yield Heard(" ".join([*buffer.parts, interim]).strip(), final=False)
            finally:
                # The socket is closing either way; make sure the feeding task
                # does not outlive it and write to a dead connection.
                pump.cancel()
                await asyncio.gather(pump, return_exceptions=True)

    @staticmethod
    async def _pump(connection: object, audio: AsyncIterator[bytes]) -> None:
        """Forward captured audio, keeping the socket alive through silence."""
        pending: asyncio.Task[bytes] | None = None
        iterator = audio.__aiter__()
        try:
            while True:
                if pending is None:
                    pending = asyncio.create_task(anext(iterator))  # type: ignore[arg-type]
                done, _ = await asyncio.wait({pending}, timeout=KEEPALIVE_INTERVAL_S)
                if pending not in done:
                    # Deepgram closes the socket with a 1011 if nothing arrives
                    # within its timeout window, and a listener who says nothing
                    # for a few seconds is a conversation, not a fault.
                    await connection.send_keep_alive()  # type: ignore[attr-defined]
                    continue
                try:
                    chunk = pending.result()
                except StopAsyncIteration:
                    break
                finally:
                    pending = None
                await connection.send_media(chunk)  # type: ignore[attr-defined]
        finally:
            if pending is not None:
                pending.cancel()
        await connection.send_close_stream()  # type: ignore[attr-defined]


class UtteranceBuffer:
    """Joins Deepgram's finalised fragments into whole utterances.

    Deepgram finalises several fragments within one sentence and marks the end
    of the sentence with ``speech_final``. Treating each fragment as a finished
    turn spawns overlapping replies that talk over each other, and over someone
    who is still speaking.
    """

    def __init__(self) -> None:
        self._parts: list[str] = []

    @property
    def parts(self) -> list[str]:
        """What has been finalised so far within the current utterance."""
        return self._parts

    def take(self, event: object) -> str | None:
        """Return a complete utterance, or None if more is still coming."""
        if not getattr(event, "is_final", False):
            return None

        text = _transcript_of(event)
        if text:
            self._parts.append(text)

        if not getattr(event, "speech_final", False):
            return None

        utterance = " ".join(self._parts).strip()
        self._parts.clear()
        return utterance or None

    def flush(self) -> str | None:
        """Return whatever has accumulated, for an utterance-end event."""
        utterance = " ".join(self._parts).strip()
        self._parts.clear()
        return utterance or None


def _transcript_of(event: object) -> str:
    """Pull the final transcript out of a Deepgram result, if it has one.

    The SDK returns generated model objects rather than plain dicts, and the
    shape differs between message types, so this reads defensively instead of
    asserting a structure.
    """
    channel = getattr(event, "channel", None)
    alternatives = getattr(channel, "alternatives", None) if channel else None
    if not alternatives:
        return ""
    transcript = getattr(alternatives[0], "transcript", "")
    return transcript.strip() if isinstance(transcript, str) else ""
