"""Typed application configuration, loaded from the environment."""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# How a language endpoint expects requests to be shaped. Vision in particular
# differs: OpenAI takes image_url parts, Anthropic takes base64 image blocks.
LlmWire = Literal["openai", "anthropic"]


# Languages nova-3 does not cover; nova-2 does.
_NOVA_2_ONLY = frozenset({"es", "fr", "pt", "hi", "ru", "zh", "ko", "uk", "sv", "tr", "id"})


def env_file_path() -> Path:
    """Locate the repository .env regardless of the working directory.

    The backend is normally launched from apps/backend while .env sits at the
    repository root. Resolving it relative to the working directory silently
    ignores the file, which is indistinguishable from settings that were never
    applied -- so search upward for the checkout marker instead.
    """
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "packs" / "bundled" / "pack.toml").is_file():
            return candidate / ".env"
    return Path(".env")


class Settings(BaseSettings):
    """Runtime configuration.

    Every provider defaults to ``mock`` so the application runs, and the whole
    test suite passes, without any credentials. Supplying keys and switching a
    mode to ``live`` is the only step needed to talk to real services.
    """

    model_config = SettingsConfigDict(
        env_prefix="PERSONAE_",
        env_file=env_file_path(),
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    deepgram_api_key: str | None = None

    # Speech model and voice. A character pack may name its own voice, in which
    # case this is only the fallback.
    stt_model: str = "flux-general-en"
    # Deepgram transcribes well over a hundred languages, but not every one on
    # every model: Spanish and French need nova-2, where German and Japanese
    # work on nova-3.
    stt_language: str = "en"
    tts_voice: str = "flux-haley-en"

    # Silence, in milliseconds, before a turn is treated as finished. Short
    # values feel responsive but cut people off mid-thought. Used by the nova
    # models; Flux detects the end of a turn itself.
    endpointing_ms: Annotated[int, Field(gt=0, le=10_000)] = 300
    utterance_end_ms: Annotated[int, Field(gt=0, le=10_000)] = 1000

    # Flux turn detection. A higher threshold clips fewer words off the end of
    # a sentence but waits longer before answering.
    #
    # Deepgram's high-reliability pairing. A lower threshold answers sooner
    # but splits a sentence at every pause for thought, and being talked over
    # is worse than waiting. The timeout is how long a pause mid-thought may
    # run before the turn is closed regardless.
    eot_threshold: Annotated[float, Field(ge=0.5, le=1.0)] = 0.85
    eot_timeout_ms: Annotated[int, Field(ge=500, le=60_000)] = 8_000
    # Confidence at which Flux says the turn has probably ended, a beat before
    # it is sure. A reply is drafted from that moment and either committed when
    # the real end arrives or thrown away if the speaker carries on.
    #
    # Off unless asked for: it fires on a breath between words, so most drafts
    # are thrown away, and a local model keeps generating an abandoned draft
    # while the real reply waits behind it. Only a hosted model that stops when
    # the client goes away comes out ahead.
    eager_eot_threshold: Annotated[float, Field(ge=0.3, le=0.9)] | None = None
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str = "gpt-4o-mini"

    # OpenAI-compatible covers OpenAI, OpenRouter, Groq, and most local servers.
    # Anthropic-shaped covers the Claude API and gateways that speak it.
    llm_wire: LlmWire = "openai"
    # Vision may need the other wire format, and often a different model.
    vision_model: str | None = None

    # When set, the websocket requires ?token=... Unset leaves it open, which
    # is right for localhost and wrong for anything reachable from elsewhere.
    access_token: str | None = None

    pack_search_paths: tuple[str, ...] = ("packs/bundled", "packs/local")

    @field_validator("eager_eot_threshold", mode="before")
    @classmethod
    def _blank_means_off(cls, value: object) -> object:
        """An empty or 'off' variable disables it, rather than failing to parse."""
        if isinstance(value, str) and value.strip().lower() in ("", "off", "none"):
            return None
        return value

    @model_validator(mode="after")
    def _language_matches_the_model(self) -> "Settings":
        """Catch a pairing the socket would refuse with an opaque 400."""
        if self.stt_model.startswith("nova-3") and self.stt_language in _NOVA_2_ONLY:
            raise ValueError(
                f"PERSONAE_STT_LANGUAGE={self.stt_language} needs PERSONAE_STT_MODEL=nova-2"
            )
        # The Flux voices are English-only. Asking for another language would
        # otherwise be honoured silently by reading it in an English accent.
        if self.tts_voice.startswith("flux-") and self.stt_language != "en":
            raise ValueError(
                f"PERSONAE_STT_LANGUAGE={self.stt_language} needs an aura-2 voice; "
                "the flux voices speak English only"
            )
        # Flux rejects an eager threshold above the final one, and it would be
        # meaningless anyway: the tentative signal must come first.
        if self.eager_eot_threshold is not None and self.eager_eot_threshold > self.eot_threshold:
            raise ValueError(
                f"PERSONAE_EAGER_EOT_THRESHOLD={self.eager_eot_threshold} must not exceed "
                f"PERSONAE_EOT_THRESHOLD={self.eot_threshold}"
            )
        return self
