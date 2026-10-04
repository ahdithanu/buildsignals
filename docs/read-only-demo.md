# Read-Only Historical Demo

## PR Description

Branch: `codex/read-only-demo`, based on the existing local temporal/acquisition
work at `14f17bc`. That base has earlier unreleased work; this branch does not
authorize publishing those changes. No production setting, migration, source
activation, push, merge, or deployment was performed for this implementation.

Adds one-click entry from the sign-in page into a bounded, read-only product
workspace. Visitors can navigate Overview, Filings, Graph, Parcels, and Map,
including historical records, source links, lifecycle evidence, and graph
relationships without signup or a password. The bounded graph explorer
traces reported companies, properties, and parcel references to other filings
with separate source evidence. The Graph tab starts from a bounded, source-backed
multi-record entity where one exists, ranked by linked source-record count; this is
a shared-reference investigation lead, not a verified project, brand, or owner.
The activity selector counts canonical source records, not unique projects.
Parcel path lists show one representative path per reported number and address
while retaining both relationship evidence items.
Canvas edges show direct relationships from the selected filing. Parcel-reference
mode follows the additional source-backed property-to-parcel edge and lists
other filing paths through reported properties; it does not assert a qualified
parcel identity or boundary. The monthly filed/issued chart counts historical
source dates only; it is not an AI prediction, live trend, or verified corporate
expansion signal. Settings, write controls, exports, and non-demo routes are
unavailable. Ordinary customers retain their existing
application and authentication flow. The login subtitle and site descriptions
use the requested development-intelligence wording.
The overview describes the populated source-filing, graph, parcel-reference,
and qualified-location surfaces while explicitly saying the demo does not claim
live planning coverage, confirmed brand expansions, verified for-sale listings,
or ranked nearby acquisition candidates.
It now also shows an acquisition-workflow readiness panel that translates the
demo into the product promise: signal intake, evidence graph context, mapped
locations, and parcel-candidate readiness. Each tile is labeled as ready,
review-needed, or needing qualified source data so the demo can explain where
BuildSignals is actionable today without fabricating parcel inventory or
for-sale claims.

## Security Boundaries

- `POST /v1/auth/demo` accepts no identity inputs. It resolves only fixed demo
  user/organization IDs and requires their existing viewer membership. Unexpected
  body properties are rejected. The disabled endpoint returns 404.
- Demo access JWTs expire after 60 minutes and contain `demo=true` and
  `read_only=true`. No refresh token is issued; an old refresh cookie is cleared.
  Access tokens remain in memory, so a reload requires another demo click.
- The demo user uses the invalid password sentinel `!nologin`, has no MFA, and
  cannot use password login, password recovery, or refresh. Ordinary access
  tokens naming the reserved demo identity/tenant are rejected.
- Central auth middleware rejects all demo mutations except logout. Reads are
  deny-by-default, with exact audited patterns for profile, summary, bounded
  parcel-reference pages, map locations, permit pages/details and individual
  graph evidence. New routes are blocked
  automatically. Settings, users, invites, API keys, billing, organization
  management, raw data, and export/download endpoints are not in the allowlist.
- PostgreSQL retains `app.current_org` transaction scoping and existing forced
  RLS policies. Every demo ORM transaction is also `READ ONLY`; even direct SQL
  writes fail. An ORM flush guard also applies on SQLite. SQLite is not proof of
  RLS; the separate restricted-role PostgreSQL integration test supplies that.
- Explicit invalid/expired credentials on protected routes return 401 even in
  permissive local development; they cannot fall back into the default
  organization. Public endpoints retain their own authentication, including the
  monitoring endpoint's separate bearer-token scheme.
- Entry is limited to 10 sessions per server-resolved client IP per minute using
  the existing limiter (Redis when configured, process-local fallback otherwise).
  Deploy behind a correctly configured trusted proxy; arbitrary client-provided
  `X-Forwarded-For` is not used by this endpoint. Multi-worker shared enforcement
  requires the existing Redis configuration. Existing global request limits apply.
- Demo responses are not cacheable. `DEMO_ENABLED=false` also invalidates access
  to previously issued demo tokens. Small paginated reads are not an anti-scraping
  guarantee; anything visible in a public demo is intentionally public.

## Configuration And Seed

New environment variable: `DEMO_ENABLED`, default `false`, server-side only.
The frontend checks `GET /v1/auth/demo`; failures hide the button. No Vite demo
flag or secret is needed. Do not enable the flag until the seed is verified.

Use a migrated **local** database first. No migration is added by this feature.
The seed never migrates a database and never makes network requests.

```bash
ENVIRONMENT=ci DATABASE_URL=sqlite:////tmp/buildsignals-demo.db \
  .venv/bin/alembic upgrade head
ENVIRONMENT=ci DATABASE_URL=sqlite:////tmp/buildsignals-demo.db \
  .venv/bin/python -m app.services.demo_seed --confirm-demo-seed \
  columbus-commercial-202401-live.db columbus-site-202401-live.db \
  columbus-commercial-202402-live.db columbus-site-202402-live.db \
  columbus-commercial-202403-live.db columbus-site-202403-live.db
```

Inputs are the six existing ignored qualification databases, not files committed
to Git. They are opened read-only. The seed validates the reviewed source keys,
Q1 2024 interval, completed runs, bounded counts and public field allowlists.
It uses existing field mappings, normalization, immutable raw evidence, permit
events, temporal projection, entity resolution, and graph relationships. Original
capture timestamps are retained. A failed cohort rolls back the entire seed.
Sources are inactive/manual, have no ingestion enrollment, and cannot enter the
production scheduler through this command. Repeating the same inputs does not
duplicate identity, permits, raw evidence, events, or graph relationships.

Before a later approved production seed, confirm the destination database, backup,
restricted runtime role, permitted derived public display, and all six inputs.
Run the same command against that explicitly approved database, then enable the
flag and smoke-test the deployed API/frontend together. These are release actions,
not actions performed by this PR.

## Evidence And Scope

The local Q1 replay contains 2,049 source records, not 2,049 unique developments.
The qualification databases were captured in September 2026. They are current
snapshots of historical filings, not reconstructed historical knowledge.
Commercial issuance and site applications have different event semantics.

The graph includes properties, source parcel references, jurisdiction and reported
filing companies. Applicant companies are projected only when the source mapping
explicitly identifies a business/DBA or legal entity. Unknown/person/mixed
semantics are excluded. `permit_applicant` is not an ownership, tenant, retailer
expansion, or beneficial-ownership assertion. This projection uses the shared
pipeline, not a demo-only raw graph insert.

No authoritative parcel geometries, verified nearby candidates, or sale listings
were fabricated. Parcel reference nodes are explicitly labeled unresolved. There
are no coordinates in this narrow cohort. The Map tab shows measured map
readiness and a clearly labeled link to the county's separate public parcel
viewer when it cannot plot source-backed locations. It accepts only valid source
coordinates and source-policy-permitted parcel polygons when such records are
admitted to the demo tenant; it does not turn a source parcel ID into a polygon.
The Parcels tab lists bounded source references and links back to filing evidence.
Full nearby acquisition workflows still require a qualified parcel source, a
reviewed permit-to-parcel join, and permitted boundary display.

## Verification

Tests: `tests/test_demo.py`, `tests/test_demo_postgres.py`,
`e2e/tests/demo.spec.ts`. PostgreSQL tests require `TEST_POSTGRES_URL` pointing
to a migrated, disposable database using a non-superuser, non-BYPASSRLS role.
Never point integration-test variables at production.

```bash
.venv/bin/python -m pytest tests/test_demo.py tests/test_demo_postgres.py -q
PYTHON=.venv/bin/python npm run e2e -- demo.spec.ts
DEMO_TEST_SNAPSHOT_DIR="$PWD" PYTHON=.venv/bin/python npm run e2e -- demo.spec.ts
npm run typecheck
npm test
npm run build
```

Default E2E uses one attributed real public permit record in a disposable database.
The optional snapshot-directory run replays all six real cohorts and asserts
2,049 records through the API. The setting is test-only. E2E owns local ports
8000/8080 and refuses existing servers.

### Local Test Receipts (2026-09-23)

- Full backend suite: 1,243 passed, 15 skipped. Skipped integration tests are
  not evidence of production readiness.
- Final demo, PostgreSQL demo isolation, and monitoring regression selection:
  52 passed, including rejection when the demo identity has no seeded records.
- Separate restricted-role PostgreSQL demo and existing RLS suite: 13 passed.
  This used a disposable local PostgreSQL database, never production.
- Frontend unit suite: 282 passed across 61 files.
- Full Playwright suite: 12 passed. Full-cohort desktop/mobile demo selection:
  2 passed, using all six local historical snapshots and asserting 2,049 records.
- TypeScript typecheck and Vite production build passed. ESLint reported no
  errors and one existing AuthContext fast-refresh warning. The build retains
  the existing large-chunk advisory.
- Repeated full-cohort seed left counts unchanged: 2,049 permits, 2,049 raw
  source records, 2,049 permit events, 4,852 graph entities and 8,115 relationships.
  Graph entities include 745 reported applicant companies and 1,031 unresolved
  parcel references. These are local demo counts, not production coverage.

The local preview is available at `http://localhost:8080/login` while its
development servers are running. Choose **View live demo**. The backend runs on
loopback port 8000 with disposable test configuration, not production secrets.

The expanded overview, parcel-reference, and map endpoints passed 49 focused
backend tests. The map test confirms that permitted geometry is returned and
`parcel_id_only` policy suppresses the same boundary. Full-cohort Playwright
passed the three demo flows at desktop and mobile widths; a subsequent one-record
run passed the same three flows after the no-data map treatment. The parcel
geometry in the backend test is synthetic test input, not demo inventory.
TypeScript checks and the Vite build passed. The current historical cohort still
contains zero mapped parcels and zero coordinate-bearing permits.

### Local derived map locations (2026-09-23)

The map now reads tenant-scoped `permit_geocodes` alongside source-provided
filing coordinates and eligible parcel records. The new table has forced
PostgreSQL RLS. Address estimates are stored separately from immutable permit
source snapshots. A geocode is displayed only while its address/city/state/ZIP
hash still matches the active filing; changed addresses invalidate it. Demo
read-only API calls never contact a geocoder or write data.

For a **disposable local SQLite demo** already seeded with Columbus data, run
`alembic upgrade head`, then explicitly run:

```bash
DATABASE_URL=sqlite:////absolute/path/to/local-demo.db ENVIRONMENT=ci \
  .venv/bin/python -m scripts.geocode_demo_filings --confirm-local-demo --limit 12
```

The command is capped at 25 distinct addresses per invocation, sends only
Columbus/OH addresses with five-digit ZIPs to the [public Census Geocoder](https://geocoding.geo.census.gov/geocoder/Geocoding_Services_API.html),
accepts a single full street/city/state/ZIP match within a bounded Columbus
coordinate box, and retains benchmark, match text, request URL, response hash,
and observation time. It does not activate ingestion or change production. The
coordinates are Census street-range estimates, **not parcel centroids** or
verified filing-site points. A local 12-address pass matched seven addresses
covering 75 filings; five were not plotted. Repeated filings can share one point.
The map and linked list distinguish source coordinates, Census estimates, and
parcel centroids. This local result is not production map coverage.

Frontend regression coverage now clicks from the overview into the Map tab and
asserts that a mapped demo layer renders geocoded filings and source parcel
rows, while still labeling Census address-range estimates and parcel centroids
separately.

The demo still has **zero qualified parcel records**. Existing parcel ingestion
and map display accept source coordinates and polygons when the source's export
policy permits them, but Franklin County source-use rights and Columbus-to-county
identifier semantics remain open. No county geometry was copied into this demo,
and no nearby or for-sale claims follow from address geocoding.

## Production Ingestion Audit

The read-only Render dashboard check still returned the Render login page in the
accessible in-app browser. Worker configuration, scheduler executions, current
successful run counts, production database inventory and source freshness remain
unverified. This demo does not switch on production ingestion. An authenticated
Render session is required to finish that audit; do not send passwords in chat.
