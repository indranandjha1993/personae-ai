"""Ending a conversation the way people do."""

from personae.speech import farewell_marked, for_speech, strip_farewell


def test_recognises_the_marker_she_uses_to_say_goodbye() -> None:
    assert farewell_marked("Bye, take care. [end]")
    assert not farewell_marked("Bye for now, what else?")


def test_the_marker_is_never_spoken_or_shown() -> None:
    assert strip_farewell("Bye, take care. [end]") == "Bye, take care."
    assert "[end]" not in for_speech("Goodbye. [end]")


def test_the_marker_is_recognised_wherever_it_lands() -> None:
    # Models are inconsistent about trailing whitespace and case.
    for reply in ("Take care.[end]", "Take care. [END]", "Take care. [end] "):
        assert farewell_marked(reply)
        assert "[" not in strip_farewell(reply)


def test_ordinary_brackets_are_left_alone() -> None:
    text = "Use the flag [verbose] when you run it."
    assert not farewell_marked(text)
    assert strip_farewell(text) == text


def test_a_farewell_reply_still_reads_naturally() -> None:
    assert strip_farewell("Good luck with it. [end]") == "Good luck with it."
