# Enterprise product roadmap (stubs)

Items requiring product/engineering investment beyond operational readiness.
Track status in [enterprise_readiness.md](enterprise_readiness.md) tier I.

---

## SSO (I1)

**Target:** SAML 2.0 and OIDC for enterprise IdPs (Okta, Azure AD, Google Workspace).

**Stub implementation path:**
1. Add `sso_connections` table (org_id, idp_metadata, client_id, enabled).
2. Routes: `GET /v1/auth/sso/:org_slug/login`, `POST /v1/auth/sso/callback`.
3. JIT provision users on first SSO login; map IdP groups → DealSignal roles.
4. Frontend: "Sign in with SSO" on login page when org has SSO enabled.

**Dependencies:** Org admin UI, secrets for IdP certs, audit log entries for SSO events.

---

## SCIM provisioning (I2)

**Target:** Automated user lifecycle from IdP (create/update/deactivate).

**Stub path:** SCIM 2.0 `/scim/v2/Users` endpoint behind org API key or mTLS.

---

## Organization API keys (I3)

**Target:** Machine-to-machine access for integrations without user JWT.

**Implemented foundation:** Organization admins can create, list, and revoke
backend-managed API keys. Secrets are generated once, stored only as SHA-256
hashes, scoped to an organization, and lifecycle events are audit logged. Admins
can manage keys from Settings. Public read endpoints accept
`Authorization: Bearer bs_live_...` or `X-API-Key` headers for tenant-scoped deal
and signal exports, enforce a per-key rate limit, and record usage events for
admin visibility.

**Initial public API:**

- `GET /v1/public/deals`
- `GET /v1/public/deals/{deal_id}`
- `GET /v1/public/deals/{deal_id}/graph-context`
- `GET /v1/public/deals/{deal_id}/workflow-history`
- `GET /v1/public/eval-runs`
- `GET /v1/public/eval-runs/{run_id}`
- `GET /v1/public/signals`
- `GET /v1/public/signals/{signal_id}/assessment-revisions`
- `GET /v1/public/assessment-revisions/{revision_id}/reviews`
- `GET /v1/public/assessment-revisions/{revision_id}/publication`

**Implemented integration polish:** Copy-ready Python and TypeScript client
snippets live in `docs/examples/` and are linked from `docs/public-api.md`.
Public API keys can now export opportunity workflow history, assessment revision
snapshots, review decisions, and publication events for downstream audit, CRM,
and data warehouse sync without allowing external systems to mutate approvals.

**Remaining path:**
1. Generate versioned Python and TypeScript SDK packages from OpenAPI once the
   API surface stabilizes.
2. Add write-scoped integration endpoints only after per-action approval scopes
   and customer-specific governance policies are in place.

---

## Billing / usage metering (I6)

**Target:** Usage-based billing for AI enrichment, memo generation, seat count.

**Stub path:** Emit usage events and daily aggregate rollups for API keys; add nightly aggregate job for AI workflow usage;

---

## Event-driven integrations (I7)

**Target:** Push Build Signals workflow events into customer warehouses, CRMs,
and governance systems without requiring constant polling.

**Implemented foundation:** Organization admins can create, update, list, and
disable webhook subscriptions with a validated event type allowlist and optional
secret reference. Matching events can be queued into durable
`webhook_deliveries` rows with pending/delivered/failed metadata, attempt
counts, response excerpts, and retry scheduling fields. Test events can be
enqueued from the admin API to verify customer configuration without touching
production workflows.

**Current event types:**

- `deal.created`
- `deal.updated`
- `signal.created`
- `assessment.revision.created`
- `assessment.review.created`
- `assessment.publication.created`
- `eval.run.completed`
- `eval.run.failed`

**Tradeoff:** The first release persists queue rows but does not perform
outbound HTTP calls synchronously inside app requests. A worker should own
signing, retries, per-customer concurrency, and dead-letter handling.

**Scaling path:** Move delivery to a dedicated worker pool with batched queue
reads, idempotency keys, exponential backoff, dead-letter retention, and
per-customer concurrency limits while preserving the subscription API.
Stripe Billing integration for invoices.

---

## Implementation priority (suggested)

1. **API keys (I3)** — unblocks integrations fastest
2. **SSO (I1)** — enterprise sales blocker
3. **SCIM (I2)** — follows SSO adoption
4. **Billing (I6)** — required for paid contracts

Each feature should ship with RBAC docs update (`docs/rbac.md`) and audit log coverage.
