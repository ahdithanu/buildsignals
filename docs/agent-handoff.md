# Current Agent Handoff

Last updated: 2026-10-16 (America/Los_Angeles). This is a dated snapshot;
inspect Git and reverify production before acting. No credentials belong here.

## Current Task

Recent-filings activation completed after user approved the existing signed-in
workspace plus a separate sanitized public-demo subset. Branch:
`codex/recent-columbus-filings` (local commits; not pushed/merged).
- Production task `3bb48eaae16549e29a7e18d2f101a149`: exit 0, 21 Columbus site
  applications inserted, zero failed, no checkpoint, provider counts 21/21.
  Destination was the sole active non-demo organization; query `.one()` fails
  closed if ambiguous. No customer rows were copied to demo.
- Public demo task `05fd7a4a8eb2493fb622e11ae08cc2e2`: exit 0, 21 reviewed public
  site applications replayed with the new explicit recent-snapshot seed path.
  Q1-only default guard remains. Source snapshots remain inactive in demo.
- Independent read-only task `41351cc7edc84394b176aa3598c76103` confirmed 21
  production recent filings; newest filed date October 13, 2026. Collection
  interval was October 1 inclusive through October 16 exclusive. Production
  source is active but manual and date-bounded, NOT automatically refreshed.
- Demo API summary: 2,070 permits, 4,919 graph entities, 8,197 relationships,
  1,057 parcel references, zero qualified parcel records/map coordinates.
  Anonymous login and read routes passed; restricted reads and all write-method
  probes returned 403. Temporary private S3 import archive was removed.
- Vercel deployment `dpl_HXpc64UPv3nNi925LnKTYaZR9pub` READY and aliased to
  www.buildsignals.ai. Demo subtitle no longer claims only Q1; filing/issuance/
  capture dates are shown separately in the list. API service image unchanged;
  the reviewed seed helper ran as a one-off task, not an API code deployment.
- Verification: 68 targeted backend tests, 3 demo frontend tests, typecheck,
  local production build and focused Ruff passed. npm audit --omit=dev: zero
  vulnerabilities. Vercel full install reported 4 moderate/6 high advisories;
  development dependency audit remains pending. Bundle-size warning remains.
- First large CLI upload was interrupted. Added explicit frontend-only Vercel
  upload rules. First allowlist attempt excluded directories and failed remote
  typecheck/lint before promotion; corrected rules included 302 frontend files
  and subsequent deployment succeeded. No checks were bypassed.

Next: configure scheduled, bounded current-source refresh using managed secret
references (existing GitHub ingestion environment is unconfigured); add durable
job receipts and recent-demo refresh policy. Do not represent this fixed-window
import as continuous ingestion or nationwide coverage. New seed CLI code is
local until its branch is published or a new API image includes it.

Recent-filings follow-up (2026-10-16): production read-only audit task
`0de200bceac54ff4ac12338d4086456a` exited 0. The sole non-demo workspace
has no registered sources. Demo has only the six inactive historical sources.
Last five GitHub ingestion-cron runs were skipped; repository variables and
production-environment secret name lists were empty. No ECS services or EventBridge
Scheduler schedules were found in us-east-1; this is not an exhaustive account audit.
Bounded local Columbus site application intake for October 1 inclusive through
October 16 exclusive returned 21 records, zero failures, no checkpoint, and
provider counts 21 before/after. Existing historical intake tests: 9 passed.
Qualification DB/report are under `/private/tmp/buildsignals-columbus-site-20261001.*`;
temporary files are not durable project inventory. This does not qualify geometry.
Production task `4f6a3c7e06164f43bce87b236d4bee8a` stopped with NoResultFound
while resolving `default-org`, before source creation or record writes. Confirm
the intended destination workspace rather than guessing another tenant. No recent
records were loaded into production; no schedule was activated. Public demo still
uses a Q1-only replay guard and historical labels; add an explicit recent cohort
path with matching UI labels/tests rather than bypassing that guard.

Public read-only demo activation was approved and completed on 2026-10-16.
App Runner operation `9a909ca644b34ba59b8303a7822d496a` SUCCEEDED with
`DEMO_ENABLED=true`; no OpenRouter configuration or source activation changed.
The existing seed pipeline loaded six reviewed Q1 Columbus snapshots into the
reserved demo tenant: 2,049 permits, 4,852 graph entities, 8,115 relationships,
and 1,038 distinct reported parcel references. Seed ECS task
`a2d789c959e14bc7b1cb592f9b9cac2a` exited 0. These are historical records, not
unique projects or live nationwide inventory. There are zero qualified parcel
records and zero mapped coordinates in this cohort; do not claim otherwise.
The temporary private S3 seed archive was removed after successful import.

Production verification: anonymous POST `/v1/auth/demo` issues a viewer token
with demo/read_only claims and 60-minute expiry. Summary, permits, graph hubs,
parcel references and map routes returned 200. Settings, users, export and
POST/PUT/PATCH/DELETE mutation probes returned 403. Browser verification clicked
`Enter demo mode` on `/login`, reached `/demo` without credentials, and displayed
the read-only banner and populated counts. Local `tests/test_demo.py`: 51 passed.
This smoke test is not a new exhaustive tenant-isolation audit.

The approved main API release to AWS is complete, with OpenRouter unconfigured
and scoring deterministic. User approved this production deployment and required
migrations on 2026-10-16. No paid model calls were approved.
Portable-agent instructions/tooling are checkpointed locally as `d4a9c83` on
`codex/portable-agent-handoff`; publishing that branch remains separate.

## Completed API Release (2026-10-16)

- Release source: main `edcbc52`; workflow run `38953119809`.
- Repaired deployment IAM trust to the exact current immutable GitHub subject,
  retaining main-only scope. GitHub reports `use_immutable_subject=true`.
- First authentication attempt stopped before application/database changes.
- First migration task then failed before connecting to the DB because its
  production CORS allowlist was missing. Registered `dealsignal-migrate:2`
  with the existing API origins; preserved role/secret references.
- Confirmed API and migration task reference the same DATABASE_URL/SECRET_KEY
  secrets without reading values. RDS has seven-day retention and a recent
  point-in-time recovery timestamp (restore procedure not tested in this task).
- Retried migrations succeeded (task `b35a3853aa694e558285c2450c346e87`, exit 0),
  upgrading `20260915_0001` through `20260928_0008`.
- New image digest: `sha256:648ec2c7fe8a4eca1cac32dd74b83872eaa0ba762abbe31f8915fd82a71d791e`.
- App Runner operation `f26e7fff97fa478ebafba78f080d7e4a` SUCCEEDED at
  2026-10-16 12:21:35 America/Los_Angeles; service is RUNNING. Workflow succeeded.
- Earlier image digest retained for rollback reference:
  `sha256:bd3ccc8bb085957656b0013a5d533ecdf99c77cbc4aafcca58480e5951632556`.
- Production sign-in page renders. Authenticated user/data workflows remain
  unverified. Demo configuration has not been enabled or seeded by this release.
- Direct readiness and database health returned 200; live ScoreResponse now has
  scoring_method/fallback_reason and OpenAPI exposes `/v1/auth/demo`.
- Through Vercel, GET `/v1/auth/demo` returns 200 with enabled=false, and
  unauthenticated GET `/v1/deals` returns 401. Model key remains absent from
  runtime variables and secret references; unset SCORING_MODE defaults deterministic.
- Full receipt: `docs/releases/2026-10-16-api-rollout.md`.

## Completed Product Work

- PR #247 merged as `4d47f4c`: OpenRouter client, optional enrichment/memos/model
  scoring, deterministic scoring default, validation/fallback, benchmark tooling.
- Review follow-up fixed exhausted timeout/connection handling, malformed JSON
  benchmark classification, production validator use, and omitted memo evidence.
- Final PR backend CI: **1,767 passed**, including PostgreSQL-backed tests,
  in 705.75 seconds. Run: GitHub Actions `38865887692`.
- Final offline OpenRouter/review subset: **38 passed**. Frontend/E2E/security/
  pre-commit/Vercel checks passed on final PR head `a59d32b`.
- Production frontend subsequently built from `edcbc52` (main), which includes
  PR #247 and only adds generated OpenAPI updates. Do not restore the obsolete
  `cleanup-and-hardening` product tree over main.

PR: https://github.com/ahdithanu/buildsignals/pull/247
Audit: `docs/openrouter-cleanup-integration.md`. Older local receipts there are
historical; the final CI receipt above supersedes their counts.

## Earlier Production Verification (2026-10-16, Superseded for API State)

Read-only observations; these are not authorization to modify cloud resources.

- `https://www.buildsignals.ai` is Vercel production, ready, deployment
  `dpl_WmgWdc8qDNWHyagTriQoc3d8wKoF`, source commit `edcbc52`.
- `vercel.json` proxies `/v1` to
  `https://xg4xjxc2p2.us-east-1.awsapprunner.com`.
- AWS App Runner `dealsignal-api` is RUNNING. Its last successful deployment
  was 2026-09-19; ECR `latest` was pushed 2026-09-18. Auto-deploy is false.
- Direct API `/health`, `/health/deep` and `/health/ready` returned healthy.
  Readiness reflects the running version; it does not prove compatibility
  with all migrations in current main.
- Live OpenAPI's ScoreResponse lacks `scoring_method`/`fallback_reason` and
  lists no `/auth/demo` routes. Live `GET /v1/auth/demo` returned 401.
  Serving `/demo` HTML with 200 is not proof of a working demo data session.
- App Runner has no `OPENROUTER_API_KEY` runtime variable or secret reference;
  no SCORING_MODE/primary/fallback model settings were configured.
- `.github/workflows/deploy-aws.yml` is manual and includes a migration task.
  No image tagged with PR #247's merge SHA was found in ECR.

Vercel connector lacked team scope; Vercel CLI access worked. AWS CLI and gh
read-only access worked in the previous agent environment. Other agents must
authenticate independently. Render MCP had no workspace selected.

## Next Actions and Dependencies

1. Portable-agent setup is implemented and verified locally. See Git history for
   its checkpoint. Publishing this new branch has not been requested; another
   machine/clone will need the branch published before it can read these files.
2. API rollout and public demo activation are complete. Ordinary authenticated
   customer workflows remain unverified. Qualified parcel geometry/geocoding is
   still required before this demo can display mapped acquisition candidates.
3. Provision an OpenRouter production key/config through a managed secret path
   only with applicable approval. Never copy or print a local key in chat.
4. Run live model smoke tests and the corrected benchmark only with paid-call
   authorization. No current post-fix model ranking/cost result is published.
   Keys/credits/model availability and key rotation remain unverified.
5. Resume acquisition pilot/source qualification work from the linked checklists
   after the immediate release blockers. Do not activate unreviewed sources.

## Evidence and Product Limits

- The 2,049 Columbus records are historical source qualification/demo data,
  not 2,049 unique projects or measured nationwide production inventory.
- No current live jurisdiction/record/freshness count was measured in this task.
- Nearby parcels are candidates unless separate source-backed availability
  evidence verifies a listing/for-sale claim.
- No paid model calls were performed. The initial production verification and
  portability tasks were read-only; the later approved deployment has the
  infrastructure/migration changes recorded above.

## Session Verification

Portability verification (2026-10-16):

- `python3 scripts/agent_status.py --check`: passed; all shared files/adapters found.
- `make agent-status`: passed; branch, commit and working-tree status reported.
- The same script with `--check` invoked by absolute path from `/private/tmp`:
  passed, correctly locating the repository rather than using the caller's folder.
- `ruff check scripts/agent_status.py`: passed.
- `git diff --check`: passed.
- Product test suites were not rerun for these docs and read-only tooling changes.
  Prior product test receipts are recorded above, not represented as new runs.
- Instruction discovery and cloud authentication inside external agent apps:
  unverified; Claude Code is installed locally, Antigravity CLI was not found.

Use `python3 scripts/agent_status.py` to inspect the actual working tree. Before
switching agents again, replace this snapshot with the latest state and next task.
