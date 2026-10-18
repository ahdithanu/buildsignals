from __future__ import annotations

import json
from email.message import Message
from pathlib import Path

import pytest

from app.services.ingestion.connectors import build_connector
from app.services.ingestion.connectors.base import ConnectorResponseError
from app.services.ingestion.connectors.ercot_mis import ErcotMisXlsxConnector
from tests.xlsx_builder import build_xlsx

ENDPOINT = "https://www.ercot.com/misapp/GetReports.do?reportTypeId=15933"
LATEST_DOC = "1281327706"  # GIS_Report_September2026, postDate 20261001 (newest GIS row)
DOWNLOAD_URL = (
    "https://www.ercot.com/misdownload/servlets/mirDownload"
    f"?mimic_duns=000000000&doclookupId={LATEST_DOC}"
)
_FIXTURES = Path(__file__).parent / "fixtures" / "ercot"


def _index_html() -> str:
    rows = json.loads((_FIXTURES / "gis_report_index_sample.json").read_text())["sampleRows"]
    cells = []
    for row in rows:
        cells.append(
            f"<tr><td class='labelOptional_ind'>{row['fileName']}</td>"
            f"<td><a href='{row['downloadPath']}'>xlsx</a></td></tr>"
        )
    return "<html><body><table>" + "".join(cells) + "</table></body></html>"


def _workbook_bytes() -> bytes:
    tabs = json.loads((_FIXTURES / "gis_report_tabs_sample.json").read_text())["tabs"]
    sheets: dict[str, list[list[object]]] = {}
    for name, tab in tabs.items():
        columns = tab["columns"]
        rows: list[list[object]] = [["NOTES: banner row before header"], list(columns)]
        rows.extend(list(r) for r in tab["sampleRows"])
        if name.endswith("Large Gen"):
            # A queued row with no approval milestone -> application stage.
            queued = [None] * len(columns)
            for header, value in {
                "INR": "99INR9999", "Project Name": "Queued Project", "County": "Travis",
                "Fuel": "SOL", "GIM Study Phase": "Screening Study", "Capacity (MW)": "100",
                "Projected COD": "46400",
            }.items():
                queued[columns.index(header)] = value
            rows.append(queued)
        sheets[name] = rows
    return build_xlsx(sheets)


class FakeHttpClient:
    def __init__(self, index_html: str, workbook: bytes) -> None:
        self._index = index_html.encode("latin-1")
        self._workbook = workbook
        self.calls: list[str] = []

    def get_bytes(self, url, *, max_bytes, params=None, headers=None):
        self.calls.append(url)
        if url == ENDPOINT:
            body = self._index
        elif url == DOWNLOAD_URL:
            body = self._workbook
        else:
            raise AssertionError(f"unexpected url: {url}")
        if len(body) > max_bytes:
            raise ConnectorResponseError("response exceeds maximum allowed size")
        message = Message()
        message["Content-Type"] = "application/octet-stream"
        return body, message


def _connector(**overrides) -> ErcotMisXlsxConnector:
    client = FakeHttpClient(_index_html(), _workbook_bytes())
    connector = ErcotMisXlsxConnector(ENDPOINT, http_client=client, **overrides)
    connector._fake = client  # type: ignore[attr-defined]
    return connector


def test_select_latest_filters_battery_family_and_picks_newest_gis():
    connector = _connector()
    latest = connector.select_latest(connector.parse_index(_index_html()))
    assert latest["doc_id"] == LATEST_DOC
    assert latest["descriptive"].startswith("GIS_Report")


def test_fetch_normalizes_interconnection_records_with_durable_inr():
    connector = _connector()
    records = list(connector.iter_records())

    # Every record carries a durable INR-based identity and ERCOT download URL.
    assert records and all(r["source_record_id"].startswith("ercot_mis:") for r in records)
    assert all(r["inr"] for r in records)
    assert all(r["source_url"] == DOWNLOAD_URL for r in records)
    assert connector._fake.calls == [ENDPOINT, DOWNLOAD_URL]  # index then one bounded download

    by_inr = {r["inr"]: r for r in records}
    # Large Gen sample row has an "Approved for Synchronization" date -> decision.
    assert by_inr["15INR0064b"]["stage"] == "decision"
    assert by_inr["15INR0064b"]["county"] == "Glasscock"
    assert by_inr["15INR0064b"]["projected_cod"] == "2026-12-03"  # Excel serial 46359
    # Crafted queued row -> application.
    assert by_inr["99INR9999"]["stage"] == "application"
    assert by_inr["99INR9999"]["event_type"] == "interconnection_queue_application"
    # Small Gen row present with its own identity + tab provenance.
    assert "22INR0596" in by_inr
    assert by_inr["22INR0596"]["tab"].endswith("Small Gen")


def test_pagination_is_bounded_and_checkpoint_advances():
    connector = _connector(page_size=2)
    first = connector.fetch()
    assert len(first.records) == 2 and first.has_more
    assert first.checkpoint == {"offset": 2}
    second = connector.fetch(first.checkpoint)
    assert second.metadata["total"] == len(list(_connector().iter_records()))
    assert second.metadata["report_period"] == "2026-10"


def test_max_records_caps_output():
    connector = _connector(max_records=1)
    records = list(connector.iter_records())
    assert len(records) == 1


def test_index_without_gis_documents_errors():
    client = FakeHttpClient("<html><body>no reports</body></html>", b"")
    connector = ErcotMisXlsxConnector(ENDPOINT, http_client=client)
    with pytest.raises(ConnectorResponseError, match="no GIS_Report"):
        list(connector.iter_records())


def test_factory_builds_ercot_connector():
    connector = build_connector("ercot_mis_xlsx", {"endpoint": ENDPOINT, "allowed_hosts": ["www.ercot.com"]})
    assert isinstance(connector, ErcotMisXlsxConnector)
    assert connector.report_type_id == "15933"
