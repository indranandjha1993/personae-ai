import pytest
from pydantic import ValidationError

from personae.packs.models import AvatarConfig
from personae.providers.factory import build_tts
from personae.providers.mock import MockTts
from personae.settings import Settings


def test_pixel_player_requires_an_explicit_url() -> None:
    with pytest.raises(ValidationError, match="requires player_url"):
        AvatarConfig(renderer="pixel-streaming")
    with pytest.raises(ValidationError, match="HTTPS"):
        AvatarConfig(player_url="javascript:alert(1)")


def test_elevenlabs_without_credentials_still_runs() -> None:
    assert isinstance(build_tts(Settings(tts_provider="elevenlabs", lip_sync="rhubarb")), MockTts)


def test_elevenlabs_with_key_requires_voice() -> None:
    with pytest.raises(ValueError, match="ELEVENLABS_TTS_VOICE"):
        build_tts(Settings(tts_provider="elevenlabs", elevenlabs_tts_api_key="test"))


def test_bundled_avatar_hides_robot_accessory() -> None:
    """Keep model-specific cleanup in the pack when renderer code is generalized."""
    from personae.main import REPO_ROOT
    from personae.packs.loader import load_packs

    character = load_packs([REPO_ROOT / "packs" / "bundled"]).get("bundled/seed")
    assert "robo_arm" in character.avatar.hidden_meshes
    assert "wear" not in character.avatar.hidden_meshes
