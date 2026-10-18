# Columbus Coverage Attestation

Attestation date: **2026-10-17**.
Live demo measurement fetched: **2026-10-18T00:05:25Z** (UTC).
Demo snapshot `captured_at` reported by the API: **2026-10-17T21:51:49Z** (UTC).

Scope: this attests only to what the **public read-only demo cohort** actually
holds, as returned live by the demo API. It is evidence of stored demo inventory,
not provider totals, not citywide completeness, not distinct projects, and not
for-sale inventory. See the explicit unknowns below.

## How this was measured

Unauthenticated demo token from `POST https://www.buildsignals.ai/v1/auth/demo`,
then `GET` with a bearer token against `/v1/demo/summary`, `/v1/demo/map`,
`/v1/demo/activity`, and `/v1/demo/parcel-references`. All counts below are the
actual JSON values returned in that single live read. Re-running can differ; this
records this read.

## Demo cohort counts (`/v1/demo/summary`)

| Field | Value |
| --- | ---: |
| `permit_records` | 2,104 |
| `graph_entities` | 5,045 |
| `relationships` | 8,403 |
| `parcel_references` | 1,088 |
| `parcel_records` | 0 |
| `mapped_permits` | 938 |
| `derived_geocoded_permits` | 938 |
| `mapped_filing_locations` | 420 |
| `mapped_parcels` | 0 |

## Stages present (`/v1/demo/activity`)

- `approved`: 2,053
- `pre_approval`: 51
- `records_considered`: 2,104 (matches `permit_records`)
- `months`: 5 (activity window the endpoint rolled up; query `limit` 5,000)

Stage labels are the pipeline's mapped stages, not a verified City of Columbus
lifecycle. Per `docs/columbus-historical-intake.md`, "issued" does not mean
currently active, and Complete/Completed/Closed mappings still await a verified
city lifecycle dictionary.

## Time depth / date range

**Not determinable from the demo endpoints.** The demo surfaces a 5-month activity
rollup (`months: 5`) but does not expose min/max event dates for the cohort. The
intake audit (`docs/columbus-historical-intake.md`) establishes the *public source*
retrospective depth (site engineering from 2019, commercial permits from 2010;
the production commercial predicate `ISSUED_YEAR >= 2025` deliberately keeps only
2025-onward, i.e. under two complete years). The exact dated extent of the demo
cohort itself is an explicit unknown here.

## Geocoding coverage

- `derived_geocoded_permits`: **938** — matches the expected 938.
- `mapped_permits`: 938 (same set; map layer is capped at 100 points per layer,
  confirmed by `/v1/demo/map` returning `permits: 100`, `limit_per_layer: 100`).
- Coverage: 938 of 2,104 permit records carry derived coordinates (~44.6%).
- `mapped_filing_locations`: 420 (derived filing-location points, distinct from
  per-permit points).
- Per `docs/measured-coverage.md`: valid-coordinate counts do not prove geocoding
  accuracy or complete geographic coverage.

## Parcels

- `parcel_references`: 1,088 permit-attached parcel reference strings; `parcel_records`
  and `mapped_parcels` are **0** — the demo holds no qualified parcel inventory.
- Top references by permit count (`/v1/demo/parcel-references`): `010247208` (58),
  `010082628` (25, 700 Children's Dr), `010183740` (24, 3535 Olentangy River Rd),
  `246321291` (18), `010291757` (16).
- A parcel reference does not establish an exact parcel match, ownership,
  availability, or an acquisition candidate (per intake audit and coverage contract).

## Freshness

- **Collection recency**: the demo snapshot was captured `2026-10-17T21:51:49Z`
  (`summary.captured_at`). That is when the demo view was assembled, not when the
  source published or changed.
- **Source-update-date completeness**: **not exposed by the demo endpoints.** The
  coverage contract (`measured_coverage.py`, `docs/measured-coverage.md`) separates
  collection recency (`last_seen_at`) from the source's own update date
  (`RawSourceRecord.source_updated_at`), and flags unknown/future source dates
  explicitly. The intake audit also recorded a future-date anomaly in the
  commercial layer (max `LAST_STATUS_DT` beyond audit date). None of that per-record
  source-date distribution is measurable from the demo.

## Gaps and explicit unknowns

- **Authenticated customer/production workspace coverage requires an authenticated
  measurement.** The `measured_coverage` contract (`GET /v1/ingestion/coverage/measured`)
  is tenant-scoped and auth-gated; we do not hold that auth here. Production
  readiness, per-source readiness status, stored-record totals, and observed-state
  rollups are **not** attested by this document. Do not infer them from the demo.
- Demo cohort dated extent (earliest/latest event date): unknown here.
- Per-record source-update-date freshness and unknown/future-date rates: unknown here.
- Distinct-project counts: unmeasured. Site + commercial feeds are not additive
  project universes; one project can carry many permits and appear in both feeds.
- Qualified parcel joins / for-sale availability: none present (parcel_records 0).
- First-market qualification gates in `docs/columbus-historical-intake.md` remain
  open; nothing here activates or accepts Columbus as a production market.

## Honesty note

These are measured demo-cohort inventory counts collected `2026-10-17T21:51:49Z`;
they are not distinct projects, not for-sale inventory, and parcel references are
unqualified (no verified parcel/ownership/availability join).

Evidence: `/v1/demo/{summary,map,activity,parcel-references}` (live, fetched
2026-10-18T00:05:25Z); `docs/measured-coverage.md`; `docs/columbus-historical-intake.md`;
`app/services/ingestion/measured_coverage.py`.
