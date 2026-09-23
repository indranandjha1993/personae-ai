"""Credential-based runtime status for the selected speech providers."""

from typing import Literal

from personae.settings import Settings


def stt_mode(settings: Settings) -> Literal["live", "mock"]:
    if settings.stt_provider == "elevenlabs":
        return "live" if settings.elevenlabs_api_key else "mock"
    if settings.stt_provider == "deepgram":
        return "live" if settings.deepgram_api_key else "mock"
    return "mock"


def tts_mode(settings: Settings) -> Literal["mock", "live", "local"]:
    if settings.tts_provider == "local":
        return "local" if settings.local_tts_base_url else "mock"
    if settings.tts_provider == "elevenlabs":
        return "live" if settings.elevenlabs_api_key else "mock"
    if settings.tts_provider == "deepgram":
        return "live" if settings.deepgram_api_key else "mock"
    return "mock"
