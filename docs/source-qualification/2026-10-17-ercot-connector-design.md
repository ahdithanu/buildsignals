# ERCOT Monthly GIS Connector — Implementation Design (`ercot_mis_xlsx`)

Date: 2026-10-17. Status: **design only** — no code written, no live fetch, no
dependency added. This plans a new **stdlib-only** ingestion connector for the
ERCOT **Monthly Generator Interconnection Status (GIS) Report** (EMIL
`PG7-200-ER`, Report Type Id **15933**).

This design is the build plan that follows the source qualification in
`docs/source-qualification/2026-10-17-utility-interconnection-queues.md`
(the ERCOT section), which already establishes the recurring public contract:
a stable `reportTypeId=15933` MIS GetReports XML index → per-document download
via the `mirDownload` servlet → a monthly XLSX with **Large Gen** / **Small Gen**
tabs, a durable per-row **INR** identity, derivable application-vs-decision
semantics from the per-row **status** / COD columns, and rights-clean reuse.

> **Companion contract-spec reconciliation.** The task referenced a possible
> `docs/source-qualification/2026-10-17-ercot-contract-spec.md`. **It does not
> exist as of this writing.** Per instruction, this design therefore targets the
> generic shape: **INR** identity + **Large Gen / Small Gen** tabs + a **status**
> column (plus a projected-COD column where present). The connector must treat
> exact column headers as **not yet confirmed from a live file** — header
> resolution is deliberately alias-based and case/space-insensitive (see §2.4)
> so that a single live-file read can finalize mappings without a code change.

## Hard constraints

- **No new dependency.** The repo has no `openpyxl`/`pandas`. XLSX is parsed with
  the standard library only: `zipfile` + `xml.etree.ElementTree` (`io`, `re`,
  `datetime` as needed). This mirrors how existing connectors stay stdlib-only
  (`csv`, `html.parser`, `urllib`).
- **Use the shared HTTP boundary.** All network I/O goes through the injected
  `HttpClient` / `RetryingHttpClient` from
  `app/services/ingestion/connectors/base.py`, using `get_text` for the XML index
  and **`get_bytes(url, max_bytes=...)`** for the XLSX download. This inherits
  host-pinning (`allowed_hosts`), public-DNS validation, same-host-only redirect
  rules, bounded reads, and transient retries. The connector never opens its own
  sockets.
- **Everything bounded.** `max_bytes` on download, plus connector-enforced
  `max_rows`, `max_cols`, `max_cell_chars`, a zip-bomb guard on total
  uncompressed size, and `max_records` across both tabs.

---

## 1. Bounded stdlib XLSX reader

New module: **`app/services/ingestion/connectors/xlsx_reader.py`** (pure parsing,
no network, no connector coupling — directly unit-testable from fixture bytes).

### 1.1 Why a bespoke reader

An `.xlsx` file is a ZIP (OPC) container of XML parts. The minimal set needed to
read tabular cells by **tab name**:

- `xl/workbook.xml` — `<sheets>` listing each `<sheet name="…" sheetId="…"
  r:id="rIdN"/>` (the **tab name** the user sees → an internal relationship id).
- `xl/_rels/workbook.xml.rels` — maps each `rIdN` → the worksheet part path
  (e.g. `worksheets/sheet1.xml`). The `name → rId → part` indirection is required
  because `sheetN.xml` numbering does **not** reliably match tab order.
- `xl/worksheets/sheetN.xml` — `<sheetData>` of `<row>`/`<c>` cells. A cell's
  value is in `<v>`; its type is the `t` attribute.
- `xl/sharedStrings.xml` — `<sst>` of `<si>` string items; a cell with `t="s"`
  stores an **integer index** into this table in its `<v>`, not the text.

Cell value encodings the reader must handle:

| `c@t` | meaning | where the value is |
|-------|---------|--------------------|
| `s` | shared string | `<v>` = 0-based index into sharedStrings |
| `inlineStr` | inline string | `<is><t>…</t></is>` (and `<r><t>` runs) |
| `str` | formula string result | `<v>` text |
| `b` | boolean | `<v>` = `0`/`1` |
| `n` / absent | number | `<v>` numeric text |
| (date) | number w/ date number-format | `<v>` serial — see §2.5 caveat |

Column position comes from the cell reference `r` (e.g. `C7`) → the letters are
decoded to a 0-based column index, so **blank/omitted cells do not shift
columns** (sparse rows are common in these reports).

### 1.2 Concrete function signatures

```python
# app/services/ingestion/connectors/xlsx_reader.py
from __future__ import annotations
import io, zipfile
from typing import Iterator
from xml.etree import ElementTree as ET

class XlsxError(ValueError):
    """Raised when bytes are not a usable XLSX workbook (caller maps to ConnectorResponseError)."""

# --- container ---------------------------------------------------------------
def open_workbook(
    data: bytes,
    *,
    max_total_uncompressed_bytes: int,
    max_entries: int = 64,
) -> zipfile.ZipFile:
    """Open XLSX bytes as a ZIP, rejecting non-zip input and zip bombs.

    Sum of ``ZipInfo.file_size`` across entries must be <= the cap, and the
    entry count must be <= ``max_entries`` (both checked BEFORE any decompress).
    """

# --- workbook structure ------------------------------------------------------
def map_sheets(zf: zipfile.ZipFile, *, max_bytes: int) -> dict[str, str]:
    """Return {visible_tab_name: worksheet_part_path} via workbook.xml + its rels.

    Reads 'xl/workbook.xml' and 'xl/_rels/workbook.xml.rels' (each bounded by
    max_bytes), joins sheet@r:id -> relationship Target, normalizes the Target to
    an 'xl/...'-rooted archive path. Raises XlsxError if either part is missing.
    """

def read_shared_strings(
    zf: zipfile.ZipFile,
    *,
    max_bytes: int,
    max_strings: int,
    max_cell_chars: int,
) -> list[str]:
    """Parse xl/sharedStrings.xml -> list of plain strings (index == position).

    Concatenates <t> text across <r> runs inside each <si>; truncates each item
    to max_cell_chars; raises XlsxError past max_strings. Returns [] if the part
    is absent (a workbook may legally have no shared strings)."""

# --- worksheet rows ----------------------------------------------------------
def iter_sheet_rows(
    zf: zipfile.ZipFile,
    part_path: str,
    shared_strings: list[str],
    *,
    max_rows: int,
    max_cols: int,
    max_cell_chars: int,
) -> Iterator[list[str | None]]:
    """Yield each worksheet row as a dense list of cell strings (None for blanks).

    Uses ET.iterparse over the part's stream and clears elements after each row
    to bound memory. Resolves shared/inline/number/bool cells to text; places
    each cell at its decoded column index (from c@r). Stops after max_rows;
    raises XlsxError if any row needs more than max_cols columns."""

def column_index(cell_ref: str) -> int:
    """'C7' -> 2 ; 'AA1' -> 26. Letters only, 0-based. Raises XlsxError if bad."""

# --- convenience -------------------------------------------------------------
def read_tab(
    data: bytes,
    tab_name: str,
    *,
    max_total_uncompressed_bytes: int,
    max_bytes_per_part: int,
    max_rows: int,
    max_cols: int,
    max_cell_chars: int,
    max_strings: int = 2_000_000,
    required: bool = True,
) -> tuple[list[str], list[list[str | None]]]:
    """High-level: open -> map sheets -> shared strings -> iter rows for ONE tab.

    Returns (header_row, data_rows). Tab match is case/whitespace-insensitive
    (see connector §2.4). If the tab is absent: raise XlsxError when required,
    else return ([], []). If present but empty, return ([], [])."""
```

### 1.3 Namespaces & robustness

- Spreadsheet-ML namespace is `http://schemas.openxmlformats.org/spreadsheetml/2006/main`;
  relationships use `http://schemas.openxmlformats.org/officeDocument/2006/relationships`
  (the `r:id` attribute) and the rels file uses
  `http://schemas.openxmlformats.org/package/2006/relationships`. The reader
  matches by **local-name** (strip the `{ns}` prefix) rather than hard-coding the
  namespace URI, so minor producer variations don't break it.
- `ET.iterparse` is used with `("start", "end")` events; elements are
  `.clear()`-ed on the `end` of each `<row>` to keep memory flat regardless of
  sheet length. `ElementTree` resolves no external entities, so no XXE path;
  still, parsing only ever runs on bytes already bounded by `get_bytes`.
- Empty/missing sheet handling: `map_sheets` raising for a missing requested tab
  is caught by the connector and (a) skipped if the other tab exists, or
  (b) surfaced as `ConnectorResponseError` if **neither** gen tab is present.

### 1.4 Bounds enforced here

| Bound | Default (connector passes) | Guards against |
|-------|----------------------------|----------------|
| `max_total_uncompressed_bytes` | `64 MiB` | zip bomb (checked pre-decompress) |
| `max_entries` | `64` | pathological archives |
| `max_bytes_per_part` | `16 MiB` | oversized workbook/sharedStrings XML |
| `max_rows` (per tab) | `20_000` | runaway sheets (report is ~1.85k rows) |
| `max_cols` | `64` | runaway columns |
| `max_cell_chars` | `2_000` | oversized cells |
| `max_strings` | `2_000_000` | sharedStrings table blowup |

The download `max_bytes` (connector `max_document_bytes`, §2.3) is the first and
cheapest bound; these reader bounds are defense-in-depth on the decompressed side.

---

## 2. The connector class

New module: **`app/services/ingestion/connectors/ercot_mis.py`**

```python
class ErcotMisXlsxConnector(BaseConnector):
    source_name = "ercot_mis_xlsx"
```

Pattern follows `legistar.py` / `html_document_index.py`: a two-step
resolve-then-fetch that builds the **full record list once** (cached on the
instance), then pages by offset via `checkpoint_offset(...)` and
`FetchEnvelope`. This matches how `LegistarPlanningConnector.fetch` and
`HTMLDocumentIndexConnector.fetch` page an in-memory record list.

### 2.1 `__init__` signature & bounds

```python
def __init__(
    self,
    endpoint: str,                       # GetReports index, reportTypeId=15933
    *,
    allowed_hosts: frozenset[str] | None = None,
    tabs: Sequence[str] = ("Large Gen", "Small Gen"),
    status_header_aliases: Sequence[str] = ("GIM Study Phase", "Status", "Project Status"),
    page_size: int = 500,
    max_records: int = 5_000,
    max_document_bytes: int = 25 * 1024 * 1024,   # XLSX download cap
    max_index_bytes: int = 4 * 1024 * 1024,       # GetReports XML cap
    max_rows_per_tab: int = 20_000,
    max_cols: int = 64,
    max_cell_chars: int = 2_000,
    report_type_id: str = "15933",
    timeout: float = 30.0,
    max_retries: int = 3,
    headers: Mapping[str, str] | None = None,
    http_client: HttpClient | None = None,
    now: Callable[[], datetime] | None = None,
) -> None:
```

- Validates every `max_*` as a positive `int` (reject `bool`), mirroring
  `legistar.py`'s loop. `page_size` is validated by `super().__init__`.
- **Host pinning.** `allowed_hosts` defaults to the endpoint host derived from
  `endpoint` (same approach as `HTMLDocumentIndexConnector`: fall back to the
  endpoint hostname). The connector constructs its own
  `RetryingHttpClient(timeout=…, max_retries=…, allowed_hosts=self.allowed_hosts)`
  when `http_client` is not injected — identical to `html_document_index.py`.
  In production the factory injects the host-pinned client (see §3).
- `headers` default `{"Accept": "application/xml,text/xml,*/*"}` for the index
  request; the XLSX request sends `Accept: application/vnd.openxmlformats-…
  ,application/octet-stream,*/*`.

### 2.2 Step 1 — resolve the latest monthly document from the MIS index

```python
def _resolve_latest_document(self) -> tuple[str, str, str | None]:
    """Return (download_url, doc_id, publish_date) for the newest GIS document."""
```

- `GET` the index: `self.http_client.get_text(self.endpoint, headers=…)`.
  Canonical endpoint:
  `https://misapp.ercot.com/misapp/GetReports.do?reportTypeId=15933`.
- Parse with `xml.etree.ElementTree`. The MIS index is a list of document
  entries; each carries a numeric **document id** and a **publish date**
  (historically `<Document><DocID>…</DocID><PublishDate>…</PublishDate>
  <ConstructedName>…</ConstructedName><ReportTypeID>…</ReportTypeID></Document>`
  under a `<ListDocstmp>`/`<Report>` root). The reader matches by **local-name**
  and tolerates casing variants (`DocID`/`DocId`), and filters to
  `ReportTypeID == report_type_id` when that element is present.
- **Pick newest:** sort by `PublishDate` (ISO) descending, tie-break on numeric
  `DocID` descending; take the first. Prefer the `.xlsx`/`.zip` artifact when the
  entry distinguishes file types; otherwise take the document id.
- **Build the download URL** for the `mirDownload` servlet:
  `https://misapp.ercot.com/misapp/servlets/mirDownload?doclookupId=<DocID>`
  (resolved relative to the endpoint host so the host stays pinned).
- Errors: empty/malformed index → `ConnectorResponseError`; no matching document
  → `ConnectorResponseError("ERCOT MIS index returned no GIS documents")`.

> **Live-validation TODO (from the qualification doc):** the MIS host + TLS
> profile must be confirmed on first real fetch (one probe hit
> `SSLV3_ALERT_HANDSHAKE_FAILURE`; `misapp.ercot.com` vs `mis.ercot.com`
> resolution differs). This is a config detail resolved by `allowed_hosts` +
> `endpoint`, not a code change. Until confirmed, `can_run_canary` stays false.

### 2.3 Step 2 — download + parse the XLSX

```python
def _records(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Resolve newest doc, download bounded bytes, parse both gen tabs -> records."""
```

- `body, _hdrs = self.http_client.get_bytes(download_url,
  max_bytes=self.max_document_bytes, headers=…)` — the single bounded download.
- If the artifact is a `.zip` wrapping the `.xlsx` (some MIS postings zip the
  file), detect the PKZip magic and, if the single contained entry is an
  `.xlsx`, unwrap it with the **same** `xlsx_reader.open_workbook` bomb guard
  before parsing; otherwise treat `body` as the `.xlsx` directly. (An `.xlsx` is
  itself a zip, so detection is by inner content: a member named
  `[Content_Types].xml` means it is already the workbook.)
- For each tab in `self.tabs`, call `xlsx_reader.read_tab(...)` with
  `required=False`; require that **at least one** gen tab yields a header.
- Build one record per data row (see §2.4), tagging the originating `tab`.
- Caches `self._record_cache` so pagination re-reads nothing (as legistar does).

### 2.4 Header resolution → record fields

Because exact headers are unconfirmed, the connector resolves columns by matching
header text **case- and whitespace-insensitively** against alias lists, recording
the resolved index per logical field. Header row is the first non-empty row.

| Canonical field | Header aliases (first match wins) | Notes |
|-----------------|-----------------------------------|-------|
| `inr` | `INR`, `Interconnection Request`, `GINR` | durable per-row id |
| `project_name` | `Project Name`, `Unit Name`, `Generation Interconnection Project`, `Project` | |
| `county` | `County` | |
| `fuel` | `Fuel`, `Fuel Type`, `Technology` | |
| `capacity_mw` | `Capacity (MW)`, `Capacity MW`, `MW`, `Summer Capacity (MW)`, `Net Max Output (MW)` | numeric → string passthrough |
| `status` | `status_header_aliases` (ctor): `GIM Study Phase`, `Status`, `Project Status` | drives event/stage |
| `projected_cod` | `Projected COD`, `COD`, `Commercial Operations Date`, `Approved for Synchronization` | milestone |

Each emitted record (one per data row):

```python
{
  "source_record_id": f"ercot_mis:{inr}:{tab_slug}",   # INR + tab; stable per row
  "event_type": "...",    # see §2.5 mapping
  "stage": "...",         # "application" | "decision"
  "project_name": "...",  # or None
  "county": "...",        # or None
  "fuel": "...",          # or None
  "capacity_mw": "...",   # raw cell text (string), or None
  "status": "...",        # raw source status text, or None
  "projected_cod": "...", # or None
  "report_period": "YYYY-MM",   # from index PublishDate (month of the report)
  "tab": "Large Gen",     # provenance
  "inr": "24INR0080",
  "source_url": download_url,   # the resolved mirDownload URL for this month
}
```

- Rows with no resolvable `inr` are **skipped** (no durable identity → cannot
  dedupe), consistent with legistar dropping items lacking a reference/matter id.
- `source_record_id` uses INR + a slug of the tab so the same INR appearing in
  different tabs (shouldn't happen, but is defended) stays distinct.

### 2.5 Application-vs-decision derivation

The task maps **queued / under-study → application**; **approved / synchronized /
in-service → decision**. Implemented as a normalized status classifier:

```python
_APPLICATION_MARKERS = ("queued", "under study", "under-study", "screening",
                        "scoping", "study", "requested", "pending")
_DECISION_MARKERS    = ("approved", "synchroniz", "in service", "in-service",
                        "commercial operation", "energized", "complete",
                        "signed", "executed")
```

- Normalize the `status` cell (casefold, collapse whitespace). Decision markers
  are checked first (a project "approved for synchronization" is a decision even
  if the phase text also contains "study"). If a non-empty `projected_cod` is
  present AND status is empty, lean to **application** (COD is a plan, not a
  completion) — documented so a live-file read can tune it.
- Result:
  - **application** → `stage="application"`,
    `event_type="interconnection_queue_application"`.
  - **decision** → `stage="decision"`,
    `event_type="interconnection_queue_decision"`.
  - unmappable/empty status → default to **application** with
    `event_type="interconnection_queue_application"` and a metadata counter
    `unmapped_status` incremented (surfaced in envelope metadata for QA), rather
    than dropping the row.

> Naming aligns with the `stage`/`event_type` convention in `legistar.py`
> (`stage` is a coarse lifecycle bucket; `event_type` is the specific event).
> The two ERCOT stages are **not** the legistar `hearing_scheduled`/
> `decision_recorded` set — they are connector-specific strings, which is fine:
> the base layer does not constrain stage vocabulary (only the legistar
> connector validates its own `record_stages`).

### 2.6 `fetch` / pagination

```python
def fetch(self, checkpoint: Checkpoint | None = None) -> FetchEnvelope:
    offset = checkpoint_offset(checkpoint)                 # key="offset"
    if self._record_cache is None:
        records, meta = self._records()
        self._record_cache = tuple(records[: self.max_records])
        self._meta = meta
    records = self._record_cache
    page = records[offset : offset + self.page_size]
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
            "doc_id": self._meta.get("doc_id"),
            "report_period": self._meta.get("report_period"),
            "offset": offset,
            "total": len(records),
            "tabs_read": self._meta.get("tabs_read"),
            "unmapped_status": self._meta.get("unmapped_status", 0),
        },
    )
```

- `checkpoint_offset` (base.py) validates the offset; `iter_pages`/`iter_records`
  from `BaseConnector` work unchanged. The repeated-checkpoint guard in
  `iter_pages` is satisfied because `offset` strictly increases.
- `max_records` is applied to the combined (Large + Small) record list after
  parsing, so the page stream never exceeds it.

### 2.7 Errors

Reuse base error types: `ConnectorResponseError` for malformed index / malformed
or absent XLSX / neither gen tab present / oversized parts; `ConnectorRequestError`
propagates from the HTTP client (host not allowlisted, non-public DNS,
cross-host redirect, size overflow, retries exhausted). `xlsx_reader.XlsxError`
is caught at the connector boundary and re-raised as `ConnectorResponseError`.

---

## 3. Exact wiring

### 3.1 `app/services/ingestion/connectors/factory.py`

Add the import beside the others and a branch before the final `raise`:

```python
from .ercot_mis import ErcotMisXlsxConnector
```

```python
    if connector_type in {"ercot_mis_xlsx", "ercot_gis"}:
        return ErcotMisXlsxConnector(
            _required(config, "endpoint"),
            allowed_hosts=_string_set(config.get("allowed_hosts"), "allowed_hosts"),
            tabs=_string_list(config.get("tabs"), "tabs") or ("Large Gen", "Small Gen"),
            status_header_aliases=(
                _string_list(config.get("status_header_aliases"), "status_header_aliases")
                or ("GIM Study Phase", "Status", "Project Status")
            ),
            max_records=int(config.get("max_records", 5000)),
            max_document_bytes=int(config.get("max_document_bytes", 25 * 1024 * 1024)),
            max_index_bytes=int(config.get("max_index_bytes", 4 * 1024 * 1024)),
            max_rows_per_tab=int(config.get("max_rows_per_tab", 20000)),
            max_cols=int(config.get("max_cols", 64)),
            max_cell_chars=int(config.get("max_cell_chars", 2000)),
            report_type_id=str(config.get("report_type_id", "15933")),
            headers=_public_headers(config),
            **common,
        )
```

Notes: `common` already supplies `page_size`, `timeout`, `max_retries`, and a
host-pinned `http_client` (built with `_production_allowed_hosts()`), so in
staging/production the download is pinned to `INGESTION_ALLOWED_HOSTS` — which
must include `misapp.ercot.com` (and any confirmed `mis.ercot.com`). The
connector's own `allowed_hosts` is a second, connector-scoped gate for the
default (non-production) client path, matching `html_document_index`.

### 3.2 `app/services/ingestion/connectors/__init__.py`

```python
from .ercot_mis import ErcotMisXlsxConnector
```

and add `"ErcotMisXlsxConnector",` to `__all__` (alphabetically near the top).
(Optionally also export `xlsx_reader` helpers if other connectors reuse them;
not required for this feature.)

### 3.3 Draft `candidate_catalog.json` entry

Append this object to the list in
`app/services/ingestion/candidate_catalog.json`. `record_type` is **`permit`**
— the closest valid value of `permit | parcel | planning` (schema
`IngestionSourceCandidate`). **Semantic caveat:** a generator interconnection
request is *not* a building permit; `permit` is used only because the schema has
no `interconnection`/`infrastructure` enum, and the `event_type`/`stage` fields
carry the true semantics. `status` is `technical_hold`; the schema validator
auto-sets `can_run_canary=False` for any non-`operational_retry` status, so the
`false` below is consistent (canary stays off until the MIS host/TLS and live
headers are validated).

```json
{
  "key": "ercot_tx_interconnection_queue",
  "name": "ERCOT Monthly GIS Interconnection Queue",
  "adapter": "ercot_mis_xlsx",
  "record_type": "permit",
  "jurisdiction": "ERCOT (Texas)",
  "base_url": "https://misapp.ercot.com/misapp/GetReports.do?reportTypeId=15933",
  "official_landing_page": "https://www.ercot.com/mp/data-products/data-product-details?id=PG7-200-ER",
  "license": "ERCOT Website User Agreement Clause 5 — public raw data may be used, reproduced, and redistributed in compilations, charts, and analyses (rights-clean for commercial use; ERCOT marks excluded)",
  "status": "technical_hold",
  "blocker_summary": "Rights-clean recurring public XLSX contract confirmed (reportTypeId=15933 MIS GetReports index -> mirDownload servlet). Held pending (1) live validation of the MIS host + TLS profile (one probe failed SSLV3_ALERT_HANDSHAKE_FAILURE; misapp vs mis host differs) and (2) a one-time read of the live file's actual column headers to finalize the alias-based field mapping. No connector has fetched a live file yet.",
  "early_warning_value": "Monthly, statewide view of new large/small generation projects entering the ERCOT queue (county, fuel, MW) before construction or COD, surfacing power-supply build-out in the Dallas-Fort Worth / data-center-adjacent load zones ahead of permits.",
  "candidate_source_fields": [
    "inr",
    "project_name",
    "county",
    "fuel",
    "capacity_mw",
    "status",
    "projected_cod",
    "tab"
  ],
  "probe_settings": {
    "connector": {
      "endpoint": "https://misapp.ercot.com/misapp/GetReports.do?reportTypeId=15933",
      "report_type_id": "15933",
      "allowed_hosts": ["misapp.ercot.com"],
      "tabs": ["Large Gen", "Small Gen"],
      "status_header_aliases": ["GIM Study Phase", "Status", "Project Status"],
      "page_size": 500,
      "max_records": 5000,
      "max_document_bytes": 26214400,
      "max_index_bytes": 4194304,
      "max_rows_per_tab": 20000,
      "max_cols": 64,
      "max_cell_chars": 2000,
      "timeout": 30.0,
      "max_retries": 3,
      "headers": {
        "User-Agent": "BuildSignals/1.0 (+https://buildsignals.ai) public MIS reader"
      }
    },
    "defaults": {
      "region": "ERCOT",
      "state": "TX",
      "jurisdiction": "ERCOT",
      "permit_type": "generator_interconnection_request",
      "source_system": "ERCOT MIS Monthly GIS (PG7-200-ER, reportTypeId=15933)"
    },
    "signal_stage": "pre_approval",
    "freshness_field": "report_period",
    "freshness_semantics": "report_period_month",
    "freshness_sla_hours": 1080,
    "canary_required_fields": [
      "source_record_id",
      "inr",
      "status",
      "tab",
      "source_url"
    ]
  },
  "probe_field_mappings": [
    { "source_field": "source_record_id", "canonical_field": "source_record_id", "is_required": true },
    { "source_field": "inr", "canonical_field": "application_number", "is_required": true },
    { "source_field": "project_name", "canonical_field": "project_name" },
    { "source_field": "county", "canonical_field": "county" },
    { "source_field": "fuel", "canonical_field": "project_type" },
    { "source_field": "capacity_mw", "canonical_field": "capacity_mw", "transform": "number" },
    { "source_field": "status", "canonical_field": "status" },
    { "source_field": "stage", "canonical_field": "approval_stage" },
    { "source_field": "projected_cod", "canonical_field": "expected_completion_at", "transform": "date" },
    { "source_field": "report_period", "canonical_field": "filed_at", "transform": "date" },
    { "source_field": "source_url", "canonical_field": "source_url" }
  ],
  "production_page_size": 500,
  "can_run_canary": false,
  "last_checked_on": "2026-10-17",
  "next_audit_on": "2026-11-17",
  "notes": "Design planned in docs/source-qualification/2026-10-17-ercot-connector-design.md; qualified in 2026-10-17-utility-interconnection-queues.md (ERCOT section, recommendation (a)). STDLIB-ONLY XLSX parse (zipfile + xml.etree) via the shared RetryingHttpClient get_bytes bound. record_type 'permit' is a schema-nearest placeholder: an interconnection request is not a building permit; event_type/stage carry true application-vs-decision semantics (queued/under-study=application, approved/synchronized/in-service=decision). Column header aliases are provisional until one live file is read. Do not promote until the MIS host/TLS profile and live headers are validated and commercial-reuse terms are re-confirmed in writing."
}
```

**Transform caveat:** `transform` values (`number`, `date`) and the
`canonical_field` names above assume the project's existing transform registry
supports them (the catalog already uses `date` and `regex_extract`). The
implementer should confirm `number` exists (or map `capacity_mw` with no
transform and coerce downstream) and that `project_type`/`capacity_mw`/
`expected_completion_at`/`approval_stage` are valid canonical fields before
relying on them; adjust to the actual canonical vocabulary if not.

---

## 4. Files the implementer will create / edit

**Create**
- `app/services/ingestion/connectors/xlsx_reader.py` — stdlib XLSX reader (§1).
- `app/services/ingestion/connectors/ercot_mis.py` — `ErcotMisXlsxConnector` (§2).
- Tests (mirror existing connector tests):
  - `tests/.../test_xlsx_reader.py` — shared strings, inline strings, numeric/
    bool cells, sparse columns, missing/empty sheet, zip-bomb + bounds, a tiny
    hand-built `.xlsx` fixture (bytes built with `zipfile` in the test, no dep).
  - `tests/.../test_ercot_mis.py` — index resolution (newest doc pick),
    two-step fetch with a fake `HttpClient` returning fixture XML + XLSX bytes,
    status→application/decision mapping, INR dedupe/skip, pagination/checkpoint,
    bounds, error paths.

**Edit**
- `app/services/ingestion/connectors/factory.py` — import + `ercot_mis_xlsx`
  branch (§3.1).
- `app/services/ingestion/connectors/__init__.py` — import + `__all__` (§3.2).
- `app/services/ingestion/candidate_catalog.json` — append the entry (§3.3).

**Also confirm (no edit assumed, but verify during implementation)**
- `INGESTION_ALLOWED_HOSTS` includes `misapp.ercot.com` (and any confirmed
  `mis.ercot.com`) in staging/production, since `factory._production_allowed_hosts`
  pins the shared client to that set.
- The transform/canonical-field vocabulary used in the catalog entry (§3.3
  caveat).

## 5. Open items carried from qualification (block activation, not the build)

1. Validate the MIS host + TLS profile against one live request
   (`SSLV3_ALERT_HANDSHAKE_FAILURE` seen on a probe; `misapp` vs `mis`).
2. Read the actual column headers from one live monthly file and finalize the
   alias lists / status markers (§2.4–2.5).
3. Re-confirm ERCOT commercial-reuse terms in writing before promotion.
4. Confirm whether the monthly artifact is a bare `.xlsx` or a `.zip`-wrapped
   `.xlsx` (the reader handles both, §2.3, but the default `Accept`/unwrap path
   should be verified).
