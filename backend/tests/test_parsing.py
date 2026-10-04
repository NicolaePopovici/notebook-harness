import json

import pytest

from backend.config import LimitsConfig
from backend.parsing.databricks_py import parse_databricks_py
from backend.parsing.ipynb import parse_ipynb
from backend.parsing.loader import NotebookLoadError, load_notebook


def test_databricks_cells_langs_and_titles(notebook):
    assert [c.lang for c in notebook.cells] == ["markdown", "python", "python", "sql", "python"]
    assert notebook.cells[1].title == "Config"
    assert notebook.format == "databricks_py"


def test_title_line_is_not_part_of_cell(notebook):
    config = notebook.cells[1]
    assert config.lines[0].text == "TOL = 0.01"
    assert config.lines[0].cell_line == 1
    assert config.lines[0].file_line == 8


def test_magic_prefix_removed_but_file_lines_kept(notebook, sample_path):
    sql = notebook.cells[3]
    assert sql.lines[0].text == "%sql"
    file_lines = sample_path.read_text().splitlines()
    for line in sql.lines:
        assert file_lines[line.file_line - 1] == f"# MAGIC {line.text}"


def test_every_line_maps_back_to_the_file(notebook, sample_path):
    file_lines = sample_path.read_text().splitlines()
    for cell in notebook.cells:
        for line in cell.lines:
            assert file_lines[line.file_line - 1].endswith(line.text)


def test_plain_python_is_one_cell():
    cells = parse_databricks_py("a = 1\n\nb = 2\n")
    assert len(cells) == 1
    assert cells[0].lines[-1].file_line == 3


def test_ipynb():
    nb = {
        "metadata": {"language_info": {"name": "python"}},
        "cells": [
            {"cell_type": "markdown", "source": ["# Title\n"]},
            {"cell_type": "code", "source": ["%sql\n", "SELECT 1"]},
            {"cell_type": "code", "source": []},
            {"cell_type": "code", "source": "x = 1\ny = 2"},
        ],
    }
    cells = parse_ipynb(json.dumps(nb))
    assert [(c.index, c.lang) for c in cells] == [(1, "markdown"), (2, "sql"), (3, "python")]
    assert cells[2].lines[1].file_line is None


@pytest.mark.parametrize(
    "path, message",
    [
        ("relative.py", "absolute path"),
        ("/does/not/exist.py", "not found"),
    ],
)
def test_load_errors(path, message):
    with pytest.raises(NotebookLoadError, match=message):
        load_notebook(path, LimitsConfig())


def test_rejects_unsupported_suffix(tmp_path):
    f = tmp_path / "notes.txt"
    f.write_text("x")
    with pytest.raises(NotebookLoadError, match="Unsupported"):
        load_notebook(str(f), LimitsConfig())


def test_rejects_large_file(tmp_path):
    f = tmp_path / "big.py"
    f.write_text("x = 1\n" * 100)
    with pytest.raises(NotebookLoadError, match="limit"):
        load_notebook(str(f), LimitsConfig(max_notebook_bytes=10))
