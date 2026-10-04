from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

CellLang = Literal["python", "sql", "markdown", "scala", "r", "shell", "run", "other"]
NotebookFormat = Literal["databricks_py", "ipynb"]


class Line(BaseModel):
    # 1-based line number within the cell.
    cell_line: int
    # 1-based line number in the notebook file; None when the format has no stable file lines (ipynb).
    file_line: int | None
    # Code as a reader sees it (Databricks "# MAGIC " prefix removed).
    text: str


class Cell(BaseModel):
    # 1-based cell number, as shown in the Databricks UI.
    index: int
    lang: CellLang
    title: str | None = None
    lines: list[Line]

    @property
    def source(self) -> str:
        return "\n".join(line.text for line in self.lines)


class Notebook(BaseModel):
    id: str
    path: str
    name: str
    format: NotebookFormat
    sha256: str
    cells: list[Cell]

    def cell(self, index: int) -> Cell | None:
        if 1 <= index <= len(self.cells):
            return self.cells[index - 1]
        return None
