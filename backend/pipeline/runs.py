"""Background generation runs with an event log that SSE clients can replay and follow."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from ..llm.client import LLMClient, LLMError
from ..parsing.models import Notebook
from . import prompts
from .cache import DocumentCache
from .generate import generate_document
from .models import Audience, Document

log = logging.getLogger(__name__)

RunStatus = Literal["pending", "running", "completed", "failed"]
EventType = Literal["run_started", "progress", "document_ready", "document_failed", "run_finished"]


class RunEvent(BaseModel):
    seq: int
    type: EventType
    audience: Audience | None = None
    message: str = ""
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Run(BaseModel):
    id: str
    notebook_id: str
    provider: str
    model: str
    audiences: list[Audience]
    status: RunStatus = "pending"
    documents: dict[Audience, Document] = Field(default_factory=dict)
    errors: dict[Audience, str] = Field(default_factory=dict)
    events: list[RunEvent] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None

    @property
    def done(self) -> bool:
        return self.status in ("completed", "failed")


class RunManager:
    def __init__(self, cache: DocumentCache, max_concurrency: int):
        self.cache = cache
        self.runs: dict[str, Run] = {}
        self._semaphore = asyncio.Semaphore(max(1, max_concurrency))
        self._changed: dict[str, asyncio.Condition] = {}
        self._tasks: set[asyncio.Task] = set()

    def start(self, notebook: Notebook, audiences: list[Audience], client: LLMClient, force: bool = False) -> Run:
        run = Run(
            id=uuid.uuid4().hex[:12],
            notebook_id=notebook.id,
            provider=client.provider_name,
            model=client.model,
            audiences=audiences,
        )
        self.runs[run.id] = run
        self._changed[run.id] = asyncio.Condition()
        task = asyncio.create_task(self._execute(run, notebook, client, force))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return run

    async def _emit(self, run: Run, type: EventType, message: str = "", audience: Audience | None = None) -> None:
        run.events.append(RunEvent(seq=len(run.events), type=type, audience=audience, message=message))
        async with self._changed[run.id]:
            self._changed[run.id].notify_all()

    async def _execute(self, run: Run, notebook: Notebook, client: LLMClient, force: bool) -> None:
        run.status = "running"
        await self._emit(run, "run_started", f"Generating {len(run.audiences)} document(s) with {client.model}")
        await asyncio.gather(*(self._one(run, notebook, client, a, force) for a in run.audiences))
        run.status = "completed" if run.documents else "failed"
        run.finished_at = datetime.now(UTC)
        await self._emit(run, "run_finished", run.status)

    async def _one(self, run: Run, notebook: Notebook, client: LLMClient, audience: Audience, force: bool) -> None:
        if not force and (cached := self.cache.get(notebook.sha256, audience, client.model, prompts.PROMPT_VERSION)):
            run.documents[audience] = cached
            await self._emit(run, "document_ready", "Loaded from cache", audience)
            return

        async def progress(message: str) -> None:
            await self._emit(run, "progress", message, audience)

        try:
            async with self._semaphore:
                document = await generate_document(notebook, audience, client, progress)
        except LLMError as exc:
            run.errors[audience] = str(exc)
            await self._emit(run, "document_failed", str(exc), audience)
            return
        except Exception as exc:
            log.exception("Generating %s document failed", audience.value)
            run.errors[audience] = f"Unexpected error: {exc}"
            await self._emit(run, "document_failed", run.errors[audience], audience)
            return

        self.cache.put(document)
        run.documents[audience] = document
        v = document.validation
        await self._emit(
            run,
            "document_ready",
            f"{v.claims_verified}/{v.claims_total} claims verified, {v.claims_unverified} unverified",
            audience,
        )

    async def follow(self, run_id: str) -> AsyncIterator[RunEvent]:
        """Yield every event of the run, past and future, until it finishes."""
        run = self.runs[run_id]
        condition = self._changed[run_id]
        sent = 0
        while True:
            while sent < len(run.events):
                yield run.events[sent]
                sent += 1
            if run.done:
                return
            async with condition:
                if sent >= len(run.events) and not run.done:
                    await condition.wait()
