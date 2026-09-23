"""Reproducible LLM-to-speech baseline; mock by default, --live opts into billing."""

import argparse
import asyncio
import json
import math
from collections.abc import AsyncIterator, Sequence
from statistics import median

from personae.live_session import LiveSession
from personae.main import REPO_ROOT
from personae.packs.loader import load_packs
from personae.protocol import MetricsMessage
from personae.providers.base import Heard
from personae.providers.factory import build_llm, build_tts
from personae.providers.mock import MockLlm, MockTts
from personae.settings import Settings


class _TextInput:
    async def transcribe(
        self, audio: AsyncIterator[bytes], keyterms: Sequence[str] = ()
    ) -> AsyncIterator[Heard]:
        async for _ in audio:
            yield Heard("Please greet me in one short sentence.", final=True)


async def benchmark(turns: int, live: bool) -> dict[str, object]:
    # Mock mode deliberately ignores real environment credentials.
    settings = Settings() if live else None
    llm = build_llm(settings) if settings else MockLlm()
    tts = build_tts(settings) if settings else MockTts()
    character = load_packs([REPO_ROOT / "packs" / "bundled"]).get("bundled/seed")
    samples: dict[str, list[float]] = {}
    for _ in range(turns):
        session = LiveSession(character, _TextInput(), llm, tts)
        await session.offer(b"\x00\x00")
        await session.close_input()
        async for message in session.run():
            if message.model_dump()["type"] == "error":
                raise RuntimeError("Benchmark provider failed; inspect backend logs")
            if isinstance(message, MetricsMessage):
                for name, value in message.values.items():
                    samples.setdefault(name, []).append(value)
    return {
        "mode": "configured providers" if live else "mock (not a production latency estimate)",
        "scope": "reply generation only; excludes STT, network and browser playback",
        "turns": turns,
        "metrics_ms": {
            name: {
                "count": len(values),
                "p50": median(values),
                "p95": sorted(values)[math.ceil(len(values) * 0.95) - 1],
            }
            for name, values in samples.items()
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--turns", type=int, default=10)
    parser.add_argument(
        "--live", action="store_true", help="Use .env providers; incurs API charges"
    )
    args = parser.parse_args()
    if not 1 <= args.turns <= 100:
        parser.error("--turns must be between 1 and 100")
    print(json.dumps(asyncio.run(benchmark(args.turns, args.live)), indent=2))


if __name__ == "__main__":
    main()
