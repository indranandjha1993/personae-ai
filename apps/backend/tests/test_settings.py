"""Configuration must default to a runnable, credential-free state."""

import pytest

from personae.settings import Settings


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
