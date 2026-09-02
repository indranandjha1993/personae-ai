"""Transcript extraction, which is pure and testable without a connection.

The streaming paths in this provider need a live Deepgram socket and are
covered by manual verification rather than the suite; this is the logic that
can be pinned down here.
"""

from dataclasses import dataclass

from personae.providers.deepgram import _transcript_of


@dataclass
class Alternative:
    transcript: object


@dataclass
class Channel:
    alternatives: list[Alternative]


@dataclass
class Event:
    channel: object


def test_reads_the_first_alternative() -> None:
    event = Event(channel=Channel(alternatives=[Alternative(transcript="  hello  ")]))
    assert _transcript_of(event) == "hello"


def test_returns_empty_for_events_without_a_transcript() -> None:
    assert _transcript_of(Event(channel=Channel(alternatives=[]))) == ""
    assert _transcript_of(Event(channel=None)) == ""
    assert _transcript_of(object()) == ""


def test_ignores_a_non_string_transcript() -> None:
    """The SDK returns generated models, so the shape is not guaranteed."""
    event = Event(channel=Channel(alternatives=[Alternative(transcript=42)]))
    assert _transcript_of(event) == ""


@dataclass
class Result:
    channel: object
    is_final: bool = False
    speech_final: bool = False


def _words(text: str) -> Result:
    return Result(channel=Channel(alternatives=[Alternative(transcript=text)]))


def test_fragments_are_joined_into_one_utterance() -> None:
    """Deepgram finalises several fragments per sentence.

    Answering each one spawns overlapping replies that talk over each other and
    over the person still speaking.
    """
    from personae.providers.deepgram import UtteranceBuffer

    buffer = UtteranceBuffer()
    first = _words("what I wanted to ask")
    first.is_final = True
    assert buffer.take(first) is None

    second = _words("is whether this works")
    second.is_final = True
    second.speech_final = True
    assert buffer.take(second) == "what I wanted to ask is whether this works"


def test_the_buffer_empties_after_an_utterance() -> None:
    from personae.providers.deepgram import UtteranceBuffer

    buffer = UtteranceBuffer()
    done = _words("hello")
    done.is_final = True
    done.speech_final = True
    assert buffer.take(done) == "hello"

    again = _words("again")
    again.is_final = True
    again.speech_final = True
    assert buffer.take(again) == "again"


def test_interim_results_are_ignored() -> None:
    from personae.providers.deepgram import UtteranceBuffer

    assert UtteranceBuffer().take(_words("guess")) is None


def test_a_silent_utterance_yields_nothing() -> None:
    from personae.providers.deepgram import UtteranceBuffer

    buffer = UtteranceBuffer()
    empty = _words("")
    empty.is_final = True
    empty.speech_final = True
    assert buffer.take(empty) is None
