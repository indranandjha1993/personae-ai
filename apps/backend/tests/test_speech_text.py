"""Text bound for a synthesiser has to be speakable."""

from personae.speech import for_speech


def test_strips_emoji_that_would_be_read_aloud() -> None:
    assert for_speech("I can respond warmly. 🙂") == "I can respond warmly."


def test_strips_markdown_emphasis() -> None:
    assert for_speech("That is **really** important") == "That is really important"
    assert for_speech("A _quiet_ point") == "A quiet point"


def test_removes_bullets_and_headings() -> None:
    assert for_speech("## Plan\n- first\n- second") == "Plan. first. second"


def test_reads_a_url_as_a_domain_rather_than_spelling_it() -> None:
    assert "https" not in for_speech("See https://example.com/docs for that")


def test_leaves_ordinary_speech_untouched() -> None:
    text = "Sure, I can do that. What are we building?"
    assert for_speech(text) == text


def test_keeps_pause_punctuation_the_voice_understands() -> None:
    # Deepgram renders an ellipsis as a thinking pause, so it must survive.
    assert "..." in for_speech("Well... maybe.")


def test_collapses_whitespace_left_behind() -> None:
    assert for_speech("one  \n\n  two") == "one two"
