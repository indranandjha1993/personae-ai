"""She chooses her own gestures.

Keyword matching cannot tell that "I'm not sure" wants a shrug rather than an
explanation, so the speaker marks the sentences that carry a gesture and the
marker never reaches the ear or the screen.
"""

from personae.expression import infer
from personae.packs.loader import load_packs
from personae.packs.models import Character
from personae.speech import gesture_marks, strip_gesture_marks


def _character() -> Character:
    from personae.main import REPO_ROOT

    return load_packs([REPO_ROOT / "packs" / "bundled"]).get("bundled/seed")


def test_a_marked_gesture_is_taken_over_the_guess() -> None:
    """Only she knows that not knowing calls for a shrug."""
    gesture, _ = infer("I am not sure, honestly.", _character(), requested=["shrug"])
    assert gesture == "gesture-shrug"


def test_a_gesture_she_cannot_make_falls_back_to_the_text() -> None:
    """The vocabulary is the character's, not the model's to invent."""
    character = _character()
    gesture, _ = infer("Let me think about that.", character, requested=["cartwheel"])
    assert gesture in character.expression.gestures


def test_the_marker_is_never_spoken() -> None:
    assert strip_gesture_marks("*shrug* I have no idea.") == "I have no idea."


def test_several_marks_are_read_in_order() -> None:
    marks = gesture_marks("*consider* Well. *explain* It works like this.")
    assert marks == ["consider", "explain"]


def test_ordinary_text_is_left_alone() -> None:
    """Asterisks are rare in speech, but emphasis must not become a gesture."""
    assert gesture_marks("She said it was fine.") == []
    assert strip_gesture_marks("She said it was fine.") == "She said it was fine."
