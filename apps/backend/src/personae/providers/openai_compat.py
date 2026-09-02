"""Streaming chat completions against any OpenAI-compatible endpoint.

Uses httpx directly rather than a vendor SDK: this is one well-specified
endpoint, and depending on a client library here would tie the project to a
particular provider's release cycle for no benefit.
"""

import json
import logging
from collections.abc import AsyncIterator, Sequence

import httpx

from personae.conversation import Message
from personae.providers.base import ProviderError

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = httpx.Timeout(60.0, connect=10.0)


class OpenAiCompatibleLlm:
    """Character-voiced replies, streamed as server-sent events."""

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model

    async def respond(
        self,
        system_prompt: str,
        transcript: str,
        history: Sequence[Message] = (),
        image: bytes | None = None,
    ) -> AsyncIterator[str]:
        if image is not None:
            logger.warning(
                "this endpoint's wire format carries no image; set "
                "PERSONAE_LLM_WIRE=anthropic to enable vision"
            )
        payload = {
            "model": self._model,
            "stream": True,
            "messages": [
                {"role": "system", "content": system_prompt},
                *history,
                {"role": "user", "content": transcript},
            ],
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}

        async with (
            httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client,
            client.stream(
                "POST",
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=headers,
            ) as response,
        ):
            response.raise_for_status()
            async for line in response.aiter_lines():
                fragment = _fragment_of(line)
                if fragment:
                    yield fragment


def _fragment_of(line: str) -> str:
    """Extract the text delta from one server-sent-events line.

    Malformed or unexpected payloads are skipped rather than raised: a single
    bad frame should not abort a reply that is otherwise streaming fine.
    """
    if not line.startswith("data:"):
        return ""
    data = line.removeprefix("data:").strip()
    if not data or data == "[DONE]":
        return ""
    try:
        parsed = json.loads(data)
    except json.JSONDecodeError:
        logger.warning("discarding malformed stream frame")
        return ""
    if not isinstance(parsed, dict):
        return ""
    # A failure reported mid-stream would otherwise be indistinguishable from
    # a reply that simply had nothing in it.
    if "error" in parsed:
        detail = parsed["error"]
        message = detail.get("message") if isinstance(detail, dict) else str(detail)
        raise ProviderError(message or "the model reported an error")
    choices = parsed.get("choices")
    if not choices:
        return ""
    delta = choices[0].get("delta") if isinstance(choices[0], dict) else None
    content = delta.get("content") if isinstance(delta, dict) else None
    return content if isinstance(content, str) else ""
