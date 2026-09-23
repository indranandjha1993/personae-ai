"""Provider-neutral speech timing, in seconds from the utterance's first sample."""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CharacterCue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str

    @model_validator(mode="after")
    def ordered(self) -> "CharacterCue":
        if self.end < self.start:
            raise ValueError("cue ends before it starts")
        return self


class VisemeCue(BaseModel):
    """Canonical mouth channels; providers must supply actual timing, not letters."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    value: Literal["aa", "ih", "ou", "ee", "oh", "closed"]
    weight: float = Field(default=1, ge=0, le=1)

    @model_validator(mode="after")
    def ordered(self) -> "VisemeCue":
        if self.end < self.start:
            raise ValueError("cue ends before it starts")
        return self


@dataclass(frozen=True, slots=True)
class SpeechChunk:
    """24 kHz mono signed little-endian PCM and optional utterance-relative cues."""

    pcm: bytes = b""
    alignment: tuple[CharacterCue, ...] = ()
    visemes: tuple[VisemeCue, ...] = ()
