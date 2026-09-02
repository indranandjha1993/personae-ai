"""Expression inference must produce varied, always-valid cues."""

from personae.expression import infer
from personae.packs.loader import load_packs
from personae.packs.models import Character

SEED = "bundled/seed"


def _character() -> Character:
    from personae.main import REPO_ROOT

    return load_packs([REPO_ROOT / "packs" / "bundled"]).get(SEED)


def test_always_returns_values_from_the_character_vocabulary() -> None:
    character = _character()
    samples = [
        "Loud and clear. I'm here, prototype engine warm.",
        "Ha! That's the funniest requirement I've read all week.",
        "Because the bridge translates vague requests into actions.",
        "No. Stop. That approach will not survive contact with users.",
        "",
        "...",
    ]
    for text in samples:
        gesture, emotion = infer(text, character)
        assert gesture in character.expression.gestures, text
        assert emotion in character.expression.emotions, text


def test_a_question_reads_as_engaged_rather_than_resting() -> None:
    """Real replies rarely contain keyword hints, so punctuation carries signal."""
    character = _character()
    gesture, _ = infer("So what are you actually trying to build here?", character)
    assert gesture != character.expression.gestures[0]


def test_an_exclamation_is_not_the_resting_emotion() -> None:
    character = _character()
    _, emotion = infer("Ha! Brilliant.", character)
    assert emotion != character.expression.emotions[0]


def test_varied_replies_do_not_all_collapse_to_one_cue() -> None:
    """The failure this guards against is every reply looking identical."""
    character = _character()
    replies = [
        "Loud and clear, the engine is warm.",
        "Why would you route it through there?",
        "Ha! No chance.",
        "Because the translation layer already handles that case.",
        "Look at this part here.",
    ]
    gestures = {infer(text, character)[0] for text in replies}
    assert len(gestures) > 1


def test_an_ordinary_reply_without_keywords_still_animates() -> None:
    """Regression: a real model reply left the avatar on the resting pair.

    Observed in the browser -- the reply contained none of the keyword hints,
    so both cues fell back and the avatar never moved.
    """
    character = _character()
    reply = (
        "Loud and clear. I'm here-prototype engine warm, metaphorical coffee "
        "dangerously overclocked."
    )
    gesture, emotion = infer(reply, character)
    assert gesture != character.expression.gestures[0]
    assert emotion != character.expression.emotions[0]


def test_a_terse_reply_stays_at_rest() -> None:
    """Not every line should animate; brevity is its own signal."""
    character = _character()
    assert infer("Fine.", character) == (
        character.expression.gestures[0],
        character.expression.emotions[0],
    )


def test_hints_match_whole_words_only() -> None:
    """Substring matching read 'ha' inside 'what' and 'changed', so she was
    amused by ordinary statements."""
    character = _character()
    for text in (
        "What has changed?",
        "I changed the handler.",
        "Perhaps we should also refactor that.",
    ):
        _, emotion = infer(text, character)
        assert emotion != "amused", text


def test_a_real_laugh_still_reads_as_amused() -> None:
    character = _character()
    assert infer("Ha! That is a good joke.", character)[1] == "amused"
