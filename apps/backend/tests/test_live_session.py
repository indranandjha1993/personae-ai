"""Live sessions: continuous listening, barge-in, and remembered turns."""

import asyncio
from collections.abc import AsyncIterator, Sequence

from personae.conversation import Message
from personae.live import MAX_PENDING_AUDIO, LiveSession
from personae.packs.loader import load_packs
from personae.packs.models import Character
from personae.protocol import ServerMessage


def _character() -> Character:
    from personae.main import REPO_ROOT

    return load_packs([REPO_ROOT / "packs" / "bundled"]).get("bundled/seed")


class ScriptedStt:
    """Emits a transcript per utterance the caller feeds it."""

    def __init__(self, utterances: list[str]) -> None:
        self._utterances = utterances

    def transcribe(self, audio: AsyncIterator[bytes]) -> AsyncIterator[str]:
        async def run() -> AsyncIterator[str]:
            index = 0
            async for _ in audio:
                if index < len(self._utterances):
                    yield self._utterances[index]
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
