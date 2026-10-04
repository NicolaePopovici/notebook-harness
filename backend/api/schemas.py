from __future__ import annotations

from pydantic import BaseModel, Field

from ..parsing.models import CellLang, Line, Notebook, NotebookFormat
from ..pipeline.models import Audience


class OpenNotebookRequest(BaseModel):
    path: str = Field(description="Absolute path to a .py (Databricks source) or .ipynb file on this machine.")


class CellSummary(BaseModel):
    index: int
    lang: CellLang
    title: str | None
    line_count: int
    file_lines: tuple[int, int] | None


class NotebookSummary(BaseModel):
    id: str
    path: str
    name: str
    format: NotebookFormat
    sha256: str
    cells: list[CellSummary]

    @classmethod
    def of(cls, notebook: Notebook) -> NotebookSummary:
        cells = []
        for cell in notebook.cells:
            first, last = cell.lines[0].file_line, cell.lines[-1].file_line
            cells.append(
                CellSummary(
                    index=cell.index,
                    lang=cell.lang,
                    title=cell.title,
                    line_count=len(cell.lines),
                    file_lines=(first, last) if first is not None and last is not None else None,
                )
            )
        return cls(**notebook.model_dump(include={"id", "path", "name", "format", "sha256"}), cells=cells)


class CodeLine(Line):
    highlighted: bool = False


class CellCode(BaseModel):
    notebook_id: str
    index: int
    lang: CellLang
    title: str | None
    highlight: tuple[int, int] | None
    lines: list[CodeLine]


class StartRunRequest(BaseModel):
    audiences: list[Audience] = Field(default_factory=lambda: list(Audience))
    provider: str | None = Field(default=None, description="Provider name from harness.yaml; defaults to the configured one.")
    force: bool = Field(default=False, description="Regenerate even if a cached document exists.")


class StartRunResponse(BaseModel):
    run_id: str


class ProviderInfo(BaseModel):
    name: str
    model: str
    default: bool
    configured: bool
    api_key_env: str | None
    api_base: str | None
