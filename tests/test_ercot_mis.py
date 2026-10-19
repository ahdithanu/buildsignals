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


def _connector(*, index_html=None, workbook=None, **overrides) -> ErcotMisXlsxConnector:
    client = FakeHttpClient(
        _index_html() if index_html is None else index_html,
        _workbook_bytes() if workbook is None else workbook,
    )
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
    assert by_inr["15INR0064b"]["approval_stage"] == "approved"
    assert by_inr["15INR0064b"]["approved_synchronization"] == "2020-05-12"
    assert by_inr["15INR0064b"]["county"] == "Glasscock"
    assert by_inr["15INR0064b"]["projected_cod"] == "2026-12-03"  # Excel serial 46359
    # Crafted queued row -> application.
    assert by_inr["99INR9999"]["stage"] == "application"
    assert by_inr["99INR9999"]["event_type"] == "interconnection_queue_application"
    assert by_inr["99INR9999"]["approval_stage"] == "pre_approval"
    # This real fixture has completed studies, FIS approval and a signed IA,
    # but neither operator approval milestone. It is still an application.
    assert by_inr["16INR0049"]["status"] == "SS Completed, FIS Completed, IA"
    assert by_inr["16INR0049"]["stage"] == "application"
    assert by_inr["16INR0049"]["approved_synchronization"] is None
    assert by_inr["16INR0049"]["approved_energization"] is None
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
    assert second.metadata["report_period"] == "2026-09"
    assert second.metadata["post_date"] == "2026-10-01"


def _queue_workbook(status=None, synchronization=None, energization=None) -> bytes:
    return build_xlsx({"Project Details - Large Gen": [
        ["INR", "Project Name", "GIM Study Phase", "IA Signed",
         "Approved for Synchronization", "Approved for Energization"],
        ["26INR0001", "Queued generator", status, "46086", synchronization, energization],
    ]})


@pytest.mark.parametrize("status", [
    "SS Completed, FIS Completed, IA", "FIS Approved", "Screening Study Complete",
    "IA Executed", "Approved", "Complete", "Not Approved for Synchronization",
    "Not Energized", "Synchronization Pending", "Commercial Operation Pending",
    "Not In Service", "Withdrawn", "Cancelled", None,
])
def test_study_progression_and_nonterminal_statuses_remain_applications(status):
    record, = _connector(workbook=_queue_workbook(status=status)).iter_records()
    assert record["stage"] == "application"
    assert record["approval_stage"] == "pre_approval"
    assert record["event_type"] == "interconnection_queue_application"


@pytest.mark.parametrize("status", [
    "Synchronized", "Energized", "In Service", "In-Service", "Commercial Operation",
    "Commercial Operations", "  IN   SERVICE  ",
])
def test_only_exact_operating_statuses_are_decisions_without_approval_dates(status):
    record, = _connector(workbook=_queue_workbook(status=status)).iter_records()
    assert record["stage"] == "decision"
    assert record["approval_stage"] == "approved"
    assert record["event_type"] == "interconnection_queue_decision"


@pytest.mark.parametrize("field", ["synchronization", "energization"])
@pytest.mark.parametrize("value,expected", [("43963", "2020-05-12"), ("2026-09-01", "2026-09-01")])
def test_valid_operator_approval_dates_produce_decisions(field, value, expected):
    record, = _connector(workbook=_queue_workbook("FIS Approved", **{field: value})).iter_records()
    assert record["stage"] == "decision"
    assert record[f"approved_{field}"] == expected


@pytest.mark.parametrize("placeholder", [
    "Yes", "No", "Not Required", "TBD", "0", "-1", "nan", "inf", "2026-02-30", "invalid",
])
def test_nondate_operator_approval_values_do_not_produce_decisions(placeholder):
    workbook = _queue_workbook("FIS Approved", placeholder, placeholder)
    record, = _connector(workbook=workbook).iter_records()
    assert record["stage"] == "application"
    assert record["approved_synchronization"] is None
    assert record["approved_energization"] is None


@pytest.mark.parametrize("label,period", [
    ("GIS_Report_September2026", "2026-09"),
    ("GIS_Report_October2026", "2026-10"),
    ("GIS_Report_April_2024", "2024-04"),
    ("GIS_Report_Jun2026", "2026-06"),
    ("GIS_Report_September2026_revised", "2026-09"),
    ("GIS_Report_Sept_2026_Corrected", "2026-09"),
    ("GIS_Report_Sep2026_CORRECTION", "2026-09"),
])
def test_reporting_period_uses_label_while_retaining_publication_date(label, period):
    index = _index_html().replace("GIS_Report_September2026", label)
    envelope = _connector(index_html=index).fetch()
    assert envelope.metadata["report_period"] == period
    assert envelope.metadata["post_date"] == "2026-10-01"
    assert envelope.records
    assert all(record["report_period"] == period for record in envelope.records)
    assert all(record["post_date"] == "2026-10-01" for record in envelope.records)
    assert all(record["report_label"] == label for record in envelope.records)


@pytest.mark.parametrize("label", ["GIS_Report_unknown", "GIS_Report_Septober2026", "GIS_Report_2026"])
def test_unknown_report_period_is_rejected_instead_of_using_publication_month(label):
    index = _index_html().replace("GIS_Report_September2026", label)
    with pytest.raises(ConnectorResponseError, match="report label"):
        _connector(index_html=index).fetch()


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
