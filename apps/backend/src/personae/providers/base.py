"""Provider boundaries.

The pipeline depends only on these protocols, never on a vendor SDK. That is what
lets the application run on mocks with no credentials, and it keeps a vendor's
types from leaking into domain code.
"""

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable


@runtime_checkable
class SttProvider(Protocol):
    """Streaming speech-to-text."""

    def transcribe(self, audio: AsyncIterator[bytes]) -> AsyncIterator[str]:
        """Yield transcript text as it becomes available."""
        ...


@runtime_checkable
class LlmProvider(Protocol):
    """Character-voiced text generation."""

    def respond(self, system_prompt: str, transcript: str) -> AsyncIterator[str]:
        """Yield the reply in streamed fragments."""
        ...


@runtime_checkable
class TtsProvider(Protocol):
    """Streaming text-to-speech."""

    def synthesize(self, text: str, voice: str, rate: float = 1.0) -> AsyncIterator[bytes]:
        """Yield PCM audio frames for ``text`` in ``voice`` at ``rate``."""
        ...
