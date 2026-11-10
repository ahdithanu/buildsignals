# Investment Areas: Research Inputs and Scoped Evidence

## Current State: Corrected Production Release Verified

November 10 correction is deployed and functionally verified. App Runner
operation `94b738facdec4ea2af519bd8ab164eb3` SUCCEEDED, 14:32:19-14:36:56 PST,
using `investment-private-3a814ee`, digest
`sha256:4dd6c3bcc8284d5b59c4b998b8971291e358d3c59fb913eca9e515384f2f7da1`.
Only the image and a one-account `INTERNAL_OPERATIONS_USER_IDS` value changed;
all other settings/secrets were preserved. No migration, source or schedule
change. The owner identity was verified read-only; no real identifier is in Git.

Final frontend runtime commit e1b6e30, deployment
`dpl_9mMaSrF9piDeEwso6b5WM66TAexS`,
`buildsignal-21rm923bj-ahdi-s-projects.vercel.app`, was built READY without domain
assignment, then promoted successfully to www.buildsignals.ai. Earlier staged
gia6zsl95 was not promoted. The old 9dvokddn6 deployment remains the recorded
frontend rollback target.

Actual owner Chrome session (no token/cookie extraction) confirmed the approved
account, owner-only Operations navigation and populated source-health, schedule
and measured-inventory data. Signals displayed the real annual2025 reference,
360-metro cohort, Ocala research0.251 and61local/61geocoded context rows, collected
November10. Generic Public records labels and capture periods replaced provider
URLs/connector names in the investment response/panel. Tampa correctly displayed
rank unavailable with available population context and no mapped local evidence;
no fabricated zero score. Required attribution and backend lineage remain.

Bounded direct App Runner and Vercel-proxy checks both passed: health200,
anonymous operations401, public demo entry200/no-store, four demo operations
routes403, demo summary200. No token/private response body was printed and no
production test/customer account was created. Ordinary customer-admin denial and
cross-tenant isolation were exercised in real local APIs/PostgreSQL/browser tests,
not falsely described as a second production account test.

Hosted backend run42913498106 passed2,286tests,91%coverage, dependency audit and
both drift checks on1e7dc61. Subsequent e1b6e30 only changed a header class and
browser fixtures; its hosted frontend/E2E/pre-commit/gitleaks checks passed.
Its redundant backend rerun may still be pending; no merge is claimed. This is
functional acceptance, not a load test, sustained monitoring or investment-model
performance validation. Full exact test receipts and first-attempt history follow.

## First Production Attempt (Superseded)

This failed attempt explains the correction; the verified release above supersedes it.
API image `investment-areas-df2236f`, ECR digest
`sha256:93f8d748dc7ed94cbe9e0a9d57e5b7b772996a5bd2ff6f0337850d6843317d02`,
rolled out successfully in App Runner operation
`fa18534c7093411db0e663d4c0942882` (11:24:03-11:27:59 PST). Only the image
identifier changed; settings/secrets/deployment mode were preserved. No migration.
The production service is RUNNING, but the new endpoint failed public-input
loading with a sanitized 503. This is NOT accepted product operation.

Vercel deployment `dpl_AZHrXqW42J4C9SePfJqg9yUCejzp`,
`buildsignal-6vq1ry9f3-ahdi-s-projects.vercel.app`, built READY and was promoted.
The existing authenticated workspace exposed the 503; the frontend was restored
to the prior `buildsignal-9dvokddn6-ahdi-s-projects.vercel.app` deployment while
the correction is verified. Do not call the new panel live yet.

Read-only network inspection found App Runner VPC connector subnets use a
default internet-gateway route without a NAT route. App Runner connector ENIs
have private addresses only; see the official AWS VPC networking documentation.
The exact release container loaded all six files and ranked 360 metros when run
with internet access. No NAT, network/security configuration, or paid service
was added. The revised implementation packages a verified annual reference
instead of performing downloads inside web requests. This does not fix egress
for any other API feature.

Reference capture: `2026-11-10T19:43:58.986728+00:00`, 360 eligible metros,
snapshot `523fea1590d2bd056ec511f0e679e5c1e738a7303f26335aeadbfc88fc0bdd98`,
whole-artifact SHA-256
`27d693e85f5af00a94936b6cd2e7620a7957177578c3134360c824f86425afb3`.
All six publisher URLs, hashes, periods and original capture timestamps remain
in the backend artifact. The API uses `input_mode=release_reference`; immutable
per-process caching makes no web requests. Local tenant evidence remains a
fresh DB query on every API request. Newer government releases are NOT checked
by reading or refreshing the panel. Refresh is an explicit, reviewed artifact
and image release, not an automatic stale-on-error fallback.

Owner additionally requested hiding connector inventories/collection diagnostics
from customer and demo surfaces, and approved retaining internal access only
for their own account. An organization-admin role alone must not suffice.
Implementation uses a server-side user-ID allowlist, default deny; production
identity was verified against one active admin membership using a read-only
production transaction. The server configuration rollout remains pending. No owner email or ID
belongs in Git. Customer-facing investment provenance now shows Public records,
period and capture date, not provider URLs/connector names; full lineage stays
on the backend. Required attribution (including map credits and source-specific
license obligations) must stay. UI hiding is not source secrecy: public repo
code and historical commits can still disclose provider URLs.

The corrected reference/operator revision is local and not production-verified
until final receipts below explicitly supersede this section. Initial GitHub
PR #271 checks passed, including hosted PostgreSQL/PostGIS tests; those checks
precede the production correction and must not be described as its verification.

## Scope and Authorization

### Correction Verification (Not Yet A Production Receipt)

Backend/reference commits 3026ea3 and 3a814ee, test-isolation correction d655106,
frontend ab3270a, browser harness 1e7dc61. Reviewer findings about nested connector
queues, stale operator caches and cross-tab refresh identity changes are fixed.
Refresh refuses changed/missing identity scope before installing a token or
retrying; customer coverage uses an explicit nested field allowlist.

- Reference/unit contracts: 114 passed; access/config/national projection: 46
  passed. Full regression initially found 9 failures (2,208 passed / 69 skipped)
  because config import tests replaced the module still referenced by API
  dependencies. Test-only restoration fixed the mismatch; all 57 affected
  auth/CORS/coverage/nearby/availability/heatmap cases then passed. No production
  authorization guard was relaxed. Final full rerun: 2,217 passed / 69 skipped
  in 312.54s, exit0. All 69 database-dependent cases passed in the separate
  PostgreSQL verification below; SQLite skips are not represented as passes.
- Frozen frontend: 418 tests / 73 files passed, typecheck and build passed.
  Existing Zod annotation and large-bundle warnings remain.
- Final combined Chromium customer/operator/demo/reference acceptance: 4 passed
  in 13.528s, no skips/retries, zero unexpected external browser requests,
  downloads or page errors. Customer/operator/demo at 1024/1440/390px; reference
  at 1440/390px. Synthetic operator only in disposable SQLite. Real reference
  cohort360, isolated local evidence0; no production inventory seeded.
- Local disposable PostgreSQL16.4/PostGIS3.4.3: 91 passed, including all 69
  PostgreSQL-dependent cases, 0 skips/failures in 47.87s. Restricted appuser had
  no superuser/BYPASSRLS/elevated grants; 67 tables enabled/forced RLS. Migration
  head 20260928_0008 and before/after drift checks passed. Container removed.
  This is actual local database verification, not a production migration.
- Exact Linux/amd64 backend image `investment-private-3a814ee` passed a
  network-disabled HTTP check using the real packaged reference: both metros200,
  anonymous401, customer internal-operations403, safe 50-state aggregates, no-store
  and empty isolated tenant. ECR digest
  `sha256:4dd6c3bcc8284d5b59c4b998b8971291e358d3c59fb913eca9e515384f2f7da1`.
  Only this unique tag was pushed; latest/worker images unchanged. API rollout
  remains pending. An initial smoke invocation failed only because /tmp script
  imports lacked PYTHONPATH; explicit /app import path corrected the harness.

API image/configuration, frontend promotion and real owner-session UI acceptance
are still pending. Successful local checks and uploaded artifacts are not live
product acceptance. No new source, paid service, model call, schedule or schema
change was made by this correction.

Rollout started after the completed local checks: App Runner operation
`94b738facdec4ea2af519bd8ab164eb3`, target `investment-private-3a814ee`.
The update verified that only the image and approved single-account operations
allowlist changed; every other setting/secret was preserved. No migration.
Operation success and actual browser acceptance remain separate pending gates.

Hosted frontend/browser checks then caught two stale synthetic access assumptions
in the browser-policy and measured-inventory tests, plus a real 9px header overflow
for the operator at 1024px on Linux. The header now keeps the account name in its
menu below the wide-desktop breakpoint; 1280px was added to layout checks. Existing
tests are being updated to use explicit synthetic operator authorization or the
customer-safe projection, not a customer-admin bypass. These failures must be
cleared before promoting the staged frontend. Initial staged, unpromoted build:
`dpl_J6ANchRegoeCA4ajRxw4iChdozfD` / `buildsignal-gia6zsl95-ahdi-s-projects.vercel.app`.
It predates the header adjustment and must not be promoted. Runtime npm audit:
0 vulnerabilities. Full install audit still reports 13 development-tool advisories
(11 moderate, 2 high); no dependency upgrade/suppression was included. Do not
describe all dependencies as vulnerability-free.

Final header/fixture correction e1b6e30: frontend418passed again, typecheck/build
passed; strict CSP/login verifier passed390/768/1440. Full Chromium suite19/19
passed in36.761s with zero skips/retries/failures, including the legacy opt-in
reference test. OS sandbox denied non-localhost outbound traffic. Operator and
customer layouts passed1024/1280/1440/390. Customer/operator switch did not leak
diagnostics and no ingestion runs were created. Test servers were stopped.
An initial measured-test timeout was caused by an already-fresh cached Permits
query; the test now explicitly refreshes rather than waiting for a nonexistent
request. API behavior and cache freshness were not weakened.

Owner approved release after verification of the authenticated, GET-only
`/v1/investment-areas?cbsa=36100` API and Investment areas panel on `/signals`.
No migration, paid-model call, new ingestion source, schedule change, inquiry,
account or fee is included. City inquiries remain drafts.

Release branch `codex/investment-area-live` starts at current `origin/main`
`2307b92`, preserving newer national parcel/discovery and CSP fixes. The root
`codex/reviewed-city-expansion` research branch is not a release base. Concurrent
frontier-hotspot and parcel-finder research is excluded from this release.

## Meaning and Limits

`metro-research-v0.3` ranks eligible metros using 70% two-year FHFA home-price
momentum percentile and 30% Census residential-unit-surge percentile. Equal
values receive average ranks. This is a research ranking, not a calibrated
expected return, investment-quality score, parcel value, or retail/multifamily
forecast. Earlier research performance numbers do not validate this corrected
implementation or geography. Local filing counts never alter the ranking.

Annual 2025 current-vintage inputs are not real-time or historical known-then
evidence. HPI requires complete four-quarter annual histories for 2023/2025.
County BPS residential units for 2022-2025 are reaggregated on a single 2025
Census county-to-CBSA crosswalk; missing history is not zero-filled. County
populations must reconcile exactly to each published metro total in both 2024
and 2025, or the metro is excluded from ranking. This is an internal consistency
gate, not independent publisher completeness. Population
growth and migration remain separate observed context. Tampa's unmatched HPI
geography produces no rank, while available population context stays visible.

The superseded first attempt downloaded six files during a web request. The
correction instead validates the fixed backend reference file and manifest,
including source/model code identity and original input provenance. No external
request occurs on this API path. Missing, corrupt or incompatible references
return sanitized 503/Retry-After 60 with a short failure cooldown; they do not
silently substitute different data. The reference is process-cached, public-only
and immutable for an image lifetime. No tenant data enters that cache. Refresh
requires a new reviewed reference/image release. The capture script has bounded
official downloads and exclusive file creation; never overwrite a prior capture
to hide provenance or code drift.

Internal access configuration and customer-safe projections are documented in
`docs/runbooks/internal-operations.md`. Local reference correction checks:
114 passed in 2.17s, scoped Ruff and diff whitespace checks passed. These do not
replace the final full-suite, operator-browser and production acceptance gates.

Local evidence is queried on every request with existing organization scope and
RLS context. Responses explicitly set Cache-Control no-store, including direct
API access; successful responses vary by Authorization and Cookie. Only the
explicitly linked Ocala GIS source contributes to Ocala's
local count. Postal addresses do not establish jurisdiction. A workspace lacking
that source honestly shows zero local rows, not another tenant's inventory.
Counts are not deduplicated projects or complete metro coverage. Source collection
time does not establish publisher filing freshness.

Investment quality remains insufficient_data: rents/yield, vacancy, lease quality,
capex, liquidity, parcel economics, jobs/wages and verified anchors/entitlements
are not supplied by the metro rank. Nearby candidates are not for-sale listings.

## Verification Before Release

- Final offline focused backend suite: 60 passed, including parser contracts,
  missing/nonfinite inputs, unit-vs-building columns, ties, tenant isolation,
  anonymous rejection, no-store, clean upstream errors, cache expiry/cooldown,
  missing/mismatched county populations in either year and division membership.
  Independent reviewer repeated all 60 plus 14 rate-limit tests; no remaining
  release blockers found in the reviewed scope.
- Release-tree frontend suite: 70 files / 376 tests passed.
- Typecheck and production build passed; existing Zod annotation and >500 KB
  bundle warnings remain. They are not represented as warning-free builds.
- Actual public-input run: 360 eligible metros; snapshot
  `09a74ba5e3f6e760f0b1a783a3d8c5c9b46230ffd30a63b0371ca8b121a73c39`
  before the review's crosswalk reconciliation guard.
- Final live browser/API/public-input run after that guard: 1 passed, both metros
  at 1440x1000 and 390x844, no mocked responses/private inventory, no overflow or
  uncaught page errors. Snapshot v2
  `523fea1590d2bd056ec511f0e679e5c1e738a7303f26335aeadbfc88fc0bdd98`,
  still 360 eligible metros. All six source hashes and periods validated. Ocala
  score 0.251 rounded; Tampa no aligned rank but demand context present. Fresh
  test org showed zero local rows, as expected. Four screenshots visually
  inspected. See e2e/README.md for opt-in run command and limitations.
- Built Linux/amd64 container passed an additional network-disabled synthetic
  HTTP check: anonymous 401, authenticated 200, no-store, isolated empty tenant.
- Production-network read-only service check: ECS task
  `3a888111f9a648aebfa86ecf289ce0bd`, STOPPED/exit 0. It loaded the public inputs
  and joined 61 Ocala context rows / 61 geocoded in the existing source workspace.
  Source last collection: `2026-11-10T05:58:38.604504+00:00`. This transient
  verification was not an API deployment or database write.
- Root research-tree full pytest cannot collect the unrelated
  `research/appreciation/scripts/stress_test.py` CLI (IndexError from sys.argv).
  The isolated release tree excludes that research; its full-suite result is
  recorded separately below rather than silently skipping the root failure.

- Full initial release-tree suite: 2 failed, 2,125 passed, 69 skipped. Both failures
  were registration 429s caused by shared in-memory limiter state. Test clients
  now reset that in-memory state and reject a Redis-backed test configuration;
  production rate limits are unchanged. Affected 45-test regression run passed.
- Final frozen-backend/fixture full suite with OPENROUTER_API_KEY= and REDIS_URL=,
  explicit disposable SQLite: **2,134 passed, 69 skipped in 537.60s**, exit 0.
  Skips: 45 evaluation PostgreSQL, 12 RLS, 9 schema reconciliation and one each
  activity baseline, migration reversibility and demo PostgreSQL. Required
  restricted-role PostgreSQL test databases were not configured; skips are not
  passes or new production RLS acceptance. Scoped Ruff passed on all eight files.

Actual deployment and production-browser receipts must be appended before
claiming production acceptance. Local browser acceptance above is not a deployed
browser receipt. No schema/dependency/entrypoint differences from
the previous production-tagged commit were found under alembic/requirements;
the release does not invoke the migration-enabled deploy workflow.

## Rollback

Previous production ECR image digest:
`sha256:3115a8ca51aedabbe52b640b607fe39a3aea6219564ccbf351b8edbd6e0bc8b2`.
On API errors, restore the recorded prior image using App Runner while preserving
all existing service configuration. Roll back the frontend to its prior Vercel
production deployment. No data migration or data rollback is required. Record
immutable new image, operation ID and frontend deployment URL after execution.
Previous frontend rollback deployment:
`buildsignal-9dvokddn6-ahdi-s-projects.vercel.app` (READY, production, main 2307b92).

## New Port Richey Is Still Not Live

The City-linked ArcGIS organization `5fOG6RMXXiEvqNzn` was searched with the
documented public catalog API: 62 public items, nextStart -1. Item
`c05de30e23354a62bbc8ceab4646fd73`, NPR 2026 Community Development Map_WFL1,
has Query capability but only MPOD, zoning and future-land-use polygon layers
(IDs 1/10/11). Its public item description/license fields were blank. No feature
rows were requested, no permit export was obtained and no source activated.
These are land-use leads, not permit submissions. A supported recurring City
permit export/feed remains the exact dependency; do not infer it from Tyler's
internal SPA calls or substitute Pasco/Port Richey jurisdiction. Inquiries stay
drafts under the owner's explicit direction.
