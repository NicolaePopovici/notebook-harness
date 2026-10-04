"""Loads a notebook from the user's disk. The notebook is read, never executed."""

from __future__ import annotations

import hashlib
from pathlib import Path

from ..config import LimitsConfig
from .databricks_py import parse_databricks_py
from .ipynb import parse_ipynb
from .models import Notebook


class NotebookLoadError(ValueError):
    pass


def load_notebook(path_str: str, limits: LimitsConfig) -> Notebook:
    path = Path(path_str).expanduser()
    if not path.is_absolute():
        raise NotebookLoadError("Please give an absolute path to the notebook file.")
    path = path.resolve()
    if not path.is_file():
        raise NotebookLoadError(f"File not found: {path}")
    if path.suffix.lower() not in limits.allowed_suffixes:
        raise NotebookLoadError(
            f"Unsupported file type '{path.suffix}'. Supported: {', '.join(limits.allowed_suffixes)}"
        )
    size = path.stat().st_size
    if size > limits.max_notebook_bytes:
        raise NotebookLoadError(f"Notebook is {size} bytes; the limit is {limits.max_notebook_bytes}.")

    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise NotebookLoadError("Notebook is not valid UTF-8 text.") from exc
    return parse_notebook_text(text, path=str(path), suffix=path.suffix.lower(), raw=raw)


def parse_notebook_text(text: str, *, path: str, suffix: str, raw: bytes | None = None) -> Notebook:
    digest = hashlib.sha256(raw if raw is not None else text.encode()).hexdigest()
    if suffix == ".ipynb":
        try:
            cells = parse_ipynb(text)
        except ValueError as exc:
            raise NotebookLoadError(f"Invalid .ipynb file: {exc}") from exc
        fmt = "ipynb"
    else:
        cells = parse_databricks_py(text)
        fmt = "databricks_py"
    if not cells:
        raise NotebookLoadError("The notebook has no cells with code.")
    return Notebook(
        id=digest[:16],
        path=path,
        name=Path(path).name,
        format=fmt,
        sha256=digest,
        cells=cells,
    )
