"""Conversation history for a live session."""

from collections import deque
from dataclasses import dataclass
from typing import Literal, TypedDict

DEFAULT_MAX_TURNS = 8


class Message(TypedDict):
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True, slots=True)
class Turn:
    """One exchange. The reply may be partial if the speaker interrupted."""

    user: str
    assistant: str


class History:
    """A bounded window of recent turns.

    A live session runs for as long as someone keeps talking, so the window is
    capped: an unbounded prompt would grow until the model refused it.
    """

    def __init__(self, max_turns: int = DEFAULT_MAX_TURNS) -> None:
        self._turns: deque[Turn] = deque(maxlen=max_turns)

    def add(self, turn: Turn) -> None:
        # A turn cut off before she answered has nothing worth remembering.
        if not turn.assistant.strip():
            return
        self._turns.append(turn)

    def messages(self) -> list[Message]:
        """Render the window as chat messages, oldest first."""
        rendered: list[Message] = []
        for turn in self._turns:
            rendered.append({"role": "user", "content": turn.user})
            rendered.append({"role": "assistant", "content": turn.assistant})
        return rendered

    def clear(self) -> None:
        self._turns.clear()
