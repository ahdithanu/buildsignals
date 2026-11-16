# Full Geographic Inventory

## Container Acceptance

Source-checkout tests do not prove the release image imports successfully.
The packaged API imports the existing agent_runtime research validation module;
Docker must copy that package without enabling research or installing its optional
SDK. A dedicated CI job now builds the image and imports app.main in a disposable
container with networking disabled and synthetic SQLite configuration. The old
image failed with a missing module; the corrected local image passed. Hosted
acceptance must use the corrected head before the staged release continues.

## Problem

The existing signal map displays one bounded page of up to100 permits and100
planning records. It is not the full workspace footprint. Unranked stored parcels
are absent from that view, and records without coordinates disappear entirely.
Catalog availability, enabled schedules and stored inventory are different facts.

## Scope

The default map view becomes Coverage; Filings keeps the existing paginated
evidence browser. The new read-only overview aggregates all active, tenant-scoped
permit, planning and parcel inventory in SQL. Counts are not derived from the
record page. It includes unmapped records and unknown state/jurisdiction buckets.

State summaries always represent the full measured inventory. State/layer
filters narrow totals and the paginated jurisdiction groups. A bounded record
browser includes parcels without saved nearby searches and records without map
coordinates. Parcel inventory is not a ranked nearby candidate or a listing.

Map markers represent aggregate record coordinates, not municipal boundaries,
parcel boundaries or exact city centers. Groups without valid coordinates remain
in counts and the list; no fallback location is invented. Existing source and
reviewed derived-coordinate eligibility must match the map-readiness inventory.

Measurements are timestamped, refreshed on demand and periodically while the
view is visible. This is not a live publisher feed, complete market coverage,
deduplicated project inventory, source freshness or evidence of sale availability.

## Interfaces

Authenticated GET `/acquisition-map/coverage` accepts bounded pagination,
`state` and `kind`. It returns measured totals, all observed state summaries and
paginated state/jurisdiction groups, with explicit total group count and page
links. `__unknown__` is the explicit missing-location filter token.

Authenticated GET `/acquisition-map/records` accepts bounded pagination,
`state`, `jurisdiction` and `kind`. It returns a count over the complete filtered
inventory plus a bounded, stable record page. It does not disclose operational
source configuration, owner/contact fields or retained raw payloads.

No migration, ingestion activation, coordinate rewrite, review acceptance or
paid model call is needed. New API/frontend publication and release remain
separate gates; this local implementation is not a production rollout.

## Dated Production Baseline

After the separately approved Orlando pilot, signed-in inspection on November15
Pacific measured20,437permits,112planningrecords,70active/locatedparcels and
5,139locatedfilings. The scoped Orlando intake reconciled70source/stored rows;
54centroids were within the quarter-mile radius and16outside. Publisher
currentness remains unknown. No saved searches or ranked parcel candidates were
created. Cherry Hill's inquiry remains DRAFT/UNSENT.

These are dated workspace counts, not current API fixtures or national coverage.
The new browser fixture is explicitly synthetic and isolated from production.

## Verification

Implemented and accepted locally; not published, merged or released. Final
frozen-runtime checks:

- Backend:3,380passed/zero skips/3existing geography-reflection warnings/427.52s.
  Both owned PostgreSQL targets report no new Alembic upgrade operations. The
  local virtualenv lacks pytest-cov; no current app coverage percentage is claimed.
- Frontend:554passed/82files/7.00s; typecheck/build/scoped ESLint passed.
- Focused backend:94passed/3dedicated-PostgreSQL skips/17.38s. Those skips are
  not isolation acceptance; independent actual non-owner PostgreSQL acceptance
  passed16tests/1.71s on the fresh UTF-8 target, including3new coverage cases.
- Actual local API-to-browser desktop/mobile journey:2passed/13.2s. The fixture
  uses existing local ingestion/normalization for217synthetic records, including
  70unrankedparcels and56unmappedrecords. External source/model calls are denied.
- Fresh normal Chrome confirmed the overview and unknown-state URL/reload.
  Synthetic screenshots are not production inventory evidence.
- Existing built strict-CSP harness passed at390/768/1440; negative inline-script
  denial remains enforced. Ruff, workflow parsing, harness and independent review
  passed. Existing cached Gitleaks staged scan passed with no leaks. No hosted
  scan or CI acceptance claimed.

The browser journey reproduced a local Leaflet deferred zoom-end callback after
map teardown. The renderer now disables zoom animation, stops before removal and
rejects queued resize callbacks for removed instances. Red reproduction, lifecycle
regressions and final browser checks passed. This is not proof of the original
reported production crash cause.

Earlier full-backend attempts failed on local provisioning: the first lacked
CREATE SCHEMA, then7failures exposed owner-only migration/trigger contracts and
SQL_ASCII encoding. Targets were recreated with explicit UTF-8; the general
restricted owner and nonce-marked DDL-owner targets remain separate from the
non-owner RLS acceptance target. No tests were weakened or deselected and no
production permissions changed. The final complete run passed without exclusions.
Both superseded and final owned PostgreSQL clusters are stopped and independently
status-confirmed; local API/frontend test ports have no listeners. Private runtime
credentials and operational receipts remain ignored, outside this change.

## Release Gate

Owner approved publication, merge and staged release after checks/CI, including
a bounded read-only schema preflight. No production migration, source activation,
access/schedule change or paid call is authorized. The normal AWS deployment
workflow applies migrations; do not dispatch it under this no-migration grant.
The preflight must establish compatibility, or hold the release (including merge
because frontend auto-release may follow) for the exact dependency.
Existing ingestion stays running; Cherry Hill inquiry stays DRAFT/UNSENT.
