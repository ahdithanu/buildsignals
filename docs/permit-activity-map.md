# Consistent Permit Activity Map

## Contract

Bare `/map` opens one all-state permit-activity view. Stored permit counts, not
the first page, parcel inventory, source configuration or selected records, color
the states. A state filter is explicit and URL-backed. Clicking the main Map
navigation again clears filters; refresh or new login at `/map` has the same
default. Explicit filtered links remain shareable.

The national choropleth includes permits without coordinates. State drilldown
adds geographic density for all eligible coordinate-bearing permits, aggregated
in SQL with a bounded response. Unmapped records remain counted and available;
they are not assigned fabricated locations. Counts are filings, not unique
projects, recent growth, market completeness, openings or properties for sale.

## Design

One dominant map, compact controls, actual counts and an accessible state list.
National state shapes use D3's Albers USA composite projection with Alaska and
Hawaii insets; state detail uses the existing Leaflet/OpenStreetMap stack.
No automatic location detection, record-driven default extent, first-page map
sampling or viewport resets on background refresh. Inventory and parcel tools
remain separate explicit views. Loading, error, zero inventory and unmapped-only
states are distinct. No internal source or scheduler diagnostics are exposed.

## Cartographic Asset

The bundled outlines are Census Bureau 2018 cartographic boundaries, 1:20m,
for small-scale thematic mapping, not current legal/parcel boundaries. Only
50 states plus DC and their names/codes/geometry are retained; all activity
values come from tenant inventory. No population or invented density is bundled.

Source: https://www2.census.gov/geo/tiger/GENZ2018/shp/cb_2018_us_state_20m.zip

Archive SHA-256: `95902e4cda23f5f403e576d1bcd0e54a0f453d9b81893b080f4c15029302e348`

Regenerate with optional conversion tool `pyshp==2.3.1`:

```sh
python scripts/build_state_boundaries.py /absolute/path/cb_2018_us_state_20m.zip src/data/us-state-boundaries.json
```

This generates only a display asset. It opens no database or network connection
and does not activate an ingestion source. Implementation and verification are
local until a separately approved staged release is accepted.

## Verification

The dedicated actual-API browser test owns a disposable SQLite database seeded
through normal ingestion with 350 explicitly synthetic permits in four states,
including one state with no locations. These are test fixtures, not inventory.
All external requests (including optional basemap tiles) are blocked. It checks
national geometry/pixels, exact counts beyond 100 records, keyboard drilldown,
mobile layout, stable refresh/pan, main navigation, URL history and reload.

```sh
RUN_PERMIT_ACTIVITY_MAP_E2E=1 OPENROUTER_API_KEY= REDIS_URL= \
E2E_API_PORT=8151 E2E_WEB_PORT=8152 \
npm run e2e -- e2e/tests/permit-activity-map.spec.ts
```

CI runs this explicitly; the ordinary baseline run skips fixture-specific tests.
Hosted CI and production acceptance are separate gates, not implied by local tests.

## API And Isolation

`GET /acquisition-map/coverage?kind=permit&limit=100&offset=0` supplies the national
view. Its permit groups, headline totals and pagination share one SQL statement
snapshot, so concurrent ingestion cannot split them. The API's separate `states`
field still describes all record kinds for existing inventory clients; the permit
map deliberately uses `groups`, not that field.

`GET /acquisition-map/permit-density?state=TX` aggregates the selected state's
eligible current records. It returns at most 2,048 grid cells, adapting resolution
from 0.025 through 8 degrees without dropping records. Each complete result comes
from one statement snapshot, with exact cell/mapped/unmapped/provenance count
reconciliation. At most nine bounded aggregate queries are attempted; response
size bounds are not a promise of constant database work at unlimited inventory.

Both APIs authenticate, use tenant-scoped queries plus existing PostgreSQL RLS,
disable response caching, and perform no writes, source requests or model calls.
Only these two audited aggregate GET paths are added to the demo allowlist;
record-list, export and write APIs remain denied. No new environment variable,
database migration, permission grant or ingestion job is introduced.

## Release Gate

This is local implementation and verification, not a deployed fix. Publication,
green hosted checks, merge and a staged API-first/frontend release need fresh
applicable approval. Release the compatible aggregate API before the frontend;
old clients remain supported. Verify real workspace totals, national/default
entry, selected-state density, refresh and isolation before claiming it live.
Do not bundle the separate SF native-location or Wake qualification branches,
repeat consumed intake tasks, or send the Cherry Hill inquiry.

## Local Acceptance Receipt

Runtime checkpoint `8c47870`, not published or live:
- Frontend608passed; focused map/demo/concurrency/nonowner PostgreSQL142passed.
- Baseline browser19passed/20fixture-specific skips; dedicated actual-API
  desktop/mobile framing2passed and built strict-local-CSP2passed, zero retries.
- Build/typecheck/scoped ESLint/Ruff/schema-drift/harness and independent review pass.
- Full backend3468passed,1existing test failed because its migration DDL requires
  table ownership while the map acceptance role deliberately has none.
  `test_migration_downgrade_upgrade_operations_are_transactionally_rolled_back`
  separately passed unchanged on a different fresh restricted DDL-owner target;
  FORCE RLS and rollback restoration were verified. Coverage91.59%,3warnings.
  This is not a single all-green full-suite claim. Hosted CI remains unverified.

The final built browser test waits for rendered geometry before measuring it;
all51 shape, pixel and framing assertions remain. Production counts and CSP
enforcement were not inferred from synthetic browser fixtures or local checks.
