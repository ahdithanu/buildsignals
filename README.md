# BuildSignal

Real-estate acquisition intelligence — a multi-tenant platform for sourcing,
underwriting, and tracking commercial real-estate deals. FastAPI backend,
React/Vite frontend, Postgres.

> **Status:** pilot. Security, auth, and CI are production-grade; track
> readiness in [docs/enterprise_readiness.md](docs/enterprise_readiness.md).
> Automated frontend gates (lint, typecheck, test, build, E2E) are green;
> manual QA in [VALIDATION.md](VALIDATION.md) §2 remains before user-facing release.

---

## Stack

| Layer | Tech |
|---|---|
| Backend | FastAPI (Python 3.11), SQLAlchemy 2, Alembic |
| Frontend | React 18 + Vite + TypeScript, shadcn/ui, TanStack Query |
| Database | Postgres in production; SQLite for local dev |
| Auth | JWT access + rotating refresh cookie, TOTP 2FA |
| Hosting | AWS App Runner + RDS + CloudFront, or Render |
| Errors | Sentry (backend + frontend) |

---

## Quickstart

Prerequisites: **Python 3.11+**, **Node 18+**, and (optionally) a local Postgres.
Without `DATABASE_URL` the backend uses a SQLite file, so you can run entirely
locally with zero infra.

```bash
git clone <repo-url> && cd DealSignal
cp .env.example .env          # then edit — see notes below
```

### Backend (API on :8000)

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Generate a dev signing secret and drop it into .env as SECRET_KEY:
python -c 'import secrets; print(secrets.token_urlsafe(32))'

alembic upgrade head          # create the schema (SQLite by default)
python seed.py                # optional: sample data
uvicorn app.main:app --reload --port 8000
```

API docs: <http://localhost:8000/docs> · health: <http://localhost:8000/health>

### Frontend (app on :8080)

```bash
npm install
npm run dev
```

The frontend talks to `http://localhost:8000` by default
(`VITE_API_BASE_URL`). All API routes are versioned under `/v1`.

### Production frontend (Vercel)

This repository is the canonical source for both the Build Signals frontend and
backend. Vercel builds the React/Vite application from the repository root
using `vercel.json` and publishes `dist/`. Set `VITE_API_BASE_URL` to the HTTPS
origin of the production FastAPI service before promoting a preview. The
separate `deal-signal-terminal` repository is superseded and receives no new
product work. See [`docs/adr/003-unified-product-repository.md`](docs/adr/003-unified-product-repository.md).

---

## Environment

`.env.example` is the source of truth and documents every variable. The ones
you actually need locally:

| Variable | Local default | Notes |
|---|---|---|
| `SECRET_KEY` | *(required)* | JWT signing key. Generate one; must be ≥32 chars in prod. |
| `DATABASE_URL` | unset → SQLite | `postgresql://…` in prod. |
| `ENVIRONMENT` | `development` | `production` turns on fail-fast config guards. |
| `SENTRY_DSN` | unset → off | Leave unset locally; Sentry is a no-op without it. |

In **production** the app *refuses to boot* on insecure config — a dev
`SECRET_KEY`, a SQLite `DATABASE_URL`, empty/`*` CORS, or `ALLOW_ANONYMOUS=true`.
That turns a misconfiguration into a loud crash instead of a silent breach.

---

## Testing

```bash
# Backend — 270 tests
pytest -q

# Frontend unit (vitest)
npm run test

# Type-check the frontend (vite's build does NOT type-check)
npm run typecheck

# Load test (needs a running API; see loadtest/README.md)
pip install locust && locust -f loadtest/locustfile.py --host http://localhost:8000

# Browser E2E (needs Node 18+; see e2e/README.md)
npm run e2e:install && npm run e2e
```

CI runs backend tests (incl. RLS + migration reversibility on real Postgres),
lint (ruff), an Alembic migration-drift check, a `pip-audit` CVE scan, and a
gitleaks secret scan on every push. See `.github/workflows/`.

Catch the lint/secret checks locally before you push:

```bash
pip install pre-commit && pre-commit install   # one time
pre-commit run --all-files                      # on demand
```

---

## Project layout

```
app/
  main.py            FastAPI app: middleware chain + router registration
  config.py          Env parsing + production fail-fast guards
  middleware/        auth context, rate limit, versioning, request-id, headers
  routes/            API endpoints (mounted under /v1)
  models/            SQLAlchemy models
  schemas/           Pydantic request/response models
  services/          business logic (security, audit, rate limiter, …)
  utils/             auth deps, org scoping, feature flags
alembic/versions/    database migrations (reversible; enforced in CI)
src/                 React frontend
scripts/             admin CLI, OpenAPI export
loadtest/  e2e/      load + browser test harnesses
docs/                runbooks and operational docs — see below
```

---

## Documentation

Workspace admins can use **AI Evaluations** at `/admin/evals` to create evidence-based
test datasets, run checks, compare versions, and enforce regression gates. See
[AI evaluation platform](docs/ai-evaluation-platform.md) for supported live workflows,
captured-output evaluation, metric limitations, and deployment instructions.

| Doc | What |
|---|---|
| [docs/runbooks/first-deploy.md](docs/runbooks/first-deploy.md) | One-time Render provisioning from scratch |
| [docs/runbooks/deploy-aws.md](docs/runbooks/deploy-aws.md) | AWS deploy (App Runner + RDS + CloudFront) |
| [docs/runbooks/deploy.md](docs/runbooks/deploy.md) | Routine deploy, smoke test, rollback |
| [docs/runbooks/incident-response.md](docs/runbooks/incident-response.md) | Sev levels, on-call, comms, postmortem |
| [docs/backups.md](docs/backups.md) | Backup & restore, RPO/RTO, DR drills |
| [docs/data-retention.md](docs/data-retention.md) | What we store, retention, right-to-erasure |
| [docs/rbac.md](docs/rbac.md) | Role matrix + per-endpoint access |
| [docs/secrets.md](docs/secrets.md) | Secret inventory, rotation, leaked-secret playbook |
| [docs/operations.md](docs/operations.md) | Env vars, CI overview |
| [docs/slo.md](docs/slo.md) | Service level objectives + error budget |
| [docs/enterprise_readiness.md](docs/enterprise_readiness.md) | Production readiness checklist (living tracker) |
| [docs/monitoring.md](docs/monitoring.md) | Dashboards, alerts, uptime setup |
| [docs/prompt-registry.md](docs/prompt-registry.md) | Tenant-scoped prompt versioning, preview, and activation boundaries |
| [docs/staging.md](docs/staging.md) | Staging environment policy |
| [docs/runbooks/staging-deploy.md](docs/runbooks/staging-deploy.md) | One-time Render staging blueprint setup |
| [infra/README.md](infra/README.md) | Uptime URL config + staging env hints |
| [docs/ops-log.md](docs/ops-log.md) | Ops drill and incident log |
| [docs/templates/postmortem.md](docs/templates/postmortem.md) | Postmortem template |
| [docs/accessibility.md](docs/accessibility.md) | Accessibility statement |
| [VALIDATION.md](VALIDATION.md) | Frontend release gate (automated + manual QA) |
| [CHANGELOG.md](CHANGELOG.md) | Release notes |
| [SECURITY.md](SECURITY.md) | Vulnerability disclosure |

---

## Deployment

**AWS (App Runner + RDS + CloudFront):** follow
[`docs/runbooks/deploy-aws.md`](docs/runbooks/deploy-aws.md) — the `Dockerfile`
image supports `serve`, `migrate`, and **`ingest`** (daily permit cron).

**Render:** [`render.yaml`](render.yaml) blueprint —
[`docs/runbooks/first-deploy.md`](docs/runbooks/first-deploy.md).

After deploy, enable daily ingestion — on AWS see
[deploy-aws.md §9](docs/runbooks/deploy-aws.md#9-daily-permit-ingestion-aws)
(ECS scheduled task or GitHub Actions). Read
[docs/runbooks/deploy.md](docs/runbooks/deploy.md) for routine ship, smoke test,
and rollback.

## License

See [LICENSE](LICENSE).
