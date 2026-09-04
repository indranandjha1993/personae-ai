"""Flux: Deepgram's voice-agent model line.

Flux detects the end of a turn itself, so the pipeline sees one finished
transcript per turn rather than a stream of fragments to reassemble.
"""

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any, ClassVar

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


class Connection:
    """Replays scripted turns and records the connect options that reached it."""

    def __init__(self, events: list[Turn]) -> None:
        self._events = events
        self.options: dict[str, object] = {}

    async def send_media(self, chunk: bytes) -> None:
        return None

    async def send_close_stream(self) -> None:
        return None

    def __aiter__(self) -> AsyncIterator[Turn]:
        async def gen() -> AsyncIterator[Turn]:
            for event in self._events:
                yield event

        return gen()


def _client_recording(connection: Connection) -> Any:
    import contextlib

    class Listen:
        class V2:
            @staticmethod
            @contextlib.asynccontextmanager
            async def connect(**options: object) -> AsyncIterator[Connection]:
                connection.options = options
                yield connection

        v2 = V2()

    class Client:
        listen = Listen()

    return Client()


@pytest.mark.timeout(10)
async def test_a_probable_ending_is_reported_and_may_be_retracted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Flux says 'probably done' before 'done'; both reach the session, as
    does the retraction when the speaker carries on."""
    connection = Connection(
        [
            Turn("Update", "Hello"),
            Turn("EagerEndOfTurn", "Hello there"),
            Turn("TurnResumed", "Hello there and"),
            Turn("EndOfTurn", "Hello there and goodbye"),
        ]
    )
    stt = FluxStt(api_key="x", eager_eot_threshold=0.4)
    monkeypatch.setattr(stt, "_client", _client_recording(connection))

    async def audio() -> AsyncIterator[bytes]:
        yield b"\x00\x01"

    heard = [item async for item in stt.transcribe(audio())]

    assert [(h.text, h.final, h.eager, h.resumed) for h in heard] == [
        ("Hello", False, False, False),
        ("Hello there", False, True, False),
        ("Hello there and", False, False, True),
        ("Hello there and goodbye", True, False, False),
    ]
    assert connection.options["eager_eot_threshold"] == 0.4


@pytest.mark.timeout(10)
async def test_eager_detection_is_left_off_unless_asked_for(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = Connection([Turn("EndOfTurn", "hi")])
    stt = FluxStt(api_key="x")
    monkeypatch.setattr(stt, "_client", _client_recording(connection))

    async def audio() -> AsyncIterator[bytes]:
        yield b"\x00\x01"

    [item async for item in stt.transcribe(audio())]
    assert connection.options.get("eager_eot_threshold") is None


class Event:
    """One control message off the synthesis socket."""

    def __init__(self, type: str, **fields: object) -> None:
        self.type = type
        for name, value in fields.items():
            setattr(self, name, value)


class SpeakConnection:
    """A synthesis socket that answers each Speak with a scripted turn.

    Audio for a sentence is its own bytes cut into pieces, so a test can tell
    which sentence a chunk belonged to.
    """

    def __init__(self, fail: bool = False) -> None:
        self.spoken: list[str] = []
        self.speeds: list[float | None] = []
        self.interrupts = 0
        self.closed = False
        self._fail = fail
        self._events: asyncio.Queue[Event | bytes] = asyncio.Queue()

    async def send_speak(self, message: Any) -> None:
        self.spoken.append(message.text)
        self._events.put_nowait(Event("SpeechStarted", speech_id="dg_sp_1"))
        if self._fail:
            self._events.put_nowait(Event("Error", code="DATA-0000", description="bad text"))
            return
        text = message.text.encode()
        for start in range(0, len(text), 4):
            self._events.put_nowait(text[start : start + 4])
        self._events.put_nowait(Event("Flushed", speech_id="dg_sp_1"))
        self._events.put_nowait(Event("SpeechMetadata", speech_id="dg_sp_1", audio_duration_ms=1))

    async def send_flush(self, message: Any = None) -> None:
        return None

    async def send_configure(self, message: Any) -> None:
        self.speeds.append(message.speed)

    async def send_interrupt(self, message: Any = None) -> None:
        self.interrupts += 1
        self._events.put_nowait(Event("SpeechInterrupted", audio_played_ms=0))

    async def send_close(self, message: Any = None) -> None:
        self.closed = True

    async def recv(self) -> Event | bytes:
        return await self._events.get()

    def __aiter__(self) -> AsyncIterator[Event | bytes]:
        async def gen() -> AsyncIterator[Event | bytes]:
            while True:
                yield await self._events.get()

        return gen()


def _speak_client(connection: SpeakConnection) -> Any:
    import contextlib

    class Speak:
        class V2:
            connects: ClassVar[int] = 0
            options: ClassVar[dict[str, object]] = {}

            @classmethod
            @contextlib.asynccontextmanager
            async def connect(cls, **options: object) -> AsyncIterator[SpeakConnection]:
                cls.connects += 1
                cls.options = options
                yield connection

        v2 = V2()

    class Client:
        speak = Speak()

    return Client()


async def _said(speaker: Any, text: str, rate: float | None = None) -> bytes:
    return b"".join([chunk async for chunk in speaker.say(text, rate)])


@pytest.mark.timeout(10)
async def test_one_connection_carries_every_sentence(monkeypatch: pytest.MonkeyPatch) -> None:
    """Connecting costs more than a sentence; it happens once per conversation."""
    connection = SpeakConnection()
    tts = FluxTts(api_key="x")
    client = _speak_client(connection)
    monkeypatch.setattr(tts, "_client", client)

    speaker = await tts.open("flux-haley-en", 1.04, expressivity=1)
    first = await _said(speaker, "Hello there.")
    second = await _said(speaker, "Nice to meet you.")
    await speaker.close()

    assert client.speak.v2.connects == 1
    assert first.strip() == b"Hello there."
    assert second.strip() == b"Nice to meet you.", "each sentence's audio stays its own"
    assert client.speak.v2.options["expressivity"] == 1
    assert client.speak.v2.options["speed"] == 1.05, "snapped to the Flux grid"


@pytest.mark.timeout(10)
async def test_a_sentence_cut_short_is_stopped_and_the_next_still_plays(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A barge-in abandons a sentence mid-stream. The socket is shared, so
    the tail of that sentence must be cleared before the next one starts."""
    connection = SpeakConnection()
    tts = FluxTts(api_key="x")
    monkeypatch.setattr(tts, "_client", _speak_client(connection))
    speaker = await tts.open("flux-haley-en", 1.0)

    heard = b""
    lines = speaker.say("A long sentence to be cut off.")
    async for chunk in lines:
        heard += chunk
        break
    # Leaving the loop does not close the generator; the session does this too.
    assert isinstance(lines, AsyncGenerator)
    await lines.aclose()

    assert heard, "some of it was heard"
    assert connection.interrupts == 1
    assert (await _said(speaker, "Next.")).strip() == b"Next.", "no leftover audio from before"


@pytest.mark.timeout(10)
async def test_the_pace_is_changed_on_the_open_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = SpeakConnection()
    tts = FluxTts(api_key="x")
    monkeypatch.setattr(tts, "_client", _speak_client(connection))
    speaker = await tts.open("flux-haley-en", 1.0)

    await _said(speaker, "Steady.")
    await _said(speaker, "Quicker!", rate=1.1)
    await _said(speaker, "Still quicker!", rate=1.1)
    await _said(speaker, "As you were.")
    await _said(speaker, "Steady again.", rate=1.0)

    # Configured on change only; a line with no rate leaves the pace alone.
    assert connection.speeds == [1.1, 1.0]


@pytest.mark.timeout(10)
async def test_a_synthesis_error_is_reported_as_a_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from personae.providers.base import ProviderError

    connection = SpeakConnection(fail=True)
    tts = FluxTts(api_key="x")
    monkeypatch.setattr(tts, "_client", _speak_client(connection))
    speaker = await tts.open("flux-haley-en", 1.0)

    with pytest.raises(ProviderError, match="bad text"):
        await _said(speaker, "Hello.")


@pytest.mark.timeout(10)
async def test_each_sentence_is_sent_visibly_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    """A sentence ending in a space is one the server can start on at once,
    rather than waiting for the Flush that follows it."""
    connection = SpeakConnection()
    tts = FluxTts(api_key="x")
    monkeypatch.setattr(tts, "_client", _speak_client(connection))
    speaker = await tts.open("flux-haley-en", 1.0)

    await _said(speaker, "Hello there.")

    assert connection.spoken == ["Hello there. "]


@pytest.mark.timeout(10)
async def test_keyterms_reach_the_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = Connection([Turn("EndOfTurn", "hey wren")])
    stt = FluxStt(api_key="x")
    monkeypatch.setattr(stt, "_client", _client_recording(connection))

    async def audio() -> AsyncIterator[bytes]:
        yield b"\x00\x01"

    [item async for item in stt.transcribe(audio(), ("Wren", "Seed"))]
    assert connection.options["keyterm"] == ["Wren", "Seed"]


@pytest.mark.timeout(10)
async def test_no_keyterms_sends_none_rather_than_an_empty_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = Connection([Turn("EndOfTurn", "hi")])
    stt = FluxStt(api_key="x")
    monkeypatch.setattr(stt, "_client", _client_recording(connection))

    async def audio() -> AsyncIterator[bytes]:
        yield b"\x00\x01"

    [item async for item in stt.transcribe(audio())]
    assert connection.options["keyterm"] is None


@pytest.mark.timeout(10)
async def test_a_quiet_turn_is_called_out(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A recogniser that hears nothing and one that is sent nothing look the
    same from outside; the log is what tells them apart."""
    import logging

    connection = Connection([Turn("EndOfTurn", "hello")])
    stt = FluxStt(api_key="x")
    monkeypatch.setattr(stt, "_client", _client_recording(connection))

    async def audio() -> AsyncIterator[bytes]:
        yield b"\x01\x00" * 800  # near-silence

    with caplog.at_level(logging.INFO, logger="personae.providers.flux"):
        [item async for item in stt.transcribe(audio())]

    assert any("very quiet" in record.message for record in caplog.records)
    assert any(record.message.startswith("turn:") for record in caplog.records)


class DroppingSpeakConnection(SpeakConnection):
    """A synthesis socket that has died since the last sentence."""

    def __init__(self) -> None:
        super().__init__()
        self.dead = True

    async def send_speak(self, message: Any) -> None:
        if self.dead:
            self.dead = False
            raise ConnectionError("no close frame received")
        await super().send_speak(message)


@pytest.mark.timeout(10)
async def test_a_dead_voice_socket_is_reopened_for_the_next_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An idle socket the server dropped is found out on the next sentence;
    it is reopened and the sentence still plays."""
    connection = DroppingSpeakConnection()
    tts = FluxTts(api_key="x")
    client = _speak_client(connection)
    monkeypatch.setattr(tts, "_client", client)
    speaker = await tts.open("flux-haley-en", 1.0)

    assert (await _said(speaker, "Still here.")).strip() == b"Still here."
    assert client.speak.v2.connects == 2
