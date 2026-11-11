# Requested-Market Clean Release Integration Plan

## Implementation Update: Clean Worktree Prepared

Parent final review approved the local integration commit after checking the
398-targeted and2,472passed/69skipped destination receipts and protected-file
diff. Confirmed source remains3d8c7fd; no wait-for-source-SHA gate remains.
July25,2023 is the engineering-review date for historical Cherry Hill case
22-P-0043, not a known filing date. The application filing date is unknown, and
that 2023 evidence is not a current retail expansion or continuity claim.
No push/PR/merge/deploy/source activation is approved.

The parent explicitly authorized uncommitted integration in
`.worktrees/requested-market-release`, branch `codex/requested-market-release`,
based on 5ff111f. This supersedes the earlier wait-before-transfer instruction:
the latest parent-owned NJ privacy guard/catalog and quarter-mile helper changes
have been ported, not ac34876 alone. Parent confirmed final source
`3d8c7fdfa52c5d42deef013fe32a9c76fc427b3d` and authorized a local integration
commit after verification, but no push/PR/merge/deploy. The root and original release worktrees remain
outside the integration writer's ownership.

Current root service/health guard diff received independent focused review with
no remaining actionable findings. Destination tests use internal_operator and
release fixture isolation, with additional main/stage/freshness poison and
pre-transport invalid-config regressions. Initial destination checks passed268;
final targeted catalog/rollout/connectors/privacy checks passed398. Full
destination backend suite passed2,472/69skipped in301.65s; its receipt is in
`docs/releases/2026-11-11-requested-market-release.md` in the new worktree.
The candidate catalog and protected privacy/auth/frontend files are unchanged.

The helper now accepts 0.25..3 miles, still at most2,000records. Parent reports
quarter-mile public reconciliation161/161/161 and161distinct, but anchor and
production qualification remain false and publisher freshness unknown. The
one-mile4,587count was over budget and held without record pages. None is
production inventory; no source activation or existing worker update occurred.
Final root source3d8c7fd and its November11 NJ receipt are now available.
Its root suite passed2,453/70skipped in293.59s. Those counts remain separate from
the destination's2,472/69skipped in301.65s because the base/test sets differ.

Final integration diff review found no remaining critical issue. Catalog,
service/health guard, operational worker and quarter-mile helper bytes match the
current parent root source; auth/frontend/schema/conftest/candidate files remain
unchanged from5ff111f. The original release worktree remains clean. The integration
is ready/tested for a local checkpoint; publishing still requires parent review
and separate approval. Consult the integration branch's enclosing commit/HEAD
for its exact local checkpoint, not root's research branch.

## Resolved Privacy Prerequisite: Corrected Checkpoint Required

**Do not integrate ac34876 alone or activate its old NJ catalog/scoped profile.**
The parent reports that the official MOD-IV manual identifies ST_ADDRESS and
CITY_STATE as mailing fields; ZIP5 is not verified as situs postal data and must
also be excluded. PROP_LOC is the verified situs-address input. The original NJ
projection/address fallback and its synthetic tests therefore require correction.
This material finding supersedes the earlier profile acceptance and the earlier
conclusion that no shared ingestion-service change was needed. Source access,
municipal counts and GUID presence do not establish address-field privacy.

The parent completed the correction in3d8c7fd; its frozen tests and independent
review passed. Integration must include that checkpoint's correction, not the old
NJ contract. Required dependencies
are the opt-in `enforce_field_allowlist` guards in both
`app/services/ingestion/service.py` and `app/services/ingestion/health.py`, enabled
with literal True only for the reviewed NJ contract and inherited scoped profile.
Postal code must remain unknown, not filled from ZIP5 or mailing-address text.
No source activation, stored-data cleanup or production privacy repair is implied.

This update records the parent's official-manual finding and an independent
design and completed-diff review; the manual was not fetched by this audit.
No remaining critical integration issue was found. The 5ff111f base recommendation
and deployed Ocala preservation requirements remain unchanged.

## Status and Authorization

November 11, 2026, America/Los_Angeles. This preserves the independent local
release-base audit and incorporates the parent's new synthetic NJ test dependency.
The initial audit owned only this root document and made no other changes.
Subsequent parent delegation authorized all integration edits and a local commit
only in the new requested-market-release worktree. No schedules, production
source registrations, production rows or deployed configuration are changed.
No fetch, external network, push/PR/merge or deployment was made by this task.
The parent reports a successful fetch with unchanged origin/main.

| Role | Exact local checkpoint |
| --- | --- |
| Root checkout / audit source | `4669af11862661b2711b556010a3c2a43cf96500` (`codex/reviewed-city-expansion`) |
| Historical SF/NJ code and receipts; insufficient for corrected NJ integration | `ac34876f04c93f5d5388b547669cedc807ef5e36` |
| Final NJ mailing/privacy/quarter-mile source checkpoint | `3d8c7fdfa52c5d42deef013fe32a9c76fc427b3d`; do not substitute ac34876 |
| Root test-isolation checkpoint | `8ec18e12eb95a7bacfdf80545496d283d5f12216` |
| Local origin/main, unchanged after parent fetch | `2307b92ab90c85116d775ae92f143045fe1befdd` |
| Recommended application/privacy base | `5ff111f28caef49ac0e4877e241a98f9e66ea745` (`codex/investment-area-live`) |

Root retains dirty `docs/agent-handoff.md`, `src/pages/MarketSignals.tsx` and
untracked research/test artifacts. The release worktree at
`.worktrees/investment-area-live` was clean during inspection. Do not clean,
reset, deploy or overwrite root to perform integration. The parent's new
`tests/test_njgin_scoped_ingestion.py` was initially untracked; it is now committed
in3d8c7fd, not ac34876/4669af1, and was transferred with release auth adaptation.

## Why 5ff111f

The release branch is 12 commits ahead of local origin/main and descends from
`2307b92`. It contains the production-verified investment reference correction,
owner-only source operations, customer-safe source projections, auth/session
revocation and frontend cache/privacy protections. The relevant runtime/security
checkpoints include `3026ea3`, `3a814ee` and `ab3270a`; final tests/docs extend
through `5ff111f`. Read that worktree's release receipt and handoff, not root's
older application implementation, for their acceptance scope.

Root diverges at `1eb6005`, not current local main: it is 21 commits ahead and two
behind origin/main. Its ancestry includes frontier hotspots, appreciation/parcel
research and an older investment application implementation. Merging root or
copying whole application files would carry unrelated research and can undo
newer production privacy behavior.

Recommendation: prepare a separate clean integration branch based on `5ff111f`.
PR #271 is recorded as open in the release handoff; this audit did not query its
current remote status. If the parent later verifies that main includes the
privacy release or its reviewed equivalent, use that newer main instead.
Otherwise keep the requested-market work stacked on the privacy release; do not
silently substitute `2307b92` just because it is named main.

**Important distinction:** `5ff111f` is the application/privacy base, not the
latest deployed ingestion-worker source baseline. The newer worker dependencies
below must be integrated explicitly. A newer application base does not justify
rolling back independently deployed worker functionality.

## Runtime and Configuration File Set

| Destination path | Exact transfer or integration requirement |
| --- | --- |
| `app/services/ingestion/catalog.json` | Retain the six SF hostname substitutions and NJ zoning correction from ac34876, then apply the mandatory new NJ privacy checkpoint: PROP_LOC-only situs address; remove ST_ADDRESS, CITY_STATE and ZIP5 from projections, allowlists and mapping fallbacks; no postal mapping/default; explicit suppression and literal enforce_field_allowlist=True. Preserve dataset IDs, PIN_NODUP identity and optional PCL_GUID projection/allowlist/group fallback. Update rights/provenance wording to reflect the corrected field semantics. |
| `scripts/recurring_regions.py` | Integrate the SF profile from `ac34876` together with the bounded-run infrastructure and deployed-worker preservation requirements below. Do not copy the older release worker over root's operational baseline. |
| `scripts/qualify_njgin_markets.py` | Add the complete new file from `ac34876`, including degenerate-ring checks, sanitized failures, aggregate-only receipts and explicit logical-versus-wire request accounting. Default mode stays offline. |
| `scripts/retail_parcel_refresh.py` | Add the helper absent from 5ff111f (prerequisite f8cceea), but use the new corrected checkpoint, not the old ac34876 NJ FIELDS entry. NJ must select only approved identity/geometry/municipality/acreage and PROP_LOC situs fields, omit mailing/postal fields, and preserve enforce_field_allowlist=True on generated profiles. Keep scopes inactive/manual, radius 0.25..3 miles and at most 2,000 records. |
| `app/services/ingestion/service.py` | Port the new opt-in, page-wide field-allowlist validation before any row from that page reaches normalization/persistence. Preserve destination service behavior outside the explicitly enabled NJ contract and do not replace unrelated privacy code. |
| `app/services/ingestion/health.py` | Port the matching opt-in canary validation, covering the main page and every stage/freshness probe. A source must not pass canary with fields that ingestion will reject. Preserve other sources' behavior and diagnostics. |
| `app/services/ingestion/production_rollout.json` | Regenerate offline from the destination's final catalog and candidate catalog. Do not copy root's generated manifest as an authoritative artifact for a different base. |
| `render.yaml` | Synchronize the three INGESTION_ROLLOUT_MANIFEST_DIGEST values to the newly generated destination manifest. Preserve other blueprint settings. Editing a checked-in pin is not authorization to apply cloud configuration. |

At the original audit checkpoint, shared HTTP transport, ArcGIS/Socrata connectors,
normalization and ingestion service matched release and root. Connectors and
normalization still have no identified transfer dependency, but the new privacy
finding now explicitly requires service and health guard patches above. Review
the final implementation diff before relying on that statement. Retain release's newer
`app/schemas/ingestion.py`; do not replace it with root's older privacy schema.
The imported field-mapping APIs needed by these helpers already exist on release.

`f8cceea` also adds `scripts/prepare_retail_market.py` and its tests. They are not
required by the parcel helper/qualifier and need not be included. Neither
`scripts/upgrade_regional_worker.py` nor scheduling/provisioning changes are
required to integrate code without activating it.

## Shared Worker Dependencies: Do Not Drop Deployed Ocala

The worker in `5ff111f` still limits verification to 1,000 rows and runs only four
pages. Applying only the 24 SF lines from `ac34876` is insufficient: the verified
SF window contained 6,544 publisher rows and would be rejected by that worker.

Required general infrastructure comes from `505229c`:

- MAX_RECORDS_PER_RUN=100,000, PAGE_SIZE=250 and a 401-page budget including the
  exhaustion probe; each service call remains at most 100 pages.
- `execute_regional_refresh` checkpoint continuation, aggregate inserted/updated/
  failed/seen counts and run IDs; reject stalled/failed/over-budget continuation.
- `reconcile_after_refresh`, count-unavailable failure handling, persisted run
  failure status and source quarantine. Preserve explicit non-demo tenant,
  advisory lock, identity matching and no silent quarantine reactivation.

The SF profile itself keeps the primary-address predicate, UTC-calendar-derived
31-day data_loaded_at window, ascending data_loaded_at/record_id keyset, explicit
mapped-field projection including data_as_of, PDDL/hostname checks, manual mode
and the existing 36-hour conservative record-update freshness gate. It does not
claim a new-filing census, deletion reconciliation or an independent publisher
heartbeat. LA and SF planning remain outside SOURCES.

**Ocala is not a new SF feature dependency, but it is an existing deployed
operational contract that a successor shared worker must preserve.** `339c227`
contains the separately accepted daily context profile; the root receipt records
61 inserted/zero failed, idempotent replay and tenant map-service eligibility.
Those are dated receipts, not new checks in this audit. Its mappings were
embedded in the worker command so they did not depend on new catalog content in
the older API image. A release-base catalog alone cannot reconstruct this source.

Do not lose any of the following when reconciling the older release worker:

- `ocala_fl_gis_new_building_projects` in SOURCES, `ocala_context_entry`,
  OCALA_CONTEXT_KEY and the source-specific 1,000-row ceiling.
- Public GrowthManagement layer 19, native statuses and dates, context-only
  labeling, publisher currentness unknown and no recent-filing/model claim.
- Exact field projection: OBJECTID, PermitNo, Applied, Subtype, Status, APN,
  Issued, Expired and WGS84 centroids; no descriptions, addresses, owner/contact
  fields or raw polygon request.
- Synthetic mapping aliases `__source_record_id`, `__latitude`, `__longitude`,
  preserving unique source_field values and raw PermitNo/centroid canary inputs.
  The earlier duplicate-mapping variant failed actual source registration.
- `ContextConnectorGuard` and `context_connector_guard`: reject extra fields,
  blank/duplicate native identity, invalid/nonfinite/out-of-area or non-WGS84
  centroids and cumulative scope above 1,000 **before persistence**; restore the
  factory override on every exit.
- Ocala's `where=1=1` inventory exception, no rolling date cutoff, incremental
  replay and five-page budget including exhaustion, separate from the 100,000-row
  regional limit. Before/seen/after reconciliation and quarantine remain required.

Also preserve already delivered regional-worker behavior when creating a shared
successor: Seattle/Cincinnati additions and deterministic sort (`29d63c4`), the
100k engine (`505229c`), and wave-2 source/update-window/count/error handling
(`1ab2e43`), including held/canary-only posture for Bend/Tacoma. These are not
authorization to enable any currently held or absent schedule.

Recommended integration approach: retain the complete operational worker at
`ac34876` as the audited shared-worker source, together with its regression
dependencies, while keeping application/API files on `5ff111f`. This file does
not depend on frontier research or the Ocala PDF connector. A strictly isolated
SF-only port is possible with the 505229c engine, but must not be represented or
deployed as a replacement for existing shared workers lacking their newer
profiles/guards. No existing task commands, images or schedules are modified by
this plan; future worker rollout needs its own scope and read-back verification.

## Exact Test Transfer Set

For the recommended shared-worker preservation approach, the focused test files
are:

| Path | Transfer rule |
| --- | --- |
| `tests/test_ingestion_catalog.py` | Apply SF hostname/NJ zoning hunks plus the new checkpoint's PROP_LOC-only address, unknown-postal, mailing-field suppression and enforcement-flag regressions. Preserve destination privacy fixtures; do not copy root's unrelated Ocala-PDF candidate assertion or obsolete mailing-address expectations. |
| `tests/test_recurring_regions.py` | Integrate SF profile/contract tests plus retained bounded execution, count, quarantine, UTC and regional/Ocala regression coverage for the chosen shared worker. |
| `tests/test_regional_refresh_integration.py` | Add checkpoint/persistence regression from ba98b59; adapt source-operation authentication to release's internal_operator fixture. |
| `tests/test_ocala_context_guard.py` | Add the complete pre-persistence safety tests from root's reviewed operational worker checkpoint. |
| `tests/test_ocala_context_refresh.py` | Add the profile/mapping/registration/currentness tests from root's reviewed operational worker checkpoint. |
| `tests/test_qualify_njgin_markets.py` | Add the complete ac34876 qualifier tests, including zero-area and request-accounting regressions. Synthetic fixtures without GUID test optional absence; they do not contradict its real presence. |
| `tests/test_retail_parcel_refresh.py` | Add helper/profile tests from the new checkpoint, replacing old NJ mailing/postal expectations with PROP_LOC-only address, postal unknown, and guard-inheritance assertions. |
| `tests/test_retail_parcel_qualification.py` | Add the helper safety tests and the corrected NJ normalization case from the new checkpoint; do not freeze the old mailing projection as the accepted contract. |
| `tests/test_njgin_scoped_ingestion.py` | Transfer the parent's updated synthetic regression and poisoned-page privacy cases only after review of the new checkpoint, with release authentication adaptation below. Do not assume ac34876 contains it. |
| `tests/test_ingestion_projection.py` plus `tests/test_njgin_scoped_ingestion.py` | Root3d8c7fd covers invalid config, whole-page rejection, non-NJ compatibility and real-service poisoned-page persistence. Destination additionally covers main/stage/freshness poisoning and invalid config before transport. Include all of these required security regressions. |

The parent's NJ test exercises the real minimal profile through source creation,
normalization, persistence, idempotent replay, graph linkage, permitted boundary
detail and other-tenant 404. Its transport is synthetic; activation is only a
local disposable-DB test action. It is not live radius/real-anchor, scheduled,
PostgreSQL RLS or production/browser acceptance.

The original catalog test expected mailing ZIP5 as postal code and used an
ST_ADDRESS situs fallback. Those assertions are superseded: add the corrected
catalog privacy cases to `tests/test_ingestion_catalog.py` in addition to its
SF/zoning hunks. The new guard tests are not included in earlier pass counts.

## Mandatory NJ Privacy Design and Regression Gate

The opt-in design is appropriate only if the final implementation meets all of
these checks; this is not approval of a partially written shared-code diff:

- NJ catalog and generated scopes use PROP_LOC alone for canonical address.
  ST_ADDRESS, CITY_STATE and ZIP5 are neither requested nor allowed, and cannot
  populate canonical address/postal data through fallback, defaults or transforms.
  Missing PROP_LOC stays missing even when a mailing address is present.
- `enforce_field_allowlist is True` enables enforcement; the NJ catalog and scoped
  profile retain that exact setting. A missing/invalid allowlist on an opted-in
  source fails closed. Do not silently convert malformed config into no guard or
  reuse a broad provider projection as an implicit permission list.
- Validate the entire raw connector page before processing its first row, not
  merely mapped/canonical fields and not after a record filter. A page containing
  a clean row followed by a poisoned row must persist zero rows from that page:
  no raw payload, canonical record, parcel fact or graph evidence from the page.
  Test poisoning in both row orders and fields that have no canonical mapping.
- Cover ST_ADDRESS, CITY_STATE, ZIP5 and unrelated unexpected owner/contact fields.
  Diagnostics must not echo their values or raw payloads. A top-level key check
  alone must not be described as a general personal-data detector or a defense
  against arbitrary sensitive text nested inside an allowed field.
- Main, stage and freshness canary pages must enforce the same rule. A mixed
  valid/poisoned page must not yield a successful canary because some rows passed,
  nor be filtered into a passing result. Canary rejection must not persist data.
- Verify unflagged existing sources retain their contracts, and that the new
  opt-in guard does not replace or bypass Ocala's independent pre-persistence
  identity/geometry/privacy guard. Do not enable this flag globally as a side
  effect of adding NJ support.
- Successful NJ ingestion and idempotent replay must preserve PIN_NODUP, situs
  address, geometry, acreage and tenant visibility while postal code is unknown.
  Assert mailing/postal fields are absent from persisted raw JSON, canonical
  fields, facts and relevant detail/map output; keep the other-tenant 404 check.

Be precise about transaction scope: a poisoned first page must save zero source
raw records in the test. A later poisoned page must save zero rows from that
page; do not claim earlier committed pages are rolled back unless explicitly
implemented and tested. Failed-run audit metadata is not a raw parcel record.
The guard prevents new leakage; it does not remove historical stored fields.

The earlier full-catalog nine-sample canary and radius/helper receipts predate
this privacy correction. They remain technical historical observations, not
approval of the old mailing-field profile or acceptance of the new guards.

## Authentication and Fixture Conflicts

On release, source creation and run endpoints are owner-only internal operations.
A normal organization administrator is insufficient. The root NJ test currently
calls `_admin_headers(db)` without first creating an allowlisted operator; copied
unchanged, source creation/run calls should fail the release guard.

Use the existing release pattern:

1. Import `internal_operator` from `tests.internal_operations_fixtures` as a pytest
   fixture and request it in the NJ test signature before making source calls.
   It creates a disposable active admin, sets INTERNAL_OPERATIONS_USER_IDS through
   monkeypatch and supplies a bearer token. No real owner identifier is needed.
2. Keep the release version of `_admin_headers`: it first resolves the seeded
   allowlisted operator. The root version is not a substitute. Preserve explicit
   tenant identity and all current response assertions.
3. Resolve the root-only `isolated_auth_limiter` argument deliberately. Release's
   client already requires an in-memory backend and clears it per test. Either
   use that existing isolation and remove the unused root fixture dependency, or
   port only the opt-in fixture additively if still needed. Never replace release
   conftest wholesale or clear an external Redis backend.
4. Keep the second registered tenant ordinary and not owner-allowlisted. Its
   explicit bearer header must still receive 404 for the first tenant's parcel.
   Do not broaden the allowlist or disable authorization to make this check pass.

The new checkpoint integration test likewise uses anonymous source-operation
requests on root; adapt it with internal_operator rather than weakening API guards.
No source operations should become customer-accessible through this integration.

Do not cherry-pick 8ec18e1 wholesale: it touches frontier tests absent on release.
Release already contains limiter isolation (ab5730e) and config identity restoration
(d655106). Preserve those, its newer nearby-parcel tests and its internal-operations
fixtures. Any additional limiter fixture is a small additive test-only decision.

## Generated Artifacts, Docs and Exclusions

Root's generated rollout manifest includes an unrelated Ocala PDF candidate
fingerprint absent from the destination candidate catalog. Copying that manifest
would create a false dependency on its parser/factory/candidate changes. Regenerate
against the destination catalogs after applying SF/NJ changes, then update all
three blueprint pins. Do not assume root's digest will be correct on the new base.

Carry the dated source receipts:

- `docs/source-qualification/2026-11-10-california-refresh.md`.
- `docs/source-qualification/2026-11-10-south-jersey-markets.md`.
- `docs/releases/2026-11-09-ocala-context-ingestion.md` for preserved worker scope.
- Relevant `docs/requested-market-queue.md` and
  `docs/parcel_source_onboarding_decisions.md` changes, merged without reverting
  newer destination context. Vero Beach/East Lansing qualification is optional
  supporting research, not an SF/NJ runtime dependency.

At actual integration, merge fresh summaries into AGENTS.md, CLAUDE.md and the
destination handoff while preserving privacy acceptance. Do not copy root harness
files wholesale. `4669af1` only records checkpoint names in the handoff and is not
a runtime dependency. This document does not itself modify shared harness files.

Explicit exclusions: root research/appreciation, frontier services/tests/flag/UI,
dirty MarketSignals changes, older investment API/services/components, unrelated
retail preparation, Ocala PDF parser/connector/candidate, worker-upgrade tooling,
cloud/scheduler changes and any migration or stored-data repair. The local zoning
mapping fix does not repair already persisted erroneous zoning facts.
Likewise this plan does not authorize a mailing/postal backfill, historical raw
payload deletion, retained-data migration or a claim that production was repaired.

Never overwrite release's auth/ingestion/operations routes, auth dependencies,
customer projection schemas, frontend session/cache controls or packaged investment
reference implementation with root versions. Preserve attribution and internal
evidence lineage; privacy does not authorize erasing licensing/provenance.

## Acceptance Before Any Later Release

First verify the clean branch contains no frontier/research or unrelated dirty
files and retains the full newer privacy baseline. Final source3d8c7fd is confirmed
and the completed diff reviewed; integration verification is local only.
Run the destination's targeted
catalog/rollout/connector/worker, Ocala guard/profile, NJ qualifier/helper/ingestion
plus service/health allowlist, postal privacy and internal-operations/tenant
regressions with explicit disposable SQLite and
REDIS_URL unset/empty; no model credentials or external transport are needed.
Check generated-manifest freshness, scoped lint and whitespace. Then run the full
backend suite and required PostgreSQL/RLS/browser checks for the intended release
surface. Do not treat skipped database tests as passed isolation tests.

The older root receipt was2,440/70skipped in266.68s; final root3d8c7fd passed
2,453/70skipped in293.59s. Destination independently passed2,472/69skipped
in301.65s, plus398targeted checks. These are distinct base/test sets; skipped
database cases remain unverified here. Never activate the old mailing-field NJ
profile; SF's independent receipt does not waive that prohibition.

Later activation remains a separate approval: exact destination/image/host policy,
SF old-URL source migration if present, fresh canary, actual scheduled count
reconciliation, replay/idempotency and tenant product/map acceptance. NJ still
needs real-anchor/radius acceptance; planning/LA and other held sources stay held.
Existing Ocala tasks must not be silently changed or downgraded while adding SF/NJ.

## Audit Receipt and Next Action

Read root/release Git status and handoffs, onboarding, requested-market receipts,
commit stats/diffs and the deployed Ocala receipt. Compared local refs, merge
bases, relevant file identities and test fixtures without modifying Git state.
Parent confirmed fetched origin/main is still 2307b92. The release worktree was
clean; root dirty files remained unchanged by this task. The new NJ test was read
for integration dependencies, not changed or executed here.

Update receipt: parent reported the official MOD-IV mailing/situs correction and
in-progress NJ-only enforcement work. Read the current owned plan and local Git
status; noted the incomplete service guard work without editing or certifying
product code. Updated only this document; no manual/network lookup, tests, stored
records, shared harness or Git refs were changed.

Final update: parent confirmed3d8c7fd, final root tests and independent review, and
authorized the integration writer's local commit after destination verification.
Final receipt, architecture and ledger corrections are included on the clean
5ff111f-based tree; no code drift from the confirmed runtime source was found.
Owner-only fixture adaptations and extra canary-phase security tests remain
destination-only. Next: parent reviews the final local commit/worktree before
any publishing approval request. Worker/Ocala preservation and no-activation
requirements still apply. No push, PR, merge or production action is authorized.
