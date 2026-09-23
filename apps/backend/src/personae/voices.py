"""Apply the deployment's selected TTS voice without changing character identity."""

from personae.packs.models import Character
from personae.settings import Settings


def configured_voice(character: Character, settings: Settings) -> Character:
    """Provider-specific environment settings are authoritative for session voice."""
    voice = {
        "deepgram": settings.deepgram_tts_voice,
        "elevenlabs": f"elevenlabs:{settings.elevenlabs_tts_voice}",
        "local": f"local:{settings.local_tts_voice}",
        "mock": "",
    }[settings.tts_provider]
    return character.model_copy(
        update={"voice": character.voice.model_copy(update={"provider_voice": voice})}
    )
