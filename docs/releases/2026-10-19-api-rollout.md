# Production API Rollout: 2026-10-19

User authorized a batched deploy of `main` to the running API. OpenRouter stays
unconfigured and scoring deterministic; no paid model calls. No source was
activated.

## Release

- Repository: `ahdithanu/buildsignals`. Source: `main` (PRs #251–#254 merged).
- Workflow: `.github/workflows/deploy-aws.yml` (manual `workflow_dispatch`, GitHub
  OIDC). Run: https://github.com/ahdithanu/buildsignals/actions/runs/39211873165
  — conclusion **success**.
- App Runner `dealsignal-api` (us-east-1) rolled out the new `:latest` image and
  is **RUNNING**.
- Migrations: the `dealsignal-migrate` step ran; there were **no new Alembic
  migrations** since the prior release (`edcbc52`), so it was a no-op at head.

## What shipped (API code on `main`)

- Ingestion health now measures **source-update-date completeness** (collection
  recency is not presented as filing recency).
- Biloxi mixed-encoding decoding reusable by the `planning_documents` connector;
  the MDEQ enSearch contract qualification record.
- `POST /v1/temporal/development-velocity` — Development Velocity v0 (a pure,
  offline, cutoff-safe signal on `activity_baseline`; the 0–100 score is an
  **unvalidated** research output).
- ERCOT (`ercot_mis_xlsx`), Census BPS and Loudoun LOLA connectors are present as
  **inert `technical_hold` candidates** — canaries/ingestion disabled, **not
  activated**. Shipping the code does not qualify, license, or enable them.

## Verification (post-deploy)

- Direct App Runner `GET /health`: **200**.
- `https://www.buildsignals.ai/v1/auth/demo`: `{"enabled":true}` (demo still live).
- Deployed OpenAPI (App Runner origin) lists `/v1/temporal/development-velocity`
  among 181 paths — the DV route is live.
- Authenticated customer workflows and the DV endpoint's live behavior were not
  exercised with a real account in this task.

## Not shipped by this deploy

- The #249 **worker** reliability fixes — the quarantine guard
  (`scripts/recurring_regions.py`) and the IAM-policy accumulation
  (`scripts/configure_regional_ingestion.py`) — live in the regional provisioning
  scripts. The live EventBridge regional schedules run an **embedded snapshot** of
  the prior worker script, so these take effect only on a **regional
  re-provision** (a separate, gated op needing fresh source canaries +
  `--confirm-production`). The API deploy does not change the running schedules.
- No source activation, no demo re-seed, no OpenRouter key. The replay/backtest
  harness is offline tooling, not a deployed service.

## Regional worker re-provision (2026-10-19, same day)

Shipped the #249 **worker** fixes (quarantine guard + IAM-policy accumulation) to
the live regional schedules, authorized by the user.

- Fresh bounded canaries for the 14 regional sources (`recurring_regions.py
  --verify`): **13 verified**. `texas_comptroller_sales_tax_locations` failed its
  canary legitimately — "recent scope is empty or exceeds the 1000-record budget"
  (the 7-day sales-tax window is out of the bounded budget right now), so it was
  NOT re-provisioned.
- `configure_regional_ingestion.py --confirm-production` re-provisioned the **13
  verified** sources: new task-definition revisions (mostly `:4`, Austin `:3`) on
  image `dealsignal-api@sha256:3115a8ca…` (today's deployed main) with the current
  `recurring_regions.py` embedded (now carrying the quarantine guard), and their
  EventBridge schedules updated + ENABLED.
- **IAM-accumulation fix verified in production**: the inline policy
  `RunVerifiedRegionalTasks` now lists 27 `ecs:RunTask` ARNs, and
  `texas_comptroller`'s existing task ARN is **preserved** — so the un-reprovisioned
  source kept RunTask permission (without the fix a subset re-provision would have
  stripped it). Its schedule is untouched and ENABLED. All 14 regional schedules
  ENABLED.
- `texas_comptroller` still runs its prior embedded script; it picks up the #249
  quarantine guard on a future re-provision once its window is in-budget. A failed
  reconciliation now quarantines a source (is_active False) and the next scheduled
  run will no longer silently re-enable it.
