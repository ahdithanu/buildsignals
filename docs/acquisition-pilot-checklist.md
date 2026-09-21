# Acquisition pilot checklist

## Local implementation, not deployed

### Cross-service acquisition regression (2026-09-21)

The authenticated nearby-parcel promotion test now follows a pre-approval permit's
source and lifecycle evidence, runs the ranked nearby search, shortlists a
candidate, promotes it into a saved opportunity, reloads its parcel graph, screens
the saved deal, and retrieves the exact persisted screening export. It explicitly
asserts that assessor value and nearby retail activity do not establish asking
price, building area, vintage, asset configuration, occupancy, or lease terms.
Only the recorded city/state passes; unestablished facts stay unknown.

A second integrated test uses real JWT authentication and persisted membership
roles, rather than an authentication override, for parcel-reference review.
Viewers can inspect evidence but cannot accept it; editors can accept, reload the
permit, and recover both source snapshot IDs, reviewer identity, and verification
time from the graph relationship. Changing active tenant denies reads and review
writes. Acceptance does not copy parcel coordinates into the permit.

All 51 nearby-search, parcel-reference/review/audit, and screening-export tests
pass, as do focused lint and whitespace checks. These are synthetic local
regressions, not qualified Columbus inventory, source licensing, real-market
match measurements, or production/browser acceptance. The review fixture has
distinct permit and parcel evidence; the legacy nearby fixture remains simplified
and cannot establish source qualification. Real-record workflow gates stay open.

### Persisted acquisition-screen history API (2026-09-21)

Each successful acquisition-screen export now saves its exact JSON bytes, SHA-256,
deal, tenant, author, and UTC creation time in `acquisition_screen_snapshots`.
The snapshot and export audit commit in the same transaction before delivery.
The export response includes `X-Acquisition-Snapshot-Id`. Historical snapshots
preserve the criteria, recorded values, unknowns, method version, and limitations
that were actually exported; subsequent changes to deal facts do not rewrite them.
There is no backfill from old audit hashes because those cannot recover old facts.

Authenticated tenant members can list metadata at
`GET /deals/{deal_id}/acquisition-screen/history` (default 20, maximum 100, offset
pagination with `has_more`) and retrieve the exact document at
`GET /deals/{deal_id}/acquisition-screen/history/{snapshot_id}`. Both require an
active deal and use no-store; cross-tenant and deleted-deal requests return 404.
Corrupted content fails its hash check instead of being returned. Editors/admins
may create new snapshots through export; viewers may read existing snapshots.
No application update/delete endpoint exists. This is application-append-only
history, not database-level WORM storage or independent evidence verification.
Organization portability and erasure include these rows.

Migration `20260921_0001` enables and forces PostgreSQL tenant RLS and adds a
tenant/deal/time index. Local SQLite and restricted-role PostgreSQL upgrade,
downgrade, and re-upgrade pass. Thirty-seven screening/criteria/export tests passed
before the additional portability regression; the final export/history suite has
three passing tests. Twelve existing portability/erasure tests and eleven real
PostgreSQL isolation tests pass. Focused lint and whitespace checks pass.

Browser integration now provides expandable screening history, ten-row pages,
timestamps, snapshot identifiers, and authenticated downloads of the saved bytes.
History loads only when expanded; new exports invalidate the current tenant/user/
deal history. Scope changes reset the panel and suppress delivery of an in-flight
historical download from the prior scope. Loading, empty, failed-request, and
download-error states remain distinct. Viewers can retrieve existing snapshots
without gaining permission to create new ones.

Verification: all 277 frontend tests across 59 files pass, including history
pagination, error/retry, and tenant-switch download regressions. Two real-local-API
Playwright workflows pass at 1440px and 390px: exported bytes exactly match the
historical download, history survives reload, and a second export refreshes the
open list. Both screenshots were inspected and horizontal overflow checks pass.
Application TypeScript, focused lint, and production build pass; the existing
large-bundle warning remains. No production migration or release was performed.
Parcel-source qualification and source-backed rent-roll, lease, and capex inputs
remain separate open gates. History is a downloadable snapshot archive, not an
in-browser underwriting comparison or independently verified acquisition example.

### Integrated regression and release-preflight repair (2026-09-21)

The broad backend run initially found nine failures: five onboarding tests and
four rollout/worker checks. All traced to a stale catalog manifest after local
commit `c04f8f0`: Columbus site-stage handling added `Approved`, and the commercial
permit freshness contract corrected `filing_event_at` to `record_updated_at`.
Reconstructing the catalog before that commit exactly reproduces the checked-in
manifest. Comparing generated manifests changes only `catalog_fingerprint` and
`manifest_digest`; hosts, source membership, waves, shards, and candidate scope
are unchanged.

The local manifest and three local Render digest pins now match those existing
catalog corrections. No source settings, runtime enrollment, paid service, or
production environment was changed during this repair. This is a release
candidate configuration repair, not production activation or release approval.
The fail-closed guard remains intact; regression tests verify that changed
freshness settings invalidate a prior manifest even when hosts are unchanged.

Verification: full backend rerun passes 1,162 tests with 12 skips; the final
focused rollout/onboarding run passes 23 tests, including one further regression
added after full-suite collection. Ten PostgreSQL RLS tests were verified
separately as recorded below, not in this SQLite run. Frontend regression passes
273 tests across 58 files, all nine real-local-API Playwright workflows pass, and
the production frontend build passes with the existing large-bundle warning.
Focused lint and whitespace checks pass. These receipts do not validate live
inventory, county source-use rights, production restoration, or deployment.

Next substantive gates remain qualified parcel evidence and the real acquisition
workflow, persisted screening history, and source-backed diligence inputs.
Production diagnostics and any release still require their separate live gates.

- [x] Scope acquisition-radar browser cache by organization and user; defer reads
  until authentication is available. Regression tests verify organization changes,
  same-organization user changes, and logout hide the previous result immediately.
  This is client-cache hardening, not a substitute for database tenant isolation.
- [x] Nearby-search history/results now use organization/user cache namespaces.
  Creating, reviewing, assigning, and promoting parcel results invalidate the
  current workspace's radar/readiness queries so returning to the map does not
  reuse stale ranked results. Focused hook tests cover creation, review,
  assignment, unauthenticated loading, and workspace changes. Live source-backed
  parcel acceptance and production browser verification remain separate gates.

- [x] Empty-map workspace diagnostics: authenticated tenant-scoped active permit,
  coordinate-bearing permit, active parcel, coordinate-bearing parcel, and saved
  search counts. Invalid geographic ranges excluded. Failed requests are not zeros.
- [ ] Verify these diagnostics against the authenticated production workspace.
- [x] Replace schematic acquisition grid with Leaflet geographic maps and an
  independent geocoded permit/planning layer. Parcel ranking still requires saved
  searches. Verified desktop/mobile with synthetic test data, not live inventory.
- [ ] Qualify a pilot-market parcel source, identifier namespace, and use rights.
  Columbus CSIR query returned 403. A separate Franklin County public sample
  succeeded: eight distinct IDs matched after a hypothesized hyphen mapping,
  but only two of ten permit street addresses matched. City/state corroboration,
  source rights, acreage semantics, and freshness remain unqualified. See
  parcel-reference-resolution.md. Historical intake is still local only.
  The offline qualification CLI now records input hashes and separate permit /
  distinct-reference counts, with 24 passing tests. It does not acquire evidence
  or make the provisional namespace production-eligible.
- [ ] Verify evidence-backed signal to nearby candidate workflow in that market.
- [x] Add structured multifamily and small-bay retail buy-box criteria with
  pass/fail/unknown results, provenance, and missing-diligence reasons.
  Initial read-only screening is implemented on opportunity details. Price,
  units/area, vintage, and an explicitly selected city/state compare saved deal
  fields against versioned user-requested defaults. Asset configuration and
  retail diligence remain unknown. Field references are traceable inputs, not
  independently verified evidence. Persisted structured criteria now have an API
  foundation, creation and selection UI, and persisted downloadable screening
  history verified on mobile and desktop.
- [ ] Add source-backed rent-roll/lease/capex diligence inputs. Current field
  references identify recorded deal inputs, not independently verified documents.
- [ ] Verify source evidence, project timeline, nearby parcels, saved opportunity,
  and export on mobile and desktop with real qualified records.
- [ ] Release and measure live inventory, freshness, and source-specific coverage.

## Interpretation

GET /acquisition-map/readiness is read-only, authenticated, and no-store. Counts
are workspace-wide and not a snapshot transaction, geographic coverage measure,
search eligibility guarantee, unique-project count, or for-sale inventory. Valid
coordinate ranges do not independently establish geocoding accuracy. Saved
search counts include historical searches; no absence of commercial opportunity
can be inferred from an empty ranked candidate list.

## Geographic map contract

GET /acquisition-map/signals requires authentication and returns no-store,
tenant-scoped records independent of nearby searches. Each layer is capped at
100 records, ordered by canonical update time and ID, with explicit truncation.
Optional two-letter state filtering narrows the query. Permit retirement is
respected. Null/out-of-range coordinates are omitted; the map uses a conservative
Web Mercator latitude range of -85 to 85. Records are not unique projects or
confirmed brand expansions. Evidence IDs and original source links remain visible.
Planning links now open /planning?record_id=... and retrieve the exact tenant-visible
event through the existing detail endpoint, independently of first-page list
limits. Its evidence, company matches, and source details use the existing
planning record presentation. A missing or failed detail request remains an error,
not a silent fallback to unrelated records. Explicit browsing clears record focus.
Planning browser-cache keys include organization and user identity.

Leaflet is lazy-loaded. OpenStreetMap raster tiles load only for the visible map,
with attribution and an origin referrer. There is no bulk fetch or offline cache.
Tile failures show a notice without hiding source records. Public tiles have no
SLA: before a larger paid rollout, select a suitably licensed managed tile service.
See https://operations.osmfoundation.org/policies/tiles/ and
https://leafletjs.com/reference.html for the basemap policy and library reference.

Remaining pilot gaps: production counts and auth verification, qualified nearby
parcel inventory, reliable geocoding, reviewed brand relevance, richer geography
filters/pagination, and unified signal-to-parcel selection. Two maps currently
separate source-record geography from saved ranked parcel results.

## Initial acquisition screening

### PostgreSQL criteria qualification (2026-09-21)

Migration 20260920_0001 now passes upgrade, downgrade, and re-upgrade on a fresh
disposable PostgreSQL cluster. PostGIS was provisioned by the cluster's test
administrator; migrations and RLS tests ran as a separate NOSUPERUSER NOBYPASSRLS
database owner. Ten PostgreSQL security regressions pass, including a new test
that round-trips structured criteria, asserts ENABLE/FORCE RLS, hides another
tenant's boxes, prevents cross-tenant updates/inserts, and returns no boxes with
an empty tenant context. The server used a local Unix socket only and was stopped
after verification. No production database or account was accessed.

This closes local PostgreSQL migration/isolation qualification for the criteria
column, not production restore evidence, actual deployment, or real parcel data.

### Browser buy-box creation (2026-09-20 evening)

Editors/admins can now create structured acquisition buy boxes directly in the
opportunity screen. The form offers multifamily/retail defaults and custom market,
price range, units/SF range, and minimum construction year. Required fields,
finite positive values, integer counts/years, and ordered ranges are checked
before submission; server validation and role enforcement remain authoritative.
Failed saves preserve the entered criteria. Successful saves select the persisted
box and refresh the organization/user-scoped list. Existing boxes are not edited
or replaced, and submitting is disabled while a request is in flight.

Seven focused UI tests pass. Both real-API desktop/mobile workflows now create
the box through the UI, validate range errors and profile defaults, reload, select
the stored box, and inspect its exported snapshot. Form screenshots at 1440px and
390px were inspected and overflow checks passed. TypeScript and focused lint pass.
The tests use synthetic local deals, not live inventory. Editing/deleting boxes,
screening history, PostgreSQL migration qualification, and production release
remain outstanding.

### Saved criteria selection (2026-09-20 evening)

The opportunity panel now lists structured saved buy boxes from the authenticated
workspace, excluding legacy unstructured boxes. Selecting one sends buy_box_id
to screening and export, hides the competing default profile/market controls,
and retains the selected identifier when list refresh fails rather than silently
screening against defaults. The list is capped at 200 and labels that limit.
Browser query keys include organization/user identity; the screening panel
remounts on organization, user, or deal changes to clear previous selection.
No localStorage persistence or cross-workspace preferences are introduced.

Five focused UI tests and both real-local-API Playwright workflows pass. The
browser workflows create a persisted box via API, reload, select it, verify
custom thresholds, and inspect the downloaded criteria snapshot at 1440px and
390px with no horizontal overflow. TypeScript and focused lint pass. Browser
creation/editing, pagination beyond the bounded list, and screening history are
still pending. This does not qualify real parcel sources or production records.

### Persisted criteria API foundation (2026-09-20)

Migration `20260920_0001` adds nullable structured acquisition criteria to the
existing tenant-scoped buy_boxes table (existing RLS policy retained). POST
/buy-box accepts a versioned acquisition_criteria object: profile, city/state,
price bounds, size bounds (units for multifamily, SF for retail), and minimum
construction year. Creator user ID and creation time are retained. Validation
rejects blank cities, nonfinite prices, reversed ranges, invalid profiles, and
unknown keys. Existing legacy boxes remain readable and unchanged.

GET /deals/{id}/acquisition-screen and POST /deals/{id}/acquisition-screen/export
accept buy_box_id. Both scope it to the current tenant, use the saved criteria
instead of caller-supplied profile/market defaults, and return the exact criteria
snapshot and buy-box identifier. Legacy boxes without structured criteria return
422 rather than silently applying defaults. Structured boxes are excluded from
the legacy numeric match-score endpoint: unresolved diligence must not become a
legacy fit score. Method acquisition-screen-v3 records this criteria behavior.

Thirty-six focused backend tests pass, covering persistence, tenant isolation,
role restrictions, custom thresholds, legacy behavior, and export snapshots.
SQLite upgrade/downgrade/re-upgrade passed in a disposable database. PostgreSQL
migration verification, browser creation/selection, and persisted screening
history remain pending. No production migration or deployment was performed.

### Incomplete-input screening (2026-09-20)

Method `acquisition-screen-v2` trims location components before deciding whether
the target and deal locations are present. Whitespace-only city/state values
are unknown, never matches or mismatches. Numeric criteria reject booleans,
strings, and nonfinite/nonpositive values as unknown while retaining support for
database Decimal prices. Recorded criteria and thresholds are unchanged. The
method version is retained in downloaded snapshots and export audit receipts.
Twenty-seven screening/export backend tests pass, including blank locations,
case/whitespace normalization, unusable numbers, and Decimal prices. This does
not add source verification or complete persisted custom screening criteria.

### Unknown financial outputs (2026-09-20)

The deal API adapter now preserves missing/nonfinite underwriting outputs as
null rather than fabricating zero NOI, IRR, equity multiple, or cash-on-cash.
Deal details, inbox, dashboard, pipeline, and memo summaries display those
values as Not calculated. Actual finite zero and negative results are retained;
percentage outputs still convert ratios to percentage points. This changes
presentation of missing results, not underwriting assumptions or calculations,
and does not independently verify existing financial outputs.

Verification: 269 frontend tests pass, including 15 new mapping regressions;
the two real-local-API acquisition workflows pass at desktop/mobile sizes and
assert four unknown financial metrics. Mobile screenshot inspected. Application
TypeScript passes; focused lint reports no errors and two existing warnings.

### Downloadable screening snapshot (2026-09-20)

Opportunity screening now has a download control for editors/admins.
`POST /deals/{deal_id}/acquisition-screen/export` produces a JSON snapshot using
the applied profile and target market, current tenant-visible active deal facts,
criterion pass/fail/unknown results, field-level basis, method version, UTC
generation time, and explicit unverified-evidence limitations. It does not export
raw parcel evidence, ownership, or geometry. The download is no-store. Viewer,
unauthenticated, cross-tenant, and deleted-deal access is rejected. A committed
audit entry records the actor, method, profile, counts, timestamp, and SHA-256 of
the exact response bytes before delivery.

This is an export-time snapshot, not persisted screening history or a guarantee
that facts did not change after the on-screen query. Source-backed underwriting
and custom criteria remain pending. Verification: 13 focused backend tests,
three UI tests, and two real-API Playwright workflows at 1440px and 390px pass;
the browser workflows inspect downloaded content and verify unknowns and market
selection are retained. TypeScript and focused lint pass. No production release
or real market records were used in these tests.

GET /deals/{deal_id}/acquisition-screen requires authentication, tenant-scopes
the active deal, and returns no-store. Profile choices are small_multifamily and
small_bay_retail. Missing/nonpositive/nonfinite numeric inputs are unknown, not
failed criteria. Any explicit failure yields outside_buy_box; otherwise missing
diligence yields needs_diligence. No investment score or recommendation is issued.
Market matching requires exact city and state rather than substring matching.
The existing legacy buy-box matcher is unchanged for compatibility. New criteria
are a preliminary separate view, not a completed underwriting or source-verification
workflow. The panel's profile and target market selection are not yet persisted;
saved criteria can now be selected in the panel but selection itself resets on reload.

### Local browser qualification (2026-09-20)

`e2e/tests/acquisition-screen.spec.ts` passes at 1440x1000 and 390x844 using
fresh migrated SQLite databases, real local authentication, deal creation, and
screening API responses (not mocked screening payloads). The checks cover profile
switching, incomplete state validation, matching and nonmatching target cities,
no-store responses, explicit unknown occupancy, and no horizontal page overflow.
Desktop and mobile screenshots were inspected. Fixtures are artificial test
deals, not ingested projects or proof of market coverage. This closes the initial
screening panel's local browser verification gap, not the qualified live-record
signal-to-parcel workflow or PostgreSQL production acceptance.

### Integrated regression pass (2026-09-20)

After the map, evidence navigation, screening, and parcel-cache changes:

- All 252 frontend tests across 55 files pass.
- All nine configured Playwright workflows pass against the real disposable local
  API/database, including login/logout, rejected passwords, deal creation,
  desktop/mobile screening, activity presentation, and measured empty inventory.
- Forty-four focused backend tests pass for parcel reference resolution, audit,
  reviewed acceptance, map diagnostics/signals, and acquisition screening.
- TypeScript and focused lint checks pass.

The broad run exposed two test-harness regressions: Node's unavailable file-backed
localStorage shadowed browser storage in the auth suite, and the legacy wireframe
test did not isolate the newly added query-driven map. Tests now explicitly use
isolated JSDOM Storage and isolate the separately tested map components. Existing
router-future and some asynchronous-test warnings remain. These results do not
claim nationwide ingestion, production restore qualification, or PostgreSQL RLS
acceptance; source qualification and production validation remain open.
