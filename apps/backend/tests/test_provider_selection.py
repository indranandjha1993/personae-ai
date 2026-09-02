"""Providers are chosen by configuration, not by an explicit mode switch."""

import pytest

from personae.providers.factory import build_llm, build_stt, build_tts
from personae.providers.mock import MockLlm, MockStt, MockTts
from personae.settings import Settings


def test_without_credentials_everything_runs_on_fakes() -> None:
    """A fresh clone must run and test with no keys at all."""
    settings = Settings()
    assert isinstance(build_stt(settings), MockStt)
    assert isinstance(build_llm(settings), MockLlm)
    assert isinstance(build_tts(settings), MockTts)


def test_a_deepgram_key_alone_enables_speech(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERSONAE_DEEPGRAM_API_KEY", "dg-key")
    settings = Settings()
    assert not isinstance(build_stt(settings), MockStt)
    assert not isinstance(build_tts(settings), MockTts)
    # The language model is independent: no key, no live model.
    assert isinstance(build_llm(settings), MockLlm)


def test_an_llm_key_alone_enables_the_language_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERSONAE_LLM_API_KEY", "llm-key")
    monkeypatch.setenv("PERSONAE_LLM_BASE_URL", "https://example.invalid/v1")
    settings = Settings()
    assert not isinstance(build_llm(settings), MockLlm)
    assert isinstance(build_stt(settings), MockStt)


def test_an_llm_key_without_a_base_url_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Half-configured is a mistake worth naming, not a silent fallback."""
    monkeypatch.setenv("PERSONAE_LLM_API_KEY", "llm-key")
    monkeypatch.delenv("PERSONAE_LLM_BASE_URL", raising=False)
    with pytest.raises(ValueError, match="LLM_BASE_URL"):
        build_llm(Settings())
