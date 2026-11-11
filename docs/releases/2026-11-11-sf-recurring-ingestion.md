# San Francisco Recurring Ingestion Release

## Current State

Production collection, idempotent manual replay and the read-only provenance/graph
audit passed. SF has **6,711 distinct source records**, not unique projects or new
filings. **Zero coordinates and zero SF map points** were measured. This is not
map or parcel-workflow acceptance. The daily SF schedule remains enabled, with
all previous 22 schedules enabled and their regional RunTask grants intact.

## Authorization And Scope

November 11, 2026. User approved merging PR271 then272, releasing the reviewed
ingestion worker and activating SF building ingestion only after fresh checks.
Existing jobs remain enabled. No migrations, paid-service upgrades, NJ activation,
historical data repair, failed-source recovery or unrelated API release.

## Merge And Image

- PR271 merged as `9980e062a4665be3907f2a783071c88ffff36a16`.
- PR272 retargeted to main after its dependency, then merged as
  `24d3c97d88dd80886f93ef7296ad087cf682ff8c`.
- Main's tree matches tested `2a8153c` exactly. Its hosted results: 2,541 backend
  tests passed,91.29% coverage;18 browser E2E passed. Lint/security checks green.
- Existing CodeBuild `dealsignal-image-build` built the tracked-file archive of
  `2a8153c`, with unique tag `worker-2a8153c`; no latest-tag rewrite.
  Build `3b59f8f2-83cc-4aa7-becb-4699233b2ba6` SUCCEEDED.
- Image digest:
  `sha256:bcfa42013f6c22a706660f7dbab3ee573da49693f3ae4acbc8aa24df7a78452a`.
- Embedded worker SHA256:
  `5b0aac770e0f074542aaf10aeeecba07277fab307f71f7927dd1645cd55d076b`.
- API auto-deploy is false; API image remains `investment-private-3a814ee`.
  The migration/API deployment workflow was not invoked.

Post-merge main CI43104819499 also passed:2,541 tests,91.29% coverage,
969.35seconds. Main frontend,security-scan,OpenAPI and pre-commit passed.
Fresh local provisioner/worker/checkpoint/Ocala guard suite:94passed in0.96s.

## Fresh Gates

Local read-only SF verification:6,711 provider rows,13 valid canary validations,
zero failed. Primary-address predicate,31-day changed-row window on data_loaded_at,
two-field data_loaded_at/record_id keyset, explicit projection and36-hour publisher
freshness gate retained. This window measures changed records, not new filings.

Exact-image ECS preflight `656d96f3be4f4a8eb979769e29e6c8fa`, task definition
`buildsignals-sf-release-check:1`, STOPPED/exit0. Public count/canary repeated from
the worker network with the same results. Explicit PostgreSQL READ ONLY transaction
with tenant-local RLS scope found zero registrations matching the reviewed SF key
or dataset ID; stored_before0 refers only to that registration scope, not a
comprehensive historical SF-data audit. No matching legacy key/URL migration or
quarantine recovery was needed. Output only
included source/count/compatibility facts, not tenant identity, secrets or records.
Task secret references, execution role, CPU/memory/network mode match the accepted
Texas worker. No image-default serve/migrate command was used.

## Schedule And Acceptance

Only the fresh SF row was supplied to the reviewed provisioner. New schedule:
`region-san_francisco_ca_building_permits_primary_a-d90cb866`, rate(1 day),
first eligible start21:46:21UTC. Task definition:
`buildsignals-region-san_francisco_ca_building_permits_primary_a-d90cb866:1`.
Canonical host allowlist is data.sf.gov. Existing regional IAM task permissions
are retained by the provisioner. All23 schedules are ENABLED after provisioning;
no existing job was paused or substituted.

An enabled schedule alone is not acceptance. The actual Scheduler invocation,
reconciliation, replay and tenant-scoped audit receipts are recorded below.
NJ remains inactive. Existing four failing feeds remain separate, without
freshness/identity/access or quarantine bypasses.

Map limitation: the reviewed SF projection/mappings do not contain coordinates.
Successful source ingestion and graph projection must not be presented as SF
map-point coverage. Report actual coordinate/map-service counts in the audit;
qualify geocoding or a parcel join separately. No inferred coordinates or new
projection fields were introduced during this acceptance run.

First task0b76fbc5dc1841b3bc61f03dc4fb5d3d started21:47:03UTC, startedBy
chronos-schedule/region-san_francisc, exact reviewed image. A separate read-only
progress task3df0feaa9582466db3ab3fafe23bfb02 exited0:at21:54:05UTC,1,638stored,
1,638seen/inserted,zero failed and a running heartbeat. This is partial inventory,
not completion. The local AWS waiter reached its maximum attempts while the
underlying ECS task was still RUNNING; this did not stop or fail the ingestion.

### Actual Scheduled Collection

First task completed with container exit0 at approximately22:16UTC. Its aggregate
receipt is statuscompleted, provider_before6,711/seen6,711/provider_after6,711,
inserted6,711/updated0/failed0/stored6,711. One chunk/run:
`e0664b5d-b68b-423e-9ec7-44bae8214cb8`. Scheduler provenance and exact image were
verified separately above. These are source-row counts, not unique projects or
6,711 newly filed permits. ECS reached STOPPED/exit0 at22:16:47UTC.

### Manual Replay

Task `ae876c1bdf284bd0b437ee934dcb4b00`, startedBy `sf-manual-replay`, ran the same
task definition/image/profile after the first task stopped. STOPPED/exit0 at
22:29:50UTC. Run `e833b1a4-a655-4965-82e9-86cf5058e0db` reconciled
6,711 before/seen/after, **zero inserts, updates or failures**, stored6,711.
This verifies same-scope idempotency on unchanged input, not a second daily
Scheduler invocation. Both database run rows say trigger=scheduled because the
worker labels that way; ECS startedBy establishes the manual/scheduled distinction.
Completed Socrata runs retain terminal checkpoints; their presence is not failure.

### Read-Only Audit

Task `ff1945d7f9d2408fa20e4c1e74608325`, task definition
`buildsignals-sf-release-check:2`, returned audit_passed/containerexit0. The audit
used PostgreSQL READ ONLY before queries, explicit tenant/RLS scope, the exact
scheduled run ID and aggregate-only output. Its executable remains in the
versioned task definition; no local temporary file is required to inspect it.
Audit-body SHA256:
`dbca5083f711d10848032a02c15b0bd3c9ce4f5c41d71536746ff27c6ee691d3`.

| Measurement | Count |
| --- | ---: |
| Active canonical SF records | 6,711 |
| Distinct external identities | 6,711 |
| Latest raw-evidence links with source URL | 6,711 |
| Raw source snapshots | 6,711 |
| Source-scoped permit graph entities | 6,711 |
| Canonical permits joined to their permit graph entity | 6,711 |
| Coordinate-bearing SF records | 0 |
| SF rows returned on the first CA map-service page | 0 |

Graph linkage was checked using GraphEntityLink record IDs, entity type and
source/tenant scope, not inferred from equal entity counts alone. Map-service
results are not browser acceptance. Missing coordinates are a measured product
gap, not a successful populated SF map. Existing demo geocoding is hard-gated
to Columbus/demo and cannot be silently applied to production SF. A separate
bounded, provenance-preserving geocoding/parcel-matching and map change is needed.

Registered task image, embedded worker SHA and data.sf.gov-only allowlist were
reverified. All23 schedules remain enabled; every regional target retains IAM
RunTask permission. No existing source quarantine was cleared.

## Rollback

For this new SF-only release, disable the named SF schedule if verification fails;
leave the other22 schedules and existing IAM grants untouched. Retain the immutable
image/task definition for diagnosis. Do not delete persisted evidence, clear
quarantine or silently rewrite source identity as a rollback. The API was not
changed by worker image publication.
