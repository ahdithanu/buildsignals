# Temporal Intelligence Foundation

## Purpose And Scope

Implements the first foundation slice of the institutional intelligence PRD:
source-backed attribute observations, normalized event assertions, historical
queries, and a basic numeric change calculation. This is not a predictive signal
engine, a Development Velocity score, or a validated investment recommendation.

The new layer is additive. Existing permit events, planning records, knowledge
graph relationships, brand reviews, and saved assessments remain available.
Ingestion adapters own domain interpretation; the temporal service has no permit
or planning-specific rules. No frontend redesign or deployment is included.

## Schema

`temporal_observations` records an entity ID snapshot, attribute, JSON value,
unit, source identity/type, raw evidence reference, source URL, geography,
confidence, methodology version, content hash, and three distinct clocks:

| Clock | Meaning |
| --- | --- |
| `effective_at` | Date applicable to the assertion, when explicitly known. Nullable. It may be a future scheduled date. |
| `first_observed_at` | When BuildSignals first captured this immutable raw content version. Derived from `RawSourceRecord.received_at`. |
| `recorded_at` | When this interpretation was persisted by BuildSignals. Server-owned, not caller-supplied. |

`source_updated_at` preserves provider metadata separately. It is neither proof
of public availability nor a replacement for BuildSignals' knowledge clocks.

`temporal_events` links a typed event assertion to one observation, retaining its
optional occurrence/scheduled date and server-recorded timestamp. Entity and
evidence are obtained through that observation, avoiding duplicate mutable data.

- Unique `(organization_id, observation_key)` makes retried writes idempotent.
  Reusing a key with different content fails instead of rewriting history.
- A series is partitioned by entity, source, external record, attribute, and
  methodology version. The normalization hash is part of ingestion methodology.
  Different sources or interpretation versions are not silently compared.
- Composite foreign keys keep observations with their own tenant's raw evidence
  and events with their own tenant's observations. Services also validate entity
  and source ownership before writing. API reads always require authentication.
- Entity IDs are historical snapshots, deliberately not graph foreign keys.
  Existing graph merges must not rewrite historical knowledge. Merge tombstones
  remain available; automatic survivor-history union is a future graph feature.
- ORM listeners and Alembic-installed database triggers reject update/delete.
  PostgreSQL additionally enables and forces row-level security. Whole-tenant
  erasure remains possible through parent-organization cascade. These controls
  do not claim protection against a privileged database administrator.

## Ingestion Semantics

Permit projections retain status/stage, project name, valuation, area, units,
and explicitly supplied filing/approval/issue/completion dates. Planning
projections retain stage, title, project name, record type, and supplied
publication/meeting/decision dates. Unbounded document text remains in existing
canonical records and raw evidence rather than being duplicated as attributes.

An unchanged poll does not grow the timeline. A correction appends a snapshot;
a return from A to B to A appends the return even when A's original raw bytes are
reused. A previously observed value becoming unavailable is represented by JSON
null, not a deletion or a guessed zero. Currency stays an exact decimal string;
the initial generic numeric calculation intentionally does not coerce strings.

Events are conservative:

- `permit.status_observed` is not a verified new opening.
- `permit.issued` requires an explicit issued date, not just a status label.
- `planning.meeting_scheduled` does not assert the meeting happened.
- `planning.decision_recorded` does not assert approval.
- A change elsewhere in a source record does not repeatedly emit the same
  unchanged lifecycle event.

Confidence describes the captured assertion, not signal profitability or the
probability of construction. Exact permit-field projections use 1.0 for mapping
fidelity; planning retains its canonical confidence. Neither is empirically
calibrated signal confidence.

## API And Historical Queries

All endpoints use the existing authenticated tenant context:

```text
GET /v1/temporal/observations?entity_id=...&attribute=...&as_of=...
GET /v1/temporal/observations?observation_id=...&as_of=...
GET /v1/temporal/events?entity_id=...&event_type=...&as_of=...
GET /v1/temporal/changes?series_key=...&as_of=...
POST /v1/temporal/activity-baseline
```

`as_of` must include a timezone. Omission means now. Reads require both
`first_observed_at <= as_of` and `recorded_at <= as_of`. Event reads additionally
require the event itself to have been recorded by the cutoff. Future scheduled
dates can be known at the cutoff; a query is a knowledge timeline, not a claim
that every returned event has already occurred.

Lists have a default limit of 100, maximum 500, and bounded offsets. Observation
responses expose source and raw-record IDs for drill-down; event responses point
to those observations. There are no public mutation endpoints in this slice.

The change endpoint compares the two most recently recorded observations in
one series, not historical market averages. It returns absolute/percent change
and direction, with evidence IDs. Zero denominators, incompatible units,
non-numeric values, and insufficient history are explicit states. It provides
no score, significance, market coverage claim, or investment recommendation.

The read-only activity-baseline endpoint adds version-pinned, correction-aware
filing or issuance counts by source and city, complete UTC windows, evidence
links, and explicit coverage-unverified states. It does not emit a Development
Velocity score. See `activity-baseline.md` for its counting contract and limits.

## Backfill And Validation Boundaries

Migration `20260914_0001` creates empty tables. Existing canonical records enter
the timeline when their source is next observed, including an unchanged poll.
This does not replay every historical raw version automatically. Historical
source availability, extraction-version registries, cross-source corroboration,
event correction/retraction resolution, relationship snapshots, and qualified
market baselines remain future work. Descriptive source-cohort diagnostics are
now available, but they do not close historical completeness gates.

An old filing imported today is excluded from a strict query dated before
today. An old raw record interpreted today is likewise excluded before the new
interpretation was recorded. A future retrospective simulator may recompute
features using an explicitly frozen model and historically available inputs,
but must label that simulated output separately from an actually emitted signal.

Do not count event rows as unique physical projects or backtest them directly:
events are versioned evidence assertions. A scoring engine must resolve
corrections, deduplicate entities/events across sources and model versions,
account for coverage gaps, and use a frozen cohort before measuring activity.

## Release And Scaling

The original temporary worktree disappeared before resumption on September 19.
Its recorded patches were recovered onto `codex/temporal-foundation-recovery` in
`/Users/ahdithebomb/Desktop/DealSignal/.worktrees/temporal-foundation` and retested.
This worktree lives inside the project rather than the system temporary folder.
The implementation remains separate from the pending parcel-reference repair
and does not change deployed data or infrastructure.

Apply the additive migration before running the new API or workers. Existing
source snapshots are not updated. Downgrade removes only the two new tables and
their history, so retain that history before any rollback once writes begin.

Tests cover idempotency, corrections/reversions, immutable writes, future and
unknown dates, historical cutoffs, cross-tenant references, authenticated reads,
numeric edge cases, ingestion compatibility, and migration reversibility.
SQLite tests cannot substitute for a production PostgreSQL RLS/restore drill.

Local verification, September 14, 2026:

- Full backend suite: 1,023 passed, 7 PostgreSQL-dependent tests skipped.
- Focused temporal service, ingestion and migration tests: 32 passed.
- Ruff and `git diff --check`: passed.
- SQLite migration upgrade/downgrade/re-upgrade and database mutation/erasure
  checks: passed.
- Independent static review findings were fixed and regression-tested.
- OpenAPI regenerated with the three authenticated read endpoints.
- No frontend changes, production migration, provisioning, push or deployment.

The new-table model/migration comparison reports no drift. The repository-wide
`alembic check` still fails for pre-existing nullability/index differences on
legacy tables (including contacts, deals, users and organizations). The same
failure was reproduced on the unchanged pre-temporal baseline using a separate
disposable database. That gate is not waived; reconcile it separately before
release. PostgreSQL-specific tests are gated by `TEST_POSTGRES_URL`; the September
14 run did not execute them. On September 19, a disposable Unix-socket-only
PostgreSQL cluster was created locally. PostGIS was installed by its administrator,
then migrations were applied as `temporal_test`, a verified non-superuser with
no BYPASSRLS privilege. Local PostgreSQL tests now cover temporal RLS,
immutability, tenant erasure, cohort ranking and history overflow. This does not
replace production-role verification, restore drills or production load testing.

Start with indexed PostgreSQL queries and bounded batches. Measure growth and
query latency before adding keyset pagination, bulk projection, partitions,
materialized historical cohorts, or a dedicated analytical store. Preserve the
raw evidence and methodology contracts when moving calculations out of process.

Next: finish historical ingestion/replay provenance, then one-market Development
Velocity with measured coverage and a documented baseline. Power constraints,
company expansion, backtesting, and the institutional terminal follow the
acceptance gates in `institutional-intelligence-roadmap.md`.
