"""The character pack schema.

Characters are data. These models are the whole contract between a pack file on
disk and the pipeline, and they are validated strictly so a malformed pack fails
at startup with a precise message rather than midway through a conversation.
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = 1

HexColour = Annotated[str, Field(pattern=r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")]


class Persona(BaseModel):
    """How the character thinks and speaks."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    prompt: Annotated[str, Field(min_length=1)]


class Voice(BaseModel):
    """How the character sounds."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider_voice: Annotated[str, Field(min_length=1)]
    rate: Annotated[float, Field(gt=0.0, le=3.0)] = 1.0
    # How animated the delivery is, from -2 (calm) to 2 (lively), on voices
    # that support it. Fixed for a whole conversation, so it belongs to the
    # character rather than to a mood.
    expressivity: Annotated[int, Field(ge=-2, le=2)] | None = None


class Theme(BaseModel):
    """How the character is presented."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    primary: HexColour = "#888888"
    secondary: HexColour = "#cccccc"


class Expression(BaseModel):
    """The closed vocabulary this character may perform.

    Inference is constrained to these values, so the backend can never emit a
    gesture the frontend has no animation for.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    gestures: Annotated[tuple[str, ...], Field(min_length=1)]
    emotions: Annotated[tuple[str, ...], Field(min_length=1)]


class Character(BaseModel):
    """A single character, as declared in one TOML file."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int
    id: Annotated[str, Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]
    display_name: Annotated[str, Field(min_length=1)]
    persona: Persona
    voice: Voice
    expression: Expression
    theme: Theme = Theme()


class PackManifest(BaseModel):
    """A pack's ``pack.toml``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int
    name: Annotated[str, Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]
