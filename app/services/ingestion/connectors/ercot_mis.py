"""ERCOT Monthly GIS (generator interconnection) report connector.

Two-step, bounded, stdlib-only: resolve the newest ``GIS_Report`` document from
the public MIS ``GetReports`` HTML index (reportTypeId 15933 on ``www.ercot.com``),
download that month's XLSX through the shared host-pinned HTTP client, and parse
the Large/Small Gen tabs into evidence-backed interconnection-request records.
Each row keeps its durable ``INR`` identity; stage is derived application vs
decision from milestone/status columns. Interconnection requests are not building
permits — ``event_type``/``stage`` carry the true semantics.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urljoin, urlsplit

from . import xlsx_reader
from .base import (
    BaseConnector,
    Checkpoint,
    ConnectorResponseError,
    FetchEnvelope,
    HttpClient,
    RetryingHttpClient,
    checkpoint_offset,
)

_EXCEL_EPOCH = date(1899, 12, 30)
# Study completion/approval and an executed IA are still queue progression.
# Only exact, realized operating statuses may substitute for an approval date;
# substrings would also match pending/negated milestones and study phases.
_DECISION_STATUSES = frozenset({
    "synchronized", "energized", "in service", "in-service",
    "commercial operation", "commercial operations",
})
_REPORT_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2,
    "march": 3, "mar": 3, "april": 4, "apr": 4, "may": 5,
    "june": 6, "jun": 6, "july": 7, "jul": 7, "august": 8, "aug": 8,
    "september": 9, "sept": 9, "sep": 9, "october": 10, "oct": 10,
    "november": 11, "nov": 11, "december": 12, "dec": 12,
}


def _report_period(label: str) -> str:
    """Use the described report month, independently of its publication date."""
    match = re.fullmatch(
        r"GIS_Report[_\s-]*(?P<month>[A-Za-z]+)[_\s-]*(?P<year>\d{4})"
        r"(?:[_\s-]+[A-Za-z0-9_\s-]+)?",
        label, re.IGNORECASE,
    )
    month = _REPORT_MONTHS.get(match["month"].casefold()) if match else None
    if not match or month is None or int(match["year"]) == 0:
        raise ConnectorResponseError("ERCOT GIS report label has no recognizable reporting period")
    return f"{match['year']}-{month:02d}"

_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "inr": ("INR",),
    "project_name": ("Project Name", "Unit Name", "Project"),
    "county": ("County",),
    "fuel": ("Fuel", "Fuel Type"),
    "technology": ("Technology",),
    "capacity_mw": ("Capacity (MW)", "Capacity MW", "MW"),
    "projected_cod": ("Projected COD", "COD", "Commercial Operations Date"),
    "approved_synchronization": ("Approved for Synchronization",),
    "approved_energization": ("Approved for Energization",),
    "ia_signed": ("IA Signed",),
}


def _norm(value: str | None) -> str:
    return " ".join((value or "").split()).casefold()


class ErcotMisXlsxConnector(BaseConnector):
    """Discover and normalize the latest monthly ERCOT GIS interconnection queue."""

    source_name = "ercot_mis_xlsx"

    def __init__(
        self,
        endpoint: str,
        *,
        allowed_hosts: frozenset[str] | None = None,
        tabs: Sequence[str] = ("Project Details - Large Gen", "Project Details - Small Gen"),
        status_header_aliases: Sequence[str] = ("GIM Study Phase", "Status", "Project Status"),
        page_size: int = 500,
        max_records: int = 5_000,
        max_document_bytes: int = 25 * 1024 * 1024,
        max_index_bytes: int = 4 * 1024 * 1024,
        max_rows_per_tab: int = 20_000,
        max_cols: int = 64,
        max_cell_chars: int = 2_000,
        report_type_id: str = "15933",
        timeout: float = 30.0,
        max_retries: int = 3,
        headers: Mapping[str, str] | None = None,
        http_client: HttpClient | None = None,
    ) -> None:
        super().__init__(page_size=page_size)
        for name, value in {
            "max_records": max_records,
            "max_document_bytes": max_document_bytes,
            "max_index_bytes": max_index_bytes,
            "max_rows_per_tab": max_rows_per_tab,
            "max_cols": max_cols,
            "max_cell_chars": max_cell_chars,
        }.items():
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if not str(report_type_id).isdigit():
            raise ValueError("report_type_id must be numeric")

        endpoint_host = (urlsplit(endpoint).hostname or "").casefold()
        if not endpoint_host:
            raise ValueError("endpoint must use HTTP or HTTPS")
        self.endpoint = endpoint
        self.report_type_id = str(report_type_id)
        self.tabs = tuple(tabs)
        self.status_header_aliases = tuple(status_header_aliases)
        self.max_records = max_records
        self.max_document_bytes = max_document_bytes
        self.max_index_bytes = max_index_bytes
        self.max_rows_per_tab = max_rows_per_tab
        self.max_cols = max_cols
        self.max_cell_chars = max_cell_chars
        self.allowed_hosts = (
            frozenset({endpoint_host}) if allowed_hosts is None
            else frozenset(host.casefold() for host in allowed_hosts)
        )
        self.headers = {
            "User-Agent": "BuildSignals/1.0 (+https://buildsignals.ai) public MIS reader",
            "Accept": "text/html,application/xhtml+xml,*/*",
            **dict(headers or {}),
        }
        self.http_client = http_client or RetryingHttpClient(
            timeout=timeout, max_retries=max_retries, allowed_hosts=self.allowed_hosts,
        )
        self._filename_re = re.compile(
            r"RPT\.0*" + re.escape(self.report_type_id)
            + r"\.0+\.(?P<postdate>\d{8})\.\d+\.(?P<desc>[^.<>\"']+)\.(?:xlsx|zip)",
            re.IGNORECASE,
        )
        self._doc_id_re = re.compile(r"doclookupId=(\d+)")
        self._record_cache: tuple[dict[str, Any], ...] | None = None
        self._meta: dict[str, Any] = {}

    # -- fetch / pagination ---------------------------------------------------
    def fetch(self, checkpoint: Checkpoint | None = None) -> FetchEnvelope:
        offset = checkpoint_offset(checkpoint)
        if self._record_cache is None:
            records, meta = self._records()
            self._record_cache = tuple(records[: self.max_records])
            self._meta = meta
        records = self._record_cache
        page = tuple(records[offset : offset + self.page_size])
        next_offset = offset + len(page)
        has_more = next_offset < len(records)
        return FetchEnvelope(
            source=self.source_name,
            records=page,
            checkpoint={"offset": next_offset} if has_more else None,
            has_more=has_more,
            metadata={
                "endpoint": self.endpoint,
                "report_type_id": self.report_type_id,
                "offset": offset,
                "total": len(records),
                **self._meta,
            },
        )

    # -- step 1: resolve newest document --------------------------------------
    def parse_index(self, html: str) -> list[dict[str, str]]:
        entries: list[dict[str, str]] = []
        for match in self._filename_re.finditer(html):
            doc = self._doc_id_re.search(html, match.end(), match.end() + 1000)
            if not doc:
                continue
            entries.append({
                "post_date": match.group("postdate"),
                "descriptive": match.group("desc"),
                "doc_id": doc.group(1),
            })
        return entries

    def select_latest(self, entries: Iterable[Mapping[str, str]]) -> dict[str, str] | None:
        gis = [e for e in entries if _norm(e["descriptive"]).startswith("gis_report")]
        if not gis:
            return None
        return dict(max(gis, key=lambda e: (e["post_date"], int(e["doc_id"]))))

    def _download_url(self, doc_id: str) -> str:
        return urljoin(
            self.endpoint,
            f"/misdownload/servlets/mirDownload?mimic_duns=000000000&doclookupId={doc_id}",
        )

    def _resolve_latest(self) -> dict[str, str]:
        body, _headers = self.http_client.get_bytes(
            self.endpoint, max_bytes=self.max_index_bytes, headers=self.headers,
        )
        latest = self.select_latest(self.parse_index(body.decode("latin-1", "replace")))
        if latest is None:
            raise ConnectorResponseError("ERCOT MIS index returned no GIS_Report documents")
        latest["download_url"] = self._download_url(latest["doc_id"])
        return latest

    # -- step 2: download + parse ---------------------------------------------
    def _records(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        latest = self._resolve_latest()
        body, _headers = self.http_client.get_bytes(
            latest["download_url"], max_bytes=self.max_document_bytes, headers=self.headers,
        )
        workbook = self._as_workbook_bytes(body)
        report_period = _report_period(latest["descriptive"])
        records: list[dict[str, Any]] = []
        tabs_read: list[str] = []
        unmapped_status = 0
        for tab in self.tabs:
            try:
                rows = xlsx_reader.read_tab(
                    workbook, tab,
                    max_total_uncompressed_bytes=64 * 1024 * 1024,
                    max_bytes_per_part=16 * 1024 * 1024,
                    max_rows=self.max_rows_per_tab,
                    max_cols=self.max_cols,
                    max_cell_chars=self.max_cell_chars,
                    required=False,
                )
            except xlsx_reader.XlsxError as exc:
                raise ConnectorResponseError(f"ERCOT workbook could not be parsed: {exc}") from exc
            if not rows:
                continue
            tab_records, unmapped = self._records_from_tab(tab, rows, latest, report_period)
            if tab_records or self._header_index(rows) is not None:
                tabs_read.append(tab)
            records.extend(tab_records)
            unmapped_status += unmapped
        if not tabs_read:
            raise ConnectorResponseError("ERCOT workbook has no recognizable Gen tab")
        meta = {
            "doc_id": latest["doc_id"],
            "report_period": report_period,
            "report_label": latest["descriptive"],
            "post_date": date.fromisoformat(latest["post_date"]).isoformat(),
            "tabs_read": tabs_read,
            "unmapped_status": unmapped_status,
            "source_url": latest["download_url"],
        }
        return records, meta

    @staticmethod
    def _as_workbook_bytes(body: bytes) -> bytes:
        if not body.startswith(b"PK"):
            return body
        # An .xlsx is itself a zip containing [Content_Types].xml. If the posting
        # is a zip WRAPPING a single .xlsx instead, unwrap it (bounded).
        import io
        import zipfile
        try:
            with zipfile.ZipFile(io.BytesIO(body)) as archive:
                names = archive.namelist()
                if "[Content_Types].xml" in names:
                    return body
                inner = [n for n in names if n.lower().endswith(".xlsx")]
                if len(inner) == 1 and archive.getinfo(inner[0]).file_size <= 64 * 1024 * 1024:
                    return archive.read(inner[0])
        except zipfile.BadZipFile:
            pass
        return body

    def _header_index(self, rows: list[list[str | None]]) -> int | None:
        for index, row in enumerate(rows):
            if row and _norm(row[0]) == "inr":
                return index
        return None

    def _resolve_columns(self, header: list[str | None]) -> dict[str, int]:
        normalized = [_norm(cell) for cell in header]
        resolved: dict[str, int] = {}
        aliases = dict(_FIELD_ALIASES)
        aliases["status"] = tuple(self.status_header_aliases)
        for field, names in aliases.items():
            for alias in names:
                target = _norm(alias)
                if target in normalized:
                    resolved[field] = normalized.index(target)
                    break
        return resolved

    def _records_from_tab(
        self, tab: str, rows: list[list[str | None]],
        latest: Mapping[str, str], report_period: str,
    ) -> tuple[list[dict[str, Any]], int]:
        header_index = self._header_index(rows)
        if header_index is None:
            return [], 0
        columns = self._resolve_columns(rows[header_index])
        if "inr" not in columns:
            return [], 0
        tab_slug = re.sub(r"[^a-z0-9]+", "-", tab.casefold()).strip("-")

        def cell(row: list[str | None], field: str) -> str | None:
            index = columns.get(field)
            if index is None or index >= len(row):
                return None
            value = row[index]
            return value.strip() if isinstance(value, str) and value.strip() else None

        records: list[dict[str, Any]] = []
        unmapped = 0
        for row in rows[header_index + 1 :]:
            inr = cell(row, "inr")
            if not inr or _norm(inr).startswith("change indicators"):
                continue
            status = cell(row, "status")
            approved_synchronization = _milestone_date(cell(row, "approved_synchronization"))
            approved_energization = _milestone_date(cell(row, "approved_energization"))
            decided = bool(approved_synchronization or approved_energization)
            if decided or _norm(status) in _DECISION_STATUSES:
                stage, event_type = "decision", "interconnection_queue_decision"
            else:
                stage, event_type = "application", "interconnection_queue_application"
                if not status:
                    unmapped += 1
            records.append({
                "source_record_id": f"ercot_mis:{inr}:{tab_slug}",
                "event_type": event_type,
                "stage": stage,
                "approval_stage": "approved" if stage == "decision" else "pre_approval",
                "inr": inr,
                "project_name": cell(row, "project_name"),
                "county": cell(row, "county"),
                "fuel": cell(row, "fuel"),
                "technology": cell(row, "technology"),
                "capacity_mw": cell(row, "capacity_mw"),
                "status": status,
                "projected_cod": _excel_date(cell(row, "projected_cod")),
                "approved_synchronization": approved_synchronization,
                "approved_energization": approved_energization,
                "report_period": report_period,
                "report_label": latest["descriptive"],
                "post_date": date.fromisoformat(latest["post_date"]).isoformat(),
                "tab": tab,
                "source_url": latest["download_url"],
            })
        return records, unmapped


def _excel_date(value: str | None) -> str | None:
    """Decode an Excel 1900-system serial (epoch 1899-12-30) to ISO; passthrough otherwise."""
    if not value:
        return None
    try:
        serial = int(float(value))
    except (TypeError, ValueError, OverflowError):
        return value
    if serial <= 0 or serial > 400_000:
        return value
    return (_EXCEL_EPOCH + timedelta(days=serial)).isoformat()


def _milestone_date(value: str | None) -> str | None:
    """Require a real date; placeholders such as Yes/TBD are not decisions."""
    decoded = _excel_date(value)
    if decoded is None:
        return None
    try:
        return date.fromisoformat(decoded).isoformat()
    except ValueError:
        return None
