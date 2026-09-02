"""Speaking a language other than English."""

import pytest

from personae.providers.deepgram import DeepgramStt
from personae.settings import Settings


def test_defaults_to_english() -> None:
    assert Settings().stt_language == "en"


def test_reads_the_language_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERSONAE_STT_LANGUAGE", "es")
    monkeypatch.setenv("PERSONAE_STT_MODEL", "nova-2")
    settings = Settings()
    assert settings.stt_language == "es"
    assert settings.stt_model == "nova-2"


def test_the_transcriber_carries_the_language() -> None:
    assert DeepgramStt(api_key="x", model="nova-2", language="es").language == "es"


def test_a_language_nova_3_cannot_do_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """Spanish and French need nova-2; pairing them with nova-3 fails at the
    socket with an opaque four hundred, so it is caught at startup instead."""
    monkeypatch.setenv("PERSONAE_STT_LANGUAGE", "fr")
    with pytest.raises(ValueError, match="nova-2"):
        Settings()


def test_a_language_nova_3_supports_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERSONAE_STT_LANGUAGE", "de")
    assert Settings().stt_language == "de"
