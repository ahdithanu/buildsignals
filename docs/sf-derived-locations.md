# SF Derived Locations

## State And Boundary

Implemented locally on `codex/sf-map-qualification`, based on the verified SF
ingestion release and its receipt. Production SF collection has 6,711 source
records; its last production audit measured zero coordinates. This development
does not change that receipt or claim new live map coverage.

The user approved qualification of up to 20 public SF addresses / 1,000 filing
rows, geocoder transmission, a bounded derived-data backfill and merge/API/map
release after checks. This is not approval for a larger backfill, migration,
paid-service upgrade or NJ activation. Existing recurring ingestion stays enabled.
Production qualification and release receipts must be recorded separately below;
local verification is not live map acceptance.

## Contract

- `app/services/sf_geocoding.py` validates one unambiguous Census match for the
  current tenant's active, canonical SF building source only. Demo identities,
  foreign sources, missing addresses, non-SF city/state/ZIP, conflicting streets,
  non-finite coordinates and out-of-bounds points fail closed.
- The conservative geographic scope is mainland SF: latitude 37.70..37.84,
  longitude -122.53..-122.35, ZIP 941xx. It is not a complete county-boundary
  classifier; excluded or unresolved addresses remain unknown, not guessed.
- Source coordinates, permit identities and raw evidence are never overwritten.
  A `PermitGeocode` row holds the current address hash, match, coordinate,
  benchmark, response hash and observation time. The stored provider URL is the
  bare endpoint, not an address-bearing query string.
- This is a mutable current-location row, not an immutable archive of every
  geocoder response. The raw filing evidence remains independent and unchanged.
- Matches are street-range estimates, not surveyed parcel locations, parcel
  boundaries, confirmed expansion or sale availability. The Census service
  describes interpolated/approximated address-range coordinates.
- `Public_AR_Current` is a mutable provider benchmark alias. The observation
  time and response hash support comparison, not exact future reproduction of
  an unavailable provider response or independent proof of positional accuracy.
- Source-provided coordinates take precedence. Partial or invalid source
  coordinates are held rather than silently replaced. Address changes invalidate
  derived points automatically. A 90-day maximum age and five-minute clock-skew
  allowance are conservative application policies, not a publisher SLA.

## Bounded Operator Worker

`scripts/backfill_sf_geocode.py` defaults to a read-only plan: no provider calls,
sleeps, commits or source activation. It requires an explicit active non-demo
organization and already-registered reviewed SF source. Example, after confirming
the database target is disposable/local or separately authorized:

```sh
python -m scripts.backfill_sf_geocode --organization-id CONFIRMED_WORKSPACE_ID --limit 20
```

Only after applicable approval, execution requires all three explicit flags:

```sh
python -m scripts.backfill_sf_geocode --organization-id CONFIRMED_WORKSPACE_ID \
  --limit 20 --scan-limit 1000 --execute \
  --confirm-address-transmission --confirm-derived-writes
```

The maximum is 200 distinct address queries and 5,000 scanned filing rows per
invocation; defaults are 20 / 1,000. A source-scoped permit-ID cursor continues
bounded scans without loading the entire workspace. Cursors are internal operator
metadata, not public demo artifacts. Receipts distinguish planned, partial,
completed and provider-error states; partial is not a completed full backfill.

The existing pinned HTTPS client permits only `geocoding.geo.census.gov`, has a
12-second timeout, 65,536-byte response cap and zero configured transient retries.
Attempts are spaced by one second, repeated literal request addresses are cached,
and provider/access errors stop the batch. Logical address-attempt counts are not
wire-request counts: the shared client bounds same-host redirects and IP failover.
Cross-host redirects and unsafe hosts remain blocked. Receipts contain counters
and error types, not addresses, request URLs, provider bodies or exception text.
The worker refreshes permits and source configuration before persisting a match.

## Map Integration

`SF_DERIVED_LOCATIONS_ENABLED=false` by default. This flag controls read-only map
and readiness use of stored evidence; it does not authorize or perform geocoding.
Eligibility is filtered before pagination, including current address hash,
tenant/source identity, provenance, coordinate bounds and age. PostgreSQL uses
native SHA256; SQLite registers an equivalent function on the local connection.
No database function, extension or new migration is introduced.

Native and derived permit counts are separate. No geocoder response, benchmark,
match text, address hash or geocoder URL is added to customer map responses.
Existing public-record evidence citations and required attribution are retained;
private source operations remain owner-only. The map explicitly labels estimates
and does not add a geocoding API route or weaken demo write restrictions.

## Parcel Gap

SF block/lot references are source-specific strings, not resolved APNs. No SF
parcel profile is currently admitted. Preserve zeros and suffixes; do not assume
removing the separator produces `blklot`, or that `mapblklot` groups one title.
Missing block or lot components need an explicit hold. Geocoding or a nearest
parcel result never constitutes reviewed parcel identity or for-sale evidence.
The existing nearby-search service still requires a confirmed retailer signal
with source coordinates; derived map display does not automatically enable it.

## Verification

Current receipts: 51 offline core/worker tests and 7 real restricted-role
PostgreSQL hash/map/RLS tests passed. Full backend with all PostgreSQL gates:
2,625 passed, no skips, three existing geography-reflection warnings, 347.22s.
Final frontend: 428 tests / 73 files passed in 4.67s. Typecheck and build passed. The build emits
existing dependency-annotation and large-chunk warnings; it is not warning-free.
Ruff and whitespace checks passed. All tests use synthetic data; no geocoder
ground truth or live match-quality rate has been measured.

Final real-API Chromium suite: 21 passed, zero skips/failures/flaky cases, 45.345s,
with RUN_SF_MAP_E2E=1 and RUN_LIVE_INVESTMENT_AREAS=1. SF desktop1440/mobile390
screenshots and marker pixels were inspected. External map tiles/fonts are
deliberately blocked: this verifies the visible marker and unavailable-background
state, not live basemap delivery. No page errors, unexpected external hosts or
downloads in the SF journey. Owner/customer/demo boundaries pass. The nearby
workflow does not imply that derived points are source-coordinate anchors.
Disposable restricted-role PostgreSQL Alembic check: no new upgrade operations.
No production migrations were run. A local green suite is not production acceptance.

Reproduce locally using the isolated PostgreSQL setup from CI and e2e/README.md:

```sh
OPENROUTER_API_KEY= python -m pytest tests -q --tb=short
npm test -- --run
npm run typecheck
npm run build
RUN_SF_MAP_E2E=1 RUN_LIVE_INVESTMENT_AREAS=1 OPENROUTER_API_KEY= \
  npx playwright test -c e2e/playwright.config.ts
```

The backend receipt above supplied TEST_POSTGRES_URL, TEST_EVAL_POSTGRES_URL and
TEST_SCHEMA_RECONCILIATION_POSTGRES_URL to the same disposable restricted-role
database. Without those variables, database skips are not equivalent verification.

## Primary References

- [Census Geocoder API](https://geocoding.geo.census.gov/geocoder/Geocoding_Services_API.html)
- [Census geocoder precision and limits](https://www.census.gov/programs-surveys/geography/technical-documentation/complete-technical-documentation/census-geocoder.html)
- [PostgreSQL 16 native SHA256/encoding](https://www.postgresql.org/docs/16/functions-binarystring.html)
