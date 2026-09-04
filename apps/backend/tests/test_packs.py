"""Character packs are data: loading must validate strictly and fail loudly."""

from pathlib import Path

import pytest

from personae.packs.loader import PackError, load_packs

FIXTURES = Path(__file__).parent / "fixtures"


def test_loads_a_valid_pack() -> None:
    registry = load_packs([FIXTURES / "goodpack"])
    character = registry.get("goodpack/armored-inventor")
    assert character.display_name == "The Armored Inventor"
    assert character.persona.prompt.startswith("You are")


def test_character_ids_are_namespaced_by_pack() -> None:
    """Two packs may use the same character id without colliding."""
    registry = load_packs([FIXTURES / "goodpack"])
    assert registry.ids() == ("goodpack/armored-inventor",)


def test_expression_vocabulary_is_exposed() -> None:
    character = load_packs([FIXTURES / "goodpack"]).get("goodpack/armored-inventor")
    assert "idle" in character.expression.gestures
    assert "neutral" in character.expression.emotions


def test_unknown_character_raises_keyerror() -> None:
    registry = load_packs([FIXTURES / "goodpack"])
    with pytest.raises(KeyError, match="nope"):
        registry.get("nope")


def test_missing_search_path_is_skipped_not_fatal() -> None:
    """A configured-but-absent path (packs/local) must not break startup."""
    registry = load_packs([FIXTURES / "goodpack", FIXTURES / "does-not-exist"])
    assert registry.ids() == ("goodpack/armored-inventor",)


def test_malformed_character_names_the_file_and_field(tmp_path: Path) -> None:
    pack = tmp_path / "broken"
    (pack / "characters").mkdir(parents=True)
    (pack / "pack.toml").write_text('schema_version = 1\nname = "broken"\n')
    (pack / "characters" / "bad.toml").write_text('schema_version = 1\nid = "bad"\n')
    with pytest.raises(PackError) as exc:
        load_packs([pack])
    assert "bad.toml" in str(exc.value)
    assert "display_name" in str(exc.value)


def test_unsupported_schema_version_is_reported_clearly(tmp_path: Path) -> None:
    pack = tmp_path / "future"
    (pack / "characters").mkdir(parents=True)
    (pack / "pack.toml").write_text('schema_version = 99\nname = "future"\n')
    with pytest.raises(PackError, match="schema_version"):
        load_packs([pack])


def test_gesture_not_in_vocabulary_is_rejected(tmp_path: Path) -> None:
    """A character may only declare emotions/gestures it can actually perform."""
    pack = tmp_path / "p"
    (pack / "characters").mkdir(parents=True)
    (pack / "pack.toml").write_text('schema_version = 1\nname = "p"\n')
    (pack / "characters" / "c.toml").write_text(
        'schema_version = 1\nid = "c"\ndisplay_name = "C"\n'
        '[persona]\nprompt = "You are C."\n'
        '[voice]\nprovider_voice = "v"\n'
        '[expression]\ngestures = []\nemotions = ["neutral"]\n'
    )
    with pytest.raises(PackError, match="gestures"):
        load_packs([pack])


def test_invalid_toml_names_the_file(tmp_path: Path) -> None:
    pack = tmp_path / "p"
    (pack / "characters").mkdir(parents=True)
    (pack / "pack.toml").write_text("schema_version = 1\nname = 'p'\nthis is not toml\n")
    with pytest.raises(PackError, match=r"pack\.toml is not valid TOML"):
        load_packs([pack])


def test_directory_without_a_manifest_is_rejected(tmp_path: Path) -> None:
    pack = tmp_path / "nomanifest"
    (pack / "characters").mkdir(parents=True)
    with pytest.raises(PackError, match=r"no pack\.toml"):
        load_packs([pack])


def test_manifest_with_a_bad_name_is_rejected(tmp_path: Path) -> None:
    pack = tmp_path / "p"
    (pack / "characters").mkdir(parents=True)
    (pack / "pack.toml").write_text('schema_version = 1\nname = "Not A Slug"\n')
    with pytest.raises(PackError, match="name"):
        load_packs([pack])


def test_later_paths_shadow_earlier_ones(tmp_path: Path) -> None:
    """A local pack may override a bundled character of the same id."""
    body = (
        'schema_version = 1\nid = "c"\ndisplay_name = "{name}"\n'
        '[persona]\nprompt = "You are C."\n'
        '[voice]\nprovider_voice = "v"\n'
        '[expression]\ngestures = ["idle"]\nemotions = ["neutral"]\n'
    )
    for index, name in enumerate(("First", "Second")):
        pack = tmp_path / f"p{index}"
        (pack / "characters").mkdir(parents=True)
        (pack / "pack.toml").write_text('schema_version = 1\nname = "shared"\n')
        (pack / "characters" / "c.toml").write_text(body.format(name=name))
    registry = load_packs([tmp_path / "p0", tmp_path / "p1"])
    assert registry.get("shared/c").display_name == "Second"


def test_expressivity_outside_the_voice_range_is_rejected(tmp_path: Path) -> None:
    """The synthesiser takes -2 to 2; anything else fails at the socket."""
    pack = tmp_path / "p"
    (pack / "characters").mkdir(parents=True)
    (pack / "pack.toml").write_text('schema_version = 1\nname = "p"\n')
    (pack / "characters" / "c.toml").write_text(
        'schema_version = 1\nid = "c"\ndisplay_name = "C"\n'
        '[persona]\nprompt = "You are C."\n'
        '[voice]\nprovider_voice = "v"\nexpressivity = 3\n'
        '[expression]\ngestures = ["idle"]\nemotions = ["neutral"]\n'
    )
    with pytest.raises(PackError, match="expressivity"):
        load_packs([pack])


def test_expressivity_is_optional_and_carried_through(tmp_path: Path) -> None:
    pack = tmp_path / "p"
    (pack / "characters").mkdir(parents=True)
    (pack / "pack.toml").write_text('schema_version = 1\nname = "p"\n')
    (pack / "characters" / "c.toml").write_text(
        'schema_version = 1\nid = "c"\ndisplay_name = "C"\n'
        '[persona]\nprompt = "You are C."\n'
        '[voice]\nprovider_voice = "v"\nexpressivity = -1\n'
        '[expression]\ngestures = ["idle"]\nemotions = ["neutral"]\n'
    )
    assert load_packs([pack]).get("p/c").voice.expressivity == -1


def test_keyterms_are_optional_and_read(tmp_path: Path) -> None:
    pack = tmp_path / "p"
    (pack / "characters").mkdir(parents=True)
    (pack / "pack.toml").write_text('schema_version = 1\nname = "p"\n')
    (pack / "characters" / "c.toml").write_text(
        'schema_version = 1\nid = "c"\ndisplay_name = "C"\nkeyterms = ["Cee", "Sea"]\n'
        '[persona]\nprompt = "You are C."\n'
        '[voice]\nprovider_voice = "v"\n'
        '[expression]\ngestures = ["idle"]\nemotions = ["neutral"]\n'
    )
    assert load_packs([pack]).get("p/c").keyterms == ("Cee", "Sea")
