# Wedge-market source qualification — NoVA data-center alley, DFW, and Census BPS baseline

Date: 2026-10-17
Author: ahdi@uaconsulting.co (research pass)
Scope: candidate feeds to ADD for the wedge markets, using only existing adapters
(`arcgis`, `socrata`, `legistar`, `ckan`, `opendatasoft`, `rss`, `civicplus_newsflash`,
`json_array`, `csv`, `planning_documents`, `html_document_index`).

This is a research/qualification note only. It proposes draft `candidate_catalog.json`
entries — nothing here is activated, and no existing file was edited.

## Method notes and constraints learned from the code

- **Valid `record_type` values are `permit`, `parcel`, `planning`** only
  (`app/services/ingestion/service.py:291`, `app/services/ingestion/onboarding.py:32`).
  Land-application / planning-case feeds map to `planning`; aggregate permit counts
  are filed as `permit` with an explicit aggregate caveat.
- **The `arcgis` connector takes its endpoint from `base_url`** and reads
  `where` / `out_fields` / `order_by_fields` / `keyset_field` / `include_geometry` /
  `include_centroid` / `query` out of `probe_settings.connector`
  (`connectors/factory.py:62`). It works against both `/FeatureServer/<n>/query` and
  `/MapServer/<n>/query` endpoints (existing entries use both).
- **The `csv` connector uses `csv.DictReader` and treats the FIRST row as the header**
  (`connectors/csv.py:64`). A source with more than one header row mis-parses. This is
  the binding constraint on the Census BPS entry below.
- No existing key or `base_url` collides with the proposals below. (Related but distinct
  existing NoVA entries: `fairfax_county_va_development_tracker_site_records`,
  `norfolk_va_*`, `virginia_beach_va_*`, `lynchburg_va_*`, `montgomery_county_md_*`,
  `virginia_vgin_statewide_parcels_narrow`. Related DFW entries already live:
  `fort_worth_tx_civic_commercial_permits`, `arlington_tx_commercial_permit_applications`,
  `arlington_tx_commercial_issued_permits`, `collin_county_tx_parcels_nearby_narrow`;
  candidate: `grand_prairie_tx_planning_cases`, `rockwall_tx_*`, `mesquite_tx_*`,
  `dallas_tx_legistar_planning_agendas`.)

---

## Ready to qualify (rights-clean / candidate-grade)

### 1. Loudoun County, VA — LOLA land applications (data-center alley)

- **Jurisdiction:** Loudoun County, VA (Ashburn / Dulles data-center corridor)
- **Endpoint:** `https://logis.loudoun.gov/gis/rest/services/Projects/LOLA_DATA/MapServer/0/query`
  (layer 0 = `LOLA_PLANS_POLY`, the Loudoun Online Land Applications dataset)
- **Adapter:** `arcgis`
- **Record type:** `planning`
- **Why it matters:** LOLA is the county's land-application tracker. For the data-center
  wedge, the earliest durable public signal is a rezoning / special-exception /
  commission-permit application — exactly what this layer carries (`PlanType`,
  `PlanStatus`, `PlanDescription`, `PlanName`) before any building permit issues.
- **Verified schema:** 14 fields; `maxRecordCount` 10,000; capabilities Map/Query/Data;
  JSON/geoJSON/PBF. Useful fields: `PlanNumber`, `PlanApplicationDate`, `PlanType`,
  `PlanStatus`, `PlanDescription`, `PlanName`. No address/parcel/decision-date fields are
  exposed. `AssignedTo` / `AssignedEmail` are staff-contact fields and should be suppressed.
- **Rights / license:** The GeoHub/data.gov harvest records mark Loudoun datasets as
  **public access and use**, and the dataset's only linked "license" is the county GIS
  disclaimer page (`https://logis.loudoun.gov/loudoun/disclaimer.html`), which is a
  **liability disclaimer that is silent on redistribution or commercial reuse** — it
  neither grants nor restricts. This is an *implied-open / public-access posture*, not an
  affirmative written grant. It is comparable to the Bend, OR "Custom License" candidates
  already carried at candidate status: fetch + canary are reasonable, but promotion to
  customer-facing writes should wait on a one-line confirmation from Loudoun OMAGI
  (mapping@loudoun.gov / 703-771-5778). Source for the public-access posture:
  data.gov harvest of the Loudoun GeoHub (e.g. the "Loudoun Online Land Applications (LOLA)
  Map" and "Loudoun Subdivisions" records, which list GeoServices REST + CSV/GeoJSON
  downloads and "public access").
- **Honest uncertainty:** License is posture, not a document. The layer is polygon-only
  and omits address/parcel, so geocoding will lean on the plan geometry centroid or a
  downstream parcel join. Refresh cadence for LOLA is not published on the service.

```json
{
  "key": "loudoun_county_va_lola_land_applications",
  "name": "Loudoun County LOLA Land Applications",
  "adapter": "arcgis",
  "record_type": "planning",
  "jurisdiction": "Loudoun County, VA",
  "base_url": "https://logis.loudoun.gov/gis/rest/services/Projects/LOLA_DATA/MapServer/0/query",
  "official_landing_page": "https://www.loudoun.gov/3362/LOLA",
  "license": "GeoHub/data.gov public-access-and-use posture; only linked terms are a liability-only GIS disclaimer silent on reuse. Candidate-grade; confirm commercial reuse with Loudoun OMAGI before promotion.",
  "status": "needs_rights_review",
  "early_warning_value": "Loudoun land applications (rezoning, special exception, commission permit, subdivision, site plan) are the earliest durable public signal of data-center-alley development before any building permit issues.",
  "candidate_source_fields": [
    "OBJECTID",
    "PlanNumber",
    "PlanApplicationDate",
    "PlanType",
    "PlanStatus",
    "PlanDescription",
    "PlanName"
  ],
  "probe_settings": {
    "connector": {
      "page_size": 25,
      "where": "PlanNumber IS NOT NULL",
      "out_fields": "OBJECTID,PlanNumber,PlanApplicationDate,PlanType,PlanStatus,PlanDescription,PlanName",
      "order_by_fields": "PlanApplicationDate DESC,OBJECTID DESC",
      "include_geometry": false,
      "query": { "f": "json", "outSR": 4326 }
    },
    "defaults": {
      "county": "Loudoun",
      "state": "VA",
      "jurisdiction": "Loudoun County",
      "permit_type": "land_application",
      "approval_stage": "pre_approval"
    },
    "signal_stage": "pre_approval",
    "freshness_field": "PlanApplicationDate",
    "freshness_semantics": "filing_event_at",
    "canary_required_fields": ["PlanNumber", "PlanType", "PlanStatus"]
  },
  "probe_field_mappings": [
    { "source_field": "PlanNumber", "canonical_field": "source_record_id", "is_required": true },
    { "source_field": "PlanNumber", "canonical_field": "application_number" },
    { "source_field": "PlanNumber", "canonical_field": "permit_number" },
    { "source_field": "PlanApplicationDate", "canonical_field": "filed_at", "transform": "date" },
    { "source_field": "PlanType", "canonical_field": "permit_type" },
    { "source_field": "PlanStatus", "canonical_field": "status" },
    { "source_field": "PlanName", "canonical_field": "project_name" },
    { "source_field": "PlanDescription", "canonical_field": "description" }
  ],
  "can_run_canary": true,
  "last_checked_on": "2026-10-17",
  "next_audit_on": "2026-11-17",
  "notes": "Layer 0 LOLA_PLANS_POLY verified 2026-10-17: 14 fields, maxRecordCount 10000, Map/Query/Data capabilities. Suppress AssignedTo/AssignedEmail (staff contacts) and raw polygon geometry. Polygon-only layer with no address or parcel field; geocoding needs plan centroid or a downstream Loudoun parcel join. Rights posture is public-access/disclaimer-only; confirm commercial reuse with OMAGI before any customer-facing write."
}
```

### 2. US Census Building Permits Survey (BPS) — South Region annual place file (historical baseline)

- **Jurisdiction:** US Census Bureau (federal); South Region file covers **both** wedge
  regions (Virginia + Texas permit-issuing places).
- **Endpoint (source):**
  `https://www2.census.gov/econ/bps/Place/South%20Region/so2025a.txt`
  (annual place-level file; the `so<YYYY>a.txt` pattern runs 1980→2025, latest = `so2025a.txt`)
- **Adapter:** `csv`
- **Record type:** `permit` (AGGREGATE counts, not individual permits — see caveat)
- **Why it matters:** BPS gives a consistent, authoritative, decades-long baseline of
  residential permit volume/valuation per permit-issuing place. It is the right historical
  normalizer for both NoVA and DFW — "is this place's current activity high or low vs its
  own history."
- **Rights / license:** **Public domain.** This is a US federal government work
  (17 U.S.C. §105); Census publishes it for public download with no reuse restriction
  stated on the file-listing page. This is the cleanest-rights item in the set.
- **BINDING CAVEAT — format:** The raw place `.txt` is comma-delimited but has **two
  header rows plus a blank line** before data (verified 2026-10-17: line 1 = column
  groups, line 2 = sub-labels, line 3 = blank, data from line 4). The `csv` connector uses
  `csv.DictReader` and assumes a **single** header row, so it will NOT parse this file
  correctly as-is. To use the `csv` adapter, point it at a **single-header normalized
  mirror** of the file (one preprocessing step to flatten the two header rows into one and
  drop the blank line). Alternatives worth weighing: HUD's SOCDS Building Permits Database
  (same underlying BPS data, re-tabulated) as a cleaner single-header export source.
- **Honest uncertainty:** There is no documented `api.census.gov` JSON endpoint for BPS
  (hence `csv`). Rows are aggregate per-place/per-year, so they do not fit the
  individual-permit record model cleanly even though `permit` is the closest allowed
  `record_type`; treat these as a baseline/context layer, not as opportunity rows.

```json
{
  "key": "census_bps_south_region_place_annual_baseline",
  "name": "Census Building Permits Survey - South Region Place Annual Baseline",
  "adapter": "csv",
  "record_type": "permit",
  "jurisdiction": "US Census Bureau (South Region places)",
  "base_url": "https://www2.census.gov/econ/bps/Place/South%20Region/so2025a.txt",
  "official_landing_page": "https://www.census.gov/construction/bps/",
  "license": "Public domain (US federal government work, 17 U.S.C. 105). No reuse restriction stated.",
  "status": "needs_format_normalization",
  "early_warning_value": "Decades-long authoritative baseline of residential permit volume and valuation per permit-issuing place; historical normalizer for both NoVA and DFW wedge markets.",
  "candidate_source_fields": [
    "Survey Date",
    "State Code",
    "6-Digit ID",
    "County Code",
    "FIPS Place Code",
    "Place Name",
    "1-unit Bldgs",
    "1-unit Units",
    "1-unit Value",
    "5+ units Bldgs",
    "5+ units Units",
    "5+ units Value"
  ],
  "probe_settings": {
    "connector": {
      "source": "https://www2.census.gov/econ/bps/Place/South%20Region/so2025a.txt",
      "delimiter": ",",
      "page_size": 500,
      "verify_snapshot": true
    },
    "defaults": {
      "country": "US",
      "jurisdiction": "US Census BPS",
      "permit_type": "residential_permits_annual_summary",
      "record_grain": "place_year_aggregate"
    },
    "signal_stage": "historical_baseline"
  },
  "probe_field_mappings": [
    { "source_field": "__source_record_id", "canonical_field": "source_record_id", "transform": "join_fields", "transform_options": { "fields": ["FIPS Place Code", "Survey Date"], "separator": "|" }, "is_required": true }
  ],
  "can_run_canary": false,
  "last_checked_on": "2026-10-17",
  "next_audit_on": "2026-11-17",
  "notes": "RIGHTS CLEAN (public domain). FORMAT BLOCKER: raw so2025a.txt has two header rows + a blank line before data (verified 2026-10-17); csv.DictReader assumes one header row and will mis-parse it. Point the csv connector at a single-header normalized mirror, or evaluate HUD SOCDS as a cleaner single-header source. Field names above are placeholders pending the normalized header; the full probe_field_mappings must be rebuilt against the flattened header. Rows are place-year aggregates, not individual permits."
}
```

---

## Blocked / needs rights (do NOT activate)

### 3. Prince William County, VA — Pending Planning Cases (data-center alley) — RIGHTS CONFLICT

- **Endpoint:** `https://gisweb.pwcva.gov/arcgis/rest/services/CountyMapper/LandDevelopment/MapServer/2/query`
  (layer 2 = "Pending Planning Cases"); adapter `arcgis`, record_type `planning`.
- **Why it would matter:** Highest-value NoVA data-center signal after Loudoun — PWC
  rezonings / special-use permits (`PlanningCaseType` values AFD, CPA, PRA, PFR, REZ, SUP,
  ZMA) are how data-center campuses move through the county. Verified fields include
  `PlanningCaseNumber`, `PlanningCaseType`, `status`, `PlanningCaseName`, `vlv_desc`,
  `TransmittalDate`, `MagisterialDistrict`, `EnergovID`; `maxRecordCount` 2000; Query
  supported. `mail` / `phone` / `pln_case_planner` / `link_staff` are contacts to suppress.
- **Why blocked:** The rights are **contradictory and lean restrictive.** The service
  `copyrightText` is "Prince William County, VA." The dataset `licenseInfo` is an
  as-is/no-warranty disclaimer that **requires the user to indemnify the county** and says
  the county "reserves the right to deny access to certain datasets." An archived county
  GIS terms excerpt (quoted on the OpenStreetMap wiki) states the digital maps "will not be
  reformatted or copied, nor be further reproduced, distributed or permitted to be used by
  any other person" — an explicit redistribution bar. A single informal 2020 email from a
  county GIS analyst (OSM mailing list) claims the data is public domain with no
  restrictions, but that is secondhand and unverified against any official page.
- **Action:** Do not activate. Pursue a written commercial-reuse grant from PWC GIS/DoD.
  Until then this stays out of the pipeline despite its high signal value.

```json
{
  "key": "prince_william_county_va_pending_planning_cases",
  "name": "Prince William County Pending Planning Cases",
  "adapter": "arcgis",
  "record_type": "planning",
  "jurisdiction": "Prince William County, VA",
  "base_url": "https://gisweb.pwcva.gov/arcgis/rest/services/CountyMapper/LandDevelopment/MapServer/2/query",
  "official_landing_page": "https://www.pwcva.gov/department/planning-office",
  "license": "CONFLICTING: service copyrightText 'Prince William County, VA'; dataset licenseInfo is as-is with a user-indemnification requirement; archived county GIS terms bar reformatting/copying/redistribution; one informal 2020 email claims public domain (unverified). Treat as restricted.",
  "status": "legal_hold",
  "blocker_summary": "High-value NoVA data-center signal (REZ/SUP/ZMA pending cases) but rights are contradictory and lean restrictive. Needs a written commercial-reuse grant from PWC before any fetch/canary against production.",
  "early_warning_value": "Pending rezonings, special-use permits, and plan amendments are how data-center campuses advance in Prince William County before issuance.",
  "candidate_source_fields": [
    "PlanningCaseNumber",
    "PlanningCaseType",
    "PlanningCaseName",
    "status",
    "vlv_desc",
    "TransmittalDate",
    "MagisterialDistrict",
    "EnergovID"
  ],
  "can_run_canary": false,
  "last_checked_on": "2026-10-17",
  "next_audit_on": "2026-11-17",
  "notes": "Layer 2 verified 2026-10-17: 20 fields, maxRecordCount 2000, Map/Query/Data. Suppress mail/phone/pln_case_planner/link_staff. BLOCKED on rights conflict; do not fetch against production until PWC confirms commercial reuse in writing. Sources: service metadata, dataset licenseInfo, PWC GTS disclaimer (pwcva.gov/disclaimer), and the OSM wiki 'Prince William County, Virginia' terms excerpt."
}
```

### 4. City of Dallas — Building Permits (Socrata `e7gq-4sah`) — STALE

- **Endpoint:** `https://www.dallasopendata.com/resource/e7gq-4sah.json`; adapter `socrata`,
  record_type `permit`. Fields: `permit_number`, `permit_type`, `issued_date`,
  `work_description`, `value`, `area`, `land_use`, `street_address`, `zip_code`,
  `contractor`, `mapsco`.
- **Why blocked:** The dataset is **historical and no longer updated** — `rowsUpdatedAt`
  ≈ 2020-08-30, and the dataset page states active permit tracking moved to the Dallas
  Accela Citizen Access portal. The portal provenance is "official" and there is no
  explicit restrictive license, so this is **blocked on freshness/value, not rights.**
  Dallas's live permits now sit behind Accela (no rights-clean machine API), which is a
  `portal`-shaped source, not one of the clean adapters.
- **Note on adjacency:** Dallas is one jurisdiction removed from Arlington (Grand Prairie,
  already a candidate, sits between them). If the goal is a live DFW add, this stale feed
  is not it.

### 5. Denton County, TX — DEV_Permits (ArcGIS MapServer) — BLANK LICENSE / COUNTY-INTERNAL

- **Endpoint:** `https://gis.dentoncounty.gov/arcgis/rest/services/DEV_Permits/MapServer/0/query`;
  adapter `arcgis`, record_type `permit`.
- **Why blocked:** Service/item license field is **blank**, and the service describes
  itself as the development-permit source feeding the county's internal Geocortex permit
  app — i.e., an operational layer, not a published open-data product. It is also a county
  layer (north DFW), less directly adjacent to Fort Worth/Arlington than the task targets.
  Needs rights confirmation and a schema probe before it could be considered.

---

## DFW honesty note (why the ready list is NoVA-heavy)

The DFW-adjacent search did not surface a *new*, live, rights-clean machine endpoint in the
Tarrant-County ring around Fort Worth + Arlington. The reasons are concrete:

- Most Tarrant suburbs (Mansfield, Grapevine, North Richland Hills, the HEB cities, etc.)
  run permitting on **Accela / Tyler / MyGov / OpenGov** transactional portals with no
  rights-clean bulk API — the same `portal` pattern already parked at candidate/hold
  status elsewhere in the catalog.
- **Grand Prairie** is already a candidate (`grand_prairie_tx_planning_cases`); Dallas's
  open Socrata permits feed is stale (item 4); Denton County's layer has blank rights
  (item 5).
- A promising-looking hosted FeatureServer (`services.arcgis.com/0L95CJ0VTaxqcmED/...
  PLANNINGCADASTRE_site_plan_case`) turned out to be **City of Austin** data (already live
  as `austin_tx_site_plan_cases`), not a DFW suburb — a red herring, not an add.

Recommendation for DFW: the cleanest next step is not another ArcGIS hunt but either
(a) a rights request to a specific Tarrant suburb's Accela/Tyler tenant, or (b) leaning on
the Census BPS baseline (item 2) plus the already-live Fort Worth + Arlington feeds for
near-term DFW coverage.

---

## Summary

- **Ready to qualify: 2** — Census BPS South Region (item 2, public-domain, but needs a
  single-header normalization step) and Loudoun County LOLA (item 1, candidate-grade
  public-access posture; confirm with OMAGI before promotion).
- **Blocked / needs rights: 3** — Prince William County Pending Planning Cases (item 3,
  rights conflict), City of Dallas permits (item 4, stale), Denton County DEV_Permits
  (item 5, blank license / county-internal).

**Top 3 to pursue first**
1. **Census BPS South Region baseline** — only fully rights-clean item; covers both wedge
   regions at once; one preprocessing step (flatten the 2-row header) unblocks it.
2. **Loudoun County LOLA** — highest data-center-alley signal value with a workable
   (public-access) rights posture; run a read-only canary, then get OMAGI's one-line
   reuse confirmation before any customer-facing write.
3. **Prince William County Pending Planning Cases** — second-highest NoVA data-center
   signal; worth a written rights request to PWC now so it can move from legal_hold to
   qualification once cleared.
