"""The application must start and serve without credentials."""

from fastapi.testclient import TestClient

from personae.main import create_app


def test_health_reports_provider_modes() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "providers": {"stt": "mock", "llm": "mock", "tts": "mock"},
        "characters": 3,
    }
