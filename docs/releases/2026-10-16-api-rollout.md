# Production API Rollout: 2026-10-16

User authorized deploying the merged API and required migrations, keeping
OpenRouter unconfigured and scoring deterministic. No paid model calls authorized.

## Release

- Repository: `ahdithanu/buildsignals`.
- Source: main `edcbc52b9d3001fa0f8d30a1ffb0f79ca0ddf9b1`, including PR #247.
- Workflow: https://github.com/ahdithanu/buildsignals/actions/runs/38953119809
  Final retry: success.
- App Runner: `dealsignal-api`, region `us-east-1`, RUNNING.
- Operation: `f26e7fff97fa478ebafba78f080d7e4a`, SUCCEEDED at
  2026-10-16 12:21:35 America/Los_Angeles.
- Image: ECR `dealsignal-api`, tags `latest` and the release SHA.
- Digest: `sha256:648ec2c7fe8a4eca1cac32dd74b83872eaa0ba762abbe31f8915fd82a71d791e`.
- Previous digest retained for rollback reference:
  `sha256:bd3ccc8bb085957656b0013a5d533ecdf99c77cbc4aafcca58480e5951632556`.
  Database migrations are already applied; review compatibility before any rollback.

## Deployment Repairs

1. The deployment role trusted the old repository name and legacy OIDC subject.
   GitHub's repository OIDC settings reported immutable subjects. Updated the
   existing trust condition to the exact current subject:
   `repo:ahdithanu@225644099/buildsignals@1216658221:ref:refs/heads/main`.
   Preserved the federated principal, STS audience and main-only restriction.
   See [GitHub's OIDC reference](https://docs.github.com/en/actions/reference/security/oidc).
2. Migration task revision 1 failed during config import, before DB connection:
   production CORS allowlist missing. Registered `dealsignal-migrate:2` with the
   same existing API origins, `https://buildsignals.ai,https://www.buildsignals.ai`.
   No startup guard disabled. Database/signing-key references match the API's;
   no secret values were printed or copied.

## Migrations and Recovery

- Successful task: `b35a3853aa694e558285c2450c346e87`, exit code 0.
- Upgraded `20260915_0001` through `20260928_0008`.
- RDS `dealsignal-pg` showed seven-day backup retention and a recent restorable
  timestamp before deployment. No restore drill was performed in this task.
- During cutover readiness temporarily returned 503; after rollout it returned 200.

## Post-Deployment Checks

- Direct `/health/ready`: 200, status=ready.
- Direct `/health/deep`: 200, status=ok, db=ok.
- Live OpenAPI includes ScoreResponse.scoring_method and fallback_reason.
- Live OpenAPI exposes `/v1/auth/demo`.
- Same-origin `https://www.buildsignals.ai/v1/auth/demo`: 200, enabled=false.
- Same-origin unauthenticated `/v1/deals`: 401, Authentication required.
- Production login page rendered sign-in, password recovery, SSO and registration.
- Bounded CloudWatch startup scan found no ERROR/Traceback matches at the time
  checked; this is not a long-term monitoring or error-rate guarantee.
- OpenRouter key absent from App Runner runtime variables and secret references.
  SCORING_MODE unset; deployed code defaults to deterministic. No model calls made.

## Remaining Verification

- Real-user login, evidence/graph/parcel data, saving/exporting and tenant-specific
  inventory were not exercised with an authenticated account in this session.
- Demo remains disabled; this rollout neither seeds demo records nor activates it.
- Production OpenRouter key provisioning, paid smoke tests and model benchmarking
  remain separate work. Do not publish model accuracy/cost recommendations yet.
- No new ingestion source activation or live coverage count was established.
