import io
import zipfile

import pytest

from app.services.ingestion.connectors import xlsx_reader
from tests.xlsx_builder import build_xlsx

BOUNDS = dict(
    max_total_uncompressed_bytes=64 * 1024 * 1024,
    max_bytes_per_part=16 * 1024 * 1024,
    max_rows=1000,
    max_cols=64,
    max_cell_chars=2000,
)


def test_reads_named_tab_with_shared_numeric_bool_cells():
    data = build_xlsx({
        "First": [["x"]],
        "Project Details - Large Gen": [
            ["INR", "Project Name", "Capacity (MW)", "Flag"],
            ["24INR0080", "Solar One", 162.1, True],
        ],
    })
    rows = xlsx_reader.read_tab(data, "Project Details - Large Gen", **BOUNDS)
    assert rows[0] == ["INR", "Project Name", "Capacity (MW)", "Flag"]
    assert rows[1] == ["24INR0080", "Solar One", "162.1", "1"]


def test_tab_match_is_case_and_whitespace_insensitive():
    data = build_xlsx({"Large  Gen": [["INR"], ["22INR0596"]]})
    rows = xlsx_reader.read_tab(data, "large gen", **BOUNDS)
    assert rows[1] == ["22INR0596"]


def test_sparse_cells_keep_column_position():
    # Only A and C are present; B must stay blank (not shift C into B).
    data = build_xlsx({"S": [["a", None, "c"]]})
    rows = xlsx_reader.read_tab(data, "S", **BOUNDS)
    assert rows[0] == ["a", None, "c"]


def test_missing_tab_required_raises_optional_returns_empty():
    data = build_xlsx({"Only": [["INR"]]})
    with pytest.raises(xlsx_reader.XlsxError):
        xlsx_reader.read_tab(data, "Absent", required=True, **BOUNDS)
    assert xlsx_reader.read_tab(data, "Absent", required=False, **BOUNDS) == []


def test_non_xlsx_bytes_raise():
    with pytest.raises(xlsx_reader.XlsxError):
        xlsx_reader.read_tab(b"not a zip", "S", **BOUNDS)


def test_zip_without_content_types_is_rejected():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("random.txt", "hello")
    with pytest.raises(xlsx_reader.XlsxError):
        xlsx_reader.read_tab(buffer.getvalue(), "S", **BOUNDS)


def test_column_index_decoding():
    assert xlsx_reader.column_index("A1") == 0
    assert xlsx_reader.column_index("C7") == 2
    assert xlsx_reader.column_index("AA1") == 26


def test_row_exceeding_max_cols_raises():
    data = build_xlsx({"S": [["a", "b", "c"]]})
    with pytest.raises(xlsx_reader.XlsxError):
        xlsx_reader.read_tab(data, "S", **{**BOUNDS, "max_cols": 2})
