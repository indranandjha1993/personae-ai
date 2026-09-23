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
        "PERSONAE_DEEPGRAM_STT_MODEL",
        "PERSONAE_DEEPGRAM_STT_LANGUAGE",
        "PERSONAE_DEEPGRAM_TTS_VOICE",
        "PERSONAE_ELEVENLABS_TTS_API_KEY",
        "PERSONAE_ELEVENLABS_TTS_MODEL",
        "PERSONAE_ELEVENLABS_TTS_VOICE",
        "PERSONAE_DEEPGRAM_STT_EOT_THRESHOLD",
        "PERSONAE_DEEPGRAM_STT_EOT_TIMEOUT_MS",
        "PERSONAE_DEEPGRAM_STT_EAGER_EOT_THRESHOLD",
        "PERSONAE_DEEPGRAM_STT_ENDPOINTING_MS",
        "PERSONAE_DEEPGRAM_STT_UTTERANCE_END_MS",
        "PERSONAE_CHARACTER_ID",
        "PERSONAE_APPEARANCE_ID",
        "PERSONAE_VOICE_ID",
        "PERSONAE_RENDER_QUALITY",
        "PERSONAE_LOCAL_TTS_BASE_URL",
        "PERSONAE_LOCAL_TTS_API_KEY",
        "PERSONAE_LOCAL_TTS_MODEL",
        "PERSONAE_LOCAL_TTS_VOICE",
        "PERSONAE_LOCAL_TTS_VOICES",
        "PERSONAE_LIP_SYNC",
        "PERSONAE_RHUBARB_PATH",
        "PERSONAE_RHUBARB_RECOGNIZER",
        "PERSONAE_TTS_PROVIDER",
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
