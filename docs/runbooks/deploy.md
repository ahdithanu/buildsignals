# Deploy runbook — DealSignal

Playbook for shipping DealSignal to production. Assumes the Render
setup declared in `render.yaml`:

- `dealsignal-api` — Python web service, Uvicorn/FastAPI
- `dealsignal-frontend` — Static site built from Vite, SPA rewrite
- Managed Postgres (dashboard-configured, not in `render.yaml`)

Migrations run automatically via `preDeployCommand: alembic upgrade head`
before Render swaps traffic. A broken migration fails the deploy and
the previous version stays live — that's why the preflight below focuses
on env vars and migration safety, not on running `alembic` by hand.

---

## Pre-deploy: 5-minute preflight

Run through this before merging to `main` (or clicking Manual Deploy
in the Render dashboard).

- [ ] CI green on the merge target (lint, alembic drift check, pytest,
      frontend build).
- [ ] Exactly one alembic head: `alembic heads` returns one line.
- [ ] `requirements.txt` updated if any deps changed.
- [ ] **New env vars set in the Render dashboard.** Env keys added this
      release must exist BEFORE deploy — a missing key raises at import
      time and the worker crashloops. Set them once, then merge.
      Non-negotiable in prod:
      - `SECRET_KEY` — any value other than `dev-secret-change-in-production`
      - `DATABASE_URL` — must be `postgres://...`, not SQLite
      - `CORS_ALLOWED_ORIGINS` — must be set, must not contain `*`
      - `REFRESH_COOKIE_SAMESITE` — `lax` or `strict`, never `none` without
        `REFRESH_COOKIE_SECURE=true`
      - `ALLOW_ANONYMOUS` — must be `false` (the app refuses to boot with
        `true` in production; see `app/config.py`)
      - `ENVIRONMENT=production` — set in `render.yaml`, but confirm it
        wasn't overridden in the dashboard
- [ ] **Migration safety** — if this release includes a new migration,
      read it and check:
      - No `ALTER TABLE ... SET NOT NULL` on a large table without a
        default (locks the table).
      - No `DROP COLUMN` unless a previous release stopped writing to it
        (otherwise old app instances during the deploy window will crash).
      - No index build on a large table without `CREATE INDEX
        CONCURRENTLY` (blocks writes).
      - Reversibility is enforced in CI (`tests/test_migration_reversibility.py`
        round-trips upgrade→downgrade→upgrade on SQLite), so a missing or
        broken `downgrade()` fails the build. Note this does NOT prove the
        downgrade is *data-safe* — a `DROP COLUMN` downgrade still destroys
        data. CI only proves it runs.
- [ ] Sentry release tag will pick up via `RENDER_GIT_COMMIT` — no manual
      action needed (see `app/main.py`).

---

## Deploy

1. **Merge PR to `main`.** Render auto-deploys the API service on push;
   the static site rebuilds in parallel.
2. **Watch the API build log** in the Render dashboard. Failure modes
   we've seen most:
   - Missing env var → `KeyError` at import time.
   - Migration failure → `preDeployCommand` fails; traffic never cuts
     over. The Render UI marks the deploy failed and keeps the previous
     version live. Fix the migration (or the DB state it hits) and
     redeploy — see "Rollback" below for when to hit rollback vs fix
     forward.
3. **Smoke test** (next section).
4. **Sentry release** is stamped automatically via `RENDER_GIT_COMMIT`.

### Manual migration path (rarely needed)

Migrations run automatically on every deploy via `preDeployCommand`. You
should only run alembic by hand if:

- A migration failed mid-run and the DB is in a partially-applied state
  (rare — Alembic transactions cover most cases).
- You need to run a data-backfill migration outside the deploy window.

Open a Render Shell into the API service and run `alembic current` to
check state, then `alembic upgrade head` or a targeted `alembic upgrade
<rev>` as needed.

---

## Smoke test — ~2 minutes

After the API service goes green:

```bash
BASE=https://api.dealsignal.com     # adjust per environment

# Basic aliveness + version
curl -sf $BASE/health | jq .        # shallow liveness — no DB check
curl -sf $BASE/health/deep | jq .   # exercises the DB; 503 if Postgres is unreachable
curl -sf $BASE/openapi.json | jq '.info.version'

# Login round-trip — proves DB, JWT, and cookie wiring are healthy
curl -sf -X POST $BASE/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"smoke@dealsignal.com","password":"<from vault>"}' \
  -c /tmp/c.txt \
  | jq '.access_token | length'
grep ds_refresh /tmp/c.txt   # refresh cookie present
```

Frontend smoke: open `https://app.dealsignal.com`, log in, load `/deals`.
First page should render with data within 3 seconds.

If any of the above fail, decide rollback vs forward-fix from the table
below before investigating further — a broken production is worse than
a delayed one.

---

## Rollback

Render keeps the previous image. Two failure modes, two responses:

| Symptom                                            | Response      |
|----------------------------------------------------|---------------|
| Boot crashloop, no migration ran                   | Roll back     |
| 5xx rate > 2% sustained for 5+ min                 | Roll back     |
| Single-endpoint regression, rest of app OK         | Forward-fix   |
| **Migration ran and broke something**              | **Stop.** Do NOT roll back the app without inspecting the migration — the code rolls back, the schema doesn't. Page the DBA / whoever wrote the migration. |

**To roll back:** Render dashboard → service → *Manual Deploy* → pick
the previous successful deploy → confirm. Takes ~90s.

**Forward-fix:** revert the offending PR, let CI pass, merge. Same path
as a normal deploy — the auto-deploy on push does the work.

---

## Recurring gotchas

- **`CORS_ALLOWED_ORIGINS` typo or empty.** App refuses to boot with a
  clear error, but the symptom looks like a generic crashloop in the
  Render UI. If a fresh deploy immediately fails on boot after touching
  CORS, that's it.
- **Static-site env vars are baked at build time.** Changing
  `VITE_API_BASE_URL` requires a static-site rebuild, not a service
  restart. Trigger a manual deploy of `dealsignal-frontend`.
- **Free plan cold starts.** The Render Free plan sleeps services after
  inactivity. `/health` will 503 for ~30s on the first request after a
  quiet period. Staging is on Free; production should be on a paid plan
  before pilot. Verify plan tier for the target env before diagnosing
  perceived slowness.
- **Refresh-cookie SameSite mismatch.** `REFRESH_COOKIE_SAMESITE=strict`
  drops the cookie on cross-site flows (magic-link emails opened from a
  different domain). Keep `lax` unless you have a reason.
- **OpenAPI drift.** `openapi.json` is committed by a CI workflow on
  every push to `main` (see `.github/workflows/openapi.yml`). If a
  frontend PR is codegened against a stale schema, pull main first.

---

## Who to page

| What broke                              | Who              |
|-----------------------------------------|------------------|
| API 5xx spike, Sentry errors            | Backend on-call  |
| Frontend white screen / build fail      | Frontend on-call |
| Postgres CPU / disk alarms              | Backend on-call → escalate to whoever owns the migration |
| Auth broken for every user              | Backend on-call, treat as SEV-1 |
| Migration failed mid-deploy             | Author of the migration first, then backend on-call |

Escalation channel: `#dealsignal-incidents` (Slack). Status page: TBD.
