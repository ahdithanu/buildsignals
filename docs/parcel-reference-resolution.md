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
