"""Application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TypedDict

from fastapi import FastAPI

from personae.settings import Settings


class AppState(TypedDict):
    """State constructed once at startup and shared by every request."""

    settings: Settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[AppState]:
    """Build long-lived resources on startup and release them on shutdown.

    Providers are constructed here rather than per-request so connections are
    reused across a session and closed deterministically on shutdown.
    """
    settings = Settings()
    yield {"settings": settings}


def create_app() -> FastAPI:
    """Build the application.

    A factory rather than a module-level singleton, so tests can construct an
    isolated instance without import-time side effects.
    """
    app = FastAPI(title="Personae AI", version="0.1.0", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, object]:
        settings = Settings()
        return {
            "status": "ok",
            "providers": {
                "stt": settings.stt_mode,
                "llm": settings.llm_mode,
                "tts": settings.tts_mode,
            },
        }

    return app


app = create_app()
