"""The OpenAI-compatible client, exercised against a stub transport.

No credentials required: the point is that the streaming and parsing logic is
correct, not that a particular vendor is reachable.
"""

import httpx
import pytest

from personae.providers.openai_compat import OpenAiCompatibleLlm, _fragment_of


def _sse(*payloads: str) -> bytes:
    return "".join(f"data: {payload}\n\n" for payload in payloads).encode()


@pytest.fixture
def llm(monkeypatch: pytest.MonkeyPatch) -> OpenAiCompatibleLlm:
    body = _sse(
        '{"choices":[{"delta":{"content":"Hello"}}]}',
        '{"choices":[{"delta":{"content":" there"}}]}',
        "[DONE]",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-key"
        assert request.url.path.endswith("/chat/completions")
        return httpx.Response(200, content=body)

    original = httpx.AsyncClient

    def patched(**kwargs: object) -> httpx.AsyncClient:
        kwargs.pop("timeout", None)
        return original(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(httpx, "AsyncClient", patched)
    return OpenAiCompatibleLlm("https://example.invalid/v1", "test-key", "test-model")


async def test_streams_fragments_in_order(llm: OpenAiCompatibleLlm) -> None:
    fragments = [part async for part in llm.respond("You are C.", "hi")]
    assert "".join(fragments) == "Hello there"


def test_ignores_the_done_sentinel_and_blank_lines() -> None:
    assert _fragment_of("data: [DONE]") == ""
    assert _fragment_of("") == ""
    assert _fragment_of(": keep-alive") == ""


def test_skips_a_malformed_frame_rather_than_failing_the_reply() -> None:
    """One bad frame must not abort a reply that is otherwise streaming."""
    assert _fragment_of("data: {not json") == ""


def test_tolerates_frames_without_content() -> None:
    assert _fragment_of('data: {"choices":[{"delta":{}}]}') == ""
    assert _fragment_of('data: {"choices":[]}') == ""
