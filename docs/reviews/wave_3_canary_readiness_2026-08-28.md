# Wave 3 canary readiness - 2026-08-28

## Scope

The manifest-pinned Wave 3 gate ran across all four deterministic shards using
the reviewed seven-host outbound policy. The wave covers 11 production sources
in Colorado, Massachusetts, and Maryland.

## Initial result

Ten sources passed immediately. Boulder Construction Permits returned valid
records but its lifecycle dates had changed from ArcGIS millisecond values to
ISO date strings. The catalog still applied a millisecond-only transform, so all
three sampled rows failed normalization.

## Repair

Boulder's application, issuance, and completion mappings now use the canonical
date parser with the existing future-date guard. This parser accepts both the
current ISO strings and legacy numeric timestamps. `IssuedDate` remains the
conservative boundary between pre-approval and approved records.

## Final result

- Sources reached: 11
- Sources passed: 11
- Sources blocked: 0
- Records fetched: 38
- Records normalized successfully: 38
- Record validation failures: 0
- Shard results: `2/2`, `3/3`, `2/2`, and `4/4`

The samples covered construction permits, demolitions, Article 80 development
projects, commercial permits, and county and statewide parcel context. The
canary transactions were rolled back and persisted no ingestion or graph data.
