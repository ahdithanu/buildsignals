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

**Existing foundation:** `METRICS_TOKEN` pattern for `/metrics`.

**Stub path:**
1. `api_keys` table (org_id, hashed_key, scopes, expires_at).
2. Middleware: `Authorization: Bearer ds_live_...` with scope checks.
3. Admin UI: create/revoke keys, scope selection (read deals, write ingestion).

---

## Billing / usage metering (I6)

**Target:** Usage-based billing for AI enrichment, memo generation, seat count.

**Stub path:** Emit usage events to `usage_events` table; nightly aggregate job;
Stripe Billing integration for invoices.

---

## Implementation priority (suggested)

1. **API keys (I3)** — unblocks integrations fastest
2. **SSO (I1)** — enterprise sales blocker
3. **SCIM (I2)** — follows SSO adoption
4. **Billing (I6)** — required for paid contracts

Each feature should ship with RBAC docs update (`docs/rbac.md`) and audit log coverage.
