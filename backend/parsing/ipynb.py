"""Parser for Jupyter notebooks (.ipynb), including Databricks-exported ones."""

from __future__ import annotations

import json
from typing import Any

from .databricks_py import MAGIC_LANGS
from .models import Cell, CellLang, Line


def parse_ipynb(text: str) -> list[Cell]:
    data = json.loads(text)
    default_lang = _default_lang(data)
    cells: list[Cell] = []
    for raw in data.get("cells", []):
        source = raw.get("source", "")
        if isinstance(source, list):
            source = "".join(source)
        line_texts = source.splitlines()
        if not any(t.strip() for t in line_texts):
            continue

        if raw.get("cell_type") == "markdown":
            lang: CellLang = "markdown"
        else:
            first = line_texts[0].strip().split(maxsplit=1)
            lang = MAGIC_LANGS.get(first[0], default_lang) if first else default_lang

        title = (raw.get("metadata") or {}).get("application/vnd.databricks.v1+cell", {}).get("title") or None
        lines = [Line(cell_line=i, file_line=None, text=t) for i, t in enumerate(line_texts, start=1)]
        cells.append(Cell(index=len(cells) + 1, lang=lang, title=title, lines=lines))
    return cells


def _default_lang(data: dict[str, Any]) -> CellLang:
    name = ((data.get("metadata") or {}).get("language_info") or {}).get("name", "python").lower()
    return {"python": "python", "sql": "sql", "scala": "scala", "r": "r"}.get(name, "other")  # type: ignore[return-value]
