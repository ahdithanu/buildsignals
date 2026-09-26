# First deploy — standing DealSignal up on Render

Zero-to-running provisioning. This is the **one-time** setup. Routine deploys
after this are just merges to `main` — see [deploy.md](deploy.md).

Everything is described by [`render.yaml`](../../render.yaml) (a Render
Blueprint): managed Postgres, a Redis key-value store for the rate limiter,
the FastAPI backend, and the static frontend. You apply the blueprint once,
supply a handful of secrets, and Render wires the rest.

---

## 0. Prerequisites

- A Render account with billing set up *if* you'll use anything beyond free
  tiers (recommended — see the plan warning in step 4).
- The GitHub repo connected to Render.
- A Resend account + API key if you want password-reset emails to actually
  send (optional; without it they're logged, not sent).
- Sentry projects (backend + frontend) if you want error tracking (optional).

---

## 1. Apply the blueprint

Render dashboard → **New → Blueprint** → pick this repo. Render reads
`render.yaml` and shows you four resources to create:

| Resource | What |
|---|---|
| `dealsignal-db` | Postgres 16 |
| `dealsignal-redis` | Redis/Valkey (rate limiter) |
| `dealsignal-api` | FastAPI backend |
| `dealsignal-frontend` | Static React site |

`DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, and `METRICS_TOKEN` are wired or
generated automatically — you don't touch them.

---

## 2. Supply the secrets

Render prompts for every `sync: false` var. There's a chicken-and-egg with
URLs (the frontend needs the API URL, CORS needs the frontend URL) — Render
assigns URLs as `https://<service-name>.onrender.com` by default, so you can
fill them in up front, or set placeholders and correct them in step 5.

**Backend (`dealsignal-api`):**

| Var | Set to |
|---|---|
| `CORS_ALLOWED_ORIGINS` | the frontend URL, e.g. `https://dealsignal-frontend.onrender.com` (no trailing slash, no `*`) |
| `APP_BASE_URL` | same frontend URL — used in password-reset links |
| `RESEND_API_KEY` | your Resend key (or leave blank to disable email) |
| `SENTRY_DSN` | backend Sentry DSN (or blank) |
| `INGESTION_ALLOWED_HOSTS` | exact reviewed worker host list from `catalog host-audit --print-required-hosts` |
| `INGESTION_HOST_POLICY_EXECUTOR` | leave blank until the API list is confirmed identical to the worker; then set the worker service name |
| `INGESTION_HOST_POLICY_DIGEST` | `policy_digest` from the executor's exact static host policy |

**Frontend (`dealsignal-frontend`):**

| Var | Set to |
|---|---|
| `VITE_API_BASE_URL` | the API URL, e.g. `https://dealsignal-api.onrender.com` |
| `VITE_SENTRY_DSN` | frontend Sentry DSN (or blank) |

> ⚠ `VITE_*` vars are baked in at **build time**. If you set or change one
> later, you must trigger a **rebuild** of the frontend, not just a restart.

---

## 3. Deploy

Render builds and deploys all four resources. On the API service:

1. `pip install -r requirements.txt`
2. **pre-deploy:** `alembic upgrade head` creates the schema (incl. row-level
   security). If this fails, the deploy stops and no broken schema ships.
3. `uvicorn` starts; Render waits for `/health` to go green.

The frontend builds (`npm install && npm run build`) and publishes `dist/`.

---

## 4. Fix the plans before a pilot

The blueprint ships `plan: free` everywhere so you can try it at no cost. Free
tiers will bite in production:

- **Postgres (free) expires after 30 days** and can't be renewed — your data
  goes with it. Upgrade to a paid instance before real use.
- **The API (free) sleeps after ~15 min idle** — the first request after that
  cold-starts (~30s) and `/health` may 503 briefly. Upgrade for a pilot.
- Free Postgres also has no point-in-time recovery — see [backups.md](../backups.md).

Upgrade in the dashboard (or bump `plan:` in `render.yaml` and re-apply).

---

## 5. Smoke test

Once the API is green:

```bash
BASE=https://dealsignal-api.onrender.com   # your API URL

curl -sf $BASE/health | jq .               # {"status":"ok"}
curl -sf $BASE/health/deep | jq .           # {"status":"ok","db":"ok"} — proves DB wiring
curl -sf $BASE/openapi.json | jq '.info.version'

# Create the first account (this becomes an org admin):
curl -sf -X POST $BASE/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@yourco.com","password":"<a-real-password>","full_name":"You","organization_name":"Your Co"}' \
  | jq '.role'                              # "admin"
```

Then open the frontend URL, log in with that account, and confirm the
dashboard loads. If the browser console shows requests going to
`localhost:8000`, `VITE_API_BASE_URL` wasn't set at build time — fix it and
rebuild the frontend (step 2 warning).

Verify metrics are protected:

```bash
curl -s -o /dev/null -w '%{http_code}\n' $BASE/metrics          # 401 (token required)
```

---

## 6. Post-deploy checklist

- [ ] Plans upgraded off free for Postgres + API (step 4).
- [ ] `CORS_ALLOWED_ORIGINS` / `APP_BASE_URL` / `VITE_API_BASE_URL` point at
      the real URLs (custom domain if you set one up).
- [ ] Password-reset email actually sends (register → forgot password → check
      inbox) if `RESEND_API_KEY` is set.
- [ ] Sentry receiving events (trigger a test error) if DSNs are set.
- [ ] A metrics scraper is pointed at `/metrics` with the `METRICS_TOKEN`
      bearer, or the endpoint is restricted at the network layer.
- [ ] Fill in the on-call / status-page TODOs in
      [incident-response.md](incident-response.md).
- [ ] **Confirm the app connects to Postgres as a NON-superuser role.**
      Tenant isolation (row-level security, migration 003) is *silently
      bypassed* by Postgres superusers — even with FORCE RLS. Render's managed
      Postgres gives a non-superuser owner by default, which is correct; but if
      you ever swap in a self-managed DB and connect as `postgres`/superuser,
      RLS provides ZERO cross-tenant protection with no error. Verify with:
      `SELECT rolsuper FROM pg_roles WHERE rolname = current_user;` → must be
      `f`. (App-layer org scoping still applies either way, but RLS is the
      defense-in-depth backstop and you want it real.)
- [ ] **Enable daily permit ingestion:** set `CORS_ALLOWED_ORIGINS` on the
      `dealsignal-permit-ingestion-cohort-1` cron service (same value as API),
      run the scoped host audit, then execute the cohort once manually. See
      [ingestion-scheduling.md](ingestion-scheduling.md).
- [ ] **Enable weekly Savannah ingestion:** set `CORS_ALLOWED_ORIGINS` and
      `INGESTION_ORGANIZATION` on `dealsignal-savannah-permit-ingestion`, run it
      once manually, and verify the bounded snapshot and graph projection
      before relying on the Monday schedule.

From here on, deploying is just merging to `main`. Read [deploy.md](deploy.md)
before the first routine deploy.
