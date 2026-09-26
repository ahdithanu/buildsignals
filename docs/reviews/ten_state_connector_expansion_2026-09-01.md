# Ten-State Connector Expansion - 2026-09-01

## Scope

This pass audited the ten states that previously had no production catalog
source: Alaska, Hawaii, Idaho, Iowa, Mississippi, Montana, New Mexico,
Oklahoma, West Virginia, and Wyoming. Admission required an official structured
source, stable identity, bounded reconciliation, current live records, and an
affirmative commercial-use basis appropriate to the retained fields.

## Production Admissions

Three official parcel-context sources cleared the gate:

- Alaska DNR statewide parcel composite: attributed derived geometry and parcel
  context, with owner, value, mailing, sales, and raw exports excluded.
- Hawaii statewide 2026 TMK parcels: public-domain identity, acreage, evidence
  link, and geometry, with owner, value, sale, legal, and raw exports excluded.
- Idaho ITS parcel framework: participating-county identity, steward, acreage,
  category, and geometry, with mailing, owner, legal, value, sale, and raw
  exports excluded.

Each source passed a bounded rollback-only canary with 5 of 5 records fetched
and normalized and zero record failures. Canary transactions persisted no
source, run, mapping, parcel, or graph records.

These additions raise production coverage from 40 to 43 states. They add parcel
context only and do not close statewide permit-lifecycle gaps in those states.

## Remaining Holds

- Iowa: useful permit and parcel candidates lack complete reconciliation or
  affirmative commercial storage/display/export rights.
- Mississippi: permit portals lack supported bulk lifecycle contracts; current
  statewide parcel candidates remain rights-held.
- Montana: the current state cadastral service is technically strong, but its
  item license is blank and source-chain commercial rights are ambiguous.
- New Mexico: current permit candidates have unstable duplicate identities or
  missing reuse grants; Albuquerque bulk evidence is stale and issued-only.
- Oklahoma: Tulsa development-plan polygons are commercially reusable planning
  context, but lack reliable lifecycle dates, status, address, and parcel IDs;
  they require spatial change detection before production admission.
- West Virginia: current oil/gas applications are valuable but outside the core
  building/retail scope and have no named reuse license; the public parcel REST
  layer is stale relative to the 2026 downloadable snapshot.
- Wyoming: current statewide parcels and Sheridan planning records are
  technically useful, but neither source publishes an affirmative commercial
  reuse grant sufficient for this production scope.

## Rollout Pin

The catalog contains 134 production sources. The generated rollout manifest
digest is
`458c44bf67d7e2a0f35d85c57023c85302669a006f9ddafd4f93c06a25cd4d13`.
Production services must use this exact digest and the manifest-generated
outbound host policy before write-enabled collection.
