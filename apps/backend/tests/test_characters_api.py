"""The bundled characters must be discoverable over HTTP without credentials."""

from fastapi.testclient import TestClient

from personae.main import create_app


def test_lists_bundled_characters() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/characters")
    assert response.status_code == 200
    body = response.json()
    ids = [c["id"] for c in body["characters"]]
    assert "bundled/seed" in ids


def test_character_summary_excludes_the_persona_prompt() -> None:
    """The system prompt is server-side detail and must not leak to clients."""
    with TestClient(create_app()) as client:
        body = client.get("/characters").json()
    entry = next(c for c in body["characters"] if c["id"] == "bundled/seed")
    assert entry["display_name"] == "Wren"
    assert entry["theme"]["primary"] == "#8b7fd4"
    assert "idle" in entry["expression"]["gestures"]
    assert "persona" not in entry
    assert "prompt" not in entry
