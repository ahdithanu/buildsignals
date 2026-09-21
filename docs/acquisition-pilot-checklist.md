# Acquisition pilot checklist

## Local implementation, not deployed

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
- [ ] Add structured multifamily and small-bay retail buy-box criteria with
  pass/fail/unknown results, provenance, and missing-diligence reasons.
  Initial read-only screening is implemented on opportunity details. Price,
  units/area, vintage, and an explicitly selected city/state compare saved deal
  fields against versioned user-requested defaults. Asset configuration and
  retail diligence remain unknown. Field references are traceable inputs, not
  independently verified evidence. Still pending: persisted custom criteria,
  source-backed rent-roll/lease/capex inputs, and saved screening history.
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
workflow. The profile and target market selection are not yet persisted.

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
