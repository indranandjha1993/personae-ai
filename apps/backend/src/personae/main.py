"""Application entry point."""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from hmac import compare_digest
from pathlib import Path
from typing import TypedDict

from fastapi import FastAPI, Request, WebSocket
from starlette.websockets import WebSocketDisconnect

from personae.live import LiveSession
from personae.packs.loader import CharacterRegistry, load_packs
from personae.protocol import (
    PLAYBACK_SAMPLE_RATE,
    AudioFrame,
    InterruptSignal,
    MalformedMessageError,
    ServerMessage,
    VisionFrame,
    decode,
)
from personae.providers.base import LlmProvider, SttProvider, TtsProvider
from personae.providers.factory import build_llm, build_stt, build_tts
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

logger = logging.getLogger(__name__)


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
                "stt": "live" if settings.deepgram_api_key else "mock",
                "llm": "live" if settings.llm_api_key else "mock",
                "tts": "live" if settings.deepgram_api_key else "mock",
            },
            "vision": settings.llm_wire == "anthropic" and bool(settings.llm_api_key),
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

    @app.websocket("/ws/live/{pack}/{character}")
    async def live(socket: WebSocket, pack: str, character: str) -> None:
        settings: Settings = socket.state.settings
        expected = settings.access_token
        if expected and not compare_digest(socket.query_params.get("token", ""), expected):
            # Refused before accepting: this socket spends metered credentials.
            logger.warning("rejected an unauthenticated connection")
            await socket.close(code=4401, reason="unauthorised")
            return

        registry: CharacterRegistry = socket.state.characters
        try:
            persona = registry.get(f"{pack}/{character}")
        except KeyError:
            await socket.close(code=4004, reason="unknown character")
            return

        await socket.accept()
        await socket.send_json(ServerMessage.ready(PLAYBACK_SAMPLE_RATE).model_dump())
        session = LiveSession(persona, socket.state.stt, socket.state.llm, socket.state.tts)

        # Reading and replying run concurrently: the whole point is that the
        # listener can speak while she is still talking.
        async def read() -> None:
            while True:
                try:
                    message = decode(await socket.receive_text())
                except WebSocketDisconnect:
                    # Without this the session waits forever for input that
                    # will never arrive, holding its upstream connections open.
                    await session.interrupt()
                    await session.close_input()
                    return
                except MalformedMessageError:
                    # Report and keep listening: one bad frame should not end
                    # a conversation that is otherwise going fine.
                    await socket.send_json(ServerMessage.error("malformed message").model_dump())
                    continue
                if isinstance(message, AudioFrame):
                    await session.offer(message.pcm_bytes())
                elif isinstance(message, VisionFrame):
                    session.see(message.jpeg_bytes())
                elif isinstance(message, InterruptSignal):
                    await session.interrupt()
                else:
                    await session.close_input()
                    return

        reader = asyncio.create_task(read())
        replies = session.run()
        logger.info("session opened: %s/%s", pack, character)
        try:
            async for outbound in replies:
                await socket.send_json(outbound.model_dump())
        except WebSocketDisconnect:
            pass
        except Exception:
            logger.exception("session failed: %s/%s", pack, character)
        finally:
            # Closing the generator stops the producer rather than leaving it
            # streaming into a queue nobody is reading.
            await replies.aclose()
            reader.cancel()
            with contextlib.suppress(asyncio.CancelledError, WebSocketDisconnect):
                await reader
            logger.info("session closed: %s/%s", pack, character)

    return app


app = create_app()
