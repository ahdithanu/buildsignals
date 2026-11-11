# NJ Retail Anchor and Radius Qualification

November 11, 2026, America/Los_Angeles. Local root research branch
`codex/reviewed-city-expansion`, starting at `4669af1`. No production source,
database, schedule, task command, image or paid-model configuration changed.

## Historical Retail Evidence

The [municipally hosted engineering review](https://chnj.gov/DocumentCenter/View/13994/ERI-Review072523?bidId=),
page 1, is an engineering review dated July 25, 2023 for case `22-P-0043` and
identifies 1114 Wynwood Avenue, Block 133.01, Lot 7, Cherry Hill. The application's
filing date is unknown from this evidence. National Watch and Diamond Exchange /
1114 Wynwood LLC proposed connecting existing office buildings and introducing
retail space. This is a documented 2023 case-evidence point, not proof
of current approval, construction, opening, investment quality or sale availability.
The authority is the [Cherry Hill Planning Board](https://www.chnj.gov/113/Planning-Board).

An exact current NJGIN lookup used municipality `0409`, `PCLBLOCK='133.01'` and
`PCLLOT='7'`, retaining the existing nonnull/non-placeholder PIN predicate. The
count was one and the single fetched row matched those three fields. Current
`PROP_LOC` is `1110-1114 WYNWOOD AVE`, consistent with the document's site number.
The derived current parcel centroid is latitude `39.9209527164208`, longitude
`-75.03311482714757`. It is not a surveyed building/store entrance or historical
known-then coordinate. Parcel continuity between 2023 and today is unverified.

The first lookup exposed the address-mapping issue below. A second bounded
count/one-row pass used the corrected projection and `validate_source_projection`
before normalization. No owner/mail values or raw polygons are retained in this
receipt. HTTP wire-attempt counts were not instrumented; these are logical
operations, with the existing pinned transport and no transient retries.

## Mailing Address Correction

The [official MOD-IV manual](https://www.state.nj.us/treasury/taxation/pdf/lpt/modIVmanual.pdf#page=18),
printed page 17 / PDF page 18, distinguishes owner Street Address (03), owner
City/State (06), owner Zip Code (07) and physical Property Location (10).
NJGIN's [official parcel page](https://www.nj.gov/njgin/edata/parcels/) links this
manual. `ST_ADDRESS` and `CITY_STATE` are not parcel situs. The service's `ZIP5`
derivation was not independently established as situs ZIP, so it must remain
unknown rather than be promoted into the property's postal code.

Local corrections:

- Map `PROP_LOC` alone to address. A missing situs stays missing; never fall back
  to owner mail. `MUN_NAME` remains the municipality and state remains NJ.
- Remove ST_ADDRESS, CITY_STATE and ZIP5 from the catalog projection/allowlist,
  and remove ZIP5's postal mapping. Suppress ST_ADDRESS, CITY_STATE, ZIP_CODE,
  ZIP5 and ZIP_PLUS4 explicitly alongside owner/value/sale exclusions.
- Nearby scope requests only OBJECTID, PIN_NODUP, PAMS_PIN, PROP_LOC, MUN_NAME,
  CALC_ACRE and temporary geometry. Preserve PIN_NODUP identity, source provenance,
  unknown owner/sale/zoning facts, inactive/manual operation and export policy.
- Set `enforce_field_allowlist=true` on NJGIN. Shared validation is opt-in, checks
  configuration before fetching and rejects an entire unexpected-field page
  before any raw-record persistence. Main, stage and freshness canary pages use
  the same guard. Error messages never echo field values. Unflagged sources keep
  their existing behavior.

This is not proof that production ever stored the affected fields. Existing
registered-source settings, normalized addresses/postcodes, raw payloads and
source-specific facts require an authorized, tenant-scoped read-only audit
before deciding whether any repair is needed. No production records were read,
deleted, scrubbed or silently rewritten in this slice. The November 10 profile
must not be activated without this follow-up correction.

## Radius Contract

The original one-mile read-only query correctly stopped at its count gate:
**4,587 publisher rows**, exceeding the **2,000-record cap**. The sanitized
diagnostic used one logical aggregate operation and fetched zero sample pages.
An initial CLI invocation returned its generic failed receipt; the diagnostic
then identified the budget boundary. This is not a successful parcel download,
a publisher denial, or a reason to raise the cap.

The inactive profile now accepts 0.25..3 miles, matching the application's smaller
nearby-search scope without increasing the maximum radius or 2,000-row cap.
Bounds, scope-key separation and existing privacy tests passed before the live
quarter-mile check. The actual command was:

```sh
OPENROUTER_API_KEY= DATABASE_URL=sqlite:// .venv/bin/python -m scripts.retail_parcel_refresh \
  --source-key new_jersey_njgin_statewide_parcels_nearby_narrow \
  --anchor-id cherry-hill-22-P-0043-historical-block-reference \
  --latitude 39.9209527164208 --longitude -75.03311482714757 \
  --radius-miles 0.25 --max-records 2000 --verify
```

Exit 0: **161 before / 161 valid / 161 after**, **161 distinct**, zero duplicate
parcel rows. The scope SHA-256 is
`0ce7efcfbd438fe61095767aca8099ed941acf1507425927e107753732d2988a`.
The result explicitly reports `read_only=true`, `production_anchor_verified=false`,
`production_qualified=false` and `publisher_freshness=unknown`. These are current
source rows near a historical-reference anchor, not deployed inventory, unique
developments, current growth predictions or verified for-sale parcels. No raw
parcel rows/polygons were printed, persisted or committed by this public check.
Wire attempts were not measured. Temporal continuity, tenant ingestion and
production/browser map acceptance remain separate.

## Application Verification

`tests/test_njgin_scoped_ingestion.py` uses explicitly synthetic transport against
the real profile, connector, normalization and disposable SQLite persistence.
It checks source evidence, replay without duplicate parcels, permitted boundary
geometry in parcel detail, graph linkage, missing owner/sale/zoning facts and a
different registered tenant's 404. Poisoned second rows with ST_ADDRESS,
CITY_STATE, ZIP5 or OWNER_NAME fail both canary and run; no raw/parcel rows from
the page are stored. These are test fixtures, not real source examples or new
inventory. `tests/test_ingestion_projection.py` covers invalid allowlists,
sanitized rejection and unchanged opt-out behavior.

Targeted catalog/health/projection/profile/rollout/application checks passed
**329 tests**; the later quarter-mile/profile/projection/application subset passed
**86 tests**. Scoped Ruff and whitespace checks passed. The privacy-core frozen
root suite passed **2,452 tests with 70 skips**; the final frozen root run including
the quarter-mile regression passed **2,453 tests with 70 skips in 293.59s**.
Skips are not passes; no new
PostgreSQL RLS or browser acceptance is claimed.

The isolated integration worktree is `.worktrees/requested-market-release`,
branch `codex/requested-market-release`, based on production-privacy checkpoint
`5ff111f`. Its independent writer must preserve owner-only operations, the newer
worker's Ocala guards and 100k engine, and incorporate this correction rather
than copying the original NJ profile alone. It is not a deployment. See
`docs/releases/2026-11-11-requested-market-integration-plan.md`.
