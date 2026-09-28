# Acquisition pilot checklist

## Local implementation, not deployed

### Planning-Anchored Nearby Parcel Searches (2026-09-27)

Planning records can now directly generate ranked nearby-parcel searches with
the same radius, persona, acreage, zoning, land-use, audit, and acquisition-case
behavior as permit-anchored searches. Search rows enforce exactly one anchor:
either a permit or a planning record. The acquisition radar exposes
`anchor_planning_id`, and the map prefers exact planning-linked parcel searches
when a selected source record has one. If no planning search has been run yet,
the UI continues to show the explicit city/state market fallback rather than
pretending that nearby parcels are directly linked.

Verification: focused backend parcel/availability/ZIP3 tests, focused
acquisition-map and nearby-parcel-panel frontend tests, and TypeScript checks
pass. The opportunity detail nearby-parcels panel now lists geocoded planning
records from the deal market as selectable anchors and calls the planning
nearby-parcel endpoint. This does not activate any new parcel source or qualify
Columbus/Franklin County rights.

### Full regional rollout visibility (2026-09-26)

The Source Health product page now renders the complete 50-state rollout queue
instead of only the first twelve state chips. Each state links back into the
state-filtered source/candidate worklist and preserves the catalog distinction:
configured/candidate regional coverage is not measured live inventory, record
freshness, or geographic completeness.

Verification: four focused Source Health frontend tests pass.

### Reviewed diligence observations on screening (2026-09-26)

Acquisition screens and exported snapshots now include recent reviewed numeric
diligence observations on the matching criterion and in an opportunity-wide
`reviewed_observations` context. The response preserves the evidence digest
check before exposing the observation, scopes records to the active tenant/deal,
and omits deleted documents. These observations are explicitly contextual:
`changes_screening_result=false`, `independently_verified=false`, and the
criterion status remains unchanged until a future source-backed verification
step converts a reviewed observation into an accepted underwriting fact.

Verification: 45 focused backend tests pass across diligence observations,
diligence reviews, and acquisition screening. No migration, source activation,
production change, push, merge, or deployment occurred.

The opportunity screening panel now displays those reviewed observations beneath
the matching criterion as contextual measurements while preserving the unknown
screening status. Four focused frontend tests pass for the panel.

### Structured diligence observations (2026-09-21)

Reviews now optionally retain a structured numeric observation in their existing
tenant-scoped JSON snapshot (`diligence-review-v2`; no new migration). Supported
metrics are leased-area occupancy percent, largest-tenant base-rent percent,
restaurant base-rent percent, base-rent-weighted remaining lease years, and bay
count. Each requires an as-of date, explicit whole-property/partial scope, and
measurement methodology. Metrics must match the criterion; values must be finite
JSON numbers, percentages are 0-100, bay counts are whole numbers up to 10,000,
and lease years are 0-100. Zero remains a recorded observation, not missing data.
Base-rent shares are not represented as gross-rent shares; leased-area occupancy
is not economic occupancy. Dates and methodology are analyst assertions.

The browser provides optional measurement entry and displays persisted values,
scope, date, and method. Failed submissions preserve inputs; criterion/workspace
changes clear incompatible state. Exact evidence and its hash remain attached.
Exports retain observations and historical downloads preserve exact bytes.
These are not independently verified facts and do not change screening results;
partial observations cannot imply whole-property qualification. Capex condition,
document verification, conflict adjudication, and explicit application of reviewed
facts to screening remain open work, not inferred from these measurements.

Verification: 22 focused backend tests, five frontend tests, and two real-local-API
Playwright workflows pass (1440px and 390px). TypeScript, focused lint, and build
pass with the existing bundle-size warning. Desktop/mobile form screenshots were
inspected. Tests use synthetic excerpts, not qualified property inventory. No
source activation, release, or production change occurred.

### Integrated backend regression and CLI test isolation (2026-09-21)

A full backend run after the export changes produced 1,175 passes, 14 skips,
and five admin-CLI setup errors. The CLI tests bypassed the ordinary per-test
database override and used the configured local application database, whose
users table lacked `totp_secret_ciphertext`. `create_all` cannot migrate an
existing table. This was not evidence of a production database failure.

The CLI test fixture now creates a fresh temporary SQLite database per test and
patches the CLI session factory, including the test assertions' sessions. It no
longer creates tables or inserts fixture records into the configured application
database. All five previously failing tests pass on rerun; focused lint passes.
The other 1,175 passes are from the preceding full run, not a second full-suite
run. Fourteen skipped tests are not represented as verified checks. No local
application migration or production modification was performed to mask the error.

### Evidence-bearing acquisition exports (2026-09-21)

New exports use `acquisition-screen-export-v2` and retain up to ten latest
opportunity-wide diligence reviews alongside the unchanged computed screen.
Each includes its exact attributed evidence, digest, criterion, assessment,
rationale, actor, and timestamp. The bounded context explicitly reports
`has_more`, ordering, and that reviews do not verify evidence or override scores.
Conflicting assessments remain separate; they are not resolved by recency.
Tenant/deal scope and active-document checks exclude unrelated or deleted
documents. Corrupt reviewed-text digests reject new exports before snapshot or
audit creation. Existing historical export bytes remain unchanged, including
when a source document is subsequently hidden; organization erasure still
removes snapshots. Exported evidence is intentionally a retained historical copy.

Verification: 17 review/export/excerpt tests pass, covering bounded inclusion,
conflicts, unchanged unknowns, unrelated-deal and foreign-tenant exclusion,
corruption rejection, exact historical retrieval, and deleted-document exclusion.
Focused lint passes. No source activation, production migration, push, or
deployment occurred. Real-property evidence and county rights remain blocked on
the previously recorded inputs, not replaced with synthetic inventory.

Browser acceptance now also covers excerpt -> reviewed criterion -> downloaded
v2 export -> reload -> byte-identical historical download at 1440px and 390px.
Both real-local-API Playwright cases pass (9.0s). They verify source text, locator,
digest, inconclusive assessment, explicit truncation metadata, unchanged screening
counts, and retention after reload. Fixtures remain synthetic and this receipt
does not close the real-record or production acceptance gates.

### Reviewed excerpt-to-criterion linkage API (2026-09-21)

Added tenant-scoped, application-append-only `diligence_reviews` records and
`POST/GET /deals/{deal_id}/diligence-reviews`. Editors/admins can link an active
same-deal excerpt to an allowlisted screening criterion with a supports,
contradicts, or inconclusive assessment and a required rationale. The write checks
the exact expected text hash and stored text integrity under a document row lock,
then retains the full attributed excerpt snapshot, actor, criterion, and time.
Creation is audited in the same transaction. It does not modify prior reviews.

Authenticated readers receive bounded history (20 by default, maximum 100,
offset pagination plus `has_more`) with no-store. Foreign-tenant, wrong-deal,
missing-excerpt, and deleted-document writes fail; reviews of soft-deleted
documents are hidden from ordinary reads. Organization portability and erasure
include review snapshots. PostgreSQL migration `20260921_0003` enables and forces
tenant RLS. This is not WORM storage or proof of document authenticity.

An analyst's assessment is not a computed pass/fail and cannot silently clear an
unknown. Each snapshot explicitly states `independently_verified=false` and
`changes_screening_result=false`. Conflicting assessments are retained as separate
reviews, not silently resolved by selecting the latest one. Structured numeric
fact extraction and application to screening remain separate work.

Verification: 25 review/excerpt/portability/erasure tests pass, including real JWT
authorization, stale/corrupt evidence rejection, actor/evidence retention, paging,
and unchanged screening unknowns. Twelve restricted-role PostgreSQL isolation
tests pass, including the new review table's read/write protections. SQLite and
PostgreSQL migration upgrade/downgrade/re-upgrade pass. No production change or
real evidence qualification occurred.

Browser review entry is now available beneath a selected diligence excerpt.
Editors/admins select a criterion and assessment with a required rationale;
viewers receive read-only history. Saves bind the exact selected text digest,
preserve the rationale on failure, and refresh bounded opportunity-wide history.
Each review displays its criterion, assessment, rationale, source locator, actor,
time, and expandable exact evidence/hash. Contradicting assessments remain
separate. Tenant/user/deal/document changes reset form state and query scope.
These assessments still do not change computed screening results.

Verification: all 281 frontend tests across 61 files pass, including failed-save
retention, evidence binding, workspace reset, viewer restrictions, and paging.
Real-local-API Playwright passes at 1440px and 390px with review save/read/reload,
unchanged screening unknowns, and no horizontal overflow. Both review screenshots
were inspected. TypeScript, focused lint, and production build pass; the existing
large-bundle warning remains (main bundle approximately 1.51 MB minified).
Test excerpts are synthetic, not a qualified real-property package. Structured
numeric fact extraction/application and independent source verification remain
unimplemented; source-use and real-property-input dependencies are unchanged.

### Bounded attributed excerpt intake (2026-09-21)

Added an additive local API for analyst-provided rent-roll, lease, CAM, and capex
text excerpts. `POST /deals/{deal_id}/document-excerpts` requires authenticated
editor/admin access to an active tenant-visible deal, a source title and date,
page/section locator, and an explicit affirmation of authorization to store the
excerpt. Text is limited to 20,000 characters and 60,000 UTF-8 bytes; blank/null
text, unknown fields, and caller-provided verification claims are rejected.
No URLs are fetched and no binary files or scripts are executed.

The exact submitted text is retained with its SHA-256, submission time, actor,
and attribution in a nullable JSON field on the existing tenant-scoped document
table. An audit event records the digest and byte count, not the text. Metadata
responses identify `analyst_provided_excerpt` without returning the excerpt;
authenticated members retrieve it via
`GET /deals/{deal_id}/documents/{document_id}/excerpt`, with no-store and active
deal/document checks. Existing document metadata creation remains compatible.
Generic organization portability/erasure includes the new field.

This is not original-file upload, independent verification, or automated fact
extraction. Original-file receipt and independent verification are explicitly
false. Source-date and authorization are analyst assertions. Screening unknowns
remain unchanged merely because text was saved. Corrections require another
record; the API exposes no excerpt-update operation. Database-level immutability
and reviewed structured fact extraction are not claimed.

Verification: 12 new schema/authentication/provenance tests and 12 existing
portability/erasure tests pass; the 11 existing restricted-role PostgreSQL RLS
regressions also pass after migration. SQLite and PostgreSQL upgrade/downgrade/
re-upgrade pass. No real property documents were supplied, production sources
activated, migrations deployed, or paid storage provisioned.

Browser intake is now available in the opportunity's Diligence excerpts section.
Editors/admins can submit attributed text after affirming storage authorization;
viewers can read saved excerpts but do not see a submission form. Metadata pages
are bounded to 20 documents, excerpt bodies load on selection, and query/form
state is scoped to tenant, user, and deal. Text renders as escaped text, never
HTML. Failed saves preserve inputs; changing workspace clears them. Source title,
date, locator, digest, and the unverified/original-file limitation remain visible.

All 279 frontend tests across 60 files pass. Real-local-API Playwright workflows
pass at 1440px and 390px, verifying required authorization, save/read/reload,
unchanged screening unknowns, and no horizontal overflow. Mobile form and desktop
excerpt screenshots were inspected. TypeScript, focused lint, and production
build pass with the existing large-bundle warning. Fixtures are synthetic text,
not an actual property package. Reviewed evidence-to-criterion linkage is now
available as described above; submitting an excerpt must not itself turn a
criterion into a pass.

### Evidence intake dependency (2026-09-21)

Inspection of `app/routes/documents.py`, `app/models/document.py`, and
`app/schemas/document.py` confirms that current document creation records metadata
only: filename, document type, optional file path, and claimed byte count. It does
not receive, retain, hash, or parse document bytes. No application object-storage
or multipart upload implementation was found. A document row is therefore not
proof that a rent roll, lease, or capex report was ingested, and must not clear
the screening's source-verification unknowns.

To qualify the first real acquisition example, obtain one authorized, redacted
property package with its address, dated rent roll, relevant lease/CAM excerpts,
and available roof/HVAC/parking reports. Missing items must remain unknown; do
not generate substitute inventory or infer leases from permit descriptions.
Personal tenant/contact/bank details are unnecessary for this qualification.
Implementation can continue on bounded evidence intake and provenance, but
real-document extraction and verification cannot be claimed without the input.
No document uploads, storage services, or paid commitments were enabled here.

The separate Franklin County dependency remains a current published use policy
or county clarification covering the proposed access, retention, and derived
display/export, plus identifier and field semantics. A product-owner approval
alone is not evidence of third-party data-use rights. The prepared inquiry is in
`docs/parcel-reference-resolution.md`; it has not been sent by this agent.

These are inputs for real-data acceptance, not proof that all remaining
engineering work is complete. Production diagnostics and release approval remain
separate gates. This checkpoint is documentation-only; no new test run or live
source request was performed.

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
  distinct-reference counts, and validates complete disjoint bounded batch
  manifests, with 33 passing tests. It does not acquire evidence
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
  Attributed excerpt intake, evidence-bound analyst reviews, and retained export
  snapshots are implemented and browser-tested. Remaining: authorized real
  property inputs, verification, and reviewed structured fact application; an
  analyst's supports/contradicts assessment alone is not a numeric screening fact.
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

## ZIP3 opportunity heatmap

GET /acquisition-map/zip3-heatmap is authenticated, tenant-scoped, read-only,
and no-store. It aggregates active permit signals and saved nearby-parcel
candidates into ZIP3 buckets so Acquisition Radar can show where development
signals overlap with parcels worth investigating. Scoring favors pre-approval
signals, mapped records, candidate density, and reviewed shortlists. The
response includes sample signals, sample nearby parcels, and explicit
availability semantics.

This is an investor lens, not a listing feed. `nearby_candidate` means a public
parcel or ranked nearby result near a signal. `verified_for_sale` remains zero
unless a listing, broker, owner, or explicit availability source is present. The
UI repeats that distinction so BuildSignals can help users find where to look
without implying a parcel is on-market from public permit or assessor data
alone.

Verified availability is represented as a current parcel fact, not a candidate
review status. BuildSignals only treats a parcel as `verified_for_sale` when a
current `availability`, `listing`, `broker_listing`, `owner_availability`, or
`sale_availability` fact has a recognized available/listed status, a listing /
broker / owner / auction evidence type, confidence of at least 0.7, and source
evidence such as a URL or excerpt. Nearby parcel proximity, assessor fields,
high land value, or user shortlist actions do not satisfy this contract.

Admin/editor users can now add reviewed parcel availability evidence from the
parcel detail page or `POST /parcels/{parcel_id}/availability-evidence`. The
endpoint creates a tenant-scoped manual ingestion source, completed ingestion
run, raw source record, immutable audit event, and current `availability` parcel
fact. It requires recognized availability status, broker/listing/owner/auction
evidence type, confidence of at least 0.7, and a source URL or excerpt. This is
for source-backed broker or owner evidence collection while automated listing
feeds remain unadmitted; it does not let a reviewer mark nearby candidates as
for sale without evidence.

The acquisition map consumes the same ZIP3 heat output as centroid bubbles sized
by score. Selecting a ZIP3 clears the single-signal focus and filters the ranked
parcel table to candidate parcels in that market cluster. These centroids are
derived from admitted source coordinates and nearby parcel coordinates; they are
not licensed ZIP boundary polygons.

Leaflet is lazy-loaded. OpenStreetMap raster tiles load only for the visible map,
with attribution and an origin referrer. There is no bulk fetch or offline cache.
Tile failures show a notice without hiding source records. Public tiles have no
SLA: before a larger paid rollout, select a suitably licensed managed tile service.
See https://operations.osmfoundation.org/policies/tiles/ and
https://leafletjs.com/reference.html for the basemap policy and library reference.

Remaining pilot gaps: production counts and auth verification, qualified nearby
parcel inventory, reliable geocoding, reviewed brand relevance, and broader
cross-page signal-to-parcel navigation. The acquisition map now
shares backend state filtering with ZIP3 heat and can filter for source-backed
verified availability. Signal geography and ranked parcel geography now share
one page-level state filter, and selecting a permit source record narrows the
ranked parcel map to nearby candidates generated from that exact anchor permit
when those saved searches exist. Selecting a planning source record now narrows
ranked parcels to exact planning-anchored searches when those saved searches
exist, or by the same city/state market with an explicit caveat before a direct
search has been run. The independent signal geography layer now supports bounded
older/newer paging over permit and planning layers. A single combined map surface
remains open.

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
