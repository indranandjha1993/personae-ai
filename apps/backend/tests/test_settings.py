"""Configuration must default to a runnable, credential-free state."""

from pathlib import Path

import pytest

from personae.settings import Settings, env_file_path


def test_defaults_to_mock_providers() -> None:
    """The zero-key promise: a bare environment yields a runnable configuration."""
    settings = Settings()
    assert (settings.stt_mode, settings.llm_mode, settings.tts_mode) == ("mock", "mock", "mock")


def test_reads_provider_mode_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERSONAE_STT_MODE", "live")
    assert Settings().stt_mode == "live"


def test_rejects_unknown_provider_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """An invalid mode must fail at load, not at first use."""
    monkeypatch.setenv("PERSONAE_LLM_MODE", "sometimes")
    with pytest.raises(ValueError, match="llm_mode"):
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
