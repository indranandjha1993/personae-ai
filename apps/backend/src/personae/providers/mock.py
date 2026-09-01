"""Credential-free provider implementations.

These are the default. They exist so the application runs, and the whole suite
passes, on a fresh clone with no API keys -- which is what makes the project
contributable. They are deliberately behavioural rather than empty: the mock
transcriber responds to audio level, and the mock synthesiser returns audio
proportional to its input, so the pipeline can be exercised end to end.
"""

import array
import asyncio
import math
from collections.abc import AsyncIterator

_SAMPLE_RATE = 24_000
_TONE_HZ = 220.0
_SILENCE_THRESHOLD = 12  # mean absolute sample value below which audio is silence


class MockStt:
    """Transcribes by measuring loudness rather than recognising speech."""

    def __init__(self, phrase: str = "this is a mock transcript") -> None:
        self._phrase = phrase

    async def transcribe(self, audio: AsyncIterator[bytes]) -> AsyncIterator[str]:
        async for chunk in audio:
            if _is_silence(chunk):
                continue
            await asyncio.sleep(0)
            yield self._phrase


class MockLlm:
    """Echoes the transcript back in fragments, as a streaming model would."""

    async def respond(self, system_prompt: str, transcript: str) -> AsyncIterator[str]:
        for fragment in (f'You said "{transcript}"', ", and I am a mock reply."):
            await asyncio.sleep(0)
            yield fragment


class MockTts:
    """Synthesises a tone whose length scales with the text."""

    def __init__(self, ms_per_character: int = 40) -> None:
        self._ms_per_character = ms_per_character

    async def synthesize(self, text: str, voice: str) -> AsyncIterator[bytes]:
        total_samples = int(_SAMPLE_RATE * self._ms_per_character * max(len(text), 1) / 1000)
        frame = _SAMPLE_RATE // 10  # 100 ms frames, as a live provider would stream
        for start in range(0, total_samples, frame):
            await asyncio.sleep(0)
            yield _tone(start, min(frame, total_samples - start))


def _is_silence(chunk: bytes) -> bool:
    if not chunk:
        return True
    samples = array.array("h")
    samples.frombytes(chunk[: len(chunk) - len(chunk) % 2])
    if not samples:
        return True
    return sum(abs(sample) for sample in samples) / len(samples) < _SILENCE_THRESHOLD


def _tone(start_sample: int, count: int) -> bytes:
    """Generate 16-bit PCM, phase-continuous across frames to avoid clicks."""
    samples = array.array(
        "h",
        (
            int(8000 * math.sin(2 * math.pi * _TONE_HZ * (start_sample + n) / _SAMPLE_RATE))
            for n in range(count)
        ),
    )
    return samples.tobytes()
