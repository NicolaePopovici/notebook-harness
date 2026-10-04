"""Formats a notebook for the prompt. Line numbers are deliberately left out: the model quotes, it does not count."""

from __future__ import annotations

from ..parsing.models import Cell, Notebook


def render_cell(cell: Cell) -> str:
    title = f' · "{cell.title}"' if cell.title else ""
    return f"=== CELL {cell.index} · {cell.lang}{title} ===\n{cell.source}"


def render_notebook(notebook: Notebook) -> str:
    cells = "\n\n".join(render_cell(c) for c in notebook.cells)
    return f"Notebook: {notebook.name} ({len(notebook.cells)} cells)\n\n{cells}\n\n=== END OF NOTEBOOK ==="
