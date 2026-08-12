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

If you deploy via `render.yaml` instead of AWS, the cron service
`dealsignal-permit-ingestion-cohort-1` runs the current explicit cohort. Staging
uses the catalog-driven due planner. The current production Blueprint retains
its explicit cohort until the production outbound-host allowlist is expanded
and a plan-only parity window is reviewed. See
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

Audit the catalog against the static outbound policy before enabling execution:

```bash
python -m app.services.ingestion.cli catalog host-audit --json
```

Use `--print-required-hosts` to emit the exact comma-separated value for review;
proposal mode succeeds when every source URL is safe even before the allowlist
is configured.
The audit checks the primary connector and any canary endpoint overrides. It
fails closed for missing hosts, non-HTTPS URLs, credentials, localhost, and IP
literals. Host matching is exact; authorizing a parent domain does not authorize
its subdomains. `GET /ingestion/host-policy` exposes the same read-only result
on the Ingestion Operations page without source query strings. Set the API
service's `INGESTION_ALLOWED_HOSTS` to the same reviewed value as the worker and
set `INGESTION_HOST_POLICY_EXECUTOR` to that worker's service name only after
verifying parity. Also set `INGESTION_HOST_POLICY_DIGEST` to the `policy_digest`
from the exact host-policy audit (`--print-policy-digest`). The UI verifies that
digest before it reports Ready; a name alone is not an attestation. Without
both values, it remains blocked.
The report never expands the worker allowlist.

Production activation order:

1. Run `catalog host-audit` and review every proposed hostname.
2. Update the API and exactly one worker with the same static allowlist.
3. Run `scheduled-due --plan-only` for a parity window and inspect due volume.
4. Enable execution only after the plan and worker capacity are approved.

For an hourly GitHub parity window, set repository variable
`INGESTION_PLAN_ONLY=true`. Clear it only after review. The workflow scopes its
host audit to the same stage and deterministic shard as the planned run.

Both `scheduled` and `scheduled-due` repeat a scoped host-policy audit
immediately before execution in staging and production. A missing or unsafe
destination exits nonzero before catalog sync or network access.

Production HTTPS connections resolve each exact allowlisted hostname, reject
non-public addresses, and connect to the validated address while preserving the
official hostname for TLS verification. Private-network egress controls remain
recommended as a second independent boundary.

Run exactly one production orchestrator. Render is the default. To enable the
GitHub scheduled workflow instead, set the repository variable
`INGESTION_ORCHESTRATOR=github` and disable the Render cron. Manual GitHub runs
remain available for explicit operations. GitHub execution requires production
values for `INGESTION_DATABASE_URL`, `INGESTION_CRON_SECRET_KEY`,
`INGESTION_CORS_ALLOWED_ORIGINS`, `INGESTION_ALLOWED_HOSTS`, and
`INGESTION_HOST_POLICY_DIGEST`. The worker validates the digest against its
exact catalog scope before collection.

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
