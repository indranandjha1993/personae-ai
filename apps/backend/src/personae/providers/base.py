"""Provider boundaries.

The pipeline depends only on these protocols, never on a vendor SDK. That is what
lets the application run on mocks with no credentials, and it keeps a vendor's
types from leaking into domain code.
"""

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from personae.conversation import Message


class ProviderError(RuntimeError):
    """An upstream provider reported a failure.

    Distinct from a transport error: the request arrived and was refused, so
    the message is worth showing rather than retrying blindly.
    """


@dataclass(frozen=True, slots=True)
class Heard:
    """What the recogniser has made of the speaker so far.

    ``final`` marks the end of a turn. Anything before it is provisional and
    may be revised by later words, but it is what lets the listener see
    themselves being heard as they speak rather than only afterwards.
    """

    text: str
    final: bool


@runtime_checkable
class SttProvider(Protocol):
    """Streaming speech-to-text."""

    def transcribe(self, audio: AsyncIterator[bytes]) -> AsyncIterator[Heard]:
        """Yield what has been heard, provisionally and then finally."""
        ...


@runtime_checkable
class LlmProvider(Protocol):
    """Character-voiced text generation."""

    def respond(
        self,
        system_prompt: str,
        transcript: str,
        history: Sequence[Message] = (),
        image: bytes | None = None,
    ) -> AsyncIterator[str]:
        """Yield the reply in streamed fragments, given prior turns.

        ``image`` is a camera frame for the model to look at, when the listener
        has the camera on and the endpoint supports vision.
        """
        ...


@runtime_checkable
class TtsProvider(Protocol):
    """Streaming text-to-speech."""

    def synthesize(self, text: str, voice: str, rate: float = 1.0) -> AsyncIterator[bytes]:
        """Yield PCM audio frames for ``text`` in ``voice`` at ``rate``."""
        ...
