"""Mock providers must be usable stand-ins, not empty stubs."""

from collections.abc import AsyncIterator

from personae.providers.base import LlmProvider, SttProvider, TtsProvider
from personae.providers.mock import MockLlm, MockStt, MockTts


async def _chunks(*items: bytes) -> AsyncIterator[bytes]:
    for item in items:
        yield item


async def test_mock_stt_emits_a_transcript() -> None:
    stt = MockStt()
    assert [text async for text in stt.transcribe(_chunks(b"\x00\x01"))]


async def test_mock_stt_output_reflects_input_volume() -> None:
    """Silence must not read as speech, or the pipeline cannot be exercised."""
    stt = MockStt()
    silent = [t async for t in stt.transcribe(_chunks(bytes(64)))]
    assert silent == []


async def test_mock_llm_streams_fragments_mentioning_the_transcript() -> None:
    llm = MockLlm()
    reply = "".join([part async for part in llm.respond("You are C.", "hello there")])
    assert "hello there" in reply


async def test_mock_tts_emits_audio_proportional_to_text() -> None:
    tts = MockTts()
    short = b"".join([c async for c in tts.synthesize("hi", "v")])
    long = b"".join([c async for c in tts.synthesize("hi there, friend", "v")])
    assert len(long) > len(short) > 0


async def test_mock_tts_emits_valid_pcm_frames() -> None:
    """Frames must be 16-bit aligned so the browser can play them directly."""
    tts = MockTts()
    audio = b"".join([c async for c in tts.synthesize("hello", "v")])
    assert len(audio) % 2 == 0


def test_mocks_satisfy_the_provider_protocols() -> None:
    assert isinstance(MockStt(), SttProvider)
    assert isinstance(MockLlm(), LlmProvider)
    assert isinstance(MockTts(), TtsProvider)
