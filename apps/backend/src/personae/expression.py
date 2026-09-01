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
    """Return a (gesture, emotion) pair valid for ``character``.

    Keyword hints alone leave most real replies on the resting pair, because a
    model rarely writes the exact words in the table. Punctuation and shape are
    therefore used as a second signal, so ordinary sentences still animate.
    """
    lowered = text.lower()
    gestures = character.expression.gestures
    emotions = character.expression.emotions

    gesture = _first_match(lowered, _GESTURE_HINTS, gestures)
    if gesture == gestures[0]:
        gesture = _shape_gesture(text, gestures)

    emotion = _first_match(lowered, _EMOTION_HINTS, emotions)
    if emotion == emotions[0]:
        emotion = _shape_emotion(text, emotions)

    return gesture, emotion


def _shape_gesture(text: str, allowed: tuple[str, ...]) -> str:
    """Fall back to sentence shape when no keyword matched."""
    stripped = text.strip()
    if not stripped:
        return allowed[0]
    if stripped.endswith("?"):
        return _prefer(("gesture-point", "gesture-consider", "gesture-indicate"), allowed)
    if len(stripped) > 90:
        return _prefer(("gesture-explain", "gesture-declaim"), allowed)
    return allowed[0]


def _shape_emotion(text: str, allowed: tuple[str, ...]) -> str:
    stripped = text.strip()
    if not stripped:
        return allowed[0]
    if "!" in stripped:
        return _prefer(("amused", "delighted", "indignant"), allowed)
    if stripped.endswith("?"):
        return _prefer(("focused", "alert", "wry"), allowed)
    if len(stripped) > 90:
        return _prefer(("focused", "solemn"), allowed)
    return allowed[0]


def _prefer(candidates: tuple[str, ...], allowed: tuple[str, ...]) -> str:
    """Pick the first candidate this character can actually perform."""
    for candidate in candidates:
        if candidate in allowed:
            return candidate
    return allowed[0]


def _first_match(
    text: str,
    hints: tuple[tuple[str, tuple[str, ...]], ...],
    allowed: tuple[str, ...],
) -> str:
    for candidate, triggers in hints:
        if candidate in allowed and any(trigger in text for trigger in triggers):
            return candidate
    return allowed[0]
