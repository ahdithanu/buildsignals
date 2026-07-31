# Enterprise readiness checklist

Living tracker for DealSignal production readiness. Update status as items
ship. IDs match the tiers used in planning conversations.

**Legend:** ✅ done · 🟡 partial · ⬜ not started · 🔒 requires org decision

---

## A — Release validation

| ID | Item | Status | Notes |
|----|------|--------|-------|
| A1 | Frontend lint / typecheck / unit tests / build | ✅ | `npm run lint`, `typecheck`, `test`, `build` all pass |
| A2 | Manual browser QA (`VALIDATION.md` §2) | 🟡 | Automated gates green; manual audit checklist remains |
| A3 | Playwright E2E (auth + deal flows) | ✅ | 4/4 pass locally; workflow enabled on PR |
| A4 | Regenerate `package-lock.json` | ✅ | Lock file committed; CI uses `npm ci` |
| A5 | Content-Security-Policy on static frontend | 🟡 | Enabled in `render.yaml`; verify zero console violations after deploy |
| A6 | Render plans off free tier | 🟡 | Blueprint defaults to `starter`; confirm in dashboard before pilot |
| A7 | Production env vars set (`CORS`, `APP_BASE_URL`, `VITE_*`) | 🔒 | Dashboard secrets — see `docs/runbooks/first-deploy.md` |
| A8 | Post-deploy smoke test | ✅ | `scripts/smoke-test.sh` |

---

## B — CI / quality gates

| ID | Item | Status | Notes |
|----|------|--------|-------|
| B1 | Backend CI (pytest, ruff, alembic, pip-audit) | ✅ | `.github/workflows/ci.yml` |
| B2 | Gitleaks secret scan | ✅ | `.github/workflows/security-scan.yml` |
| B3 | Frontend CI on `main` push | ✅ | `.github/workflows/frontend.yml` |
| B4 | E2E CI on pull request | ✅ | `.github/workflows/e2e.yml` |
| B5 | `npm ci` in frontend workflows | ✅ | Lock file in sync |
| B6 | Pre-commit hooks adopted locally | ✅ | CI workflow + `pre-commit install` locally |
| B7 | OpenAPI drift check | ✅ | `.github/workflows/openapi.yml` |
| B8 | Dependabot backlog triaged | 🟡 | Weekly schedule configured; triage open PRs weekly |

---

## C — Security

| ID | Item | Status | Notes |
|----|------|--------|-------|
| C1 | JWT + httpOnly refresh cookie | ✅ | Cookie path `/v1/auth` (deploy note: users re-login once) |
| C2 | RLS tenant isolation | ✅ | Migration 003; non-superuser CI tests |
| C3 | Rate limiting (Redis-backed) | ✅ | `GlobalRateLimitMiddleware` |
| C4 | Security headers (API + static) | ✅ | `SecurityHeadersMiddleware` + `render.yaml` |
| C5 | Export policy / boundary gating | ✅ | Merged in PR #23 |
| C6 | Secrets runbook | ✅ | `docs/secrets.md` |
| C7 | RBAC documentation | ✅ | `docs/rbac.md` |
| C8 | SSO (SAML/OIDC) | ⬜ | Product feature — see tier I |
| C9 | Secrets vault (not env-only) | 🔒 | AWS Secrets Manager / Vault — org infra choice |
| C10 | SOC 2 Type II | 🔒 | Compliance program |
| C11 | Annual penetration test | 🔒 | Third-party engagement |

---

## D — Observability & SLOs

| ID | Item | Status | Notes |
|----|------|--------|-------|
| D1 | Sentry (backend + frontend) | ✅ | Optional via DSN env vars |
| D2 | Prometheus `/metrics` | ✅ | Bearer token protected |
| D3 | Request ID tracing | ✅ | `X-Request-ID` middleware |
| D4 | SLO targets documented | ✅ | `docs/slo.md` |
| D5 | Grafana/Datadog dashboards | 🟡 | Example alert rules in `docs/prometheus/alerts.example.yml` |
| D6 | Alerting + error-budget burn | 🟡 | Example rules + monitoring guide |
| D7 | External uptime monitor on `/health/deep` | ✅ | `infra/uptime.env` + `scripts/setup-infra.sh` + uptime workflow |
| D8 | Customer-facing SLA | 🔒 | Legal + business decision |

---

## E — Incident response

| ID | Item | Status | Notes |
|----|------|--------|-------|
| E1 | Incident runbook | ✅ | `docs/runbooks/incident-response.md` |
| E2 | On-call rotation defined | 🟡 | Template in runbook §On-call — fill org names |
| E3 | Paging tool configured | 🟡 | PagerDuty/Opsgenie setup doc in runbook |
| E4 | Status page URL | 🟡 | Placeholder in runbook — configure provider |
| E5 | `#dealsignal-incidents` comms channel | 🔒 | Create Slack channel |
| E6 | Postmortem template | ✅ | In incident runbook §6 |
| E7 | Sev-1/2 comms cadence | ✅ | Documented (30 min updates) |
| E8 | Security incident playbook | ✅ | Runbook §5 + `docs/secrets.md` |

---

## F — Backups & DR

| ID | Item | Status | Notes |
|----|------|--------|-------|
| F1 | Backup procedures documented | ✅ | `docs/backups.md` |
| F2 | Render Postgres automated backups | 🟡 | Included on paid plans; verify retention |
| F3 | Restore drill (quarterly) | 🟡 | Procedure in `docs/backups.md`; log in `docs/ops-log.md` |
| F4 | Point-in-time recovery tested | ⬜ | Requires paid Postgres + drill |
| F5 | Cross-region DR | ⬜ | Not required for pilot; document RTO/RPO targets first |

---

## G — Environments

| ID | Item | Status | Notes |
|----|------|--------|-------|
| G1 | Production (Render blueprint) | ✅ | `render.yaml` |
| G2 | Local dev (SQLite + Vite proxy) | ✅ | README |
| G3 | CI throwaway DBs | ✅ | SQLite + PostGIS Postgres service |
| G4 | AWS deploy path documented | ✅ | `docs/runbooks/deploy-aws.md` |
| G5 | Staging environment | ✅ | `render-staging.yaml` + `docs/staging.md` |
| G6 | Staging data policy | ✅ | Documented in `docs/staging.md` |

---

## H — Product quality

| ID | Item | Status | Notes |
|----|------|--------|-------|
| H1 | Accessibility audit fixes | 🟡 | CR-1 keyboard access shipped; full axe pass in A2 |
| H2 | Parcel map + boundary export | ✅ | PR #23 boundary policy gating |
| H3 | Deal brand-match resolution | ✅ | Merged in PR #23 |
| H4 | Parcel map unit/integration tests | ✅ | `parcel-map.test.tsx`, `nearby-parcels-panel.test.tsx`, etc. |
| H5 | API versioning (`/v1`) | ✅ | Middleware + versioned routes |
| H6 | Data retention policy | ✅ | `docs/data-retention.md` |
| H8 | Scheduled permit/parcel ingestion | ✅ | Render cron + `scripts/daily-ingestion.sh` + GHA workflow |

---

## I — Enterprise product features

| ID | Item | Status | Notes |
|----|------|--------|-------|
| I1 | SSO (SAML/OIDC) | ⬜ | Stub in `docs/enterprise-product-roadmap.md` |
| I2 | SCIM provisioning | ⬜ | Stub in roadmap |
| I3 | Organization API keys | ⬜ | Stub in roadmap |
| I4 | Custom roles / fine-grained RBAC | 🟡 | Base RBAC documented; custom roles TBD |
| I5 | Audit log export | 🟡 | Data portability routes exist |
| I6 | Billing / usage metering | ⬜ | |
| I7 | Dedicated tenant isolation | ⬜ | |
| I8 | Custom domain + TLS | 🔒 | Render dashboard |
| I9 | DPA / BAA templates | 🔒 | Legal |
| I10 | Customer admin console | ⬜ | |

---

## J — Documentation & process

| ID | Item | Status | Notes |
|----|------|--------|-------|
| J1 | Deploy runbook | ✅ | `docs/runbooks/deploy.md` |
| J2 | First-deploy runbook | ✅ | `docs/runbooks/first-deploy.md` |
| J3 | Operations reference | ✅ | `docs/operations.md` |
| J4 | Architecture decision records | ✅ | `docs/adr/` (001 versioning, 002 refresh cookie) |
| J5 | Release notes process | ✅ | `CHANGELOG.md` |
| J6 | Public accessibility statement | ✅ | `docs/accessibility.md` (fill contact email) |

---

## Quick verification commands

```bash
# Frontend gates
npm ci && npm run lint && npm run typecheck && npm run test && npm run build

# Backend
python3 -m pytest -q

# E2E (boots servers)
npm run e2e:install && npm run e2e

# Post-deploy smoke
BASE=https://your-api.onrender.com ./scripts/smoke-test.sh
```

---

## Deploy note: refresh cookie path change

This release sets `REFRESH_COOKIE_PATH=/v1/auth` (was `/auth`). After deploy,
existing users' refresh cookies at the old path will not be sent — they must
log in once. Plan comms if you have active pilot users.
