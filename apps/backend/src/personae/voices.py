"""Server-owned voice catalogue. Clients select IDs, never URLs or credentials."""

from dataclasses import dataclass
from typing import Literal

from personae.settings import Settings


@dataclass(frozen=True)
class VoiceChoice:
    label: str
    mode: Literal["mock", "live", "local"]
    settings: Settings
    voice: str | None = None


def tts_mode(settings: Settings) -> Literal["mock", "live", "local"]:
    if settings.tts_provider == "local":
        return "local" if settings.local_tts_base_url else "mock"
    if settings.tts_provider == "elevenlabs":
        return "live" if settings.elevenlabs_tts_api_key else "mock"
    if settings.tts_provider == "deepgram":
        return "live" if settings.deepgram_api_key else "mock"
    return "mock"


def voice_choices(settings: Settings) -> dict[str, VoiceChoice]:
    mode = tts_mode(settings)
    choices = {
        "default": VoiceChoice("Demo tone" if mode == "mock" else "Character voice", mode, settings)
    }
    if settings.deepgram_api_key:
        choices["deepgram:default"] = VoiceChoice(
            "Deepgram · configured voice",
            "live",
            settings.model_copy(update={"tts_provider": "deepgram"}),
            settings.deepgram_tts_voice,
        )
    if settings.elevenlabs_tts_api_key and settings.elevenlabs_tts_voice:
        choices["elevenlabs:default"] = VoiceChoice(
            "ElevenLabs · configured voice",
            "live",
            settings.model_copy(update={"tts_provider": "elevenlabs"}),
            f"elevenlabs:{settings.elevenlabs_tts_voice}",
        )
    if settings.local_tts_base_url:
        for voice in settings.local_tts_voices:
            choices[f"local:{voice}"] = VoiceChoice(
                f"Local · {voice}",
                "local",
                settings.model_copy(update={"tts_provider": "local", "local_tts_voice": voice}),
                f"local:{voice}",
            )
    return choices
