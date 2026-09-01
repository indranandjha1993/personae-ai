"""Provider selection must be explicit and fail early on misconfiguration."""

import pytest

from personae.providers.factory import build_llm, build_stt, build_tts
from personae.providers.mock import MockLlm, MockStt, MockTts
from personae.settings import Settings


def test_defaults_build_mock_providers() -> None:
    settings = Settings()
    assert isinstance(build_stt(settings), MockStt)
    assert isinstance(build_llm(settings), MockLlm)
    assert isinstance(build_tts(settings), MockTts)


def test_live_stt_without_a_key_fails_at_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Misconfiguration must surface at boot, not on the first user utterance."""
    monkeypatch.setenv("PERSONAE_STT_MODE", "live")
    with pytest.raises(ValueError, match="DEEPGRAM_API_KEY"):
        build_stt(Settings())


def test_live_tts_without_a_key_fails_at_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERSONAE_TTS_MODE", "live")
    with pytest.raises(ValueError, match="DEEPGRAM_API_KEY"):
        build_tts(Settings())


def test_live_llm_without_a_key_fails_at_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERSONAE_LLM_MODE", "live")
    with pytest.raises(ValueError, match="LLM_API_KEY"):
        build_llm(Settings())


def test_live_llm_without_a_base_url_fails_at_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERSONAE_LLM_MODE", "live")
    monkeypatch.setenv("PERSONAE_LLM_API_KEY", "test-key")
    with pytest.raises(ValueError, match="LLM_BASE_URL"):
        build_llm(Settings())


def test_live_providers_are_constructed_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERSONAE_STT_MODE", "live")
    monkeypatch.setenv("PERSONAE_TTS_MODE", "live")
    monkeypatch.setenv("PERSONAE_LLM_MODE", "live")
    monkeypatch.setenv("PERSONAE_DEEPGRAM_API_KEY", "dg-key")
    monkeypatch.setenv("PERSONAE_LLM_API_KEY", "llm-key")
    monkeypatch.setenv("PERSONAE_LLM_BASE_URL", "https://example.invalid/v1")
    settings = Settings()
    assert not isinstance(build_stt(settings), MockStt)
    assert not isinstance(build_llm(settings), MockLlm)
    assert not isinstance(build_tts(settings), MockTts)
