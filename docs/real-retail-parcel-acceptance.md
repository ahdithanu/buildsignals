# Real Retail-To-Parcel Acceptance

November22,2026. Local acceptance only, on the isolated retail integration branch
based on released maincdd7ee4. No production ingestion, configuration, sources,
schedules, access, deployment or paid-model calls changed in this task. This is
not new live geographic coverage. Cherry Hill remains DRAFT/UNSENT.

## Evidence And Scope

The separately approved capture used3physical GETs/20,107response-body bytes,
within100parcel rows/6GETs/2MiB. It retained one real ALDI sign application and62
distinct county parcel IDs;63received parcel rows include a repeated anchor.
No owner/contact fields, parcel boundaries, listings or effective zoning rules
were captured. The provider marked the spatial response transfer-limited, so
this is a bounded subset, not an exhausted neighborhood population. Publisher
currentness remains unknown. A sign filing is not proof of a store opening.

The source-scoped parcel reference, street, city and state corroborate one
anchor. A one-filing audit reports1address-corroborated,0ambiguous,0unmatched
and0conflicting-address cases; this is not a population match rate or calibrated
identity probability. Capture hashes and detailed receipts remain private.

## Verified Journey

1. Replay the immutable retained rows through the real Socrata/ArcGIS connectors,
   catalog mappings, normalization, raw storage, company matching and graph code.
   Each isolated local tenant has1permit,62parcels and63raw records. Replaying
   the retained first page inserts/updates zero additional records. The parcel
   run remains partial with its checkpoint; no invented source-exhaustion page
   or full-snapshot retirement is used. These tenants repeat the same62IDs;
   their combined row count is not unique geographic inventory.
2. Create the initial opportunity through the existing retailer opportunity
   service, deriving its identity from the real filing rather than inserting a
   fabricated deal. This setup precedes the browser portion. Retailer identity
   confirmation is distinct from confirming an opening.
3. In the actual API/browser, explicitly accept the corroborated parcel identity
   using a local agent/test actor. The recorded confidence0.5 is an uncalibrated
   engineering input, not a source fact or human-approved review. The rationale
   and private manifest say so. Persist the audit/raw/hash provenance and leave
   native permit coordinates null.
4. Preview the labelled reviewed parcel centroid and explicitly search0.25miles.
   PostGIS returns47centroid candidates from the retained cohort;15other retained
   centroids lie outside that radius despite the source's polygon-intersection
   query. The map renders47markers, with no invented parcel boundaries.
5. Inspect a non-anchor parcel and its evidence. Sale availability, zoning,
   effective use rules and entitlements remain unknown/not assessed; no AI or
   financial-return claim is made. Parcel land area is not building square feet.
6. Shortlist and promote into a saved opportunity, reload, retry promotion and
   receive the same saved deal. The search preserves reviewed-anchor provenance.
   No additional source request or model call occurs during replay or browsers.

## Verification Receipts

| Gate | Result |
| --- | --- |
| Private capture policy | 7offline tests passed; independent review passed |
| Replay/target guards | 7offline tests passed, including RED/GREEN exact owned database/role/port/nonce binding |
| Raw/canonical reconciliation | Exact63raw payloads and62canonical parcels per checked cohort, unchanged native permit coordinates; read-only transactions |
| Actual restricted PostgreSQL negative checks | 6passed/5.71s on the original completed cohorts: own-read controls, cross-tenant API/direct-SQL denial, role restrictions, no-store/no-write GETs and93demo write denials |
| Real-corpus desktop/mobile journey | 2passed/21.7s, zero skips/retries; actual API, no fulfilled response mocks |
| Corrected display desktop/mobile postcheck | 2passed/12.9s, zero retries; existing saved real opportunities, no business writes; null facts/risk stay unknown after reload |
| Final extended read-only desktop/mobile postcheck | 2passed/15.1s; also waits for saved graph/source context and follows the persisted parcel link; supersedes the12.9s postcheck |
| Checked-in synthetic browser regression | 2passed/13.9s, zero retries; null facts/risk and unknown display asserted after reload |
| Focused frontend regression | 45passed/1.39s after18reproduction failures |
| Full frontend suite | 697passed/86files7.83s; expected error-boundary fixture stderr retained |
| Typecheck / build | Passed; build8.53s with existing Zod annotation/chunk-size warnings |
| Scoped ESLint | Zero errors; one existing unused-disable warning in the deal adapter |

The browser console is not described as clean: deliberately blocked external
fonts/analytics and expected authentication401responses are recorded. Neither
final real-data run reported uncaught page errors or forbidden business writes.
The6negative tests used earlier completed tenants; the final real browser used
new isolated tenants for the explicit agent-review manifest. They are separate
receipts, not one stitched full-suite run.

The saved opportunity's graph link retains parcel, candidate, search and promotion
evidence and opens the real parcel map. The top signal-location panel still only
plots native geocoded permit matches, so this case truthfully shows no geocoded
permit/planning evidence there. This task does not claim a new parcel-led map in
that panel. The original reviewed-anchor search map remains populated.

The backend implementation did not change in this slice. Its previous3592test
full-suite receipt remains historical; it was not rerun merely for reassurance.
Current restricted-database/replay/API checks are recorded above. No fresh hosted
CI or production acceptance is implied. Private operational details stay ignored.
Post-acceptance schema/role/drift checks passed. Owned local database/volumes were
removed and database/browser ports verified clear; unowned processes preserved.

## Display Defect Found And Fixed

Visual review caught missing asking price/year/building area displayed as0 and
missing risk displayed as medium. The deal adapter/types now preserve null;
currency formatting and overview/preview badges show unknown, while genuine
recorded zeros remain zero. Added regression cases exercise malformed, missing
and known values; the existing synthetic browser gate asserts these displays.
This fixes the reviewed deal path, not every legacy dashboard/score fallback.

## Repeatable Offline Commands

Run from this product checkout with the existing locked dependencies, Node22 and
the project Python environment; no model key is needed:

```sh
npm exec --offline -- vitest run src/test/deal-financial-unknowns.test.ts src/test/deal-inbox-preview.test.tsx
npm exec --offline -- vitest run
npm run typecheck
npm run build
CI=1 node node_modules/@playwright/test/cli.js test -c e2e/reviewed-anchor.playwright.config.ts --workers=1 --retries=0 --trace=off
python3 scripts/agent_status.py --check
```

The checked-in browser command uses labelled synthetic rows in disposable local
storage. It must not be presented as another real-record capture. Real-corpus
replay/browser commands require the retained private corpus, pinned hashes and a
fresh independently verified restricted local database; detailed targets and
operational commands are deliberately not copied into public documentation.

Remaining release gates: separately authorized publication/hosted checks and
production release. Additional parcel capture/intake and effective use-rule or
listing evidence need their own applicable source/access scope. Do not repeat
the consumed capture or treat this local test as a production intake approval.
