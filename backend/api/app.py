from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from ..config import Settings, load_settings
from ..llm.client import CompletionFn
from ..pipeline.cache import DocumentCache
from ..pipeline.runs import RunManager
from .routes import router


def create_app(settings: Settings | None = None, completion_fn: CompletionFn | None = None) -> FastAPI:
    """Build the app. `completion_fn` replaces litellm.acompletion (used by tests)."""
    settings = settings or load_settings()
    app = FastAPI(title="Notebook Documentation Harness", version="0.1.0")
    app.state.settings = settings
    app.state.completion_fn = completion_fn
    app.state.notebooks = {}
    app.state.runs = RunManager(
        DocumentCache(settings.cache.dir, settings.cache.enabled),
        settings.generation.max_concurrency,
    )
    app.include_router(router)

    if settings.server.static_dir.is_dir():
        app.mount("/", StaticFiles(directory=settings.server.static_dir, html=True), name="frontend")
    else:

        @app.get("/", include_in_schema=False)
        async def index() -> dict[str, str]:
            return {"message": "Notebook Documentation Harness API. No frontend build found.", "docs": "/docs"}

    return app
