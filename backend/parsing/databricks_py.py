"""Parser for Databricks notebooks exported as source (.py)."""

from __future__ import annotations

import re

from .models import Cell, CellLang, Line

HEADER = "# Databricks notebook source"
SEPARATOR = "# COMMAND ----------"
MAGIC_PREFIX = re.compile(r"^# MAGIC ?")
TITLE = re.compile(r"^# DBTITLE \d+,(.*)$")

MAGIC_LANGS: dict[str, CellLang] = {
    "%python": "python",
    "%sql": "sql",
    "%md": "markdown",
    "%md-sandbox": "markdown",
    "%scala": "scala",
    "%r": "r",
    "%sh": "shell",
    "%run": "run",
}


def is_databricks_source(text: str) -> bool:
    return text.lstrip("﻿").startswith(HEADER)


def parse_databricks_py(text: str) -> list[Cell]:
    """Split a Databricks source file into cells, keeping each line's position in the file.

    Plain .py files without the Databricks header are treated as a single Python cell.
    """
    raw_lines = text.lstrip("﻿").splitlines()
    start = 1 if raw_lines and raw_lines[0].strip() == HEADER else 0

    chunks: list[list[tuple[int, str]]] = [[]]
    for file_line, raw in enumerate(raw_lines[start:], start=start + 1):
        if raw.strip() == SEPARATOR:
            chunks.append([])
        else:
            chunks[-1].append((file_line, raw))

    cells: list[Cell] = []
    for chunk in chunks:
        cell = _build_cell(chunk, index=len(cells) + 1)
        if cell is not None:
            cells.append(cell)
    return cells


def _build_cell(chunk: list[tuple[int, str]], index: int) -> Cell | None:
    title: str | None = None
    body: list[tuple[int, str]] = []
    for file_line, raw in chunk:
        if title is None and (m := TITLE.match(raw)):
            title = m.group(1).strip() or None
            continue
        body.append((file_line, raw))

    # Separators are surrounded by blank lines; they are not part of the cell.
    while body and not body[0][1].strip():
        body.pop(0)
    while body and not body[-1][1].strip():
        body.pop()
    if not body:
        return None

    is_magic = all(MAGIC_PREFIX.match(raw) or not raw.strip() for _, raw in body)
    lang: CellLang = "python"
    lines: list[Line] = []
    for cell_line, (file_line, raw) in enumerate(body, start=1):
        text = MAGIC_PREFIX.sub("", raw, count=1) if is_magic else raw
        lines.append(Line(cell_line=cell_line, file_line=file_line, text=text))

    if is_magic:
        first = lines[0].text.strip().split(maxsplit=1)
        lang = MAGIC_LANGS.get(first[0], "other") if first else "other"

    return Cell(index=index, lang=lang, title=title, lines=lines)
