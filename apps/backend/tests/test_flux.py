"""Flux: Deepgram's voice-agent model line.

Flux detects the end of a turn itself, so the pipeline sees one finished
transcript per turn rather than a stream of fragments to reassemble.
"""

from collections.abc import AsyncIterator
from typing import Any

import pytest

from personae.providers.factory import build_stt, build_tts
from personae.providers.flux import FluxStt, FluxTts, _supported_speed
from personae.settings import Settings


class Turn:
    """One event off the Flux socket."""

    def __init__(self, event: str, transcript: str) -> None:
        self.event = event
        self.transcript = transcript


class FakeConnection:
    """Replays a scripted turn, recording what was sent."""

    def __init__(self, events: list[Turn]) -> None:
        self._events = events
        self.media: list[bytes] = []
        self.closed = False

    async def send_media(self, chunk: bytes) -> None:
        self.media.append(chunk)

    async def send_close_stream(self) -> None:
        self.closed = True

    def __aiter__(self) -> AsyncIterator[Turn]:
        async def gen() -> AsyncIterator[Turn]:
            for event in self._events:
                yield event

        return gen()


@pytest.mark.timeout(10)
async def test_words_are_shown_while_still_being_spoken(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The listener should see themselves being heard as they talk.

    Interim updates are provisional and never answered, but showing them is
    what makes the conversation feel live rather than turn-based.
    """
    connection = FakeConnection(
        [
            Turn("StartOfTurn", "Hello"),
            Turn("Update", "Hello how"),
            Turn("EndOfTurn", "Hello, how are you?"),
        ]
    )
    stt = FluxStt(api_key="x")
    monkeypatch.setattr(stt, "_client", _client_yielding(connection))

    async def audio() -> AsyncIterator[bytes]:
        yield b"\x00\x01"

    heard = [item async for item in stt.transcribe(audio())]

    assert [(h.text, h.final) for h in heard] == [
        ("Hello", False),
        ("Hello how", False),
        ("Hello, how are you?", True),
    ]
    assert sum(1 for h in heard if h.final) == 1, "only one turn is answered"


@pytest.mark.timeout(10)
async def test_an_empty_turn_is_not_answered(monkeypatch: pytest.MonkeyPatch) -> None:
    """Silence ends a turn too; there is nothing to reply to."""
    connection = FakeConnection([Turn("EndOfTurn", "   ")])
    stt = FluxStt(api_key="x")
    monkeypatch.setattr(stt, "_client", _client_yielding(connection))

    async def audio() -> AsyncIterator[bytes]:
        yield b"\x00\x01"

    assert [item async for item in stt.transcribe(audio())] == []


def _client_yielding(connection: FakeConnection) -> Any:
    """A stand-in whose listen.v2.connect(...) hands back ``connection``."""
    import contextlib

    class Listen:
        class V2:
            @staticmethod
            @contextlib.asynccontextmanager
            async def connect(**_: object) -> AsyncIterator[FakeConnection]:
                yield connection

        v2 = V2()

    class Client:
        listen = Listen()

    return Client()


@pytest.mark.parametrize(
    ("requested", "expected"),
    [(1.04, 1.05), (1.0, 1.0), (0.5, 0.9), (3.0, 1.5), (1.23, 1.25)],
)
def test_the_speaking_rate_is_snapped_to_what_flux_accepts(
    requested: float, expected: float
) -> None:
    """Flux takes 0.05 steps and rejects anything else outright, so a pack's
    own rate must be rounded rather than allowed to fail mid-sentence."""
    assert _supported_speed(requested) == expected


def test_the_model_name_chooses_the_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Flux is a different endpoint, so switching is a matter of naming it."""
    monkeypatch.setenv("PERSONAE_DEEPGRAM_API_KEY", "x")
    monkeypatch.setenv("PERSONAE_STT_MODEL", "flux-general-en")
    monkeypatch.setenv("PERSONAE_TTS_VOICE", "flux-haley-en")

    assert isinstance(build_stt(Settings()), FluxStt)
    assert isinstance(build_tts(Settings()), FluxTts)


def test_the_nova_and_aura_clients_are_still_reachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Aura-2 remains the only way to speak anything but English."""
    from personae.providers.deepgram import DeepgramStt, DeepgramTts

    monkeypatch.setenv("PERSONAE_DEEPGRAM_API_KEY", "x")
    monkeypatch.setenv("PERSONAE_STT_MODEL", "nova-3")
    monkeypatch.setenv("PERSONAE_TTS_VOICE", "aura-2-thalia-en")

    assert isinstance(build_stt(Settings()), DeepgramStt)
    assert isinstance(build_tts(Settings()), DeepgramTts)
