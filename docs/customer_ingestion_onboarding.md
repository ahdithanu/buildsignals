# Customer Ingestion Onboarding

## Purpose

The onboarding control plane turns the reviewed production catalog into an
organization-specific ingestion plan. It does not discover sources, bypass
source review, or authorize network access. Those remain separate catalog,
legal-review, host-policy, and worker-deployment responsibilities.

## Data Model

`organization_ingestion_enrollments` stores one desired ingestion scope per
organization:

- nationwide or selected-state coverage
- permit, planning, and parcel record types
- reviewed rollout waves and deterministic shard count
- enabled state and the exact reviewed catalog-manifest digest
- catalog-sync, dispatch, error, creation, and update timestamps

`organization_ingestion_enrollment_sources` stores the resulting source-level
schedule. Each row belongs to one organization and one catalog source key and
tracks cadence, page bounds, next run, lease state, failures, completion, and
error details. Removed scope is retained as `removed` history instead of being
deleted. A tenant-paused source remains paused during catalog synchronization.

Both tables use organization foreign keys and PostgreSQL row-level security.
The API never accepts an organization ID from the request body; it derives the
tenant from the authenticated membership.

## API Workflow

1. Call `POST /v1/ingestion/onboarding/plan` to preview source and state scope.
2. Review `covered_regions`, `missing_regions`, automatic/manual counts, and
   every source's cadence and rollout wave.
3. An organization admin calls `PUT /v1/ingestion/onboarding/enrollment`.
4. Read the persisted state with `GET /v1/ingestion/onboarding/enrollment`.

Admins can activate or change scope. Editors and viewers can inspect plans and
the current enrollment but cannot mutate it. Every activation is audit logged.

## Operator CLI Workflow

The ingestion CLI also supports `onboarding plan` and `onboarding activate`.
Both require an explicit `--organization` (an existing active organization's ID
or slug) and print JSON containing the resolved organization, current catalog
manifest digest, and plan. Unknown, inactive, or ambiguous organizations fail
closed; there is no default-tenant enrollment.

```bash
python -m app.services.ingestion.cli onboarding plan \
  --organization "$ORGANIZATION_ID" \
  --coverage-mode selected_states --region TX --region GA \
  --record-type permit --record-type planning \
  --rollout-wave 1 --shard-count 4

python -m app.services.ingestion.cli onboarding activate \
  --organization "$ORGANIZATION_ID" --actor-user-id "$ADMIN_USER_ID" \
  --coverage-mode selected_states --region TX --region GA \
  --record-type permit --record-type planning \
  --rollout-wave 1 --shard-count 4 --dry-run

python -m app.services.ingestion.cli onboarding activate \
  --organization "$ORGANIZATION_ID" --actor-user-id "$ADMIN_USER_ID" \
  --coverage-mode selected_states --region TX --region GA \
  --record-type permit --record-type planning \
  --rollout-wave 1 --shard-count 4
```

These are trusted operator commands using the configured database credentials,
not a substitute for API authentication. Activation, including dry-run, requires
an explicit existing active user with admin membership in the selected active
organization. The CLI validates that membership before catalog writes and uses
the actor and tenant as the service context. It never creates a synthetic system
user, accepts an arbitrary audit identity, or bypasses tenant/FK checks. Planning
uses the existing system context and performs no mutations.

- Coverage defaults to `nationwide`, which rejects `--region`. For
  `selected_states`, repeat `--region` with at least one valid US state name/code
  or DC. Names are normalized by the existing onboarding service.
- Repeat `--record-type` for `permit`, `planning`, or `parcel`; omission selects
  all three. Repeat `--rollout-wave` for values 1 through 4; omission selects all
  four. Duplicate types or waves are rejected, as in the API.
- `--shard-count` accepts 1 through 128 and defaults to 4. It determines every
  selected source's shard assignment, not a single execution shard. There is no
  onboarding `--shard-index` or alternative-catalog option.
- Both commands require the checked-in manifest to match the current full
  production and candidate catalogs. In staging/production they also verify
  `INGESTION_ROLLOUT_MANIFEST_DIGEST` against the deployment attestation.
- Review `plan.sources`, `plan.source_count`, `plan.missing_regions`, and
  automatic/manual counts before applying. Valid but uncovered selections can
  produce an empty plan; candidates are never silently enrolled to fill gaps.
- `plan` and `activate --dry-run` issue no catalog, enrollment, or audit writes,
  including temporary writes. Dry-run returns catalog create/update/unchanged
  counts, `enrollment: null`, and zero enrollment-source mutation counts; those
  zeros are not a forecast of enrollment changes.
- Applying synchronizes only the selected reviewed sources and enables the
  enrollment. Scope replaces the previous selection; removed sources remain
  history, and tenant-paused sources stay paused. Reapplying the same scope does
  not duplicate enrollment or source rows.
- Every applied activation records the API-equivalent `ingestion_enrollment`
  created/updated audit event, actor, tenant, requested scope, source count, and
  missing regions in the same transaction. Errors roll back catalog, enrollment,
  and audit changes together. Success exits 0; validation/runtime failures exit
  nonzero. No command fetches records or invokes the dispatcher.

## Current Coverage Contract

The reviewed production catalog currently contains 134 sources and covers 43
states plus the District of Columbia. Iowa, Mississippi, Montana, New Mexico,
Oklahoma, West Virginia, and Wyoming remain explicit production gaps. They are
researched and represented in the candidate queue, but candidate presence is
not production coverage.

Mississippi now has two prioritized early-warning candidates:

- the statewide MDEQ Permit Activity Search for application and decision events
- D'Iberville council/planning agendas for development agreements, land-use
  cases, business openings, and infrastructure commitments

Both remain legal holds until commercial storage and derived-display rights and
supported reconciliation contracts are confirmed.

## Boundaries And Tradeoffs

- Catalog-only provisioning prevents an onboarding request from introducing an
  unreviewed URL or widening the outbound host policy.
- A normalized relational control plane keeps operational scheduling simple;
  ingested permit, parcel, party, and opportunity facts still project into the
  knowledge graph with evidence and provenance.
- Retaining removed and paused rows improves auditability at modest storage
  cost.
- Manifest pinning can make onboarding temporarily unavailable after a catalog
  change. This is intentional: production scope must be reviewed and regenerated
  before customer activation resumes.

## Continuous Dispatch

Activation does not perform a network fetch inside the API request. The
separate [customer ingestion dispatcher](./customer_ingestion_dispatcher.md)
claims due enrollment-source rows with expiring leases, establishes a fresh
organization context and database session per tenant, and calls the existing
bounded source executor. It enforces organization, source, page, and wall-clock
limits; isolates failures between customers; and applies exponential retry
backoff without expanding catalog or host policy.
