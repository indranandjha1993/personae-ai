"""Deployment settings select independent personality, appearance and voice."""

import pytest
from fastapi.testclient import TestClient

from personae.main import create_app


def test_default_experience() -> None:
    with TestClient(create_app()) as client:
        config = client.get("/characters").json()["experience"]
    assert config == {
        "character_id": "bundled/seed",
        "appearance_id": "bundled/seed",
        "voice_id": "default",
        "quality": "auto",
        "barge_in_enabled": True,
        "microphone_auto_gain": True,
    }


def test_env_selects_independent_experience(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERSONAE_BARGE_IN_ENABLED", "false")
    monkeypatch.setenv("PERSONAE_MICROPHONE_AUTO_GAIN", "false")
    monkeypatch.setenv("PERSONAE_CHARACTER_ID", "bundled/mentor")
    monkeypatch.setenv("PERSONAE_APPEARANCE_ID", "bundled/analyst")
    monkeypatch.setenv("PERSONAE_RENDER_QUALITY", "low")
    monkeypatch.setenv("PERSONAE_LOCAL_TTS_BASE_URL", "http://localhost:8880/v1")
    monkeypatch.setenv("PERSONAE_VOICE_ID", "local:af_heart")
    with TestClient(create_app()) as client:
        config = client.get("/characters").json()["experience"]
    assert config == {
        "character_id": "bundled/mentor",
        "appearance_id": "bundled/analyst",
        "voice_id": "local:af_heart",
        "quality": "low",
        "barge_in_enabled": False,
        "microphone_auto_gain": False,
    }


@pytest.mark.parametrize("field", ["CHARACTER_ID", "APPEARANCE_ID", "VOICE_ID", "RENDER_QUALITY"])
def test_bad_selection_fails_at_boot(monkeypatch: pytest.MonkeyPatch, field: str) -> None:
    monkeypatch.setenv(f"PERSONAE_{field}", "missing")
    with pytest.raises(ValueError, match=r"PERSONAE_|render_quality"), TestClient(create_app()):
        pass
