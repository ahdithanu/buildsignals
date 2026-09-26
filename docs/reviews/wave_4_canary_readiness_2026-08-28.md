# Wave 4 canary readiness - 2026-08-28

## Scope

The manifest-pinned Wave 4 gate ran across four deterministic shards. The wave
covers 67 production sources across 32 states and the District of Columbia on
51 reviewed outbound hosts. Every run used bounded samples and rollback-only
transactions.

## Initial result

Sixty-one sources passed immediately. Six source contracts had drifted:

- Delaware stormwater NOI returned undated rows ahead of usable lifecycle data.
- DC Basic Business Licenses changed fields and in-district values.
- Greenville County's parcel service had stopped.
- Portland's permit class was populated in `FOLDERTYPE`, not `TYPE`.
- Fairfax's prior DevelopmentTracker service began requiring a token.
- Detroit's keyset transport field was absent from its explicit output fields.

## Repairs

The catalog now filters Delaware to dated records, maps DC's current public
business-license schema, uses the official City of Greenville weekly parcel
layer, filters Portland by `FOLDERTYPE`, uses Fairfax's public approved-site
replacement with an `approved_only` label, and explicitly requests Detroit's
`ObjectId` cursor. Focused canaries then passed all six repaired sources with
18 of 18 records normalized successfully.

## Final result

- Sources reached: 67
- Sources passed: 66
- Sources with catalog or record-validation failures: 0
- Records fetched: 329
- Records normalized successfully: 327
- Records intentionally filtered: 2
- Record validation failures: 0
- Shard results: `15/15`, `13/14`, `22/22`, and `16/16`

The sole unavailable source was Louisville/Jefferson County LOJIC parcels. It
passed the initial Wave 4 run with three valid records, then the official host
began redirecting queries to a maintenance page during the final run and an
immediate targeted retry. This is recorded as transient external availability,
not a schema, normalization, or policy failure. Production should retain normal
retry and health-alert behavior and must not replace the source with an
unverified mirror. An official Louisville Metro 2025 public parcel view was
also evaluated, but it is marked deprecated and is not an acceptable substitute
for the normally daily authoritative LOJIC feed; using it would make stale
geometry appear current.

All canary transactions were rolled back and persisted no ingestion, mapping,
or graph data. The generated rollout manifest digest is
`4d836e56cf92517db2ffb39db186a2e9c1bd0ef0169e5a97f02e922d6a4dee82`.
