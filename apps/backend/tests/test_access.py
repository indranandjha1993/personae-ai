"""The socket spends metered credentials, so who may open it matters."""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from personae.main import create_app


def test_open_by_default_for_local_use() -> None:
    """With no token configured the endpoint stays usable out of the box."""
    with (
        TestClient(create_app()) as client,
        client.websocket_connect("/ws/live/bundled/seed") as socket,
    ):
        assert socket.receive_json()["type"] == "ready"


def test_a_configured_token_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERSONAE_ACCESS_TOKEN", "let-me-in")
    with (
        TestClient(create_app()) as client,
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/ws/live/bundled/seed") as socket,
    ):
        socket.receive_json()


def test_the_right_token_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERSONAE_ACCESS_TOKEN", "let-me-in")
    with (
        TestClient(create_app()) as client,
        client.websocket_connect("/ws/live/bundled/seed?token=let-me-in") as socket,
    ):
        assert socket.receive_json()["type"] == "ready"


def test_a_wrong_token_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERSONAE_ACCESS_TOKEN", "let-me-in")
    with (
        TestClient(create_app()) as client,
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/ws/live/bundled/seed?token=wrong") as socket,
    ):
        socket.receive_json()
