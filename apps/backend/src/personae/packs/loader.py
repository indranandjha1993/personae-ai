"""Discovery and validation of character packs."""

import tomllib
from collections.abc import Iterable, Sequence
from pathlib import Path

from pydantic import ValidationError

from personae.packs.models import SCHEMA_VERSION, Character, PackManifest


class PackError(Exception):
    """A pack could not be loaded.

    Always names the offending file, and the field where one applies, so the
    cause is obvious without reading the loader.
    """


class CharacterRegistry:
    """The loaded characters, addressed by namespaced id."""

    def __init__(self, characters: dict[str, Character]) -> None:
        self._characters = characters

    def get(self, character_id: str) -> Character:
        try:
            return self._characters[character_id]
        except KeyError:
            known = ", ".join(sorted(self._characters)) or "none"
            raise KeyError(f"unknown character {character_id!r}; loaded: {known}") from None

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._characters))

    def __len__(self) -> int:
        return len(self._characters)


def _describe(error: ValidationError, path: Path) -> str:
    problems = "; ".join(
        f"{'.'.join(str(p) for p in issue['loc']) or '<root>'}: {issue['msg']}"
        for issue in error.errors()
    )
    return f"{path.name} is invalid -- {problems}"


def _read_toml(path: Path) -> dict[str, object]:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise PackError(f"{path.name} is not valid TOML -- {exc}") from exc


def _check_schema_version(declared: object, path: Path) -> None:
    """Reject unsupported versions with a migration hint, not a field error."""
    if declared != SCHEMA_VERSION:
        raise PackError(
            f"{path.name} declares schema_version {declared!r}, "
            f"but this build supports {SCHEMA_VERSION}"
        )


def _load_pack(pack_dir: Path) -> dict[str, Character]:
    manifest_path = pack_dir / "pack.toml"
    if not manifest_path.is_file():
        raise PackError(f"{pack_dir.name} has no pack.toml")

    raw_manifest = _read_toml(manifest_path)
    _check_schema_version(raw_manifest.get("schema_version"), manifest_path)
    try:
        manifest = PackManifest.model_validate(raw_manifest)
    except ValidationError as exc:
        raise PackError(_describe(exc, manifest_path)) from exc

    characters: dict[str, Character] = {}
    for character_path in sorted((pack_dir / "characters").glob("*.toml")):
        raw = _read_toml(character_path)
        _check_schema_version(raw.get("schema_version"), character_path)
        try:
            character = Character.model_validate(raw)
        except ValidationError as exc:
            raise PackError(_describe(exc, character_path)) from exc
        characters[f"{manifest.name}/{character.id}"] = character
    return characters


def load_packs(search_paths: Iterable[Path | str]) -> CharacterRegistry:
    """Load every pack found on ``search_paths``.

    Later paths win on collision, so a local pack can shadow a bundled one. A
    path that does not exist is skipped: ``packs/local`` is optional by design.
    """
    characters: dict[str, Character] = {}
    for raw_path in search_paths:
        pack_dir = Path(raw_path)
        if not pack_dir.is_dir():
            continue
        characters.update(_load_pack(pack_dir))
    return CharacterRegistry(characters)


__all__: Sequence[str] = ("CharacterRegistry", "PackError", "load_packs")
