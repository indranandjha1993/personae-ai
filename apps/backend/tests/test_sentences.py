"""Splitting a reply as it streams, so speech can start before it ends."""

from personae.sentences import SentenceBuffer


def _feed(buffer: SentenceBuffer, *fragments: str) -> list[str]:
    out: list[str] = []
    for fragment in fragments:
        out.extend(buffer.feed(fragment))
    return out


def test_releases_a_sentence_as_soon_as_it_is_complete() -> None:
    buffer = SentenceBuffer()
    assert _feed(buffer, "Hello there. ", "How are") == ["Hello there."]


def test_holds_an_unfinished_sentence_back() -> None:
    buffer = SentenceBuffer()
    assert _feed(buffer, "I was thinking that") == []


def test_flush_gives_up_the_remainder() -> None:
    buffer = SentenceBuffer()
    _feed(buffer, "One. Two")
    assert buffer.flush() == "Two"


def test_the_first_release_comes_early_so_she_starts_sooner() -> None:
    """A long opening clause would otherwise leave her silent for its whole
    duration, which is the delay this exists to remove."""
    buffer = SentenceBuffer()
    released = _feed(buffer, "Right, so the thing about that particular problem is ")
    assert released == ["Right,"]


def test_later_clauses_are_not_split_on_commas() -> None:
    # Only the opening is split aggressively; after that, whole sentences.
    buffer = SentenceBuffer()
    _feed(buffer, "First. ")
    assert _feed(buffer, "Then, after a while, something else happened.") == [
        "Then, after a while, something else happened."
    ]


def test_handles_questions_and_exclamations() -> None:
    buffer = SentenceBuffer()
    assert _feed(buffer, "Really? ", "Yes! ") == ["Really?", "Yes!"]


def test_does_not_split_on_a_decimal_point() -> None:
    buffer = SentenceBuffer()
    assert _feed(buffer, "It costs 3.50 today. ") == ["It costs 3.50 today."]


def test_nothing_left_after_a_flush() -> None:
    buffer = SentenceBuffer()
    _feed(buffer, "Done.")
    buffer.flush()
    assert buffer.flush() == ""


def test_does_not_split_after_a_common_abbreviation() -> None:
    """Splitting on "Dr." makes her say the title, pause, then the name."""
    buffer = SentenceBuffer()
    assert _feed(buffer, "Dr. Smith called about it. ") == ["Dr. Smith called about it."]


def test_does_not_split_inside_an_ellipsis() -> None:
    # Deepgram renders an ellipsis as a thinking pause; breaking it loses that.
    buffer = SentenceBuffer()
    assert _feed(buffer, "Well... I suppose so. ") == ["Well... I suppose so."]


def test_does_not_split_after_a_single_initial() -> None:
    buffer = SentenceBuffer()
    assert _feed(buffer, "It was J. R. R. Tolkien. ") == ["It was J. R. R. Tolkien."]


def test_ellipsis_split_across_fragments_is_never_spoken_alone() -> None:
    """A dot run at the end of a fragment may be the head of an ellipsis."""
    buffer = SentenceBuffer()
    spoken: list[str] = []
    for fragment in ("Hmm.", "..", "maybe."):
        spoken.extend(buffer.feed(fragment))
    spoken.append(buffer.flush())

    assert [text for text in spoken if text] == ["Hmm.", "..maybe."]


def test_a_held_dot_run_is_still_released_at_the_end() -> None:
    """Whatever is held back must not be swallowed when the reply stops."""
    buffer = SentenceBuffer()
    spoken = list(buffer.feed("Trailing off.."))
    spoken.append(buffer.flush())

    assert "".join(spoken) == "Trailing off.."
