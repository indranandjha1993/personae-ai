"""Typed application configuration, loaded from the environment."""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

ProviderMode = Literal["mock", "live"]


class Settings(BaseSettings):
    """Runtime configuration.

    Every provider defaults to ``mock`` so the application runs, and the whole
    test suite passes, without any credentials. Supplying keys and switching a
    mode to ``live`` is the only step needed to talk to real services.
    """

    model_config = SettingsConfigDict(
        env_prefix="PERSONAE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    stt_mode: ProviderMode = "mock"
    llm_mode: ProviderMode = "mock"
    tts_mode: ProviderMode = "mock"

    deepgram_api_key: str | None = None
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str = "gpt-4o-mini"

    pack_search_paths: tuple[str, ...] = ("packs/bundled", "packs/local")
