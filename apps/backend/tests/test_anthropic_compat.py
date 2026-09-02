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


SENT_HEADERS: dict[str, str] = {}


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    seen: list[dict[str, object]] = []
    SENT_HEADERS.clear()

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        SENT_HEADERS.update(request.headers)
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


async def test_sends_the_api_key_header_anthropic_expects(
    captured: list[dict[str, object]],
) -> None:
    """api.anthropic.com authenticates on x-api-key; Bearer alone gets a 401."""
    llm = AnthropicCompatibleLlm("https://example.invalid/v1", "secret", "m")
    async for _ in llm.respond("You are C.", "hi"):
        pass

    assert SENT_HEADERS["x-api-key"] == "secret"
    # Gateways in front of the API often want the bearer form as well.
    assert SENT_HEADERS["authorization"] == "Bearer secret"


async def test_vision_can_use_a_different_model(captured: list[dict[str, object]]) -> None:
    """A frame often warrants a larger model than plain conversation."""
    llm = AnthropicCompatibleLlm("https://example.invalid/v1", "k", "text-model", "vision-model")
    async for _ in llm.respond("You are C.", "hi"):
        pass
    assert captured[0]["model"] == "text-model"

    async for _ in llm.respond("You are C.", "what is this?", image=b"\xff\xd8jpeg"):
        pass
    assert captured[1]["model"] == "vision-model"


async def test_the_character_is_marked_cacheable(captured: list[dict[str, object]]) -> None:
    """Her character is over a thousand tokens and identical every turn.

    Prefill dominates the wait before she starts speaking, so it is sent in
    the cacheable form. An endpoint that does not understand the annotation
    ignores it, so there is no cost to sending it always.
    """
    llm = AnthropicCompatibleLlm("http://x/v1", "k", "haiku")
    async for _ in llm.respond("you are Wren", "hello"):
        pass

    system = captured[0]["system"]
    assert isinstance(system, list)
    assert system[0]["text"] == "you are Wren"
    assert system[0]["cache_control"] == {"type": "ephemeral"}
