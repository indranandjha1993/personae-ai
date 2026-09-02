"""The Anthropic-shaped client, exercised against a stub transport."""

import base64
import json

import httpx
import pytest

from personae.providers.anthropic_compat import AnthropicCompatibleLlm, _fragment_of


def _stream(*deltas: str) -> bytes:
    lines = [
        f"data: {json.dumps({'type': 'content_block_delta', 'delta': {'text': d}})}\n\n"
        for d in deltas
    ]
    return "".join(lines).encode()


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        assert request.url.path.endswith("/messages")
        return httpx.Response(200, content=_stream("Hello", " there"))

    original = httpx.AsyncClient

    def patched(**kwargs: object) -> httpx.AsyncClient:
        kwargs.pop("timeout", None)
        return original(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(httpx, "AsyncClient", patched)
    return seen


async def test_streams_text_deltas_in_order(captured: list[dict[str, object]]) -> None:
    llm = AnthropicCompatibleLlm("https://example.invalid/v1", "k", "m")
    parts = [p async for p in llm.respond("You are C.", "hi")]
    assert "".join(parts) == "Hello there"


async def test_sends_a_camera_frame_as_an_image_block(
    captured: list[dict[str, object]],
) -> None:
    """Vision is why this wire format exists; the frame must reach the model."""
    llm = AnthropicCompatibleLlm("https://example.invalid/v1", "k", "m")
    frame = b"\xff\xd8\xff\xe0jpegbytes"
    async for _ in llm.respond("You are C.", "what is this?", image=frame):
        pass

    content = captured[0]["messages"][-1]["content"]  # type: ignore[index]
    blocks = {block["type"] for block in content}
    assert blocks == {"text", "image"}
    image_block = next(b for b in content if b["type"] == "image")
    assert base64.b64decode(image_block["source"]["data"]) == frame


async def test_omits_the_image_block_when_no_frame_is_given(
    captured: list[dict[str, object]],
) -> None:
    llm = AnthropicCompatibleLlm("https://example.invalid/v1", "k", "m")
    async for _ in llm.respond("You are C.", "hello"):
        pass
    content = captured[0]["messages"][-1]["content"]  # type: ignore[index]
    assert {block["type"] for block in content} == {"text"}


def test_ignores_events_that_are_not_text_deltas() -> None:
    assert _fragment_of('data: {"type":"message_start"}') == ""
    assert _fragment_of('data: {"type":"content_block_delta","delta":{}}') == ""
    assert _fragment_of("data: {not json") == ""
    assert _fragment_of("event: ping") == ""
