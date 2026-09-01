"""Application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TypedDict

from fastapi import FastAPI, Request, WebSocket
from starlette.websockets import WebSocketDisconnect

from personae.packs.loader import CharacterRegistry, load_packs
from personae.protocol import AudioFrame, ServerMessage
from personae.providers.base import LlmProvider, SttProvider, TtsProvider
from personae.providers.factory import build_llm, build_stt, build_tts
from personae.session import MalformedMessageError, Session, decode
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
    stt: SttProvider
    llm: LlmProvider
    tts: TtsProvider


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[AppState]:
    """Build long-lived resources on startup and release them on shutdown.

    Packs are read once here so a malformed pack fails the boot with a precise
    message, rather than surfacing midway through someone's conversation.
    """
    settings = Settings()
    characters = load_packs(REPO_ROOT / path for path in settings.pack_search_paths)
    # Built here so a missing credential fails the boot rather than the first
    # utterance of whoever happens to connect first.
    yield {
        "settings": settings,
        "characters": characters,
        "stt": build_stt(settings),
        "llm": build_llm(settings),
        "tts": build_tts(settings),
    }


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

    @app.websocket("/ws/session/{pack}/{character}")
    async def session(socket: WebSocket, pack: str, character: str) -> None:
        registry: CharacterRegistry = socket.state.characters
        try:
            persona = registry.get(f"{pack}/{character}")
        except KeyError:
            # Refuse before accepting, so the client sees a failed handshake
            # rather than an open socket that immediately dies.
            await socket.close(code=4004, reason="unknown character")
            return

        await socket.accept()
        turn = Session(persona, socket.state.stt, socket.state.llm, socket.state.tts)
        try:
            await _drive(socket, turn)
        except WebSocketDisconnect:
            return

    return app


async def _drive(socket: WebSocket, turn: Session) -> None:
    """Read inbound frames until the client stops, then stream the reply."""
    while True:
        try:
            message = decode(await socket.receive_text())
        except MalformedMessageError:
            await socket.send_json(ServerMessage.error("malformed message").model_dump())
            continue
        if isinstance(message, AudioFrame):
            await turn.offer(message)
            continue
        await turn.close_input()
        break

    async for outbound in turn.run():
        await socket.send_json(outbound.model_dump())
    await socket.send_json({"type": "done"})


app = create_app()
