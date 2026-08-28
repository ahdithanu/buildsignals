# Scheduled permit & parcel ingestion

DealSignal manages **87 permit feeds** and **38 parcel feeds** in the checked-in
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
`INGESTION_ALLOWED_HOSTS` list, its `INGESTION_HOST_POLICY_DIGEST`, the reviewed
`INGESTION_ROLLOUT_MANIFEST_DIGEST`, an explicit `INGESTION_ROLLOUT_WAVE`, and
optional `REDIS_URL`.

See [deploy-aws.md §9](deploy-aws.md#9-daily-permit-ingestion-aws) for full setup.

### Option B — GitHub Actions (quickest to enable)

1. Set the six production secrets listed below: database URL, app secret, CORS
   origins, the reviewed static source-host allowlist, its policy digest, and
   the reviewed rollout manifest digest.
2. Set repository variable **`INGESTION_ORCHESTRATOR=github`** and disable the
   Render or EventBridge scheduler for the same environment.
3. Workflow **`.github/workflows/ingestion-cron.yml`** runs hourly at minute 17 UTC.
4. RDS must be reachable from the runner (public RDS + SG, or self-hosted runner in VPC).

Manual run: Actions → **ingestion-cron** → Run workflow.

**You do not need Render** for ingestion if you use either AWS option above.

---

## Render (alternative hosting)

If you deploy via `render.yaml` instead of AWS, the cron service
`dealsignal-permit-ingestion-cohort-1` is the manifest-pinned Wave 1 worker. It
runs every six hours and rotates through four deterministic shards, covering
the 27 reviewed Texas, Washington, and New York sources once per UTC day with a
single paid cron service. The checked-in Blueprint sets
`INGESTION_PLAN_ONLY=true`; review a complete four-run parity window before
changing it to `false` in Render. See [first-deploy.md](first-deploy.md). Skip
this section if you are on AWS.

Savannah runs separately as `dealsignal-savannah-permit-ingestion` every Monday
at 10:30 UTC. It uses `scheduled-due`, is pinned to rollout wave 4 and the exact
reviewed manifest digest, and authorizes only `pub.sagis.org`. Its first manual
execution should remain bounded and be reviewed before relying on the recurring
schedule.

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

## Nationwide rollout manifest

The checked-in
`app/services/ingestion/production_rollout.json` file is the deterministic
review artifact for the current production and retry-candidate catalogs.
It records every exact source key, state, source type, signal stage, required
host, policy digest, and a recommended four-shard capacity layout. Runtime shard
count may differ without changing the reviewed source membership. A catalog edit
must regenerate the file:

```bash
python -m app.services.ingestion.cli catalog rollout-manifest \
  --output app/services/ingestion/production_rollout.json
python -m app.services.ingestion.cli catalog rollout-manifest --check
```

The four reviewed source waves are:

1. Texas, Washington, and New York.
2. California, North Carolina, and Florida.
3. Colorado, Massachusetts, and Maryland.
4. Every other production-catalog state plus the District of Columbia in the
   nationwide expansion queue.

Run or inspect one wave without changing the catalog:

```bash
python -m app.services.ingestion.cli scheduled-due \
  --organization default-org \
  --rollout-wave 1 \
  --plan-only
```

Wave scope is applied to catalog synchronization, the host audit, due plan,
unsynced-source accounting, and executable source set. Sharding is deterministic
inside that wave. GitHub
manual dispatches expose the same `rollout_wave` choice; scheduled runs can use
the `INGESTION_ROLLOUT_WAVE` repository variable.

Manifest generation and plan-only runs do not authorize network access. A
production `scheduled-due` execution requires an explicit wave; omitting it is
allowed only for plan-only inspection. Applying
the manifest's `allowed_hosts_value` and `policy_digest` to a deployed worker is
a separate production activation requiring explicit approval. The worker must
also receive the manifest's `manifest_digest` as
`INGESTION_ROLLOUT_MANIFEST_DIGEST`; this pins deployment approval to the exact
catalog fields, effective URLs, source keys, candidates, and wave membership.

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

1. Regenerate and review `production_rollout.json`; CI must pass `--check`.
2. Run `catalog host-audit` for the selected wave and review every hostname.
3. Update the API and exactly one worker with the same static allowlist and digest.
4. Run `scheduled-due --rollout-wave N --plan-only` for a parity window.
5. Enable that wave only after its plan, evidence, and worker capacity are approved.

For the Render Wave 1 worker, a complete plan-only parity window must report
shard source counts `11`, `6`, `6`, and `4`, totaling 27, with
`catalog_synced=true`, `unsynced_source_count=0`, and no host-policy or manifest
failure. Plan-only catalog rows are staged inside the transaction so new
sources appear in the due plan, then rolled back before the command exits.

To activate collection after that review:

1. Keep the checked-in 16-host allowlist, host-policy digest, and rollout
   manifest digest unchanged.
2. Set `INGESTION_PLAN_ONLY=false` on
   `dealsignal-permit-ingestion-cohort-1` in Render.
3. For a controlled first pass, temporarily set `INGESTION_SHARD_INDEX` to
   `0`, run the cron manually, and review run/evidence/health counts. Repeat for
   shards `1` through `3` before removing the override.
4. Confirm the worker returns to UTC rotation and enable Render failure
   notifications.

Candidate retries use an independent preflight and never inherit production
source authorization implicitly. Runtime verifies that the checked-in manifest
is current and that every selected candidate is named in it before checking the
host allowlist and digest. The effective catalog currently contains no
unpromoted runnable candidates, so the retry worker exits without network
access. When a candidate becomes runnable, review its exact hosts first:

```bash
python -m app.services.ingestion.cli catalog candidate-host-audit \
  --print-required-hosts
python -m app.services.ingestion.cli catalog candidate-host-audit \
  --allowed-hosts reviewed.example.gov \
  --print-policy-digest
```

Then regenerate the rollout manifest, set the candidate worker's allowlist,
host-policy digest, and manifest digest, deploy, and run the candidate canary.
The candidate canary sample size must match the reviewed manifest. Candidate
host preflight occurs
before any request and fails the whole selected retry batch atomically.

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
`INGESTION_CORS_ALLOWED_ORIGINS`, `INGESTION_ALLOWED_HOSTS`,
`INGESTION_HOST_POLICY_DIGEST`, and `INGESTION_ROLLOUT_MANIFEST_DIGEST`. The
worker validates both network policy and exact reviewed catalog scope before
collection.

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
| `INGESTION_ROLLOUT_WAVE` | all (plan-only) | Reviewed nationwide wave, 1-4; required for production execution |
| `INGESTION_ROLLOUT_MANIFEST_DIGEST` | unset | Reviewed `manifest_digest`; required for production wave and candidate execution |
| `INGESTION_PLAN_ONLY` | `false` | Print due work without fetching records |

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| CORS / config crash with `ENVIRONMENT=production` | Set `CORS_ALLOWED_ORIGINS` on the ingest task |
| GHA fails with "secret ... is not configured" | Add all six production ingestion secrets listed above |
| ECS task can't reach RDS | SG / VPC — same network rules as App Runner |
| No sources listed | Run `catalog sync` first |
| 409 ActiveRunConflict | Stale run in `ingestion_runs` — investigate before retry |
