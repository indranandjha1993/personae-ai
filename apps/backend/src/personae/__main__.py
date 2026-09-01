"""Run the server with ``python -m personae``.

Mirrors the documented uvicorn command so both entry points behave identically.
The sansio WebSocket implementation is required: the default one imports the
deprecated ``websockets.legacy`` module.
"""

import uvicorn


def main() -> None:
    uvicorn.run(
        "personae.main:app",
        host="127.0.0.1",
        port=8000,
        ws="websockets-sansio",
    )


if __name__ == "__main__":
    main()
