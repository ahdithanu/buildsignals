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

- Qualify a Columbus-area parcel source, field scope, and identifier namespace.
- Measure exact-match, ambiguous, unmatched, and conflicting-address rates on
  the historical cohort before enabling enrichment.
- Add explicit reviewed acceptance with both source evidence records retained.
- Preserve the existing deal-centered nearby search and its radius/ranking
  controls; do not treat an anchor parcel as a ranked nearby candidate.
- Verify the signed-in source-to-timeline-to-parcel-to-saved-deal workflow.

The first-quarter Columbus permits are still local qualification data, not
production inventory. This API alone does not populate missing parcel sources.
