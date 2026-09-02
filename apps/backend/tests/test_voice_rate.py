"""A character's speaking rate must reach the synthesiser."""

from collections.abc import AsyncIterator, Sequence

import pytest

from personae.conversation import Message
from personae.live import LiveSession
from personae.packs.loader import load_packs
from personae.protocol import ServerMessage
from personae.providers.base import Heard


class RecordingTts:
    """Captures the arguments a session passes to synthesis."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, float]] = []

    def synthesize(self, text: str, voice: str, rate: float = 1.0) -> AsyncIterator[bytes]:
        self.calls.append((text, voice, rate))

        async def frames() -> AsyncIterator[bytes]:
            yield b"\x00\x00"

        return frames()


class StubStt:
    def transcribe(self, audio: AsyncIterator[bytes]) -> AsyncIterator[Heard]:
        async def once() -> AsyncIterator[Heard]:
            async for _ in audio:
                break
            yield Heard("hello", final=True)

        return once()


class StubLlm:
    def respond(
        self,
        system_prompt: str,
        transcript: str,
        history: Sequence[Message] = (),
        image: bytes | None = None,
    ) -> AsyncIterator[str]:
        async def once() -> AsyncIterator[str]:
            yield "a reply"

        return once()


@pytest.fixture
def characters() -> object:
    from personae.main import REPO_ROOT

    return load_packs([REPO_ROOT / "packs" / "bundled"])


async def test_each_character_speaks_at_its_own_rate(characters: object) -> None:
    """Characters declare distinct rates; a shared default flattens them."""
    tts = RecordingTts()
    character = characters.get("bundled/seed")  # type: ignore[attr-defined]
    session = LiveSession(character, StubStt(), StubLlm(), tts)
    await session.offer(b"\x10\x20" * 40)
    await session.close_input()
    async for _ in session.run():
        pass

    assert tts.calls, "synthesis was never called"
    _, voice, rate = tts.calls[0]
    assert voice == character.voice.provider_voice
    assert rate == character.voice.rate


def test_every_character_declares_a_voice_and_rate(characters: object) -> None:
    for cid in characters.ids():  # type: ignore[attr-defined]
        voice = characters.get(cid).voice  # type: ignore[attr-defined]
        assert voice.provider_voice
        assert voice.rate > 0


def test_server_message_types_are_stable() -> None:
    assert ServerMessage.ready(24000).model_dump()["type"] == "ready"
