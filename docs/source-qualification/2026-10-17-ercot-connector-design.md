# ERCOT Monthly GIS Connector (`ercot_mis_xlsx`)

Original design: 2026-10-17. Updated for the PR #252 review corrections on
2026-10-18. The connector and stdlib XLSX reader are implemented on
`codex/ercot-connector`, stacked on open PR #251. The former design-only
pseudocode and draft catalog mapping have been superseded by the source files
and regression tests; they must not be copied back into the implementation.

## Current status and authorization

`ercot_tx_interconnection_queue` remains `technical_hold` with
`can_run_canary=false`. It has inert `probe_settings` and `probe_field_mappings`,
not production enrollment. Offline checks exercise synthetic fixtures and a
local test database; they do not establish live connector operation or rights.
See `docs/agent-handoff.md` for actual command receipts.

Live host/TLS/contract verification, a bounded canary and written
commercial-reuse confirmation remain qualification gates. The present task
authorizes no live ingestion, activation, merge or deployment. The dated manual
observations in `2026-10-17-ercot-contract-spec.md` are useful contract evidence,
but are not a connector canary and do not supply commercial reuse clearance.

## Supported fetch and parsing contract

The product is ERCOT Monthly Generator Interconnection Status (GIS), EMIL
`PG7-200-ER`, report type `15933`. The configured public endpoint is
`https://www.ercot.com/misapp/GetReports.do?reportTypeId=15933`.

`ErcotMisXlsxConnector` resolves the `GIS_Report` document family from the HTML
index and downloads the newest publication using its posting date and document
id. Co-located battery reports in the same listing are excluded. All network
I/O uses the injected shared `HttpClient`/`RetryingHttpClient`, inheriting
host restrictions, public DNS checks, bounded reads and retry behavior; there
are no direct sockets or access-control bypasses.

Workbook tabs are `Project Details - Large Gen` and
`Project Details - Small Gen`. The `INR` header is located dynamically after
banner rows. Header aliases are matched with case/space normalization. The
reader resolves tab names through workbook relationships, preserves sparse
column positions, handles shared/inline strings and numeric cells, and decodes
Excel 1900-system date serials in the connector.

The shared reader is `app/services/ingestion/connectors/xlsx_reader.py`, using
only `zipfile` and `xml.etree.ElementTree`. Downloads, archive entry count,
uncompressed bytes, part bytes, rows, columns, cells and shared strings are
bounded. Current defaults include a 25 MiB document cap, 64 MiB total
uncompressed cap, 16 MiB part cap, 20,000 rows per tab, 64 columns, 2,000
characters per cell and 5,000 records across both tabs. The factory accepts
`ercot_mis_xlsx` and `ercot_gis`; it does not activate a catalog candidate.

## Classification and normalization contract

An interconnection request is not an ordinary building permit. The existing
schema has no dedicated interconnection record class, so `record_type=permit`
is a storage compatibility choice. Preserve
`permit_type="Generation interconnection request"` and
`permit_subtype="ERCOT Monthly GIS queue"`, explicit
`interconnection_queue_application` / `interconnection_queue_decision` event
types and source `stage=application` / `decision` evidence.

The supported canonical `approval_stage` is separately emitted as
`pre_approval` / `approved`; do not map the source stage vocabulary directly
into that validator. Study completion, FIS approval, signed IA and projected
COD do not independently establish an operator decision. In particular,
`SS Completed, FIS Completed, IA` remains an application without positive
energization/synchronization evidence. Decision detection uses validated
operator milestone dates or a narrow exact status allowlist, never generic
`approved`, `complete` or substring matching. Negative, pending and ambiguous
milestones do not become decisions merely because the cells are nonempty.

Catalog mappings use the actual canonical permit vocabulary. County, fuel,
technology, MW, projected COD, report month, raw stage and original status stay
in source evidence/unmapped fields when no canonical equivalent exists. Do not
invent canonical fields such as `county`, `project_type`, `capacity_mw` or
`expected_completion_at`, and do not repurpose a forecast COD as a permit date.
The immutable raw payload and normalized `unmapped` evidence retain these
interconnection facts through persistence; the persisted permit uses
`attributes` directly for unmapped values. The INR plus tab provides the
existing stable source identity across monthly observations.

## Report month is not posting date

Select the latest document by publication date, but derive `report_period`
from its descriptive GIS report label. For example,
`RPT.00015933.0000000000000000.20261001.160829144.GIS_Report_September2026.xlsx`
has report month `2026-09` and posting date `2026-10-01`. Full/abbreviated month
names, optional separators and correction suffixes are expected. Unknown
report labels fail explicitly rather than inventing a month from publication.
Report month is a snapshot period, not the request filing date or a permit
approval date; publication date likewise must not be mapped to `filed_at`.
The probe's supported freshness contract uses `post_date` with
`freshness_semantics=dataset_refreshed_at`. Raw source-update timestamps therefore
describe publication freshness, while `report_period` remains snapshot evidence.

## Regression and remaining qualification

Offline regression scope covers study-stage misclassification, negative and
ambiguous milestone/status cells, positive operator milestones, canonical
normalization, supported ingestion-service persistence with preserved source
evidence, and September versus October report/posting dates. Reader, catalog,
rollout manifest and lint checks remain relevant. Passing counts and skipped
checks must be recorded only after execution in the current handoff.

Before promotion, obtain written commercial-reuse confirmation, then under
separate authorization verify the current public host/TLS and workbook
contract using the supported connector and capture a bounded canary receipt.
A future activation must retain tenant isolation, host bounds, evidence and
explicit event semantics. No queue snapshot alone proves construction,
energization, available capacity, a parcel opportunity or a validated
power-constraint signal.
