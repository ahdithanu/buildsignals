# Release harness

`scripts/release_harness.py` is the local BuildSignals release controller. It
does not push, merge, deploy, seed data, change credentials, or enable persistent
automation. It persists non-secret state so an interrupted operator can restart
from the last observed PR, commit, check run, deployment, environment, and next
action instead of guessing.

## Entry points

Start or resume a dry-run release record:

```bash
python scripts/release_harness.py start --pr 127
python scripts/release_harness.py status
```

Reconcile after interruption with observed external state:

```bash
python scripts/release_harness.py resume --observed-json /path/to/observed.json
python scripts/release_harness.py resume --live-github --pr 127 --expected-deployment-target Preview
python scripts/release_harness.py watch --live-github --pr 127 --expected-deployment-target production --interval-seconds 30 --max-cycles 40
python scripts/release_harness.py work --task "fix frontend npm ci" --live-github --pr 127 --expected-deployment-target production --repair-executor codex-local-repair
```

`--live-github` uses the existing authenticated `gh` CLI in read-only mode. It
inspects the PR state, current default-branch head, required check rollup, and
GitHub deployment records for the exact release commit. For a merged PR, the
release commit is the merge commit or main branch head, not the old PR head or
its preview deployment. If the merge commit is no longer the current default
branch head, reconciliation fails as superseded even if that old commit still
has a successful Production deployment. It does not merge, rerun, cancel,
approve, deploy, or change settings. If `gh` is not authenticated or cannot read
the repository, the inspection fails; do not create credentials in this harness.

The observed fixture remains available for offline testing and maps to the same
reconciliation contract:

```json
{
  "head_sha": "exact commit SHA under release",
  "checks": "pending|failed|passed",
  "run_id": "GitHub Actions run id",
  "deployment_id": "Vercel deployment id",
  "deployment_target": "production|preview",
  "deployment_status": "queued|building|ready|failed",
  "environment": "production",
  "current_default_sha": "current main SHA when known"
}
```

`--expected-deployment-target` pins the intended target before the first
reconcile; use it to prevent a Preview deployment from satisfying a production
release. `watch` repeats the same reconciliation and leaves the state in
`waiting` when checks or deployments are still pending. Pending is not a
failure. Failed, cancelled, skipped, superseded, unknown-target, or
target-mismatched observations fail closed. If the maximum cycle count is
reached, the state remains waiting with `watch timeout` as the reason.

Record a substantive repair attempt without losing the release identity:

```bash
python scripts/release_harness.py resume --record-repair frontend-npm-ci
```

Repair attempts are bounded. When the budget is exhausted, the harness enters a
failure state and waits for operator review instead of looping on the same broken
change.

`work` drives the local repair loop for one explicit product task. Product
repair uses the installed `codex exec` noninteractive CLI in workspace-write
sandbox mode. The repair prompt is generated only from the selected task and
harness safety rules; it does not copy commands or instructions from CI logs or
deployment logs. It then validates with allowlisted local commands:

- `harness-validation`
- `harness-lint`

Waiting external states do not consume repair attempts. If a repair ran before
interruption, resume validates it before attempting another repair. Missing or
unsupported repair executors create a blocker and preserve the task for
resumption. The harness still does not push, merge, deploy, mutate databases, or
change access settings; those remain explicit approved actions outside this
local repair loop.

Run the deployed demo acceptance gate only when the operator is ready to perform
live read-only checks:

```bash
python scripts/release_harness.py acceptance \
  --api-base https://api.example.com \
  --expected-backend "$EXPECTED_BACKEND_SHA" \
  --bearer-token "$READ_ONLY_SMOKE_TOKEN" \
  --run-smoke-script \
  --run-product-gate \
  --product-freshness-hours 72 \
  --require-browser-gate \
  --run-browser-gate \
  --frontend https://app.example.com \
  --live-acceptance
```

Without `--live-acceptance`, the gate records a skipped result. Without a bearer
token, the live gate checks backend readiness but blocks the product-flow claim.
With `--run-smoke-script`, the harness also runs `scripts/smoke-test.sh` with
`BASE` and optional `FRONTEND`; it strips common token/password environment
variables before invoking the script. With `--run-browser-gate`, the harness
runs the existing Playwright demo spec locally. If `--require-browser-gate` is
set and the browser gate is missing or fails, acceptance is blocked/failed and
cannot mark the release accepted. Acceptance also blocks unless the durable
release SHA still matches the observed release SHA and current default-branch
SHA, and the recorded deployment target/status identify the intended ready
Production deployment. Do not put tokens in `--observed-json`, state files, or
logs.

`--run-product-gate` is stricter than the demo/browser gate. It is for the
clarified product outcome: coverage for all existing parcel sources in the
current repository source universe, located parcels for those sources, a usable
heat map, and traceable insights. It calls only read-only live API endpoints and
blocks unless all evidence comes from the intended deployed backend:

- `GET /v1/ingestion/coverage/measured?record_type=parcel` must show at least
  one configured source and stored parcel, zero disabled/empty/stale/unknown
  date/future-date sources, zero unlocated stored parcels, and only `fresh`
  source readiness. The denominator is the versioned repository parcel-source
  manifest built from `catalog.json`, `promoted_catalog.json`, and unpromoted
  parcel entries in `candidate_catalog.json`, not only the sources that happen
  to have ingested rows.
- Every manifest source must appear in live measured coverage. Held, disabled,
  missing, zero-row, stale, failed, or absent sources remain explicit blockers
  with source keys and reasons. Unknown provider/source totals or missing
  extraction-completion evidence block a completeness claim even when the
  currently ingested subset is fully geolocated.
- `GET /v1/acquisition-map/readiness` must show ranked-map readiness, geocoded
  signals, saved searches, and `geocoded_parcels == parcels`.
- `GET /v1/acquisition-map/zip3-heatmap` must return nonempty, deduplicated
  ZIP3 buckets with valid coordinates, method metadata, source/freshness
  explanations, and for-sale semantics that distinguish candidates from
  verified availability.
- `GET /v1/dashboard/ai-insights` must return deterministic insights with
  source-record evidence and a time window or generation timestamp. Generic
  dashboard hints without traceable records block full product readiness.

If the coverage response is paginated, unavailable, synthetic, stale, or missing
source pages, the product gate blocks. Local fixtures and demo data can test the
contract but cannot satisfy live data-coverage readiness.

## Safety model

- The default mode is dry-run. Any mutating adapter must call the harness
  fail-closed guard and require explicit authorization before it can POST, PATCH,
  merge, deploy, seed, or change settings.
- State is stored in `.release/harness-state.json`; the file is non-secret and
  should contain exact SHAs, run IDs, deployment IDs, environment names, phase,
  next action, and bounded event history.
- A file lock at `.release/harness.lock` enforces single-owner execution on this
  machine. A second live worker fails rather than racing the release queue.
  Stale lock metadata left by a dead process is overwritten and marked as
  reclaimed.
- Resume reconciliation fails closed on superseded commits, deployment ID
  mismatch, or deployment target mismatch. This specifically prevents confusing
  a preview deploy with production or assuming Render is the live target when
  Vercel/AWS identity says otherwise.
- Waiting states are explicit (`checks pending`, `deployment pending`) and are
  not treated as failures. Failure states require repair or operator review.

## Acceptance coverage

Production-ready means all required checks are complete for the release
revision, the intended deployment target is identified, `/health/ready` proves
schema compatibility for the intended backend, the frontend is routed to that
backend, the core demo flow passes in a browser, read-only demo mutation
attempts are rejected, and the state file records the exact SHA/deployment
evidence accepted. Deployed/verified-live is stronger: it additionally requires
live target evidence for the intended production deployment. The harness must
not describe API-only checks or an old preview as production ready.

Full product-ready, for parcel/map/insight coverage, is stronger still. It
requires live measured evidence for every existing parcel source in the current
repository manifest: configured, enabled, ingested, extraction-complete,
deduplicated, geolocated, fresh, and source-date-current where the source can
provide those concepts. Catalog entries, onboarding decisions, or admitted-source
ledgers are denominator evidence only until the production API reports current
stored records, geolocation counts, provider totals or explicit unknowns, and
source-level completion evidence for the signed-in tenant. The current source
ledgers include many narrowly admitted parcel sources and many explicit
legal/technical/freshness holds; they must not be converted into a nationwide
completeness claim.

The acceptance gate is read-only and targets the intended backend. Its direct
HTTP probe checks readiness and then exercises the product surfaces that
correspond to the demo: Overview, Filings, Graph, Parcels, and Map. The existing
smoke script adds health/deep-health/readiness/OpenAPI checks and optional
frontend security-header checks. The browser gate runs `e2e/tests/demo.spec.ts`,
which covers demo entry, core navigation, Overview/Product overview, Graph,
Parcels, Map, and read-only mutation restrictions. Absent fixtures,
credentials, browser evidence, or live deployment evidence must be reported as
blocked or unverified rather than as production smoke passed.

Provider-specific deployment inspection currently uses GitHub deployment records
for the exact SHA. If Vercel or AWS does not publish usable deployment
environment/target identity there, the harness cannot honestly prove the target
and must remain blocked/fail closed until an approved read-only provider source
is available.
