"""Splitting a reply into speakable pieces while it is still arriving.

Synthesising the whole reply at once means she says nothing until the model has
finished writing, which is most of the delay in a spoken exchange. Releasing
each sentence as it completes lets her start on the first while the rest is
still being written.
"""

import re
from collections.abc import Iterator

# A sentence ends at punctuation followed by a space or the end of what has
# arrived so far, but not mid-number.
_SENTENCE_END = re.compile(r"(?<!\d)([.!?])(?=\s|$)")

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
            match = _SENTENCE_END.search(self._pending)
            if not match:
                return
            sentence = self._pending[: match.end()].strip()
            self._pending = self._pending[match.end() :]
            if sentence:
                self._released_any = True
                yield sentence

    def flush(self) -> str:
        """Return whatever is left, for the end of the reply."""
        remainder = self._pending.strip()
        self._pending = ""
        return remainder
