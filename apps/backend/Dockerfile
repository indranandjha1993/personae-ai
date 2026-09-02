# syntax=docker/dockerfile:1

FROM python:3.13-slim AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
COPY --from=ghcr.io/astral-sh/uv:0.12.7 /uv /usr/local/bin/uv

WORKDIR /app

# Dependencies install in their own layer so a source edit does not reinstall
# the world.
COPY apps/backend/pyproject.toml apps/backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev

COPY apps/backend/src ./src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev

# The character packs live at the repository root, and the app locates that
# root by looking for them.
COPY packs /packs

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000

# Runs unprivileged: nothing here needs root.
RUN useradd --create-home --uid 10001 wren && chown -R wren /app
USER wren

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/health').read()"

# The sansio implementation is required: the default imports the deprecated
# websockets.legacy module.
CMD ["uvicorn", "personae.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--ws", "websockets-sansio"]
