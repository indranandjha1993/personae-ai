"""Preparing a reply to be spoken.

Every character reaches the synthesiser and is read aloud, so markdown, emoji,
and URLs become stumbles. The persona prompt asks for none of them; this is the
guard for when the model produces them anyway.
"""

import re
from collections.abc import Collection

_EMOJI = re.compile("[\U0001f300-\U0001faff\U00002600-\U000027bf\U0001f1e6-\U0001f1ff️⭐❤]+")
_URL = re.compile(r"https?://([^\s/]+)\S*")
_HEADING = re.compile(r"^#{1,6}\s*", re.MULTILINE)
_BULLET = re.compile(r"^\s*[-*+]\s+", re.MULTILINE)
_NUMBERED = re.compile(r"^\s*\d+[.)]\s+", re.MULTILINE)
_BOLD = re.compile(r"\*\*(.+?)\*\*|__(.+?)__", re.DOTALL)
_ITALIC = re.compile(r"(?<!\w)[*_](.+?)[*_](?!\w)", re.DOTALL)
_CODE = re.compile(r"`+([^`]+)`+")


# She appends this when the conversation has reached its natural end. A marker
# rides the token stream where a structured field would fight it, and judging
# the ending from context beats matching words: "I told him goodbye" is not a
# farewell, and "right, I'm off then" is.
_FAREWELL = re.compile(r"\s*\[\s*end\s*\]\s*$", re.IGNORECASE)


def farewell_marked(reply: str) -> bool:
    """True when she has signalled that the conversation is over."""
    return _FAREWELL.search(reply) is not None


# Anywhere, not just at the end: sentences are spoken as they stream, so a
# marker mid-reply would otherwise be read aloud before the turn closes.
_FAREWELL_ANYWHERE = re.compile(r"\s*\[\s*end\s*\]\s*", re.IGNORECASE)


def strip_farewell(reply: str) -> str:
    """Remove the marker; it is never spoken and never shown."""
    return _FAREWELL_ANYWHERE.sub(" ", reply).strip()


def for_speech(text: str) -> str:
    """Return `text` with anything that would be mispronounced removed."""
    cleaned = strip_farewell(text)
    cleaned = _EMOJI.sub("", cleaned)
    # A spoken URL should be the site, not a spelled-out address.
    cleaned = _URL.sub(r"\1", cleaned)
    cleaned = _CODE.sub(r"\1", cleaned)
    cleaned = _BOLD.sub(lambda m: m.group(1) or m.group(2) or "", cleaned)
    cleaned = _ITALIC.sub(r"\1", cleaned)
    # A heading or bullet is a sentence when read aloud.
    cleaned = _HEADING.sub("", cleaned)
    cleaned = _BULLET.sub("", cleaned)
    cleaned = _NUMBERED.sub("", cleaned)
    # A line break between list items reads as a sentence break; one inside a
    # wrapped paragraph is just a space.
    cleaned = re.sub(r"\n\s*\n+", " ", cleaned)
    cleaned = re.sub(r"(?<=[^.!?:;])\n(?=\S)", ". ", cleaned)
    cleaned = re.sub(r"\n", " ", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\s+([.,;:!?])", r"\1", cleaned)
    return cleaned.strip()


# She marks her own gestures inline, as *explain* or *shrug*. Keyword guessing
# cannot tell that "I'm not sure" wants a shrug rather than a lecture; she
# knows what she means, so she is asked to say.
_GESTURE_MARK = re.compile(r"\*\s*([a-z][a-z-]{1,20})\s*\*")

# Models miswrite the marker often enough to plan for: a leading "*wave" with
# the closing asterisk forgotten is still unmistakably a mark, and left alone
# it is read aloud and printed in the caption.
_GESTURE_MARK_UNCLOSED = re.compile(r"(?:^\s*|(?<=[.!?] ))\*+\s*([a-z][a-z-]{1,20})\b\*?")


def gesture_marks(reply: str, known: Collection[str]) -> list[str]:
    """Gestures the reply asks for, in the order they appear.

    Only words in ``known`` count: a starred word that is not in the
    character's vocabulary is emphasis, not a gesture, and treating it as one
    would delete a word she meant to say.
    """
    names = _mark_words(known)
    marks = [m.group(1).lower() for m in _GESTURE_MARK.finditer(reply)]
    remainder = _GESTURE_MARK.sub(" ", reply).lstrip()
    marks.extend(m.group(1).lower() for m in _GESTURE_MARK_UNCLOSED.finditer(remainder))
    return [mark for mark in marks if mark in names]


def strip_gesture_marks(reply: str, known: Collection[str]) -> str:
    """Remove the markers; they are never spoken and never shown.

    A starred word outside the vocabulary keeps its word and loses only the
    asterisks: this is a voice, and no sentence says an asterisk aloud.
    """
    names = _mark_words(known)

    def keep_or_drop(match: re.Match[str]) -> str:
        return " " if match.group(1).lower() in names else f" {match.group(1)} "

    text = _GESTURE_MARK.sub(keep_or_drop, reply)
    text = _GESTURE_MARK_UNCLOSED.sub(keep_or_drop, text.lstrip())
    text = text.replace("*", " ")
    return re.sub(r"\s{2,}", " ", text).strip()


def _mark_words(known: Collection[str]) -> set[str]:
    """Vocabulary names as they appear in a marker, prefix and bare."""
    names = set()
    for name in known:
        names.add(name.lower())
        names.add(name.lower().removeprefix("gesture-"))
    return names
