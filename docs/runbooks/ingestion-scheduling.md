# Scheduled permit & parcel ingestion

DealSignal manages **83 permit feeds** and **38 parcel feeds** in the checked-in
production catalog. Each dispatcher run syncs the catalog, computes due work
from explicit numeric source cadence, and fetches only due active sources.

---

## AWS (primary for App Runner / ECS deploys)

### Option A — ECS Fargate scheduled task (recommended)

Use the same ECR image as App Runner with command **`ingest`**:

```bash
docker run --rm ... dealsignal-api:latest ingest
```

Wire **EventBridge** to an hourly ECS scheduled task (`cron(17 * * * ? *)`). The task
needs the same env as App Runner: `DATABASE_URL`, `SECRET_KEY`,
`ENVIRONMENT=production`, `CORS_ALLOWED_ORIGINS`, the reviewed static
`INGESTION_ALLOWED_HOSTS` list, and optional `REDIS_URL`.

See [deploy-aws.md §9](deploy-aws.md#9-daily-permit-ingestion-aws) for full setup.

### Option B — GitHub Actions (quickest to enable)

1. Set the four production secrets listed below: database URL, app secret, CORS
   origins, and the reviewed static source-host allowlist.
2. Set repository variable **`INGESTION_ORCHESTRATOR=github`** and disable the
   Render or EventBridge scheduler for the same environment.
3. Workflow **`.github/workflows/ingestion-cron.yml`** runs hourly at minute 17 UTC.
4. RDS must be reachable from the runner (public RDS + SG, or self-hosted runner in VPC).

Manual run: Actions → **ingestion-cron** → Run workflow.

**You do not need Render** for ingestion if you use either AWS option above.

---

## Render (alternative hosting)

If you deploy via `render.yaml` instead of AWS, a cron service
`dealsignal-ingestion` runs `./scripts/daily-ingestion.sh`. Staging uses the
catalog-driven due planner. The current production Blueprint retains its
explicit cohort until the production outbound-host allowlist is expanded and a
plan-only parity window is reviewed. See
[first-deploy.md](first-deploy.md). Skip this section if you are on AWS.

---

## What each run does

1. **Catalog sync** — upsert reviewed production sources.
2. **Due plan** — intersect active tenant sources with the checked-in catalog,
   apply deterministic sharding, and calculate cadence or retry eligibility.
3. **Bounded execution** — resume and run each due source independently.
4. **Health check** — report health for the attempted sources.

Catalog sync records catalog activation provenance in source settings. A tenant
operator's paused source stays paused during ordinary sync, while a source that
was disabled by the catalog can be reactivated by a later catalog release.

Each source defaults to its checked-in `max_pages_per_run` policy, or 10 pages
when no override is declared. `INGESTION_MAX_PAGES_PER_SOURCE` can temporarily
override all due sources, up to 100 pages.
Clean partial runs remain immediately due so bounded backfills continue on the
next dispatch. Failed runs use `retry_interval_minutes`; completed runs use
`collection_interval_minutes`. Fresh active leases are skipped, while stale
leases remain eligible for the ingestion service's atomic reclaim.

Inspect the exact plan without fetching:

```bash
python -m app.services.ingestion.cli scheduled-due \
  --organization default-org \
  --as-of 2026-08-11T12:00:00+00:00 \
  --plan-only
```

The same plan is available at `GET /ingestion/schedule-plan`, including state
filtering and deterministic shard parameters.

Run exactly one production orchestrator. Render is the default. To enable the
GitHub scheduled workflow instead, set the repository variable
`INGESTION_ORCHESTRATOR=github` and disable the Render cron. Manual GitHub runs
remain available for explicit operations. GitHub execution requires production
values for `INGESTION_DATABASE_URL`, `INGESTION_CRON_SECRET_KEY`,
`INGESTION_CORS_ALLOWED_ORIGINS`, and `INGESTION_ALLOWED_HOSTS`.

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
| `INGESTION_MAX_PAGES_PER_SOURCE` | catalog | Optional pages-per-source override |
| `INGESTION_SHARD_COUNT` | `1` | Stable number of worker shards, 1-128 |
| `INGESTION_SHARD_INDEX` | `0` | Zero-based shard assigned to this worker |
| `INGESTION_STAGE` | `all` | Optional signal-stage boundary retained from stage-scoped deployments |
| `INGESTION_PLAN_ONLY` | `false` | Print due work without fetching records |

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| CORS / config crash with `ENVIRONMENT=production` | Set `CORS_ALLOWED_ORIGINS` on the ingest task |
| GHA fails with "secret ... is not configured" | Add all four production ingestion secrets listed above |
| ECS task can't reach RDS | SG / VPC — same network rules as App Runner |
| No sources listed | Run `catalog sync` first |
| 409 ActiveRunConflict | Stale run in `ingestion_runs` — investigate before retry |
