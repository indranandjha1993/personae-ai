"""Resolve the server-owned character experience once, before serving traffic."""

from personae.packs.loader import CharacterRegistry
from personae.settings import Settings
from personae.voices import voice_choices


def experience_config(settings: Settings, registry: CharacterRegistry) -> dict[str, object]:
    selected = {
        "character_id": settings.character_id,
        "appearance_id": settings.appearance_id or settings.character_id,
        "voice_id": settings.voice_id,
        "quality": settings.render_quality,
    }
    for field in ("character_id", "appearance_id"):
        try:
            registry.get(selected[field])
        except KeyError as error:
            raise ValueError(f"PERSONAE_{field.upper()} names an unknown character pack") from error
    character = registry.get(selected["character_id"])
    appearance = registry.get(selected["appearance_id"])
    if character.avatar.renderer == "vrm" and appearance.avatar.renderer != "vrm":
        raise ValueError("PERSONAE_APPEARANCE_ID must use a VRM avatar for a browser character")
    if character.avatar.renderer == "pixel-streaming" and appearance != character:
        raise ValueError(
            "Hosted characters manage their own appearance; omit PERSONAE_APPEARANCE_ID"
        )
    if settings.voice_id not in voice_choices(settings):
        raise ValueError("PERSONAE_VOICE_ID is not available with the configured TTS providers")
    return {
        **selected,
        "barge_in_enabled": settings.barge_in_enabled,
        "microphone_auto_gain": settings.microphone_auto_gain,
    }
