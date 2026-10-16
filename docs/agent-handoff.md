# Current Agent Handoff

Last updated: 2026-10-16 (America/Los_Angeles). This is a dated snapshot;
inspect Git and reverify production before acting. No credentials belong here.

## Current Task

Make BuildSignals portable between Codex, Claude Code, Antigravity and other
agents. Shared instructions, adapters, onboarding, a handoff template and an
offline status command are implemented locally on `codex/portable-agent-handoff`, based
on `origin/main` at `edcbc52`. See actual Git status for commit state.

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

## Production Verification (2026-10-16)

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
2. Production API release: user was asked to approve deploying current API to
   AWS with required migrations, keeping OpenRouter disabled/deterministic.
   No approval was received before the user switched to the portability task.
   Inspect current main, migration scope and deploy runbook before release.
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
- No paid model calls, production config changes, migrations, or API deployment
  were performed during the production verification/agent-portability tasks.

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
