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
