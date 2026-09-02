"""
Silence must not end the session.

Deepgram closes an idle socket with a 1011, which used to propagate up and
kill the whole conversation the moment the user stopped talking for a moment.
"""

import asyncio
from collections.abc import AsyncIterator

import pytest

from personae.providers import deepgram
from personae.providers.deepgram import DeepgramStt


class RecordingConnection:
    """Stands in for the Deepgram socket, noting what it was sent."""

    def __init__(self) -> None:
        self.keep_alives = 0
        self.media: list[bytes] = []
        self.closed = False

    async def send_keep_alive(self) -> None:
        self.keep_alives += 1

    async def send_media(self, chunk: bytes) -> None:
        self.media.append(chunk)

    async def send_close_stream(self) -> None:
        self.closed = True


@pytest.mark.timeout(10)
async def test_silence_is_held_open_with_keep_alives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A speaker who pauses is having a conversation, not disconnecting."""
    # Scaled down so the test spends milliseconds, not seconds, in silence.
    monkeypatch.setattr(deepgram, "KEEPALIVE_INTERVAL_S", 0.02)
    connection = RecordingConnection()

    async def audio() -> AsyncIterator[bytes]:
        yield b"\x00\x01"
        # Long enough to cross several keepalive intervals.
        await asyncio.sleep(0.05)
        yield b"\x02\x03"

    await DeepgramStt._pump(connection, audio())

    assert connection.keep_alives >= 2, "silence must be filled with keepalives"
    assert connection.media == [b"\x00\x01", b"\x02\x03"]
    assert connection.closed, "the stream still closes once audio truly ends"


@pytest.mark.timeout(10)
async def test_continuous_audio_needs_no_keep_alive() -> None:
    """Keepalives are for gaps; a steady stream already holds the socket."""
    connection = RecordingConnection()

    async def audio() -> AsyncIterator[bytes]:
        for _ in range(3):
            yield b"\x00\x01"

    await DeepgramStt._pump(connection, audio())

    assert connection.keep_alives == 0
    assert len(connection.media) == 3
