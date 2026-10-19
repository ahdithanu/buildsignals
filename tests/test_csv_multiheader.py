from pathlib import Path

import pytest

from app.services.ingestion.connectors import build_connector
from app.services.ingestion.connectors.csv import CSVConnector

FIXTURE = Path(__file__).parent / "fixtures" / "bps" / "place_sample.txt"


def test_skip_leading_lines_and_explicit_fieldnames_parse_multiheader_file():
    # The BPS place file has two header rows + a blank separator before data.
    fieldnames = [f"col{i}" for i in range(41)]
    connector = CSVConnector(
        str(FIXTURE), delimiter=",", encoding="latin-1",
        skip_leading_lines=3, fieldnames=fieldnames, page_size=100,
    )
    records = list(connector.iter_records())

    # All 5 trimmed data rows parse; none consumed as a header.
    assert len(records) == 5
    assert records[0]["col0"] == "2025" and records[0]["col16"] == "Abbeville"
    # Texas (state code 48) and Virginia (51) rows are present.
    states = {row["col1"] for row in records}
    assert "48" in states and "51" in states


def test_defaults_unchanged_without_new_options(tmp_path):
    path = tmp_path / "simple.csv"
    path.write_text("a,b\n1,2\n3,4\n")
    connector = CSVConnector(str(path))
    records = list(connector.iter_records())
    assert records == [{"a": "1", "b": "2"}, {"a": "3", "b": "4"}]


def test_factory_passes_skip_and_fieldnames():
    connector = build_connector("csv", {
        "source": str(FIXTURE), "delimiter": ",", "encoding": "latin-1",
        "skip_leading_lines": 3, "fieldnames": [f"col{i}" for i in range(41)],
    })
    assert isinstance(connector, CSVConnector)
    assert connector.skip_leading_lines == 3 and len(connector.fieldnames) == 41


def test_skip_leading_lines_rejects_negative():
    with pytest.raises(ValueError, match="skip_leading_lines"):
        CSVConnector("x.csv", skip_leading_lines=-1)
