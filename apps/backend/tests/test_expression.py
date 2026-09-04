"""Expression inference must produce varied, always-valid cues."""

from personae.expression import infer, pace
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


LONG = "Another thought about the engine follows on from the last one."


def test_guessed_gestures_come_every_other_sentence() -> None:
    """People gesture on the clause that carries the weight, not on every line."""
    character = _character()
    rest = character.expression.gestures[0]
    assert infer(LONG, character, beat=0)[0] != rest
    assert infer(LONG, character, beat=1)[0] == rest
    assert infer(LONG, character, beat=2)[0] != rest


def test_a_keyword_gesture_is_not_rationed() -> None:
    """A goodbye waves whichever sentence it lands on."""
    character = _character()
    assert infer("Goodbye then, see you soon.", character, beat=1)[0] == "gesture-wave"


def test_the_hands_rest_after_a_gesture_she_chose() -> None:
    character = _character()
    rest = character.expression.gestures[0]
    assert infer(LONG, character, beat=2, after_mark=True)[0] == rest


def test_a_chosen_gesture_colours_the_mood() -> None:
    """A shrug is not a neutral face; the gesture says what the words do not."""
    character = _character()
    assert infer("I really do not know about it.", character, requested=["shrug"]) == (
        "gesture-shrug",
        "amused",
    )


def test_a_keyword_still_outranks_the_gesture_for_mood() -> None:
    character = _character()
    _, emotion = infer("Careful, watch the edge.", character, requested=["shrug"])
    assert emotion == "alert"


def test_pace_follows_mood() -> None:
    assert pace("amused") > 1.0
    assert pace("solemn") < 1.0
    assert pace("neutral") == 1.0
    assert pace("no-such-mood") == 1.0
