# Production readiness audit — 2026-10-22

Observed approximately 15:28–15:36 UTC (08:28–08:36 America/Los_Angeles).
Checkout: `codex/p0-8-eval-gate`, HEAD `f95fbd5`; this is not evidence that
this branch is deployed. The user authorized production checklist work. This
audit used read-only AWS metadata and public HTTP checks; no cloud configuration,
source activation, migrations, customer records, secret values or paid model calls.
Public demo sessions were created solely to verify the existing demo boundary;
tokens remained in process memory and were never logged or saved.

## Fresh verification receipts

| Check | Observed result | Claim boundary |
| --- | --- | --- |
| AWS access | STS identity resolves to the existing `emos-deploy` IAM user | Establishes read access, not application authorization |
| API service | App Runner `dealsignal-api`, us-east-1, `RUNNING`; configured HTTP `/health` probe every 10 seconds, timeout 5 seconds | Running service metadata, not full workflow acceptance |
| Direct/public health | Direct App Runner `/health` and `https://www.buildsignals.ai/health` both HTTP 200 | Public route response, not authenticated tenant health |
| Unauthenticated protection | Public `GET /v1/deals?limit=1` HTTP 401 | One endpoint, not complete authorization attestation |
| Public demo | Session HTTP 200, `is_demo=true`, viewer; summary HTTP 200; empty `POST /v1/deals` HTTP 403; `GET /v1/deals/export` HTTP 403 | Existing public demo only; no customer workspace checked |
| Ingestion schedules | All 16 schedules in `buildsignals-ingestion` ENABLED: 14 regional plus Columbus production/demo | Configuration state only; not successful ingestion or coverage |
| Worker rollout distinction | Texas Comptroller schedule last modified October 16; other regional schedules October 19 | Consistent with dated rollout receipt; embedded commands/images not inspected |
| Database protection metadata | RDS `dealsignal-pg` available, encrypted, backup retention 7 days; latest restorable time `2026-10-22T15:28:17Z` | Confirms provider backup/PITR metadata; no restore performed |
| Snapshot inventory | Eight available encrypted automated snapshots, October 15–22; newest `rds:dealsignal-pg-2026-10-22-07-18`, created `07:18:15.679Z` | Snapshot availability does not prove recoverability |
| Existing inspection copy | `dealsignal-pg-restore-inspect-20261007` available, created `2026-10-07T21:42:49.755Z` | Existence alone does not prove restore drill, RLS or RTO |

The active backup provider for this inspected database is AWS RDS. Historical
Render daily-snapshot/no-PITR assumptions in `docs/backups.md` must not be treated
as current production facts. RDS reports a latest restorable time; measured RPO
and RTO still require a documented restore and application/isolation acceptance.
The database currently reports `MultiAZ=false` and `DeletionProtection=false`.
These are observed settings, not changes made by this task.

## Operational gaps found

- `aws cloudwatch describe-alarms --region us-east-1` returned zero metric alarms
  and zero composite alarms. `aws sns list-topics --region us-east-1` returned
  no topics. No reusable SNS alert destination was found in this region/account.
  This does not rule out external monitoring or other regions; none was verified.
- All 16 schedules have no dead-letter configuration, with maximum event age
  900 seconds and maximum retries 2. Scheduler invocation success does not prove
  the ECS application task succeeded. `AWS/Scheduler` currently lists only
  `InvocationAttemptCount` (unscoped and `ScheduleGroup=buildsignals-ingestion`).
- `aws ecs list-tasks --cluster dealsignal-cicd --desired-status STOPPED
  --max-results 30` returned no task ARNs. No recent task outcome was established;
  provider retention/visibility makes this an absence of evidence, not zero failures.
- `/ecs/buildsignals-ingestion` has 30-day log retention; `/ecs/dealsignal-migrate`
  has 14 days. App Runner application and service log groups under
  `/aws/apprunner/dealsignal-api/1d89815a963b4a3cb37ca6b752048d16/` have no explicit
  retention configured. No raw logs were retrieved.
- App Runner metadata returned no observability configuration. Secret-binding
  **names only** were inspected: `DATABASE_URL`, `METRICS_TOKEN`, `SECRET_KEY`.
  MFA key provisioning cannot be inferred from these names; plain environment
  values were deliberately not retrieved.
- **API cache policy defect:** public proxied demo session responses returned
  `Cache-Control: public, max-age=0, must-revalidate`; direct App Runner returned
  `Cache-Control: no-store`. Public response `x-vercel-cache` was `MISS`.
  The checked-in global Vercel cache header is consistent with the override.
  No token cache disclosure was observed. An API-specific no-store configuration
  needs deployment and a fresh public-header check before this issue closes.

**Closed later in this session:** the cache correction was staged, authenticated
stage checks passed, and deployment `dpl_A9YYo2JuK92juqsYUsn6CNuD8EQB` was promoted
to the existing public domains. At `2026-10-22T15:41:10Z`, public demo auth and
summary were 200/no-store, demo write and export probes were 403/no-store, and
unauthenticated deals were 401/no-store. `/login` stayed 200 with the existing
frontend revalidation policy. See [sanitized smoke receipt](2026-10-22-api-cache-smoke.json).
The earlier unprotected stage checks followed Vercel SSO to its login page and
were discarded; authenticated `vercel curl` checks established actual API behavior.
No protection setting was weakened.

Release scope: only `vercel.json` cache rules changed in the frontend. Compared
with deployed source `1736239`, all tracked frontend/build inputs otherwise match.
The CLI uploaded the existing 302-file frontend allowlist, excluding local DBs,
private configuration and backend work. Previous production deployment
`dpl_3mb6kFrh4AkZsUCFiFUUeLa8kkSx` remains a rollback reference (it retains the
cache defect). No API image, migration or worker deployment accompanied this fix.

Local gates: typecheck passed; frontend 366 tests passed; production build passed
with the existing large-bundle warning. The Vercel cache-policy regression suite
passed 12 tests. Remote production build completed successfully. Full CSP,
customer workflow and visual acceptance are not established by these checks.

## Checklist disposition

Dated health, enabled-schedule configuration, backup provider/retention,
available-snapshot inventory, and demo read/write/export boundaries have fresh
receipts above. These narrow verification items can close for this audit date.

Still open: delivered failure alerts with an owned destination and tested
failure/recovery path; recent successful ingestion and authenticated measured
coverage; actual restored-copy application/RLS checks and measured RPO/RTO;
MFA rollout state; authenticated production acquisition workflow; qualified
parcel rights/evidence; independent diligence verification; all separate
source/legal/activation gates. The cache-policy repair is closed by the later
release receipt above. No broad institutional
production-readiness or security attestation is made.

Commands used selected metadata fields with AWS CLI `--query`; no environment,
task overrides, log messages, database rows or subscription addresses were output.
No cloud mutation or release occurred during the initial read-only audit; the
separately recorded frontend correction above was subsequently released under
the user's production-checklist instruction.

## Frontend deployment identity

Read-only Vercel deployment metadata resolves the public aliases to READY
production deployment `dpl_3mb6kFrh4AkZsUCFiFUUeLa8kkSx`, source `main` commit
`17362390e37b192790240c95a5cd500c756d9a14` (PR #263 merge).
`vercel inspect` also confirms its deployed global public cache header.
At inspection time, tracked frontend/build files (`src`, package manifests,
Vite configuration, `index.html`, `vercel.json`) have no committed differences
between that deployed commit and checkout HEAD. This is source comparison,
not a rebuilt artifact-equivalence guarantee; subsequent edits need review.
