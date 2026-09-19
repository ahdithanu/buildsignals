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
copied into the permit. This is a backend review action, not yet a signed-in
UI workflow. Real Columbus acceptance is still gated on qualified parcel data.

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
- Connect the reviewed-acceptance API to the signed-in review workflow.
- Preserve the existing deal-centered nearby search and its radius/ranking
  controls; do not treat an anchor parcel as a ranked nearby candidate.
- Verify the signed-in source-to-timeline-to-parcel-to-saved-deal workflow.

The first-quarter Columbus permits are still local qualification data, not
production inventory. This API alone does not populate missing parcel sources.
