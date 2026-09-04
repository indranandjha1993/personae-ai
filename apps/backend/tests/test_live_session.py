"""Live sessions: continuous listening, barge-in, and remembered turns."""

import asyncio
from collections.abc import AsyncIterator, Sequence

from personae.conversation import Message
from personae.live import MAX_PENDING_AUDIO, LiveSession
from personae.packs.loader import load_packs
from personae.packs.models import Character
from personae.protocol import ServerMessage
from personae.providers.base import Heard, Speaker, SynthesizingSpeaker


def _character() -> Character:
    from personae.main import REPO_ROOT

    return load_packs([REPO_ROOT / "packs" / "bundled"]).get("bundled/seed")


class ScriptedStt:
    """Emits a transcript per utterance the caller feeds it."""

    def __init__(self, utterances: list[str]) -> None:
        self._utterances = utterances

    def transcribe(
        self, audio: AsyncIterator[bytes], keyterms: Sequence[str] = ()
    ) -> AsyncIterator[Heard]:
        async def run() -> AsyncIterator[Heard]:
            index = 0
            async for _ in audio:
                if index < len(self._utterances):
                    yield Heard(self._utterances[index], final=True)
                    index += 1

        return run()


class SlowLlm:
    """Streams slowly, so a barge-in can land mid-reply."""

    def __init__(self, fragments: list[str], delay: float = 0.05) -> None:
        self.fragments = fragments
        self.delay = delay
        self.seen_history: list[Sequence[Message]] = []
        self.seen_images: list[bytes | None] = []
        self.seen_prompts: list[str] = []

    def respond(
        self,
        system_prompt: str,
        transcript: str,
        history: Sequence[Message] = (),
        image: bytes | None = None,
    ) -> AsyncIterator[str]:
        self.seen_history.append(list(history))
        self.seen_images.append(image)
        self.seen_prompts.append(system_prompt)

        async def run() -> AsyncIterator[str]:
            for fragment in self.fragments:
                await asyncio.sleep(self.delay)
                yield fragment

        return run()


class SilentTts:
    async def open(self, voice: str, rate: float = 1.0, expressivity: int | None = None) -> Speaker:
        return SynthesizingSpeaker(self.synthesize, voice, rate)

    def synthesize(self, text: str, voice: str, rate: float = 1.0) -> AsyncIterator[bytes]:
        async def run() -> AsyncIterator[bytes]:
            for _ in range(10):
                await asyncio.sleep(0.02)
                yield b"\x00\x00"

        return run()


async def _drain(session: LiveSession, limit: int = 60) -> list[ServerMessage]:
    out: list[ServerMessage] = []
    async for message in session.run():
        out.append(message)
        if len(out) >= limit:
            break
    return out


async def test_answers_an_utterance_without_an_explicit_stop() -> None:
    """Live mode ends a turn on silence, not on a button."""
    session = LiveSession(
        _character(), ScriptedStt(["hello"]), SlowLlm(["hi ", "there"], 0.0), SilentTts()
    )
    await session.offer(b"\x10\x20" * 40)
    await session.close_input()
    kinds = [m.model_dump()["type"] for m in await _drain(session)]
    assert "transcript" in kinds
    assert "reply" in kinds
    assert "audio" in kinds


async def test_barge_in_stops_the_reply_in_flight() -> None:
    llm = SlowLlm(["one ", "two ", "three ", "four ", "five"], 0.05)
    session = LiveSession(_character(), ScriptedStt(["hello"]), llm, SilentTts())
    await session.offer(b"\x10\x20" * 40)

    async def interrupt() -> None:
        await asyncio.sleep(0.06)
        await session.interrupt()
        await session.close_input()

    # Referenced so it cannot be collected mid-flight.
    task = asyncio.create_task(interrupt())
    messages = await _drain(session)
    await task
    kinds = [m.model_dump()["type"] for m in messages]
    assert "interrupted" in kinds, kinds


async def test_an_interrupted_reply_is_remembered_as_spoken() -> None:
    """Her next answer must not reference words the listener never heard."""
    llm = SlowLlm(["the first part ", "the second part"], 0.05)
    session = LiveSession(_character(), ScriptedStt(["a", "b"]), llm, SilentTts())
    await session.offer(b"\x10\x20" * 40)

    async def interrupt_then_speak() -> None:
        await asyncio.sleep(0.06)
        await session.interrupt()
        await session.offer(b"\x30\x40" * 40)
        await asyncio.sleep(0.2)
        await session.close_input()

    task = asyncio.create_task(interrupt_then_speak())
    await _drain(session)
    await task

    assert len(llm.seen_history) >= 2, "the second turn never ran"
    remembered = "".join(m["content"] for m in llm.seen_history[1])
    assert "the first part" in remembered
    assert "the second part" not in remembered


async def test_a_camera_frame_reaches_the_model() -> None:
    llm = SlowLlm(["looking"], 0.0)
    session = LiveSession(_character(), ScriptedStt(["what is this"]), llm, SilentTts())
    session.see(b"\xff\xd8jpeg")
    await session.offer(b"\x10\x20" * 40)
    await session.close_input()
    await _drain(session)
    assert llm.seen_images == [b"\xff\xd8jpeg"]


async def test_a_frame_is_used_once_and_not_repeated() -> None:
    """A still from a minute ago no longer shows what the camera sees."""
    llm = SlowLlm(["ok"], 0.0)
    session = LiveSession(_character(), ScriptedStt(["a", "b"]), llm, SilentTts())
    session.see(b"\xff\xd8jpeg")
    await session.offer(b"\x10\x20" * 40)
    await session.offer(b"\x30\x40" * 40)
    await session.close_input()
    await _drain(session)
    assert llm.seen_images == [b"\xff\xd8jpeg", None]


async def test_audio_backlog_is_bounded() -> None:
    """A client that outruns transcription must not grow memory without limit.

    Dropping stale microphone audio is acceptable; blocking the reader that
    also carries interrupts is not.
    """
    session = LiveSession(_character(), ScriptedStt([]), SlowLlm([], 0.0), SilentTts())
    for _ in range(500):
        await session.offer(b"\x10\x20" * 800)
    assert session.backlog() <= MAX_PENDING_AUDIO


async def test_she_is_told_when_she_can_see() -> None:
    """Without this she denies having a camera even while one is attached."""
    llm = SlowLlm(["ok"], 0.0)
    session = LiveSession(_character(), ScriptedStt(["what is this"]), llm, SilentTts())
    session.see(b"\xff\xd8jpeg")
    await session.offer(b"\x10\x20" * 40)
    await session.close_input()
    await _drain(session)
    assert "you can see the person" in llm.seen_prompts[0].lower()


async def test_she_is_not_told_she_can_see_when_no_frame_arrived() -> None:
    llm = SlowLlm(["ok"], 0.0)
    session = LiveSession(_character(), ScriptedStt(["hello"]), llm, SilentTts())
    await session.offer(b"\x10\x20" * 40)
    await session.close_input()
    await _drain(session)
    assert "you can see the person" not in llm.seen_prompts[0].lower()


async def test_she_can_end_the_conversation_after_speaking() -> None:
    """A goodbye should close the call, but only once she has finished saying it."""
    llm = SlowLlm(["Bye, take care. [end]"], 0.0)
    session = LiveSession(_character(), ScriptedStt(["bye"]), llm, SilentTts())
    await session.offer(b"\x10\x20" * 40)
    await session.close_input()

    kinds = [m.model_dump()["type"] async for m in session.run()]
    assert kinds[-1] == "farewell", kinds
    # The last audio must precede it, or she is cut off mid-word.
    assert kinds.index("audio") < kinds.index("farewell")


async def test_the_marker_never_reaches_the_listener() -> None:
    llm = SlowLlm(["Goodbye. [end]"], 0.0)
    session = LiveSession(_character(), ScriptedStt(["bye"]), llm, SilentTts())
    await session.offer(b"\x10\x20" * 40)
    await session.close_input()

    replies = [m.model_dump() async for m in session.run() if m.model_dump()["type"] == "reply"]
    assert replies[0]["text"] == "Goodbye."


async def test_an_ordinary_reply_does_not_end_the_conversation() -> None:
    llm = SlowLlm(["What else can I help with?"], 0.0)
    session = LiveSession(_character(), ScriptedStt(["hello"]), llm, SilentTts())
    await session.offer(b"\x10\x20" * 40)
    await session.close_input()

    kinds = [m.model_dump()["type"] async for m in session.run()]
    assert "farewell" not in kinds


async def test_audio_starts_before_the_reply_is_finished() -> None:
    """The whole point: she should be speaking the first sentence while the
    model is still writing the second."""
    llm = SlowLlm(["First thought here. ", "Second thought here."], 0.08)
    session = LiveSession(_character(), ScriptedStt(["hello"]), llm, SilentTts())
    await session.offer(b"\x10\x20" * 40)
    await session.close_input()

    kinds = [m.model_dump()["type"] async for m in session.run()]
    # Audio must appear before the final reply text, not after it.
    assert "audio" in kinds
    assert kinds.index("audio") < kinds.index("reply"), kinds


async def test_every_sentence_is_spoken() -> None:
    spoken: list[str] = []

    class RecordingTts:
        async def open(
            self, voice: str, rate: float = 1.0, expressivity: int | None = None
        ) -> Speaker:
            return SynthesizingSpeaker(self.synthesize, voice, rate)

        def synthesize(self, text: str, voice: str, rate: float = 1.0) -> AsyncIterator[bytes]:
            spoken.append(text)

            async def frames() -> AsyncIterator[bytes]:
                yield b"\x00\x00"

            return frames()

    llm = SlowLlm(["One thing. ", "Then another."], 0.0)
    session = LiveSession(_character(), ScriptedStt(["hi"]), llm, RecordingTts())
    await session.offer(b"\x10\x20" * 40)
    await session.close_input()
    await _drain(session)

    assert "".join(spoken).replace(" ", "") == "Onething.Thenanother."


async def test_each_sentence_is_announced_before_its_audio() -> None:
    """The caption should follow her voice, so the client needs to know which
    sentence is being spoken as it is spoken."""
    llm = SlowLlm(["First thought. ", "Second thought."], 0.0)
    session = LiveSession(_character(), ScriptedStt(["hi"]), llm, SilentTts())
    await session.offer(b"\x10\x20" * 40)
    await session.close_input()

    messages = [m.model_dump() async for m in session.run()]
    spoken = [m["text"] for m in messages if m["type"] == "speaking"]
    assert spoken == ["First thought.", "Second thought."]

    # Each announcement must precede the audio it describes.
    kinds = [m["type"] for m in messages]
    assert kinds.index("speaking") < kinds.index("audio")


async def test_the_farewell_marker_is_never_announced() -> None:
    llm = SlowLlm(["Goodbye. [end]"], 0.0)
    session = LiveSession(_character(), ScriptedStt(["bye"]), llm, SilentTts())
    await session.offer(b"\x10\x20" * 40)
    await session.close_input()

    spoken = [
        m.model_dump()["text"] async for m in session.run() if m.model_dump()["type"] == "speaking"
    ]
    assert all("[end]" not in text for text in spoken)


class BlindSpotLlm:
    """Streams nothing when given a picture, and text when not.

    Some endpoints accept an image, report output tokens, and then stream no
    content at all; she must not be struck dumb by that.
    """

    def __init__(self) -> None:
        self.calls: list[bytes | None] = []

    def respond(
        self,
        system_prompt: str,
        transcript: str,
        history: Sequence[Message] = (),
        image: bytes | None = None,
    ) -> AsyncIterator[str]:
        self.calls.append(image)
        fragments = [] if image is not None else ["I can hear ", "you fine."]

        async def run() -> AsyncIterator[str]:
            for fragment in fragments:
                yield fragment

        return run()


async def test_she_still_answers_when_vision_returns_nothing() -> None:
    """Losing her sight for a turn beats losing her voice."""
    llm = BlindSpotLlm()
    session = LiveSession(_character(), ScriptedStt(["hello"]), llm, SilentTts())
    session.see(b"\xff\xd8jpeg")
    await session.offer(b"\x10\x20" * 40)
    await session.close_input()

    messages = await _drain(session)
    kinds = [m.model_dump()["type"] for m in messages]
    replies = [m.model_dump()["text"] for m in messages if m.model_dump()["type"] == "reply"]

    assert llm.calls == [b"\xff\xd8jpeg", None], "the turn is retried without the picture"
    assert "audio" in kinds, "she speaks on the retry"
    assert replies == ["I can hear you fine."]


class MuteLlm:
    """Never streams anything, picture or not."""

    def respond(
        self,
        system_prompt: str,
        transcript: str,
        history: Sequence[Message] = (),
        image: bytes | None = None,
    ) -> AsyncIterator[str]:
        async def run() -> AsyncIterator[str]:
            nothing: tuple[str, ...] = ()
            for fragment in nothing:
                yield fragment

        return run()


async def test_a_reply_with_no_words_is_reported() -> None:
    """A silent success reads as the app having died; say so instead."""
    session = LiveSession(_character(), ScriptedStt(["hello"]), MuteLlm(), SilentTts())
    await session.offer(b"\x10\x20" * 40)
    await session.close_input()

    messages = [m.model_dump() for m in await _drain(session)]
    assert any(m["type"] == "error" for m in messages)
    assert not any(m["type"] == "reply" for m in messages)


class HeardStt:
    """Replays scripted recogniser events, one per audio frame offered."""

    def __init__(self, events: list[Heard], on_start: object = None, gap: float = 0.01) -> None:
        self._events = events
        self._on_start = on_start
        self._gap = gap

    def transcribe(
        self, audio: AsyncIterator[bytes], keyterms: Sequence[str] = ()
    ) -> AsyncIterator[Heard]:
        async def run() -> AsyncIterator[Heard]:
            # A real socket takes a moment to connect and spaces its events
            # out in time; without the yields here nothing else gets to run.
            await asyncio.sleep(0)
            if callable(self._on_start):
                self._on_start()
            index = 0
            async for _ in audio:
                if index < len(self._events):
                    yield self._events[index]
                    index += 1
                    await asyncio.sleep(self._gap)

        return run()


class EchoLlm:
    """Answers with the words it was given, so the reply names its transcript."""

    def __init__(self, delay: float = 0.0) -> None:
        self.delay = delay
        self.transcripts: list[str] = []

    def respond(
        self,
        system_prompt: str,
        transcript: str,
        history: Sequence[Message] = (),
        image: bytes | None = None,
    ) -> AsyncIterator[str]:
        self.transcripts.append(transcript)

        async def run() -> AsyncIterator[str]:
            await asyncio.sleep(self.delay)
            yield f"You said {transcript}."

        return run()


class CountingTts:
    """Counts connections and records every line said through them."""

    def __init__(self) -> None:
        self.opened = 0
        self.said: list[tuple[str, float | None]] = []

    async def open(self, voice: str, rate: float = 1.0, expressivity: int | None = None) -> Speaker:
        self.opened += 1
        recorder = self

        class Held:
            def say(self, text: str, rate: float | None = None) -> AsyncIterator[bytes]:
                recorder.said.append((text, rate))

                async def frames() -> AsyncIterator[bytes]:
                    yield b"\x00\x00"

                return frames()

            async def close(self) -> None:
                return None

        return Held()

    def synthesize(self, text: str, voice: str, rate: float = 1.0) -> AsyncIterator[bytes]:
        async def frames() -> AsyncIterator[bytes]:
            yield b"\x00\x00"

        return frames()


async def _offer_turns(session: LiveSession, turns: int) -> None:
    for _ in range(turns):
        await session.offer(b"\x10\x20" * 40)
    await session.close_input()


async def test_a_reply_drafted_on_a_probable_ending_is_sent_once_confirmed() -> None:
    """The recogniser is fairly sure a beat before it is certain; answering
    from that moment is where the last few hundred milliseconds go."""
    llm = EchoLlm()
    stt = HeardStt([Heard("hello", final=False, eager=True), Heard("hello", final=True)])
    session = LiveSession(_character(), stt, llm, SilentTts())
    await _offer_turns(session, 2)

    messages = [m.model_dump() for m in await _drain(session)]
    kinds = [m["type"] for m in messages]

    assert llm.transcripts == ["hello"], "one answer, not one per signal"
    # Nothing of the reply leaves before the turn is confirmed.
    assert kinds.index("transcript") < kinds.index("audio")
    assert [m["text"] for m in messages if m["type"] == "reply"] == ["You said hello."]


async def test_a_draft_is_dropped_when_the_speaker_carries_on() -> None:
    """A retracted ending means the draft answered half a sentence."""
    llm = EchoLlm(delay=0.05)
    stt = HeardStt(
        [
            Heard("hello", final=False, eager=True),
            Heard("hello and", final=False, resumed=True),
            Heard("hello and goodbye", final=True),
        ]
    )
    session = LiveSession(_character(), stt, llm, SilentTts())
    await _offer_turns(session, 3)

    messages = [m.model_dump() for m in await _drain(session)]
    replies = [m["text"] for m in messages if m["type"] == "reply"]

    assert replies == ["You said hello and goodbye."]
    assert "hello" in llm.transcripts, "the draft was attempted"


async def test_the_voice_is_connected_once_for_the_whole_conversation() -> None:
    """Connecting costs more than a sentence does; it happens once."""
    tts = CountingTts()
    llm = SlowLlm(["One thing. ", "Then another."], 0.0)
    session = LiveSession(_character(), ScriptedStt(["a", "b"]), llm, tts)
    await _offer_turns(session, 2)
    await _drain(session)

    assert tts.opened == 1
    assert len(tts.said) == 4, "two sentences per turn, two turns"


async def test_the_voice_is_connecting_before_anyone_speaks() -> None:
    """Paid while the listener is still saying hello, not inside the answer."""
    tts = CountingTts()
    seen_at_start: list[int] = []
    stt = HeardStt([Heard("hi", final=True)], on_start=lambda: seen_at_start.append(tts.opened))
    session = LiveSession(_character(), stt, SlowLlm(["ok"], 0.0), tts)
    await _offer_turns(session, 1)
    await _drain(session)

    assert seen_at_start == [1]


async def test_her_pace_quickens_when_she_is_amused() -> None:
    tts = CountingTts()
    llm = SlowLlm(["Ha! That is a good joke."], 0.0)
    session = LiveSession(_character(), ScriptedStt(["hi"]), llm, tts)
    await _offer_turns(session, 1)
    await _drain(session)

    rates = [rate for _, rate in tts.said]
    assert len(rates) == 2, "'Ha!' and the sentence after it"
    # The opening line never changes pace: nothing is playing yet to hide
    # the cost of the change behind.
    assert rates[0] is None
    assert rates[1] is not None
    assert rates[1] > _character().voice.rate


async def test_the_hands_rest_between_guessed_gestures() -> None:
    """Gesturing on every line reads as a puppet; the guessed ones alternate."""
    # No comma in the opening line: the splitter would release the clause
    # before it on its own, and the count of sentences is the point here.
    llm = SlowLlm(
        [
            "Loud and clear the engine is warm today. ",
            "Another thought about the engine follows. ",
            "The third one about the engine lands quietly.",
        ],
        0.0,
    )
    session = LiveSession(_character(), ScriptedStt(["hi"]), llm, SilentTts())
    await _offer_turns(session, 1)

    cues = [m.model_dump() async for m in session.run()]
    gestures = [m["gesture"] for m in cues if m["type"] == "expression"]
    assert gestures[0] != "idle"
    assert gestures[1] == "idle"
    assert gestures[2] != "idle"


async def test_the_hands_rest_after_a_gesture_she_chose() -> None:
    llm = SlowLlm(
        [
            "Loud and clear the engine is warm today. ",
            "*shrug* Honestly I do not know about it at all. ",
            "The third one about the engine lands quietly.",
        ],
        0.0,
    )
    session = LiveSession(_character(), ScriptedStt(["hi"]), llm, SilentTts())
    await _offer_turns(session, 1)

    cues = [m.model_dump() async for m in session.run()]
    gestures = [m["gesture"] for m in cues if m["type"] == "expression"]
    assert gestures == [gestures[0], "gesture-shrug", "idle"]
    assert gestures[0] != "idle"


async def test_she_is_told_when_the_camera_is_off() -> None:
    """Told nothing, she guesses; told plainly, she says so."""
    llm = SlowLlm(["ok"], 0.0)
    session = LiveSession(_character(), ScriptedStt(["hello"]), llm, SilentTts())
    await _offer_turns(session, 1)
    await _drain(session)
    assert "camera is off" in llm.seen_prompts[0].lower()


async def test_the_recogniser_is_told_her_name() -> None:
    """A general model hears "Wren" as "Ren" or "Ryan" until told to expect it."""
    told: list[Sequence[str]] = []

    class NotingStt:
        def transcribe(
            self, audio: AsyncIterator[bytes], keyterms: Sequence[str] = ()
        ) -> AsyncIterator[Heard]:
            told.append(tuple(keyterms))
            return ScriptedStt([]).transcribe(audio)

    session = LiveSession(_character(), NotingStt(), SlowLlm([], 0.0), SilentTts())
    await _offer_turns(session, 1)
    await _drain(session)

    assert told == [("Wren", "Seed")]


async def test_speaking_over_her_stops_the_reply() -> None:
    """The recogniser is the barge-in signal: words arriving while she talks
    are the listener talking, and she stops without the client's help."""
    llm = EchoLlm(delay=0.05)
    stt = HeardStt(
        [
            Heard("hello", final=True),
            Heard("wait a", final=False),
            Heard("wait a moment", final=True),
        ]
    )
    session = LiveSession(_character(), stt, llm, SilentTts())
    await _offer_turns(session, 3)

    messages = [m.model_dump() for m in await _drain(session, limit=200)]
    kinds = [m["type"] for m in messages]

    assert kinds.count("interrupted") == 1
    assert kinds.index("interrupted") < kinds.index("reply"), "the first reply was cut off"
    # What was said over her is answered once she has stopped.
    assert [m["text"] for m in messages if m["type"] == "transcript"] == ["hello", "wait a moment"]
    assert [m["text"] for m in messages if m["type"] == "reply"] == ["You said wait a moment."]


async def test_her_own_voice_coming_back_does_not_stop_her() -> None:
    """Without echo cancellation her words reach the microphone. A fragment
    made only of words she has just said is taken to be her, not the listener."""
    llm = EchoLlm(delay=0.05)
    # The echo arrives while she is speaking, which is the only time it can.
    stt = HeardStt([Heard("hello", final=True), Heard("you said hello", final=False)], gap=0.12)
    session = LiveSession(_character(), stt, llm, SilentTts())
    await _offer_turns(session, 2)

    kinds = [m.model_dump()["type"] for m in await _drain(session, limit=200)]
    assert "interrupted" not in kinds
    assert "reply" in kinds


class FlakyStt:
    """A recogniser whose socket dies once, then works."""

    def __init__(self) -> None:
        self.connections = 0

    def transcribe(
        self, audio: AsyncIterator[bytes], keyterms: Sequence[str] = ()
    ) -> AsyncIterator[Heard]:
        self.connections += 1
        attempt = self.connections

        async def run() -> AsyncIterator[Heard]:
            async for _ in audio:
                if attempt == 1:
                    raise RuntimeError("keepalive ping timeout")
                yield Heard("hello", final=True)

        return run()


async def test_a_dropped_recogniser_is_reconnected_not_fatal() -> None:
    """A socket that dies ends a moment of listening, not the conversation."""
    from personae import live

    setattr(live, "RECONNECT_DELAY_S", 0.01)  # noqa: B010 - module constant, for speed
    stt = FlakyStt()
    session = LiveSession(_character(), stt, SlowLlm(["ok"], 0.0), SilentTts())
    await _offer_turns(session, 2)

    kinds = [m.model_dump()["type"] for m in await _drain(session)]

    assert stt.connections == 2
    assert "error" not in kinds
    assert "reply" in kinds


async def test_a_recogniser_that_keeps_dying_is_reported() -> None:
    from personae import live

    setattr(live, "RECONNECT_DELAY_S", 0.01)  # noqa: B010 - module constant, for speed

    class DeadStt:
        def transcribe(
            self, audio: AsyncIterator[bytes], keyterms: Sequence[str] = ()
        ) -> AsyncIterator[Heard]:
            async def run() -> AsyncIterator[Heard]:
                async for _ in audio:
                    raise RuntimeError("gone")
                yield Heard("", final=True)  # pragma: no cover - makes this a generator

            return run()

    session = LiveSession(_character(), DeadStt(), SlowLlm(["ok"], 0.0), SilentTts())
    await _offer_turns(session, 10)

    kinds = [m.model_dump()["type"] for m in await _drain(session)]
    assert kinds[-1] == "error"


def test_echo_is_her_words_and_only_her_words() -> None:
    from personae.live import is_echo

    spoken = "You said hello. What are we untangling today?"
    assert is_echo("you said hello", spoken)
    assert is_echo("What are we", spoken)
    assert not is_echo("wait a moment", spoken)
    assert not is_echo("hello wait", spoken)
    assert not is_echo("", spoken)
