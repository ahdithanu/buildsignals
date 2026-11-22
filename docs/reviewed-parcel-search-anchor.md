# Reviewed Parcel Search Anchor

## Task Packet

Outcome: an eligible retail filing without native coordinates can explicitly
start nearby discovery from its currently accepted parcel centroid, then be
shortlisted and promoted without rewriting the filing's source location.

Baseline: released93435f6 rejects this search and hides coordinate-less permit
options. The real Orlando ALDI filing BLD2026-19334 has qualified parcel reference
302325900200060; the prior70-row production intake did not create search inputs
or ranked candidates. The prior quarter-mile source query intersected polygons;
only54 centroids were inside that distance. These dated receipts are not a new
measurement, listing, opening or entitlement claim.

Ownership: Pascal owns anchor resolution/search integration and focused backend
tests. Averroes owns the existing panel/client/types/frontend tests. Parent owns
schema/routes, integration, evidence qualification, browser proof and documentation.
Gauss owns the completed harness check and independently reviews adoption docs.
No two lanes write the same files; subsequent review is independent of authors.

## Decision Record

Status: local implementation, not released. This adds a read-only preview
interface and an optional stale-state precondition to existing search creation.
It retains the layered service/API structure and existing persisted JSON fields;
no domain reorganization or schema migration is needed.

Copying a county centroid into native permit coordinates would destroy source
meaning. Accepting a fuzzy reference or browser-supplied point would bypass
identity review. Instead, use current audited analyst acceptance as an explicit,
labelled location method and snapshot the server-resolved evidence with a new
search. Native source coordinates remain the first choice. A future dedicated
anchor table is deferred until multiple consumers demonstrate the need; revisit
the JSON representation if an indexed anchor-history query becomes necessary.

Tradeoff: conservative stale/ambiguous evidence rejection can require re-review.
That is preferable to silently researching around the wrong property. Review the
interface, tenant boundaries and lock order independently before acceptance.

## Contract

- Preview is authenticated, tenant/deal/match scoped and read-only with no-store:
  `GET /deals/{deal_id}/nearby-parcel-anchors/{brand_match_id}`.
- Preserve native source coordinates as the first choice. Census street-range
  estimates cannot become a verified search anchor.
- Missing native coordinates do not themselves authorize a fallback. Require a
  unique current analyst-accepted typed permit-to-parcel relationship, current
  raw IDs/normalization hashes, matching address/ID, active records and unexpired
  review. Both evidence rows must belong to the same review and have a matching
  authoritative acceptance audit. A user-set source_system marker is not proof.
- The panel labels this method `Reviewed parcel centroid`. Preview readiness is
  not a write. Unavailable, loading or mismatched responses cannot create a search.
- Explicit search creation includes the preview as `expected_anchor`; the server
  locks and revalidates its evidence, then uses server-resolved coordinates.
  Client coordinates are a stale-state precondition, never location authority.
- Persist the reviewed method/IDs/hashes with the new search and candidates in
  existing JSON snapshots. No migration, permit-coordinate copy, historical search
  rewrite or new automatic fallback search. Native callers remain compatible.
- Existing role checks, demo write denial, ranker, proximity grouping, shortlist,
  promotion idempotency, provenance and unknown availability/zoning rules remain.

## Verification Gates

November22 current-main local gates passed:3592backend/zero skips/91.7268%/
3existing geography warnings,673frontend/type/build,7actualrestricted-PG anchor
cases,2synthetic desktop/mobile workflow cases and2separate recovery cases.
Joined raw payload projection is regression-tested. One retained real ALDI filing
passed ingestion/matching/graph/idempotent local replay; no retained real parcel
cohort or real-record full journey is accepted. The first bounded capture stopped
at a parcel-response gate; a fresh bounded capture decision is pending. No hosted
CI, production retail workflow, listing, opening or entitlement claim is implied.

Focused RED/GREEN covers native precedence, incomplete/nonfinite coordinates,
missing/forged/expired/stale/conflicting/ambiguous reviews, cross-tenant reads,
preview mismatch, persistent provenance and unchanged permit coordinates.
API proof includes auth/no-store/read-only and role enforcement; frontend proof
includes selection, pending/unavailable states and explicit expected-anchor input.
Accessibility proof covers labelled controls, focus, keyboard selection and mobile
layout. Observability review requires useful bounded errors/audits without raw
payloads or secrets. Performance proof bounds relationship/evidence work and
checks query behavior, not just response size. Statistical review verifies distance
units/grouping and avoids probability or investment-return claims. Migration gate:
none added; legacy native callers and historical JSON snapshots must still work.

An actual local ingestion-to-review-to-search-to-shortlist-to-promotion flow must
use qualified real source rows through existing normalization/raw/graph code.
Locate an authorized retained corpus first. Receipts or synthetic test fixtures
alone cannot establish this real-record acceptance. Browser proof uses a disposable
local API/database and fresh desktop/mobile views; no production business writes.

Local work is authorized, not publication/release, source activation, paid calls
or a production intake/replay. New external data access needs an applicable
bounded scope and evidence basis. Cherry Hill inquiry remains DRAFT/UNSENT.
Record exact commands, outcomes, limitations and the next dependency in handoff.
