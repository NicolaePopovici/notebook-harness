"""Entry point for `uv run harness`."""

from __future__ import annotations

import logging
import threading
import webbrowser

import uvicorn

from .api.app import create_app
from .config import load_settings


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = load_settings()
    name, provider = settings.get_provider()
    url = f"http://{settings.server.host}:{settings.server.port}"
    logging.getLogger("harness").info("Provider: %s (%s). Open %s", name, provider.model, url)
    if not provider.is_configured():
        logging.getLogger("harness").warning("Provider '%s' needs %s to be set.", name, provider.api_key_env)

    if settings.server.open_browser:
        threading.Timer(1.5, webbrowser.open, args=[url]).start()
    uvicorn.run(create_app(settings), host=settings.server.host, port=settings.server.port)


if __name__ == "__main__":
    main()
