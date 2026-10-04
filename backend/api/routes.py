from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from ..config import Settings
from ..llm.client import CompletionFn, ContextTooLargeError, LLMClient
from ..parsing.loader import NotebookLoadError, load_notebook
from ..parsing.models import Notebook
from ..pipeline.generate import build_prompt
from ..pipeline.models import DraftDocument
from ..pipeline.runs import Run, RunManager
from .schemas import (
    CellCode,
    CodeLine,
    NotebookSummary,
    OpenNotebookRequest,
    ProviderInfo,
    StartRunRequest,
    StartRunResponse,
)

router = APIRouter(prefix="/api")


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _runs(request: Request) -> RunManager:
    return request.app.state.runs


def _notebook(request: Request, notebook_id: str) -> Notebook:
    notebook = request.app.state.notebooks.get(notebook_id)
    if notebook is None:
        raise HTTPException(404, f"Notebook {notebook_id} is not open. Open it again with POST /api/notebooks.")
    return notebook


def _run(request: Request, run_id: str) -> Run:
    run = _runs(request).runs.get(run_id)
    if run is None:
        raise HTTPException(404, f"Run {run_id} not found.")
    return run


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/providers", response_model=list[ProviderInfo])
async def list_providers(request: Request) -> list[ProviderInfo]:
    settings = _settings(request)
    return [
        ProviderInfo(
            name=name,
            model=cfg.model,
            default=name == settings.provider,
            configured=cfg.is_configured(),
            api_key_env=cfg.api_key_env,
            api_base=cfg.api_base,
        )
        for name, cfg in settings.providers.items()
    ]


@router.post("/notebooks", response_model=NotebookSummary)
async def open_notebook(body: OpenNotebookRequest, request: Request) -> NotebookSummary:
    try:
        notebook = load_notebook(body.path, _settings(request).limits)
    except NotebookLoadError as exc:
        raise HTTPException(400, str(exc)) from exc
    request.app.state.notebooks[notebook.id] = notebook
    return NotebookSummary.of(notebook)


@router.get("/notebooks/{notebook_id}", response_model=Notebook)
async def get_notebook(notebook_id: str, request: Request) -> Notebook:
    return _notebook(request, notebook_id)


@router.get("/notebooks/{notebook_id}/cells/{index}", response_model=CellCode)
async def get_cell(
    notebook_id: str,
    index: int,
    request: Request,
    start: int | None = Query(default=None, ge=1, description="First cell line to highlight."),
    end: int | None = Query(default=None, ge=1, description="Last cell line to highlight."),
) -> CellCode:
    notebook = _notebook(request, notebook_id)
    cell = notebook.cell(index)
    if cell is None:
        raise HTTPException(404, f"Cell {index} not found; the notebook has {len(notebook.cells)} cells.")
    highlight = None
    if start is not None:
        end = end or start
        if end < start or end > len(cell.lines):
            raise HTTPException(400, f"Line range {start}-{end} is outside cell {index} (1-{len(cell.lines)}).")
        highlight = (start, end)
    lines = [
        CodeLine(**line.model_dump(), highlighted=highlight is not None and highlight[0] <= line.cell_line <= highlight[1])
        for line in cell.lines
    ]
    return CellCode(notebook_id=notebook_id, index=index, lang=cell.lang, title=cell.title, highlight=highlight, lines=lines)


@router.post("/notebooks/{notebook_id}/runs", response_model=StartRunResponse, status_code=202)
async def start_run(notebook_id: str, body: StartRunRequest, request: Request) -> StartRunResponse:
    notebook = _notebook(request, notebook_id)
    settings = _settings(request)
    try:
        name, provider = settings.get_provider(body.provider)
    except KeyError as exc:
        raise HTTPException(400, str(exc.args[0])) from exc
    if not provider.is_configured():
        raise HTTPException(400, f"Provider '{name}' needs the {provider.api_key_env} environment variable.")
    if not body.audiences:
        raise HTTPException(400, "Choose at least one audience.")

    completion_fn: CompletionFn | None = request.app.state.completion_fn
    client = LLMClient(name, provider, settings.generation, completion_fn)
    # Fail before starting if the notebook can't fit, rather than three times in the background.
    for audience in body.audiences:
        try:
            client.check_fits(*build_prompt(notebook, audience), output=DraftDocument)
        except ContextTooLargeError as exc:
            raise HTTPException(400, f"{notebook.name} is too large for {name}: {exc}") from exc
    run = _runs(request).start(notebook, list(dict.fromkeys(body.audiences)), client, force=body.force)
    return StartRunResponse(run_id=run.id)


@router.get("/runs/{run_id}", response_model=Run)
async def get_run(run_id: str, request: Request) -> Run:
    return _run(request, run_id)


@router.get("/runs/{run_id}/events")
async def run_events(run_id: str, request: Request) -> StreamingResponse:
    _run(request, run_id)
    runs = _runs(request)

    async def stream():
        async for event in runs.follow(run_id):
            if await request.is_disconnected():
                return
            data = json.dumps(event.model_dump(mode="json"))
            yield f"id: {event.seq}\nevent: {event.type}\ndata: {data}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
