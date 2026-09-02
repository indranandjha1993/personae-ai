"""Configuration must default to a runnable, credential-free state."""

from pathlib import Path

import pytest

from personae.settings import Settings, env_file_path


def test_defaults_to_no_credentials() -> None:
    """The zero-key promise: a bare environment yields a runnable configuration."""
    settings = Settings()
    assert settings.deepgram_api_key is None
    assert settings.llm_api_key is None


def test_defaults_to_the_openai_wire_format() -> None:
    assert Settings().llm_wire == "openai"


def test_reads_the_wire_format_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERSONAE_LLM_WIRE", "anthropic")
    assert Settings().llm_wire == "anthropic"


def test_rejects_an_unknown_wire_format(monkeypatch: pytest.MonkeyPatch) -> None:
    """An invalid value must fail at load, not at first use."""
    monkeypatch.setenv("PERSONAE_LLM_WIRE", "grpc")
    with pytest.raises(ValueError, match="llm_wire"):
        Settings()


def test_settings_are_immutable() -> None:
    settings = Settings()
    with pytest.raises(ValueError, match="frozen"):
        settings.llm_model = "other"


def test_finds_the_repository_env_file_from_any_working_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The backend is launched from apps/backend, but .env lives at the root.

    Resolving it relative to the working directory silently ignores the file,
    which looks exactly like a configuration that was never applied.
    """
    monkeypatch.chdir(tmp_path)
    assert env_file_path().name == ".env"
    assert env_file_path().is_absolute()
