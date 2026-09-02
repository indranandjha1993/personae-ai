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


def test_the_persona_forbids_inventing_a_name_for_the_listener() -> None:
    """Speech recognition mishears words as names, and she picked one up."""
    from personae.main import REPO_ROOT
    from personae.packs.loader import load_packs

    prompt = load_packs([REPO_ROOT / "packs" / "bundled"]).get("bundled/seed").persona.prompt
    assert "never guess or invent one" in prompt.lower()


def test_the_marker_is_stripped_wherever_it_lands_in_a_stream() -> None:
    """Sentences are spoken as they arrive, so a marker in the middle of one
    would be read aloud."""
    assert "[end]" not in for_speech("Bye now. [end] Wait, one more thing.")
    assert "end" not in for_speech("Done. [END]").lower().replace("done", "")
