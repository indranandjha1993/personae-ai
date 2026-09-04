"""Gesture and emotion inference.

Inference is always constrained to the vocabulary the character declares, so the
backend cannot emit a cue the frontend has no animation for. When nothing
matches, the first declared value is used -- every character therefore has a
well-defined resting state.
"""

import re
from collections.abc import Sequence

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
    # The everyday ones first, so a goodbye waves rather than explains.
    ("gesture-wave", ("goodbye", "bye", "see you")),
    ("gesture-namaste", ("namaste", "pranam")),
    ("gesture-explain", ("because", "so", "means", "works")),
    ("gesture-point", ("there", "this", "that", "look")),
    ("gesture-declaim", ("hear", "behold", "truly", "indeed")),
    ("gesture-welcome", ("welcome", "friend", "hello")),
    ("gesture-summon", ("come", "bring", "call")),
    ("gesture-consider", ("perhaps", "maybe", "think")),
    ("gesture-indicate", ("here", "note", "see")),
    ("gesture-dismiss", ("no", "stop", "enough")),
)

# The mood a gesture usually carries. She marks the gesture herself, and what a
# shrug or a hand on the chest means about her face follows from it more
# reliably than from any word in the sentence.
_GESTURE_EMOTIONS: dict[str, tuple[str, ...]] = {
    "gesture-shrug": ("amused", "wry", "neutral"),
    "gesture-sincere": ("focused", "solemn"),
    "gesture-declaim": ("alert", "indignant", "focused"),
    "gesture-wave": ("amused", "delighted"),
    "gesture-welcome": ("amused", "delighted"),
    "gesture-namaste": ("focused", "solemn"),
    "gesture-consider": ("focused",),
    "gesture-precise": ("focused",),
    "gesture-explain": ("focused",),
    "gesture-dismiss": ("wry", "unimpressed", "amused"),
    "gesture-settle": ("focused", "solemn"),
    "gesture-no": ("indignant", "alert"),
    "gesture-yes": ("amused", "focused"),
    "gesture-point": ("alert", "focused"),
    "gesture-indicate": ("focused",),
    "gesture-summon": ("amused", "alert"),
}

# How a mood changes her pace, as a multiplier on the character's own rate.
# Small on purpose: a voice that lurches between speeds sounds edited, where
# one that slows a little when serious sounds like a person.
_EMOTION_PACE: dict[str, float] = {
    "solemn": 0.94,
    "unimpressed": 0.96,
    "alert": 1.04,
    "amused": 1.06,
    "delighted": 1.08,
    "impatient": 1.1,
}


def pace(emotion: str) -> float:
    """The speaking-rate multiplier for a mood; 1.0 for anything unlisted."""
    return _EMOTION_PACE.get(emotion, 1.0)


def infer(
    text: str,
    character: Character,
    requested: Sequence[str] = (),
    beat: int = 0,
    after_mark: bool = False,
) -> tuple[str, str]:
    """Return a (gesture, emotion) pair valid for ``character``.

    A gesture the speaker asked for wins, since only she knows what she meant.
    Otherwise keyword hints are tried, and then the shape of the sentence:
    hints alone leave most real replies at rest, because a model rarely writes
    the exact words in the table.

    ``beat`` is the sentence's position in the reply and ``after_mark`` whether
    the previous sentence carried a gesture she chose. People gesture on the
    clause that carries the weight, not on every line, so the guessed gesture
    is only offered every other sentence and never straight after a chosen
    one; the hands come back to rest between.
    """
    lowered = text.lower()
    gestures = character.expression.gestures
    emotions = character.expression.emotions

    for name in requested:
        candidate = name if name.startswith("gesture-") else f"gesture-{name}"
        if candidate in gestures:
            emotion = _first_match(lowered, _EMOTION_HINTS, emotions)
            if emotion == emotions[0]:
                emotion = _prefer(_GESTURE_EMOTIONS.get(candidate, ()), emotions)
            if emotion == emotions[0]:
                emotion = _shape_emotion(text, emotions)
            return candidate, emotion

    gesture = _first_match(lowered, _GESTURE_HINTS, gestures)
    if gesture == gestures[0] and beat % 2 == 0 and not after_mark:
        gesture = _shape_gesture(text, gestures)

    emotion = _first_match(lowered, _EMOTION_HINTS, emotions)
    if emotion == emotions[0]:
        emotion = _shape_emotion(text, emotions)

    return gesture, emotion


# A spoken reply is typically one or two sentences; thresholds tuned to longer
# text leave almost everything at rest.
_SUBSTANTIAL = 24


def _shape_gesture(text: str, allowed: tuple[str, ...]) -> str:
    """Fall back to sentence shape when no keyword matched.

    Only genuinely short utterances rest. Anything a person would actually say
    aloud gets a gesture, otherwise the avatar stands motionless through most
    of the conversation.
    """
    stripped = text.strip()
    if len(stripped) < _SUBSTANTIAL:
        return allowed[0]
    if stripped.endswith("?"):
        return _prefer(("gesture-point", "gesture-consider", "gesture-indicate"), allowed)
    if len(stripped) > 90 or stripped.count(".") > 1:
        return _prefer(("gesture-explain", "gesture-declaim"), allowed)
    return _prefer(("gesture-indicate", "gesture-explain", "gesture-welcome"), allowed)


def _shape_emotion(text: str, allowed: tuple[str, ...]) -> str:
    stripped = text.strip()
    if len(stripped) < _SUBSTANTIAL:
        return allowed[0]
    if "!" in stripped:
        return _prefer(("amused", "delighted", "indignant"), allowed)
    if stripped.endswith("?"):
        return _prefer(("focused", "alert", "wry"), allowed)
    if len(stripped) > 90:
        return _prefer(("focused", "solemn"), allowed)
    return _prefer(("focused", "alert", "wry", "amused"), allowed)


def _prefer(candidates: Sequence[str], allowed: tuple[str, ...]) -> str:
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
    words = set(re.findall(r"[a-z']+", text))
    for candidate, triggers in hints:
        # Whole words only: matching substrings found "ha" inside "what" and
        # "changed", so ordinary statements read as amusement.
        if candidate in allowed and words.intersection(triggers):
            return candidate
    return allowed[0]
