"""Streaming chat against an Anthropic-shaped endpoint.

Covers the Claude API and gateways that speak it. Kept separate from the
OpenAI-compatible client because the two disagree on how images are sent, and
that difference is the whole reason a wire setting exists.
"""

import json
import logging
from collections.abc import AsyncIterator, Sequence

import httpx

from personae.conversation import Message

logger = logging.getLogger(__name__)

# A frame adds thousands of input tokens, so the first byte can take a while.
REQUEST_TIMEOUT = httpx.Timeout(120.0, connect=10.0)
MAX_TOKENS = 512


class AnthropicCompatibleLlm:
    """Character-voiced replies, optionally given a camera frame to look at."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        vision_model: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        # Vision often warrants a different, usually larger, model.
        self._vision_model = vision_model or model

    async def respond(
        self,
        system_prompt: str,
        transcript: str,
        history: Sequence[Message] = (),
        image: bytes | None = None,
    ) -> AsyncIterator[str]:
        content: list[dict[str, object]] = [{"type": "text", "text": transcript}]
        if image is not None:
            import base64

            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": base64.b64encode(image).decode("ascii"),
                    },
                }
            )

        payload = {
            "model": self._vision_model if image is not None else self._model,
            "max_tokens": MAX_TOKENS,
            "stream": True,
            "system": system_prompt,
            "messages": [*history, {"role": "user", "content": content}],
        }
        headers = {
            # The first-party API authenticates on x-api-key; gateways in front
            # of it commonly want the bearer form, so both are sent.
            "x-api-key": self._api_key,
            "Authorization": f"Bearer {self._api_key}",
            "anthropic-version": "2023-06-01",
        }

        async with (
            httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client,
            client.stream(
                "POST", f"{self._base_url}/messages", json=payload, headers=headers
            ) as response,
        ):
            response.raise_for_status()
            async for line in response.aiter_lines():
                fragment = _fragment_of(line)
                if fragment:
                    yield fragment


def _fragment_of(line: str) -> str:
    """Extract the text delta from one server-sent-events line.

    Anthropic streams typed events; only content_block_delta carries text. A
    malformed frame is skipped rather than raised, so one bad line cannot abort
    a reply that is otherwise streaming.
    """
    if not line.startswith("data:"):
        return ""
    data = line.removeprefix("data:").strip()
    if not data:
        return ""
    try:
        parsed = json.loads(data)
    except json.JSONDecodeError:
        logger.warning("discarding malformed stream frame")
        return ""
    if not isinstance(parsed, dict) or parsed.get("type") != "content_block_delta":
        return ""
    delta = parsed.get("delta")
    text = delta.get("text") if isinstance(delta, dict) else None
    return text if isinstance(text, str) else ""
