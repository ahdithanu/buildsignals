# Parcel Reference Review

`GET /ingestion/permits/{permit_id}/parcel-candidates?parcel_source_id=...`
requires authentication and a tenant-visible active permit and parcel source.
It is a read-only candidate lookup, not an automatic identity merge.

The service uses exact external parcel or physical-group IDs within the
specified source. Leading zeros and punctuation are preserved. It returns at
most 20 candidates, marks truncation, and reports ambiguous multi-row matches.
Retired parcels and cross-tenant evidence are excluded. Source and permit
evidence IDs, capture time, source update time, and last verification time are
available for review. No raw source payload or personal ownership data is
included.

Matching state and normalized full address corroborate an identifier; missing
or contradictory addresses remain review cases. Confidence is categorical,
not a fabricated calibrated probability. Even a single corroborated candidate
does not write coordinates, create a graph edge, or imply for-sale availability.

Each candidate now reports independent state, city, and street comparisons as
`match`, `missing`, or `conflict`. The combined address comparison gives
conflicts precedence over missing fields, and requires all three components
to match for corroboration. Blank values never corroborate identity. Existing
boolean fields remain available for clients.

## Columbus Qualification Status (2026-09-19)

The official CSIR parcel-layer metadata is readable at
https://gis.columbus.gov/arcgis/rest/services/Applications/CSIR_Public/MapServer/3.
It lists PARCELID, PARCEL_CD, and LOWPARCELID identifiers, but their equivalence
to permit parcel references has not been verified. Copyright text is blank;
commercial reuse rights remain unqualified, not implicitly granted.

A bounded read-only check selected the first ten January commercial permits
ordered by external record ID, queried only those exact references across the
three ID fields, requested at most 100 rows, and excluded geometry, ownership,
and contact fields. The official query endpoint returned HTTP 403. No parcel
payload was received, persisted, or linked; no match rate can be reported.
Do not reinterpret this access failure as zero matches, retry against hidden
interfaces, or activate this source. Next research can assess a supported
official extract or obtain an authorized query interface and reuse terms.

## Remaining Gates

### Official extract follow-up (2026-09-20)

Read-only review of the county's published [current extract directory](https://apps.franklincountyauditor.com/GIS_Shapefiles/CurrentExtracts/)
confirmed a listed 20260917_Parcel_Polygons.zip (141,615,888 bytes). This is a
possible supported distribution channel, not evidence of a successful download,
field mapping, commercial reuse permission, or coverage in BuildSignals.
The [parcel CSV directory](https://apps.franklincountyauditor.com/Parcel_CSV/)
lists annual folders through 2025; it must not be advertised as a current 2026
parcel snapshot. No bulk files or ownership records were downloaded or ingested.
Source-use qualification and exact namespace validation remain open before a
bounded field-level sample can be accepted for production use.

### County query qualification sample (2026-09-20)

The separately published [Franklin County tax-parcel layer](https://gis.franklincountyohio.gov/hosting/rest/services/ParcelFeatures/Parcel_Features_WebMercator/MapServer/0)
accepted bounded public queries (HTTP 200). This is a county distribution source,
not an alternate Columbus CSIR access path. Three requests were made: eight
distinct IDs from the first ten January commercial permits ordered by external
record ID, one row to inspect identifier formatting, and those same eight IDs
with the observed hyphen format. No geometry, ownership, or contact fields were
requested. No database or production source was changed.

- Original nine-digit references: zero returned rows.
- Hypothesis `NNNNNNNNN -> NNN-NNNNNN`: eight rows for eight distinct references,
  no reported transfer truncation and no duplicate IDs in the returned sample.
- Permit-weighted street comparison: two matches, eight conflicts, zero ambiguous,
  zero unmatched after formatting, zero missing streets. This is ten permits,
  **not ten distinct parcels**; three permits share one reference.
- Three conflicts involve county address ranges. Four involve different streets
  (three permits on MERCHANTS ROW versus WORTH AVE and one THE STRAND versus
  GRAMERCY ST). One is LOCKBOURNE RD versus LOCKBOURNE AVE. None is auto-accepted.
- City/state are not established by the selected county fields. Even the two
  matching streets are not fully corroborated parcel identities.
- `LOWPARCELID` is a separate map-routing identifier; do not treat it as the
  permit reference or strip its suffix without qualification.
- `LASTUPDATE` and `VALID` were null in all eight rows. Freshness is unknown.
- `STATEDAREA` metadata says Legal Acres, but observed values include 35,069
  alongside `ACRES=0.80507449`. Units are inconsistent with the alias. Do not map
  that field to acreage or infer a universal conversion. Geometry-derived
  `ACRES` also requires qualification before underwriting use.

`scripts/franklin_parcel_qualification.py` provides an offline, non-mutating sample
report for caller-supplied records. It preserves leading zeros, rejects other
identifier formats, keeps address ranges as conflicts, and refuses failed or
truncated responses. Twelve unit tests pass. It is deliberately not connected
to production resolution or ingestion. No returned parcel payload was persisted.
The formatting observation is preliminary, not a cohort-wide match rate or
approved namespace. Reuse rights, historical parcel changes, geometry, and
evidence-backed acceptance remain open. The 2,049 historical permits remain
local qualification data only.

#### Reproducible offline reports

From the repository root, with authorized local evidence files:

```sh
.venv/bin/python -m scripts.franklin_parcel_qualification --permits /absolute/path/permits.json --parcels /absolute/path/parcels.json
```

The permit input is a JSON array with `parcel_id` and `address`; the parcel input
is a complete ArcGIS response containing `features[].attributes.PARCELID` and
`SITEADDRESS`. The tool only reads these files and prints a JSON report. It does
not fetch, change databases, or activate sources. Inputs are limited to 10 MB
each and 10,000 records each. Failed, truncated, and malformed responses fail
with exit code 2 and no report rather than generating zero-match statistics.

Reports include UTC measurement time and SHA-256 hashes of the exact input bytes.
The hashes identify supplied evidence, but do not authenticate its origin or
establish capture time or freshness. Record those separately with source receipts.
Counts distinguish evaluated permit rows, distinct supported permit references,
returned parcel rows, and distinct returned parcel identifiers. Repeated permit
references remain repeated in the permit-weighted outcome counts. The report
omits street addresses and unselected fields such as owner names. Full-cohort
analysis still requires a complete authorized parcel response for the selected
references; a caller-supplied subset cannot establish county-wide match rates.
Twenty-four tests cover reporting, exact-byte receipts, malformed evidence,
bounds, repeated references, and failure handling. Production eligibility remains
false in every report.

### Reviewed Acceptance Implemented

`POST /ingestion/permits/{permit_id}/parcel-acceptance` requires strict
authenticated editor/admin access. Supply the parcel source, parcel ID, the
expected current raw evidence IDs for both records, a reason of 10-1000
characters, and explicit analyst-assigned confidence. Stale evidence,
ambiguous/truncated matches, missing or conflicting address evidence, and
missing typed graph entities are rejected. A current reviewed link to another
parcel must be resolved before accepting a new target.

Acceptance creates a `permit_for` graph relationship using the existing graph
service. Each review retains both raw-record identifiers, capture dates,
normalization hashes, reviewer ID, reason, and a unique review identifier in
evidence payloads; an audit log is written in the same transaction. PostgreSQL
row locks serialize reviews and canonical record updates. Repeated reviews
reuse the relationship but append a new review/evidence pair. Existing graph
confidence semantics retain the maximum confidence; each review's requested
confidence remains recorded separately and is not a calibrated probability.

No coordinates, availability claims, raw source data, or nearby rankings are
copied into the permit. The backend and UI have not yet been verified together
against live parcel data. Real Columbus acceptance remains gated on source qualification.

### Permit Review UI

The permit detail page includes a parcel-source selector, candidate comparison
results, evidence identifiers, and links to parcel details. Editor/admin users
can submit an explicit rationale and confidence for an eligible candidate.
Viewers cannot access the acceptance form. Ambiguous, truncated, failed, and
uncorroborated results do not enable acceptance. A stale-evidence rejection
requires a reload and new review inputs; success refreshes the permit graph.
Review state and query keys are scoped to the tenant and permit.

Verification: six focused frontend tests, TypeScript checks, and a production
build passed. Playwright rendered mocked review records at 1440x1000 and
390x844 with no horizontal overflow. These are UI fixtures, not production
data or live end-to-end acceptance. The build retains a large-bundle warning.

### Measurement API Implemented

`GET /ingestion/sources/{permit_source_id}/parcel-reference-audit?parcel_source_id=...`
requires authentication and active tenant-visible sources of the correct types.
It evaluates at most 100 permits per request (default 50), ordered by permit ID,
and returns `next_after_id` for keyset pagination. Each permit occupies exactly
one bucket: missing reference, no local match, ambiguous, address corroborated,
conflicting address, or missing address evidence. Ambiguity takes precedence
over individual candidate address checks. The response includes candidate
evidence for drill-down and is marked `Cache-Control: no-store`.

No eligible stored parcel evidence yields `parcel_evidence_unavailable` and
zero **evaluated** permits, not a zero match-rate claim. Measurements describe
only the requested page and current local snapshots. They do not establish
source completeness or a frozen historical population. The diagnostic reuses
the single-permit resolver; the 100-permit cap bounds its per-permit queries.
Bulk offline population analysis should use a dedicated batched query if scale
warrants it. The endpoint is read-only and performs no external requests.

This implements the measurement mechanism; real Columbus matching remains
unmeasured while the parcel-source access and qualification gates are open.

- Qualify a Columbus-area parcel source, field scope, and identifier namespace.
- Measure exact-match, ambiguous, unmatched, and conflicting-address rates on
  the historical cohort before enabling enrichment.
- Verify reviewed acceptance against a qualified live parcel source.
- Preserve the existing deal-centered nearby search and its radius/ranking
  controls; do not treat an anchor parcel as a ranked nearby candidate.
- Verify the signed-in source-to-timeline-to-parcel-to-saved-deal workflow.

The first-quarter Columbus permits are still local qualification data, not
production inventory. This API alone does not populate missing parcel sources.
