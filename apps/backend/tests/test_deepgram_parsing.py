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
class Interim:
    channel: object
    is_final: bool = False
    speech_final: bool = False


def test_only_finalised_events_count_as_transcripts() -> None:
    """Interim guesses change as you speak; answering one would be premature."""
    from personae.providers.deepgram import _is_final

    channel = Channel(alternatives=[Alternative(transcript="hello")])
    assert not _is_final(Interim(channel=channel))
    assert _is_final(Interim(channel=channel, is_final=True))
    assert _is_final(Interim(channel=channel, speech_final=True))
