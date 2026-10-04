from backend.pipeline.models import DraftCitation
from backend.validation.citations import CitationValidator


def resolve(notebook, cell, quote):
    return CitationValidator(notebook).resolve_citation(DraftCitation(cell=cell, quote=quote))


def test_exact_single_line(notebook):
    c = resolve(notebook, 2, "TOL = 0.01")
    assert c.status == "verified"
    assert c.cell_lines == (1, 1)
    assert c.file_lines == (8, 8)


def test_partial_line_and_whitespace_differences(notebook):
    c = resolve(notebook, 3, 'filter(F.col("st")   ==  "O")')
    assert c.status == "verified"
    assert c.cell_lines == (4, 4)


def test_multi_line_skips_blank_lines(notebook):
    c = resolve(notebook, 3, 'from pyspark.sql import functions as F\nr = spark.read.parquet(SRC)')
    assert c.status == "verified"
    assert c.cell_lines == (1, 3)


def test_magic_prefix_in_quote_is_tolerated(notebook):
    c = resolve(notebook, 4, "# MAGIC WHERE abs(r.amt - i.amt) <= 0.01")
    assert c.status == "verified"
    assert c.cell_lines == (5, 5)
    assert c.file_lines == (24, 24)


def test_ellipsis_gap(notebook):
    c = resolve(notebook, 4, "CREATE OR REPLACE TEMP VIEW m AS\n...\nWHERE abs(r.amt - i.amt) <= 0.01")
    assert c.status == "verified"
    assert c.cell_lines == (2, 5)


def test_wrong_cell_is_relocated(notebook):
    c = resolve(notebook, 2, 'dropDuplicates(["rid"])')
    assert c.status == "relocated"
    assert c.cell == 5
    assert c.claimed_cell == 2


def test_invented_quote_is_not_found(notebook):
    c = resolve(notebook, 2, "TOLERANCE = 0.05")
    assert c.status == "not_found"
    assert c.cell_lines is None


def test_trivial_quote_is_rejected(notebook):
    assert resolve(notebook, 5, "x").status == "not_found"


def test_ambiguous_relocation_is_rejected(notebook):
    # "spark." appears in cells 3 and 5; it is not in cell 2.
    assert resolve(notebook, 2, "spark.").status == "not_found"


def test_match_count_reports_duplicates(notebook):
    c = resolve(notebook, 4, "r.amt")
    assert c.status == "verified"
    assert c.match_count == 2
