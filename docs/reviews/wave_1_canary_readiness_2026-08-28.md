# Wave 1 canary readiness - 2026-08-28

## Scope

The manifest-pinned Wave 1 readiness gate ran against all four deterministic
shards using the reviewed 16-host outbound policy. Each source was limited to a
three-record canary page, although connector-specific freshness probes and
multi-stage samples can return additional bounded records.

## Result

- Sources reached: 27
- Sources passed: 26
- Sources blocked: 1
- Records fetched: 206
- Records normalized successfully: 206
- Record validation failures: 0
- Persisted ingestion sources, runs, mappings, or records: 0

Shard results were `11/11`, `5/6`, `6/6`, and `4/4`. The successful samples
included approved permits, pre-approval permit applications, planning hearings,
state license applications, retailer location filings, and parcel snapshots.

## Open blocker

`dallas_tx_legistar_planning_agendas` returned three valid
`hearing_scheduled` records with no normalization errors. Its newest publisher
modification timestamp was approximately 393 hours old, exceeding the reviewed
336-hour freshness SLA. The connector already requests the bounded event window
in newest-ID order, so no connector regression was identified.

Keep the Dallas source blocked from Wave 1 activation until a later canary sees
a publisher update inside the 14-day window. Do not weaken the reviewed
freshness control merely to make the gate pass.

## Verification

The focused ingestion CLI, health, and Legistar suites passed 107 tests. The
complete backend suite passed 878 tests with 5 skips. The canary transaction was
rolled back after every shard, and a direct database check confirmed that the
live validation persisted no ingestion state.
