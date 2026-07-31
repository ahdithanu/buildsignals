# Scheduled permit & parcel ingestion

DealSignal ingests **78 permit feeds** and **38 parcel feeds** from
`app/services/ingestion/catalog.json`. Runs are on-demand by default; this
doc covers turning on **daily automated ingestion**.

---

## What each run does

1. **Catalog sync** — upsert sources from `catalog.json` into the DB
2. **Run-all** — fetch, normalize, and persist records for every active source
   (resumes from last checkpoint per source)

Default bounds: **10 pages per source** per run (~5k records/page on Socrata).
Adjust with `INGESTION_MAX_PAGES_PER_SOURCE` (max 100).

---

## Render (recommended)

`render.yaml` includes a **cron service** `dealsignal-ingestion`:

| Setting | Value |
|---------|-------|
| Schedule | `0 6 * * *` (06:00 UTC daily) |
| Command | `./scripts/daily-ingestion.sh` |
| Org | `INGESTION_ORGANIZATION=default-org` (override in dashboard) |

**First-time setup after deploy:**

1. Apply blueprint (includes cron job).
2. Set `CORS_ALLOWED_ORIGINS` on the **cron service** (same as API — required
   for `ENVIRONMENT=production` config import).
3. In Render shell on **API** or **cron** service:
   ```bash
   python seed.py   # if fresh DB
   ./scripts/daily-ingestion.sh   # manual first run
   ```
4. Confirm runs in **Ingestion Operations** UI or:
   ```bash
   python -m app.services.ingestion.cli health --organization default-org
   ```

Cron run logs: Render dashboard → `dealsignal-ingestion` → Logs.

---

## GitHub Actions (AWS / no Render cron)

`.github/workflows/ingestion-cron.yml` runs daily at 06:00 UTC when configured:

| Secret | Required | Purpose |
|--------|----------|---------|
| `INGESTION_DATABASE_URL` | Yes | Production Postgres URL |
| `INGESTION_CRON_SECRET_KEY` | No | ≥32 chars if you prefer not to use the CI default |

Manual trigger: Actions → **ingestion-cron** → **Run workflow**.

---

## Manual / one-off

```bash
export DATABASE_URL=postgresql://...
export ENVIRONMENT=development   # or production + CORS set

./scripts/daily-ingestion.sh

# Or step by step:
python -m app.services.ingestion.cli catalog sync --organization default-org
python -m app.services.ingestion.cli run-all --organization default-org --max-pages-per-source 10
```

Single source:

```bash
python -m app.services.ingestion.cli run \
  --organization default-org \
  --source-key austin_tx_issued_construction_permits \
  --max-pages 10
```

---

## Staging

`render-staging.yaml` includes `dealsignal-ingestion-staging` (daily, 5 pages/source).
Use synthetic data only — see `docs/staging.md`.

---

## Monitoring

- **UI:** `/ingestion-operations` — source health, last run age, failures
- **CLI:** `python -m app.services.ingestion.cli health --organization default-org --json`
- **Alerting:** wire Sentry or page on cron job failure in Render / GitHub Actions

---

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `INGESTION_ORGANIZATION` | `default-org` | Target org slug or UUID |
| `INGESTION_MAX_PAGES_PER_SOURCE` | `10` | Pages fetched per source per run |
| `INGESTION_STAGE` | `all` | Filter: `all`, `pre_approval_and_approved`, `approved_only` |

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Cron exits immediately with CORS error | Set `CORS_ALLOWED_ORIGINS` on cron service env |
| No sources listed | Run `catalog sync` first |
| All sources `unknown` health | No completed runs yet — trigger manual run |
| Run timeout on Render | Reduce `INGESTION_MAX_PAGES_PER_SOURCE` or split by stage |
| 409 ActiveRunConflict | Previous run still marked running — check `ingestion_runs` table |
