"""Preparing a reply to be spoken.

Every character reaches the synthesiser and is read aloud, so markdown, emoji,
and URLs become stumbles. The persona prompt asks for none of them; this is the
guard for when the model produces them anyway.
"""

import re

_EMOJI = re.compile("[\U0001f300-\U0001faff\U00002600-\U000027bf\U0001f1e6-\U0001f1ff️⭐❤]+")
_URL = re.compile(r"https?://([^\s/]+)\S*")
_HEADING = re.compile(r"^#{1,6}\s*", re.MULTILINE)
_BULLET = re.compile(r"^\s*[-*+]\s+", re.MULTILINE)
_NUMBERED = re.compile(r"^\s*\d+[.)]\s+", re.MULTILINE)
_BOLD = re.compile(r"\*\*(.+?)\*\*|__(.+?)__", re.DOTALL)
_ITALIC = re.compile(r"(?<!\w)[*_](.+?)[*_](?!\w)", re.DOTALL)
_CODE = re.compile(r"`+([^`]+)`+")


def for_speech(text: str) -> str:
    """Return `text` with anything that would be mispronounced removed."""
    cleaned = _EMOJI.sub("", text)
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
