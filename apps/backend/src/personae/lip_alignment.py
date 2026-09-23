"""Optional audio analysis for timed mouth motion; buffers one phrase.

Rhubarb is an external executable, never downloaded or invoked by default.
Its mouth shapes are reduced to VRM vowel channels, not a full facial rig.
"""

import asyncio
import contextlib
import shutil
import tempfile
import wave
from collections.abc import AsyncGenerator, AsyncIterator
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from personae.providers.base import ProviderError, Speaker, TtsProvider
from personae.speech_events import SpeechChunk, VisemeCue

MAX_PCM = 24_000 * 2 * 30  # Thirty seconds per phrase; bounded independently of the model.


class _Mouth(BaseModel):
    start: float
    end: float
    value: Literal["A", "B", "C", "D", "E", "F", "G", "H", "X"]


class _Result(BaseModel):
    mouthCues: list[_Mouth] = Field(max_length=4096)  # noqa: N815 - vendor JSON


def parse_rhubarb(raw: object) -> tuple[VisemeCue, ...]:
    channels: dict[str, Literal["aa", "ih", "ou", "ee", "oh", "closed"]] = {
        "A": "closed",
        "B": "ih",
        "C": "ee",
        "D": "aa",
        "E": "oh",
        "F": "ou",
        "G": "ih",
        "H": "aa",
        "X": "closed",
    }
    return tuple(
        VisemeCue(start=cue.start, end=cue.end, value=channels[cue.value])
        for cue in _Result.model_validate(raw).mouthCues
    )


class Rhubarb:
    def __init__(self, executable: str, recognizer: str = "phonetic") -> None:
        resolved = shutil.which(executable)
        if resolved is None:
            raise ValueError("PERSONAE_RHUBARB_PATH must name an installed Rhubarb executable")
        self._executable = resolved
        self._recognizer = recognizer

    async def analyze(self, pcm: bytes, text: str) -> tuple[VisemeCue, ...]:
        with tempfile.TemporaryDirectory(prefix="personae-speech-") as directory:
            audio = Path(directory) / "speech.wav"
            dialog = Path(directory) / "dialog.txt"
            dialog.write_text(text, encoding="utf-8")
            with wave.open(str(audio), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(24_000)
                wav.writeframes(pcm)
            process = await asyncio.create_subprocess_exec(
                self._executable,
                "-r",
                self._recognizer,
                "-f",
                "json",
                "-q",
                "--dialogFile",
                str(dialog),
                str(audio),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                async with asyncio.timeout(30):
                    stdout, _ = await process.communicate()
                if process.returncode != 0:
                    raise ProviderError("Rhubarb could not analyze the speech")
                result = _Result.model_validate_json(stdout)
                return parse_rhubarb(result.model_dump())
            finally:
                if process.returncode is None:
                    with contextlib.suppress(ProcessLookupError):
                        process.kill()
                    await process.wait()


class AlignedSpeaker:
    def __init__(self, speaker: Speaker, analyzer: Rhubarb) -> None:
        self._speaker = speaker
        self._analyzer = analyzer

    async def say(self, text: str, rate: float | None = None) -> AsyncIterator[SpeechChunk]:
        pcm = bytearray()
        stream = self._speaker.say(text, rate)
        try:
            async for chunk in stream:
                pcm.extend(chunk if isinstance(chunk, bytes) else chunk.pcm)
                if len(pcm) > MAX_PCM:
                    raise ProviderError("Speech exceeds the 30-second alignment limit")
        finally:
            if isinstance(stream, AsyncGenerator):
                await stream.aclose()
        if not pcm:
            return
        cues = await self._analyzer.analyze(bytes(pcm), text)
        yield SpeechChunk(visemes=cues)
        # Keep transport frames small so interrupt handling remains responsive.
        for start in range(0, len(pcm), 4800):
            yield SpeechChunk(pcm=bytes(pcm[start : start + 4800]))

    async def close(self) -> None:
        await self._speaker.close()


class AlignedTts:
    def __init__(self, provider: TtsProvider, analyzer: Rhubarb) -> None:
        self._provider = provider
        self._analyzer = analyzer

    async def open(self, voice: str, rate: float = 1.0, expressivity: int | None = None) -> Speaker:
        return AlignedSpeaker(await self._provider.open(voice, rate, expressivity), self._analyzer)

    def synthesize(self, text: str, voice: str, rate: float = 1.0) -> AsyncIterator[bytes]:
        return self._provider.synthesize(text, voice, rate)
