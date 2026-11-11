# Requested-Market Release Integration

## Publication Update

November 11: after explicit user approval for PR-only publication, branch
`codex/requested-market-release` was pushed and
[PR #272](https://github.com/ahdithanu/buildsignals/pull/272) opened, stacked on
the still-open [privacy PR #271](https://github.com/ahdithanu/buildsignals/pull/271).
The verified runtime commit is86c8ee1; this follow-up changes documentation only.
Initial hosted checks started, with gitleaks and pre-commit successful; backend,
E2E and preview were still running at observation. The PR is the source of truth
for current check results and documentation-only head changes.

No merge, production deploy, source activation, schedule/environment change,
production audit/repair, migration or paid/model call is authorized by this
publication. Production behavior and inventory are unchanged. Keep the parent
privacy dependency intact and require separate release approval.

## State at Local Freeze

November 11, 2026, America/Los_Angeles. Worktree
`/Users/ahdithebomb/Desktop/DealSignal/.worktrees/requested-market-release`,
branch `codex/requested-market-release`, base `5ff111f`. This is a clean-base
integration, not a production release or source activation. The parent confirmed
final source3d8c7fd and authorized a tested local commit only. The enclosing Git
commit is the exact integration checkpoint; nothing is pushed, published,
scheduled, activated, merged or deployed.

Historical source checkpoint is root `ac34876` / `4669af1`. Final parent source
is `3d8c7fdfa52c5d42deef013fe32a9c76fc427b3d`, including the NJ mailing
correction, opt-in service/canary guard, scoped ingestion test, quarter-mile
follow-up and final receipt/architecture/ledger documentation. Source code was
imported without changing root. Do not activate the older ac34876 NJ projection.

## Preserved and Integrated

- Application/privacy baseline remains 5ff111f: owner-only source operations,
  customer-safe projections, authorization/session invalidation, frontend cache
  isolation and packaged annual investment reference. No auth/routes/schemas/src,
  config, main, investment service/reference or root conftest replacement.
- Canonical SF URLs preserve existing dataset IDs. Only SF building enters the
  manual regional profile: 31 UTC-calendar-day changed-row window, primary-address
  predicate, data_loaded_at/record_id keyset, explicit projection including
  data_as_of, canonical PDDL contract checks and existing 36-hour freshness gate.
  LA and SF planning remain outside SOURCES.
- The full newer operational worker is preserved, not replaced by 5ff111f's older
  four-page implementation: 100,000-row/401-page ceiling, <=100-page checkpoint
  chunks, aggregate reconciliation and persisted quarantine. Existing city/wave-2
  semantics remain; held sources are not activated.
- Ocala retains the embedded layer19 context source, native dates/statuses and
  unknown publisher currentness; unique synthetic mapping aliases; raw field,
  identity and WGS84 centroid guard before persistence; 1,000-row ceiling and
  five-page exhaustion budget; incremental replay and no rolling-date cutoff.
  See the imported dated Ocala receipt, not this integration, for its historical
  scheduled-run and replay acceptance.
- NJ keeps PIN_NODUP identity and optional PAMS_PIN/GUID context. PROP_LOC alone
  supplies site address. ST_ADDRESS/CITY_STATE mailing data and unverified
  ZIP5/ZIP_CODE/ZIP_PLUS4 are suppressed, postal code unknown, municipality not
  zoning. No historical stored-data cleanup or continuity inference is made.
- NJ alone opts into enforce_field_allowlist=True. Service validates configuration
  before transport and the entire connector page before filtering/normalization/
  persistence; health applies the same guard to main/stage/freshness canaries.
  Errors are generic, without publisher field values. This is a top-level field
  boundary, not a general free-text or nested personal-data detector.
- The nearby helper selects only reviewed identity, PROP_LOC, municipality,
  acreage and geometry fields; generated profiles remain inactive/manual with
  a 0.25..3-mile radius and at most 2,000 rows. It neither verifies an anchor nor
  creates schedules, source records or production inventory.

No candidate-catalog/Ocala-PDF parser/factory changes, frontier/research, root
MarketSignals edits, retail preparation or worker-upgrade/provisioning tools were
copied. The destination manifest was regenerated against its unchanged candidate
catalog, then all three blueprint manifest pins were synchronized. This does
not apply any cloud environment or scheduler setting.

## Destination Test Adaptation

The NJ scoped ingestion/replay/detail/tenant regression and regional checkpoint
integration test use the existing release internal_operator fixture, not ordinary
admin-only or anonymous source requests. The second NJ tenant remains ordinary
and receives 404. Release conftest and config restoration are unchanged.

Only the copied NJ test's root-only isolated_auth_limiter argument was removed:
the release client already requires the in-memory backend and clears it per test.
No limits or guards changed. The NJ test additionally asserts PROP_LOC address,
unknown postal code and absence of mailing/postal keys in raw storage.

Destination-only projection regressions explicitly poison a two-row page in each
canary phase and verify invalid allowlist configuration fails before transport.
The imported real-service poison test asserts zero RawSourceRecord/ParcelRecord
rows. Earlier committed pages are not claimed to roll back on a later bad page.

## Verification

All commands run in this worktree using the existing root Python environment:

```sh
env OPENROUTER_API_KEY= REDIS_URL= DATABASE_URL=sqlite:// ENVIRONMENT=development \
  /Users/ahdithebomb/Desktop/DealSignal/.venv/bin/python -m pytest -q --tb=short \
  tests/test_ingestion_projection.py tests/test_njgin_scoped_ingestion.py \
  tests/test_regional_refresh_integration.py tests/test_ocala_context_guard.py \
  tests/test_ocala_context_refresh.py tests/test_recurring_regions.py \
  tests/test_qualify_njgin_markets.py tests/test_retail_parcel_refresh.py \
  tests/test_retail_parcel_qualification.py
```

Initial integration result: **268 passed in 3.17s**, before the quarter-mile
follow-up and destination-only additional projection tests.

```sh
env OPENROUTER_API_KEY= REDIS_URL= DATABASE_URL=sqlite:// ENVIRONMENT=development \
  /Users/ahdithebomb/Desktop/DealSignal/.venv/bin/python -m pytest -q --tb=short \
  tests/test_ingestion_projection.py tests/test_njgin_scoped_ingestion.py \
  tests/test_retail_parcel_refresh.py tests/test_retail_parcel_qualification.py \
  tests/test_ingestion_catalog.py tests/test_ingestion_rollout.py \
  tests/test_ingestion_connectors.py tests/test_ingestion_health.py \
  tests/test_internal_operations_access.py
```

Final targeted result after both follow-ups: **398 passed in 19.61s**.

Offline catalog rollout-manifest generation and --check passed. Scoped Ruff
passed using existing `/opt/anaconda3/bin/ruff`; the root .venv has no Ruff module
and that initial module invocation failed without installing anything.
`git diff --check` passed. Protected application/auth/frontend/schema/conftest/
candidate files were compared to HEAD and remain unchanged.

```sh
env OPENROUTER_API_KEY= REDIS_URL= DATABASE_URL=sqlite:// ENVIRONMENT=development \
  /Users/ahdithebomb/Desktop/DealSignal/.venv/bin/python -m pytest tests -q --tb=short
```

Full destination backend suite: **2,472 passed, 69 skipped in 301.65s**, with
code frozen after the quarter-mile follow-up and destination-only tests. No new
PostgreSQL/RLS, browser E2E or hosted CI acceptance is claimed. Parent root pass
counts are source receipts, not acceptance for this different integrated tree.

Final focused diff review found no remaining critical issue. Catalog, service,
health, operational worker and scoped helper were byte-compared with the current
confirmed root3d8c7fd source and match. The destination-only changes to tests are the explicit
operator fixture adaptation, extra postal/raw assertions and main/stage/freshness/
pre-transport guard regressions described above. Candidate catalog and protected
application/auth/frontend files remain identical to the 5ff111f baseline.

## Imported Public Evidence, Not Live Inventory

The parent reports a successful bounded public check with the corrected NJ
quarter-mile profile: provider_before=161, records_valid=161, provider_after=161,
distinct_parcels=161, duplicate_parcel_rows=0, read_only=true,
production_anchor_verified=false, production_qualified=false and publisher
freshness unknown. Scope SHA256:
`0ce7efcfbd438fe61095767aca8099ed941acf1507425927e107753732d2988a`.
This integration made no public network calls and did not independently rerun it.

The parent ties that query to historical Cherry Hill case 22-P-0043, with an
engineering review dated July 25, 2023, block133.01/lot7 and a unique current
PROP_LOC lookup. Application filing date is unknown. That 2023 evidence does
not establish 2023-to-current parcel continuity, a current retail anchor, a sale
listing, deployed ingestion or 161 rows of live tenant inventory.
The one-mile count was 4,587, above the unchanged 2,000-row cap: it was held
without fetching record pages. Quarter-mile support changes the minimum to the
existing product minimum; it does not raise maximum radius or record budget.
The parent is recording the full source receipt separately.

Historical SF direct source/canary observations and operational worker receipts
are imported as dated documentation. None grants new source activation, publisher
reuse rights, production configuration changes or a new live-coverage claim.

## Source and Authorization Proof

Catalog, service, health, recurring worker and nearby helper bytes match the final
3d8c7fd source. The qualifier and inherited worker/profile safety tests were
likewise transferred from that reviewed source. Source-creation/run calls in
both new ingestion integrations use release's existing internal_operator fixture.
No app/routes, app/schemas, auth dependencies, app/config.py, app/main.py, src/,
investment implementation/reference, conftest or candidate catalog was changed
from5ff111f. No root frontier/research/MarketSignals or unrelated dirty files were
included. The original investment-area-live worktree remained clean.

The destination adds dedicated poison tests for main/stage/freshness canary
pages and invalid allowlist configuration before transport. These intentionally
go beyond root's acknowledged dedicated-probe coverage gap. They and the
release's owner-only denial/tenant tests passed in the destination full suite.
No owner credentials or production tenant identifiers were used.

The final root receipt is2,453passed/70skipped in293.59s; destination is
2,472passed/69skipped in301.65s. These counts are not interchangeable: release
base5ff111f includes additional privacy tests and a different test set than the
research root. No skipped case is counted as database/RLS acceptance.

Final documentation includes the November11 NJ retail/radius receipt and
ingestion architecture contract from3d8c7fd. The November10 South Jersey
qualification is preserved as history with an explicit superseding privacy/
quarter-mile notice, so its older mailing projection cannot be treated as the
current contract. The requested-market queue and other source-qualification
notes remain qualification records, not activation manifests.
The engineering-review versus filing-date clarification above is a parent-reviewed
documentation correction to the imported source receipt, not a new source claim.

## Remaining Gates

Local commit is authorized after the completed checks. Parent reviews the final
worktree/checkpoint before requesting publishing approval. Preserve all
source/privacy limits; no push, PR, merge or deployment is authorized.

Source activation, any old-URL SF tenant-source migration, worker image/task/
schedule changes, production writes/migrations, API/frontend deployment,
publisher inquiries and paid/model calls remain outside this integration.
Keep existing Ocala schedules untouched; later worker rollout must preserve their
accepted context contract. Actual scheduled reconciliation, tenant map/browser
acceptance and real-anchor review remain separate required evidence.
