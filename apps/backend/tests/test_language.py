"""Speaking a language other than English.

Only the aura-2 voices speak anything but English, so every non-English
setting here also selects one.
"""

import pytest

from personae.providers.deepgram import DeepgramStt
from personae.settings import Settings


def test_defaults_to_english() -> None:
    assert Settings().stt_language == "en"


def test_reads_the_language_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERSONAE_STT_LANGUAGE", "es")
    monkeypatch.setenv("PERSONAE_STT_MODEL", "nova-2")
    monkeypatch.setenv("PERSONAE_TTS_VOICE", "aura-2-thalia-en")
    settings = Settings()
    assert settings.stt_language == "es"
    assert settings.stt_model == "nova-2"


def test_the_transcriber_carries_the_language() -> None:
    assert DeepgramStt(api_key="x", model="nova-2", language="es").language == "es"


def test_a_language_nova_3_cannot_do_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """Spanish and French need nova-2; pairing them with nova-3 fails at the
    socket with an opaque four hundred, so it is caught at startup instead."""
    monkeypatch.setenv("PERSONAE_STT_LANGUAGE", "fr")
    monkeypatch.setenv("PERSONAE_STT_MODEL", "nova-3")
    monkeypatch.setenv("PERSONAE_TTS_VOICE", "aura-2-thalia-en")
    with pytest.raises(ValueError, match="nova-2"):
        Settings()


def test_a_language_nova_3_supports_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERSONAE_STT_LANGUAGE", "de")
    monkeypatch.setenv("PERSONAE_STT_MODEL", "nova-3")
    monkeypatch.setenv("PERSONAE_TTS_VOICE", "aura-2-thalia-en")
    assert Settings().stt_language == "de"


def test_a_flux_voice_cannot_speak_another_language(monkeypatch: pytest.MonkeyPatch) -> None:
    """The flux voices are English-only, and would otherwise read German
    aloud in an English accent rather than refusing."""
    monkeypatch.setenv("PERSONAE_STT_LANGUAGE", "de")
    monkeypatch.setenv("PERSONAE_STT_MODEL", "nova-3")
    monkeypatch.setenv("PERSONAE_TTS_VOICE", "flux-haley-en")
    with pytest.raises(ValueError, match="English only"):
        Settings()
