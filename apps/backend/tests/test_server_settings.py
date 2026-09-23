"""The Python entry point honors validated server configuration."""

from unittest.mock import patch

import pytest

from personae.__main__ import main
from personae.settings import Settings


def test_server_defaults() -> None:
    settings = Settings()
    assert (settings.server_host, settings.server_port, settings.log_level) == (
        "127.0.0.1",
        8000,
        "INFO",
    )


def test_entry_point_uses_server_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERSONAE_SERVER_HOST", "0.0.0.0")
    monkeypatch.setenv("PERSONAE_SERVER_PORT", "8100")
    monkeypatch.setenv("PERSONAE_LOG_LEVEL", "WARNING")
    with patch("personae.__main__.uvicorn.run") as run:
        main()
    run.assert_called_once_with(
        "personae.main:app",
        host="0.0.0.0",
        port=8100,
        log_level="warning",
        ws="websockets-sansio",
    )


@pytest.mark.parametrize("port", [0, 65536])
def test_invalid_server_port(port: int) -> None:
    with pytest.raises(ValueError, match="server_port"):
        Settings(server_port=port)
