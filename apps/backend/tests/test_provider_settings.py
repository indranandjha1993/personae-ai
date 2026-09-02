"""Speech model and timing are configurable without editing code."""

import pytest

from personae.providers.deepgram import DeepgramStt, DeepgramTts
from personae.settings import Settings


def test_sensible_defaults_without_any_configuration() -> None:
    settings = Settings()
    assert settings.stt_model
    assert settings.tts_voice
    assert settings.endpointing_ms > 0
    assert settings.utterance_end_ms > 0


def test_reads_the_speech_model_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERSONAE_STT_MODEL", "nova-2")
    monkeypatch.setenv("PERSONAE_TTS_VOICE", "aura-2-luna-en")
    settings = Settings()
    assert settings.stt_model == "nova-2"
    assert settings.tts_voice == "aura-2-luna-en"


def test_reads_turn_timing_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """How long she waits before answering is the main thing worth tuning."""
    monkeypatch.setenv("PERSONAE_ENDPOINTING_MS", "400")
    settings = Settings()
    assert settings.endpointing_ms == 400


def test_rejects_a_negative_silence_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERSONAE_ENDPOINTING_MS", "-1")
    with pytest.raises(ValueError, match="endpointing_ms"):
        Settings()


def test_a_character_voice_overrides_the_configured_default() -> None:
    """The pack decides who speaks; the setting only fills the gap."""
    tts = DeepgramTts(api_key="x", voice="aura-2-thalia-en")
    assert tts.voice_for("aura-2-luna-en") == "aura-2-luna-en"
    assert tts.voice_for("") == "aura-2-thalia-en"


def test_the_transcriber_keeps_its_configured_model() -> None:
    assert DeepgramStt(api_key="x", model="nova-2").model == "nova-2"
