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
