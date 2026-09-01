"""Application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TypedDict

from fastapi import FastAPI, Request

from personae.packs.loader import CharacterRegistry, load_packs
from personae.settings import Settings


def _repo_root() -> Path:
    """Locate the repository root by walking up to the directory holding packs/.

    Counting parent levels is brittle -- it breaks silently if the layout moves --
    so search upward for the checkout marker instead. Note that ``packs`` alone
    would be ambiguous: this package contains a ``packs`` module of its own.
    """
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "packs" / "bundled" / "pack.toml").is_file():
            return candidate
    return here.parents[4]


REPO_ROOT = _repo_root()


class AppState(TypedDict):
    """State constructed once at startup and shared by every request."""

    settings: Settings
    characters: CharacterRegistry


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[AppState]:
    """Build long-lived resources on startup and release them on shutdown.

    Packs are read once here so a malformed pack fails the boot with a precise
    message, rather than surfacing midway through someone's conversation.
    """
    settings = Settings()
    characters = load_packs(REPO_ROOT / path for path in settings.pack_search_paths)
    yield {"settings": settings, "characters": characters}


def create_app() -> FastAPI:
    """Build the application.

    A factory rather than a module-level singleton, so tests can construct an
    isolated instance without import-time side effects.
    """
    app = FastAPI(title="Personae AI", version="0.1.0", lifespan=lifespan)

    @app.get("/health")
    async def health(request: Request) -> dict[str, object]:
        settings: Settings = request.state.settings
        registry: CharacterRegistry = request.state.characters
        return {
            "status": "ok",
            "providers": {
                "stt": settings.stt_mode,
                "llm": settings.llm_mode,
                "tts": settings.tts_mode,
            },
            "characters": len(registry),
        }

    @app.get("/characters")
    async def characters(request: Request) -> dict[str, object]:
        """Summarise the loaded characters.

        Deliberately omits the persona prompt: it is server-side detail, and
        shipping it to the browser would invite trivial prompt extraction.
        """
        registry: CharacterRegistry = request.state.characters
        return {
            "characters": [
                {
                    "id": character_id,
                    "display_name": character.display_name,
                    "theme": character.theme.model_dump(),
                    "expression": character.expression.model_dump(),
                }
                for character_id in registry.ids()
                for character in (registry.get(character_id),)
            ]
        }

    return app


app = create_app()
