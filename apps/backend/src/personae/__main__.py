"""Run the server with ``python -m personae``.

Loads server host, port and logging from the application environment settings.
The sansio WebSocket implementation is required: the default one imports the
deprecated ``websockets.legacy`` module.
"""

import uvicorn

from personae.settings import Settings


def main() -> None:
    settings = Settings()
    uvicorn.run(
        "personae.main:app",
        host=settings.server_host,
        port=settings.server_port,
        log_level=settings.log_level.lower(),
        ws="websockets-sansio",
    )


if __name__ == "__main__":
    main()
