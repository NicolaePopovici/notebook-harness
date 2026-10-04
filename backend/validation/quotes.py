"""Finds a model-supplied quote in the notebook and works out its line range.

The model never gives line numbers: it copies code, and this module finds it.
Matching ignores whitespace differences and blank lines, and treats "..." as a gap.
"""

from __future__ import annotations

import bisect
import re
from dataclasses import dataclass

from ..parsing.databricks_py import MAGIC_PREFIX
from ..parsing.models import Cell

ELLIPSIS = re.compile(r"\s*(?:\.\.\.|…)\s*")
CODE_FENCE = re.compile(r"^\s*```[\w-]*\s*$")
# Longest span (in lines) a quote with "..." gaps may cover.
MAX_GAP_SPAN = 40


@dataclass(frozen=True)
class QuoteMatch:
    cell_index: int
    cell_lines: tuple[int, int]
    file_lines: tuple[int, int] | None
    match_count: int


def _norm(text: str) -> str:
    return " ".join(text.split())


def _normalize_quote(quote: str) -> list[str]:
    lines = []
    for raw in quote.splitlines():
        if CODE_FENCE.match(raw):
            continue
        norm = _norm(MAGIC_PREFIX.sub("", raw.strip(), count=1))
        if norm:
            lines.append(norm)
    return lines


class _CellIndex:
    """Cell text with blank lines removed, joined by newlines, plus a map from character offset to line."""

    def __init__(self, cell: Cell):
        self.cell = cell
        self.starts: list[int] = []
        self.cell_lines: list[int] = []
        parts: list[str] = []
        offset = 0
        for line in cell.lines:
            norm = _norm(line.text)
            if not norm:
                continue
            self.starts.append(offset)
            self.cell_lines.append(line.cell_line)
            parts.append(norm)
            offset += len(norm) + 1
        self.text = "\n".join(parts)

    def line_at(self, offset: int) -> int:
        return self.cell_lines[bisect.bisect_right(self.starts, offset) - 1]

    def find_spans(self, fragments: list[str]) -> list[tuple[int, int]]:
        """All (start_line, end_line) spans where the fragments appear in order."""
        spans = []
        start = self.text.find(fragments[0])
        while start != -1:
            end = start + len(fragments[0])
            ok = True
            for frag in fragments[1:]:
                pos = self.text.find(frag, end)
                if pos == -1:
                    ok = False
                    break
                end = pos + len(frag)
            if ok:
                span = (self.line_at(start), self.line_at(end - 1))
                if len(fragments) == 1 or span[1] - span[0] < MAX_GAP_SPAN:
                    spans.append(span)
            start = self.text.find(fragments[0], start + 1)
        return spans


def _fragments(quote: str) -> list[str]:
    needle = "\n".join(_normalize_quote(quote))
    return [f.strip() for f in ELLIPSIS.split(needle) if f.strip()]


def _to_match(index: _CellIndex, spans: list[tuple[int, int]]) -> QuoteMatch:
    start, end = spans[0]
    cell = index.cell
    file_start = cell.lines[start - 1].file_line
    file_end = cell.lines[end - 1].file_line
    file_lines = (file_start, file_end) if file_start is not None and file_end is not None else None
    return QuoteMatch(cell_index=cell.index, cell_lines=(start, end), file_lines=file_lines, match_count=len(spans))


class QuoteLocator:
    def __init__(self, cells: list[Cell]):
        self._indexes = {cell.index: _CellIndex(cell) for cell in cells}

    def locate(self, cell_index: int, quote: str) -> QuoteMatch | None:
        """Find the quote in the named cell. Returns None if it isn't there."""
        fragments = _fragments(quote)
        index = self._indexes.get(cell_index)
        if not fragments or index is None:
            return None
        spans = index.find_spans(fragments)
        return _to_match(index, spans) if spans else None

    def locate_elsewhere(self, quote: str, exclude: int) -> QuoteMatch | None:
        """Find the quote in another cell, only if exactly one cell contains it."""
        fragments = _fragments(quote)
        if not fragments:
            return None
        found = []
        for index in self._indexes.values():
            if index.cell.index == exclude:
                continue
            if spans := index.find_spans(fragments):
                found.append(_to_match(index, spans))
        return found[0] if len(found) == 1 else None
