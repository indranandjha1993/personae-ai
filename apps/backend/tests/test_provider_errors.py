"""A provider that refuses must say so.

An endpoint reporting a failure mid-stream looks exactly like a reply with
nothing in it, and reaches the listener as an unexplained silence.
"""

import pytest

from personae.providers.anthropic_compat import _fragment_of as anthropic_fragment
from personae.providers.base import ProviderError
from personae.providers.openai_compat import _fragment_of as openai_fragment


def test_an_anthropic_error_event_is_raised() -> None:
    line = (
        'data: {"type":"error","error":{"type":"authentication_error",'
        '"message":"OAuth session expired"}}'
    )
    with pytest.raises(ProviderError, match="OAuth session expired"):
        anthropic_fragment(line)


def test_an_openai_error_payload_is_raised() -> None:
    line = 'data: {"error":{"message":"insufficient quota","type":"insufficient_quota"}}'
    with pytest.raises(ProviderError, match="insufficient quota"):
        openai_fragment(line)


@pytest.mark.parametrize(
    "line",
    [
        'data: {"type":"content_block_delta","delta":{"text":"hello"}}',
        'data: {"type":"message_start","message":{}}',
        "data: [DONE]",
        "event: ping",
    ],
)
def test_ordinary_frames_still_pass_through(line: str) -> None:
    """Only a real error interrupts; everything else streams as before."""
    anthropic_fragment(line)
