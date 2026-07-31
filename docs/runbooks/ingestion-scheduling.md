# Scheduled permit & parcel ingestion

DealSignal ingests **78 permit feeds** and **38 parcel feeds** from
`app/services/ingestion/catalog.json`. Each run syncs the catalog, then fetches
and normalizes records for every active source.

---

## AWS (primary for App Runner / ECS deploys)

### Option A — ECS Fargate scheduled task (recommended)

Use the same ECR image as App Runner with command **`ingest`**:

```bash
docker run --rm ... dealsignal-api:latest ingest
```

Wire **EventBridge** → ECS scheduled task daily (`cron(0 6 * * ? *)`). The task
needs the same env as App Runner: `DATABASE_URL`, `SECRET_KEY`,
`ENVIRONMENT=production`, `CORS_ALLOWED_ORIGINS`, optional `REDIS_URL`.

See [deploy-aws.md §9](deploy-aws.md#9-daily-permit-ingestion-aws) for full setup.

### Option B — GitHub Actions (quickest to enable)

1. Set repo secret **`INGESTION_DATABASE_URL`** (RDS connection string).
2. Workflow **`.github/workflows/ingestion-cron.yml`** runs at **06:00 UTC** daily.
3. RDS must be reachable from the runner (public RDS + SG, or self-hosted runner in VPC).

Manual run: Actions → **ingestion-cron** → Run workflow.

**You do not need Render** for ingestion if you use either AWS option above.

---

## Render (alternative hosting)

If you deploy via `render.yaml` instead of AWS, a cron service
`dealsignal-ingestion` runs `./scripts/daily-ingestion.sh` daily. See
[first-deploy.md](first-deploy.md). Skip this section if you are on AWS.

---

## What each run does

1. **Catalog sync** — upsert sources from `catalog.json`
2. **Run-all** — fetch/normalize/persist (resumes checkpoints per source)

Defaults: **10 pages per source** (`INGESTION_MAX_PAGES_PER_SOURCE`, max 100).

---

## Manual / one-off

```bash
export DATABASE_URL=postgresql://...
export ENVIRONMENT=development   # or production + CORS set

./scripts/daily-ingestion.sh
```

Or via Docker on AWS:

```bash
docker run --rm --env-file .env.production $ECR_IMAGE ingest
```

---

## Monitoring

- **UI:** `/ingestion-operations`
- **CLI:** `python -m app.services.ingestion.cli health --organization default-org --json`
- **Alerting:** ECS task failure → SNS; GHA failure → GitHub notifications

---

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `INGESTION_ORGANIZATION` | `default-org` | Target org slug or UUID |
| `INGESTION_MAX_PAGES_PER_SOURCE` | `10` | Pages per source per run |
| `INGESTION_STAGE` | `all` | `all`, `pre_approval_and_approved`, `approved_only` |

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| CORS / config crash with `ENVIRONMENT=production` | Set `CORS_ALLOWED_ORIGINS` on the ingest task |
| GHA skips with "secret not set" | Add `INGESTION_DATABASE_URL` in GitHub repo secrets |
| ECS task can't reach RDS | SG / VPC — same network rules as App Runner |
| No sources listed | Run `catalog sync` first |
| 409 ActiveRunConflict | Stale run in `ingestion_runs` — investigate before retry |
