# Investment Areas: Research Inputs and Scoped Evidence

## Scope and Authorization

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

Public input URLs and SHA-256 hashes are returned as provenance. Six fixed
official files are fetched at most once per hour per API process, with a
single-flight lock, 20-second request timeouts, no retries and 12 MB/file cap.
A failed refresh returns sanitized 503/Retry-After 60 and does not serve an
expired snapshot. No tenant data enters the public cache. Concurrent cold
requests receive retryable 503 while one refresh runs; cold starts depend on
publisher availability. No historical version archive is implied by this cache.

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
