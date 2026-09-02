"""Splitting a reply into speakable pieces while it is still arriving.

Synthesising the whole reply at once means she says nothing until the model has
finished writing, which is most of the delay in a spoken exchange. Releasing
each sentence as it completes lets her start on the first while the rest is
still being written.
"""

import re
from collections.abc import Iterator

# Titles and abbreviations that end in a full stop without ending a sentence.
_ABBREVIATIONS = (
    "mr",
    "mrs",
    "ms",
    "dr",
    "prof",
    "sr",
    "jr",
    "st",
    "e.g",
    "i.e",
    "etc",
    "vs",
    "approx",
    "no",
)

# A sentence ends at punctuation followed by a space or the end of what has
# arrived so far. It does not end mid-number, inside an ellipsis, after a
# single initial, or after one of the abbreviations above.
_SENTENCE_END = re.compile(
    r"(?<!\d)"  # not a decimal point
    r"(?<![A-Z])"  # not a lone initial: J. R. R.
    r"(?<!\.\.)"  # not the tail of an ellipsis
    r"([.!?])"
    r"(?!\.)"  # not the start of one either
    r"(?=\s|$)"
)

# The opening is cut at the first comma so she starts sooner. Long enough to be
# worth saying on its own, short enough that the pause before it is brief.
_OPENING_BREAK = re.compile(r"^([^,]{4,60},)\s")


class SentenceBuffer:
    """Accumulates fragments and releases whole sentences as they finish."""

    def __init__(self) -> None:
        self._pending = ""
        self._released_any = False

    def feed(self, fragment: str) -> Iterator[str]:
        """Take a fragment of the reply, yielding whatever is now speakable."""
        self._pending += fragment

        # Only the very first release is split at a comma: after she has begun,
        # whole sentences carry better prosody than clauses.
        if not self._released_any:
            opening = _OPENING_BREAK.match(self._pending)
            if opening:
                self._pending = self._pending[opening.end() :]
                self._released_any = True
                yield opening.group(1).strip()

        while True:
            match = self._next_end()
            if not match:
                return
            # A run of dots at the very end of what has arrived may be the head
            # of an ellipsis whose tail is in the next fragment. Waiting one
            # fragment costs nothing and avoids speaking a bare "..".
            if self._pending[match.end() :] == "" and self._pending.rstrip().endswith(".."):
                return
            sentence = self._pending[: match.end()].strip()
            self._pending = self._pending[match.end() :]
            if sentence:
                self._released_any = True
                yield sentence

    def _next_end(self) -> re.Match[str] | None:
        """Find the next real sentence end, stepping over abbreviations."""
        start = 0
        while True:
            match = _SENTENCE_END.search(self._pending, start)
            if not match:
                return None
            head = self._pending[: match.start()].rstrip().lower()
            word = re.split(r"[\s(]", head)[-1] if head else ""
            if word in _ABBREVIATIONS:
                start = match.end()
                continue
            return match

    def flush(self) -> str:
        """Return whatever is left, for the end of the reply."""
        remainder = self._pending.strip()
        self._pending = ""
        return remainder
