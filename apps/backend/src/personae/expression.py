"""Gesture and emotion inference.

Inference is always constrained to the vocabulary the character declares, so the
backend cannot emit a cue the frontend has no animation for. When nothing
matches, the first declared value is used -- every character therefore has a
well-defined resting state.
"""

from personae.packs.models import Character

_EMOTION_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("amused", ("ha", "funny", "joke", "laugh")),
    ("delighted", ("wonderful", "glad", "excellent", "love")),
    ("focused", ("build", "design", "work", "plan", "how")),
    ("solemn", ("sorry", "loss", "grave", "duty")),
    ("indignant", ("no", "never", "wrong", "refuse")),
    ("impatient", ("hurry", "already", "again", "still")),
    ("wry", ("obviously", "sure", "of course")),
    ("alert", ("careful", "watch", "danger")),
    ("unimpressed", ("fine", "whatever", "meh")),
)

_GESTURE_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("gesture-explain", ("because", "so", "means", "works")),
    ("gesture-point", ("there", "this", "that", "look")),
    ("gesture-declaim", ("hear", "behold", "truly", "indeed")),
    ("gesture-welcome", ("welcome", "friend", "hello")),
    ("gesture-summon", ("come", "bring", "call")),
    ("gesture-consider", ("perhaps", "maybe", "think")),
    ("gesture-indicate", ("here", "note", "see")),
    ("gesture-dismiss", ("no", "stop", "enough")),
)


def infer(text: str, character: Character) -> tuple[str, str]:
    """Return a (gesture, emotion) pair valid for ``character``."""
    lowered = text.lower()
    gesture = _first_match(lowered, _GESTURE_HINTS, character.expression.gestures)
    emotion = _first_match(lowered, _EMOTION_HINTS, character.expression.emotions)
    return gesture, emotion


def _first_match(
    text: str,
    hints: tuple[tuple[str, tuple[str, ...]], ...],
    allowed: tuple[str, ...],
) -> str:
    for candidate, triggers in hints:
        if candidate in allowed and any(trigger in text for trigger in triggers):
            return candidate
    return allowed[0]
