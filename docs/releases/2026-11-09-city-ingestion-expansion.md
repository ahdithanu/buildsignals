# Reviewed city ingestion expansion

Follow-up: user authorized a 100,000-record regional-run ceiling and production
schedule updates. All 16 regional task definitions now embed the upgraded worker
hash `0d6d2ace3f9791be067eb8ddb652cf6cb90d4ab36fec51354dcb79dff5e6eee5`.
The worker uses 401 total 250-row pages, including an exhaustion probe, in resumed
chunks of <=100 pages (the shared service's per-call ceiling). Canary, quarantine
and count reconciliation remain; a post-run count outage now fails closed.
290 focused tests and scoped Ruff pass, including real SQLite checkpoint resume,
normalization and aggregate receipts. This is not a 100,000-row live load test.
Independent read-back verified all 16
task command hashes match the tested local worker bytes. Original first-city-run bounds below are
historical; Columbus production/demo task definitions are unchanged.

Upgrader preserves existing task image, command arguments, secret references,
network, role, retries, cadence and enabled/disabled state. It rejects scheduler
input overrides and mismatched source/tenant identities before writes. Existing
IAM task grants are retained; new revision grants precede target switching.
Texas revision 4 is expedited to November 9, 18:59:29 PST, then repeats daily.
Fresh Texas canary: 2,264 provider records, 10 valid samples, zero failures.
The actual expedited scheduled run passed:

| Check | Result |
|---|---|
| ECS task | `3205e9c70c2047bfae9682f6fb5b0beb` |
| Invocation | `chronos-schedule/region-texas_comptr`, task revision 4 |
| Container | STOPPED, exit 0 |
| Ingestion run | `b5c2181c-d360-4526-940e-c2279a7dd759`, completed |
| Provider before / seen / after | 2,264 / 2,264 / 2,264 |
| Inserted / updated / failed | 2,264 / 0 / 0 |
| Stored source records | 3,340, including earlier inventory |

Exact receipt log: `/ecs/buildsignals-ingestion`, stream
`region-texas_comptroller_sales_tax_locations-bfbdec33/worker/3205e9c70c2047bfae9682f6fb5b0beb`.
Two independent aggregate-only read-only database tasks
`8a0b3d92e6cf4efcae2115e45115336c` and `75f70b8c225549f08d2aeb9247c33ff5`
observed the active source, same scheduled run, recent heartbeat and zero failures
at 828 and 2,000 processed rows respectively. Both audit tasks exited 0.

These source records describe sales-tax-location registrations, not construction
permits, unique development projects or verified for-sale parcels. Success proves
this 2,264-record refresh, not a 100,000-row load test or complete statewide
coverage. No authenticated map/browser verification was performed in this rollout.

Date: November 9, 2026, America/Los_Angeles.

## Scope

Added Seattle land-use applications and Cincinnati commercial permits to the
explicit regional worker allowlist. Both already have reviewed Public Domain
catalog entries. Existing commercial, terminal-status, field-selection and
suppression predicates are preserved. No held sources were activated.

These are bounded new-application intakes: 31-day application-date window,
incremental storage, 250 rows/page, four pages maximum, provider count at most
1,000, canary before ingestion and control totals before/after. This does not
reconcile later changes to applications older than the window or retire records
that disappear from the source predicate. Empty recent scopes still fail the
existing guard rather than being called successful collections.

Cincinnati now uses `applieddate DESC, :id ASC` to stabilize tied-date paging.
Offset paging is not a publisher transaction snapshot; equal counts alone do
not prove completeness against concurrent publisher edits.

## Live verification and activation

- Seattle: provider count 3; 3 valid canary samples, zero failures.
- Cincinnati: provider count 316; 10 valid samples, zero failures.
- Both daily schedules created and updated to task revision 2 before first run.
- Worker image pinned to the existing regional image digest
  `sha256:3115a8ca51aedabbe52b640b607fe39a3aea6219564ccbf351b8edbd6e0bc8b2`.
- Production destination derived from the existing Columbus production task;
  no demo/customer record copy, API deployment or migration.
- Both first scheduled tasks completed with exit 0. Task definitions independently
  verified to contain the pagination fix and use the existing production tenant.

| Source | Run ID | Before / seen / after | Inserted / stored | Failed |
|---|---|---|---|---|
| Cincinnati | `77377f05-8577-42e8-bc29-7f51c666e7fd` | 316 / 316 / 316 | 316 / 316 | 0 |
| Seattle | `4f2cdb33-0b2f-4632-b0bc-b6c853c37c30` | 3 / 3 / 3 | 3 / 3 | 0 |

ECS tasks: Cincinnati `e9fb4a30e03c4e14b01955f1c61dff61`, Seattle
`00803596983a47cda45f21f1bdf6d5c6`; both scheduled revision 2. Exact CloudWatch
streams in `/ecs/buildsignals-ingestion` use the schedule name followed by
`/worker/<task-id>`. These receipts establish 319 newly stored records, not unique
projects, map-coordinate completeness, publisher completeness or browser display.
No fresh all-source inventory total is claimed.

Final local checks: 214 regional/provisioning/catalog tests passed in 3.10s;
scoped Ruff and whitespace checks passed. Independent read-only review completed;
full backend/PostgreSQL/browser suites not run for this scoped worker change.

## Existing operational gaps

Read-only November 8 receipts show successful Columbus production/demo refreshes
and ten successful regional feeds. Four regional failures were reproduced with
bounded public canaries on November 9:

- Arlington issued permits: publisher refresh 77.2 hours old versus 72-hour SLA.
- Dallas planning: publisher timestamp 608.8 hours old versus 336-hour SLA.
- Miami-Dade: invalid provider count response; root cause not yet established.
- Texas registrations: 2,264 recent records, exceeding the 1,000-record budget.

No freshness threshold or request budget was relaxed. Schedule ENABLED does not
mean ingestion succeeded. October 24 inventory counts are no longer current.

Arlington geometry is available in a bounded 5-row sample from each feed, but
catalog suppression excludes raw geometry and the normal pipeline stores raw
payloads. A privacy-preserving derived-point implementation needs a separate
review; do not simply enable raw geometry. Orlando's admitted mapping already
supports GeoJSON points; commercial-cohort source geometry completeness remains
unverified. Do not manufacture geocodes or call nearby parcels for sale.
