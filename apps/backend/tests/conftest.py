"""Test-wide isolation from developer configuration.

The suite must behave identically on a machine with a fully populated .env and
on a fresh clone with none, so tests never read the developer's real
credentials or provider modes.
"""

from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def _isolate_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name in (
        "PERSONAE_LOCAL_TTS_BASE_URL",
        "PERSONAE_LOCAL_TTS_API_KEY",
        "PERSONAE_LOCAL_TTS_MODEL",
        "PERSONAE_LOCAL_TTS_VOICE",
        "PERSONAE_LOCAL_TTS_VOICES",
        "PERSONAE_LIP_SYNC",
        "PERSONAE_RHUBARB_PATH",
        "PERSONAE_RHUBARB_RECOGNIZER",
        "PERSONAE_TTS_PROVIDER",
        "PERSONAE_ELEVENLABS_API_KEY",
        "PERSONAE_ELEVENLABS_VOICE",
        "PERSONAE_ELEVENLABS_MODEL",
        "PERSONAE_LLM_VISION",
        "PERSONAE_STT_MODE",
        "PERSONAE_LLM_MODE",
        "PERSONAE_TTS_MODE",
        "PERSONAE_DEEPGRAM_API_KEY",
        "PERSONAE_LLM_API_KEY",
        "PERSONAE_LLM_BASE_URL",
        "PERSONAE_LLM_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)

    # pydantic-settings binds env_file at class creation, so the developer's
    # real .env would still be read. Rebind the model's configured path to one
    # that cannot exist.
    from personae.settings import Settings

    original = Settings.model_config["env_file"]
    Settings.model_config["env_file"] = "/nonexistent/.env"
    yield
    Settings.model_config["env_file"] = original
