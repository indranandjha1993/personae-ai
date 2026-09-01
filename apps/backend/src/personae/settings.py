"""Typed application configuration, loaded from the environment."""

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

ProviderMode = Literal["mock", "live"]


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

    stt_mode: ProviderMode = "mock"
    llm_mode: ProviderMode = "mock"
    tts_mode: ProviderMode = "mock"

    deepgram_api_key: str | None = None
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str = "gpt-4o-mini"

    pack_search_paths: tuple[str, ...] = ("packs/bundled", "packs/local")
