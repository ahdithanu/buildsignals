# Columbus Historical-Source Intake Audit

Audit date: **2026-09-19**. Public endpoint observations: **18:40-18:42 UTC**.
Scope: BuildSignals sidecar audit of two existing catalog entries in the
`temporal-foundation` worktree. This document is the only file written by this
audit. No source activation, import, provisioning, push, deployment, or production
database inspection was performed.

## Decision

**Columbus is a candidate, not an accepted first market.** Both official public
endpoints were reachable and returned bounded aggregate results. Retrospective
event-date history is available today: site engineering from 2019 and commercial
building permits from 2010. That does not establish complete project coverage,
historical public availability, or BuildSignals knowledge at those dates.

The exact current catalog predicates matched **3,499 site rows** and **11,862
commercial permit rows** in this audit. These are live public-source aggregate
measurements, not imported inventory, distinct projects, configured source counts,
or proof that collection is operating. The commercial catalog's `ISSUED_YEAR >=
2025` predicate excludes most of the historical source; changing it requires a
separately approved intake, not this audit.

## Local Configuration Reviewed

Local evidence: `app/services/ingestion/catalog.json` (entries beginning at lines
8224 and 8412 at audit time), `app/services/ingestion/production_rollout.json`,
`tests/test_ingestion_catalog.py` (Columbus mapping tests), and
`docs/institutional-intelligence-roadmap.md` (P0.8 historical-input gate).
Rollout membership and fixture tests establish configuration intent only. No
configured source/shard total or test fixture is presented as a live measurement.

| Property | Site engineering | Commercial building permits |
| --- | --- | --- |
| Catalog key | `columbus_oh_site_engineering_applications` | `columbus_oh_commercial_building_permits` |
| Official layer | [S1] | [B1] |
| Selected population | Site Compliance Plan, plus commercial Lot Split; non-null identity, filing date, address | Commercial; issued year >= 2025; non-null identity, address |
| Event mapping | `B1_FILE_DD` -> `filed_at` | `ISSUED_DT` -> `issued_at`; no filing date mapping |
| Status mapping | `B1_APPL_STATUS`; Complete/Completed/Closed -> approved; everything else -> pre_approval | `PERMIT_STATUS`; default approval stage approved |
| Status date | `LAST_STATUS_DT` -> `status_updated_at` | `LAST_STATUS_DT` -> `status_updated_at` |
| Configured freshness | `B1_FILE_DD`, `filing_event_at` | `LAST_STATUS_DT`, **`filing_event_at`** |
| Reconciliation intent | Daily full snapshot | Periodic full |
| Paging intent | 1,000 rows; `OBJECTID ASC`, keyset `OBJECTID`; no geometry | Same |

The site predicate does not restrict every Site Compliance Plan to a commercial
subtype. Conversely, it excludes other engineering record types. Neither source
is a comprehensive commercial-project census.

## Official Metadata and Access Log

All URLs below are City of Columbus services or its ArcGIS organization. Access
date for every successful request in this section is **2026-09-19**.

| Check | UTC time | Result |
| --- | --- | --- |
| Site layer via web reader [S1] | Before 18:40:48 | Tool reported URL inaccessible/internal error; not evidence that the public service was down. |
| Site layer via sandboxed curl [S1] | 18:40:48 | `curl: (6) Could not resolve host: maps2.columbus.gov`; network-path failure, no provider payload. |
| Site layer via approved network retry [S1] | Approximately 18:41 | Valid ArcGIS JSON; name Site Engineering Permits, max record count 2,000, statistics and pagination supported. |
| Site application item [S2] | 18:41:13 | HTTP 200; public City application; describes records from 2019 onward; CC0 dedication in `licenseInfo`. |
| Building application item [B2] | 18:41:13 | HTTP 200; public application; advertises issued permits from 2010 onward plus historical permits through 1999; CC0 dedication. |
| Building service item [B3] | 18:41:13 | HTTP 200; owner `ColumbusOhioGIS`, organization `9yy6msODkIBzkUXU`; issued permits from 2010 onward, nightly updates; CC0 dedication. |
| Building layer, direct request [B1] | 18:41:14 | HTTP 200; BuildingPermits, max record count 2,000; date reference UTC; `dataLastEditDate` = 2026-09-19T09:03:44.238Z. |
| Six count/date aggregates [S3], [B4] | 18:41:28-18:41:31 | HTTP 200 for every query; one aggregate feature each; no ArcGIS error returned. |
| Eight annual/status/future-date aggregates [S3], [B4] | 18:41:49-18:41:51 | HTTP 200 for every query; no reported transfer-limit exceedance; at most 17 grouped rows returned. |
| Temporal metadata recheck [S1], [B1] | 18:42:02 | HTTP 200; both `isDataVersioned=false`, both `relationships=[]`. Site explicitly reports `supportsQueryWithHistoricMoment=false`, `startArchivingMoment=-1`; building layer provides no affirmative historic-moment archive evidence. |
| Application/map linkage [S4], [S5], [B5], [B6] | 18:42:02-18:42:15 | HTTP 200; site year views all reference layer 22; building map includes the catalog layer and two separate historic layers. |

Site metadata declares `America/New_York` with daylight-saving support; building
metadata declares UTC. The range table below renders returned epoch milliseconds
in UTC, without assuming a local-midnight interpretation. Field aliases mostly
repeat database names and do not supply a full lifecycle dictionary. Validate
calendar-day normalization before monthly cohorting.

The site app warns that accuracy and completeness are not guaranteed [S4]. Its
year-specific map views are filters over the same live layer, not versioned
snapshots [S5]. The building app's pre-2000 history is in separate layers [B6]:
`Historic_Building_Permits_No_CoO/FeatureServer/92` and
`Historic_Building_Permits/FeatureServer/0`. Their contents, rights scope, counts,
date ranges, and joinability were **not audited** here. They are not supplied by
either catalog entry. No coverage for 2000-2009 has been established.

CC0 is supported by the official item metadata, not merely copied from the local
catalog. Retain the catalog's attribution and personal-data suppression policies;
this is source-evidence review, not a legal opinion or authorization to redistribute
raw records. No individual permit payloads, personal names, attachments, or
geometries were downloaded for this audit.

## Measured Current-Snapshot Inventory

Dates are inclusive observed extrema, rendered as UTC dates. These are row counts
from the live layers, not distinct `B1_ALT_ID` counts. Separate requests are not a
transactionally frozen snapshot. Non-null counts do not establish nonblank or
valid identifiers, addresses, or parcels.

| Layer and predicate | Rows | Event-date non-null | Earliest event date | Latest event date | Address non-null |
| --- | ---: | ---: | --- | --- | ---: |
| Site, whole layer (`1=1`) | 6,368 | 6,368 | 2019-01-03 | 2026-09-16 | 5,803 |
| Site, selected types before required-field filters (`S_types`) | 3,812 | 3,812 | 2019-01-03 | 2026-09-16 | 3,499 |
| Site, exact catalog (`S_catalog`) | 3,499 | 3,499 | 2019-01-03 | 2026-09-16 | 3,499 |
| Building, whole layer (`1=1`, not commercial-only) | 682,462 | 682,462 | 2010-01-04 | 2026-09-17 | 682,012 |
| Building, all commercial (`B_types`) | 140,319 | 140,319 | 2010-01-04 | 2026-09-17 | 140,203 |
| Building, exact catalog (`B_catalog`) | 11,862 | 11,862 | 2025-01-02 | 2026-09-17 | 11,862 |

Measured via [S3] and [B4], 18:41:28-18:41:31 UTC. Every population above also
returned non-null `B1_ALT_ID` and `B1_PARCEL_NBR` counts equal to its row count.
Within the selected site types, **313 rows lack an address and are excluded**.
Across all commercial years, **116 rows lack an address**. The catalog's loss of
older commercial history is principally deliberate year filtering, not absence
from the public service. No change to either filter was made.

### Annual Distribution

Measured via grouping by the publisher's `FILED_YEAR` / `ISSUED_YEAR` fields,
18:41:49-18:41:51 UTC. Cross-checks between year fields and actual timestamps
remain open. Counts sum to their respective aggregate populations.

| Year | Site selected types | Site exact catalog | All commercial years | Commercial exact catalog |
| --- | ---: | ---: | ---: | ---: |
| 2010 | Not established | Not established | 7,172 | Excluded |
| 2011 | Not established | Not established | 8,489 | Excluded |
| 2012 | Not established | Not established | 9,251 | Excluded |
| 2013 | Not established | Not established | 10,115 | Excluded |
| 2014 | Not established | Not established | 9,353 | Excluded |
| 2015 | Not established | Not established | 8,989 | Excluded |
| 2016 | Not established | Not established | 8,630 | Excluded |
| 2017 | Not established | Not established | 9,166 | Excluded |
| 2018 | Not established | Not established | 9,368 | Excluded |
| 2019 | 60 | 47 | 9,620 | Excluded |
| 2020 | 43 | 34 | 7,366 | Excluded |
| 2021 | 53 | 41 | 8,040 | Excluded |
| 2022 | 253 | 225 | 7,803 | Excluded |
| 2023 | 855 | 792 | 7,617 | Excluded |
| 2024 | 922 | 858 | 7,478 | Excluded |
| 2025 | 957 | 890 | 6,957 | 6,957 |
| 2026, partial | 669 | 612 | 4,905 | 4,905 |

The sharp increase in site rows around 2022-2023 is a **coverage/comparability
question**, not a proven economic acceleration or proven data migration. Aggregate
results cannot distinguish those explanations. Monthly continuity, changes in
record types, retention, and omissions require provider reconciliation. Never
compare incomplete 2026 totals directly with complete calendar years.

## Event Semantics and Data-Quality Findings

1. **Filed is not issued.** Site `B1_FILE_DD` is the catalog's application-filing
   event date. The official building service explicitly concerns issued permits
   [B3]; `ISSUED_DT` is issuance, not application filing, construction start, or
   occupancy. The building schema has no `B1_FILE_DD`. Do not substitute issuance
   for filing or infer application-to-issuance lead time from this layer alone.
2. **Current status is not a status history.** `LAST_STATUS_DT` describes the
   current status record, not an observed sequence of transitions. The site
   catalog's Complete/Completed/Closed -> approved rule needs a verified city
   lifecycle dictionary; Closed does not independently prove project approval.
   Live site counts were Active 66, Approved 2, Closed 692, Complete 726,
   Completed 1,584, Corrections Required 364, and Under Review 65. The **two
   literal Approved records fall through the current rule to pre_approval**.
3. **Issued does not mean currently active.** Exact-catalog commercial counts
   were Certificate of Occupancy Issued 351, Expired Permit 227, Final Inspection
   Approved 7,332, and Permit Issued 3,952. Defaulting all to an approved stage is
   only broad issued-permit context, not evidence of current approval validity,
   active construction, or a recent approval event.
4. **Freshness configuration conflates concepts.** Commercial `LAST_STATUS_DT`
   is labeled `filing_event_at` despite being mapped to `status_updated_at`.
   Site filing recency and building status recency are neither collection health
   nor dataset refresh time. The observed building dataset edit timestamp is
   dataset-level evidence only, not per-record publication time. Both entries
   request 48-hour date validation; that is a configured rule, not proof of
   successful ingestion or source SLA compliance.
5. **Future status anomaly measured.** Site maximum `LAST_STATUS_DT` was
   2026-09-17T11:23:16Z. Commercial maximum was **2026-10-23T00:00:00Z**, both for
   all commercial rows and the exact catalog, beyond the audit date. A bounded
   count using `LAST_STATUS_DT > TIMESTAMP '2026-09-21 18:41:00'` returned **1**
   exact-catalog commercial row and **0** site rows. The whole building layer's
   maximum was 2026-10-30T00:00:00Z. This proves a date anomaly, not its cause or
   how ingestion currently handles it. Quarantine/flag and test it before using
   latest-status timestamps in freshness or baseline calculations.

These findings come from catalog inspection and the bounded status/date
aggregates [S3], [B4]. No catalog or application code was modified.

## Overlap and Completeness Limits

- Site engineering and commercial permits can describe different stages or
  components of the same physical project. They are not two additive project
  universes. One site may have many alterations, trade permits, phases, or lot
  splits; approved site work does not guarantee a subsequent building permit.
- Neither layer advertises relationship records (`relationships=[]`). Cross-layer
  identity overlap, duplicate permit identifiers, and distinct-project counts
  were **not measured**. Preserve `(source_key, B1_ALT_ID)` identities; do not
  treat `OBJECTID` or matching parcel/address alone as a cross-source project ID.
  Future linkage needs explicit record references where possible, then reviewed
  parcel/address/time/project evidence, with ambiguous and unmatched cases kept.
- The defensible starting geography is the issuing City of Columbus jurisdiction,
  not the whole Columbus metropolitan area or a utility service territory.
  Suburban issuers, parcel boundary changes, annexations, and utility boundaries
  require independent coverage review. Map extent and hardcoded city defaults
  do not prove jurisdiction membership for every record.
- Null-address filtering can systematically remove early-stage or unusual-site
  projects. Non-null parcel fields do not establish valid/current parcel joins.
  Missing or changing geometry, non-geocoded records, deleted records, blank
  fields, duplicate identities, and historical corrections remain unquantified.
- Valuation, square footage, and units are available in the commercial schema,
  but their missingness, units, revisions, and overlap across component permits
  were not audited. Permit counts cannot stand in for physical expansion,
  expenditure, electrical load, available power, or investment outcomes.

## Historical Availability Contract

Treat any future approved download of these layers as a **retrospective archive
observed at capture time**, not an as-known-then corpus. An event dated 2019 and
first captured in 2026 is not eligible for a 2019 knowledge cutoff. Preserve source
event time, source status/update time, trusted raw receipt, and server-assigned
observation/event recording times separately. Do not backdate receipt or recording
from `FILED_YEAR`, `ISSUED_YEAR`, item creation, or event dates.

The site app item was created in 2026; the building service item in 2023. Those
metadata dates identify these items, not the earliest possible public availability
of their records. Earlier publication might have existed elsewhere, but this audit
did not prove it. No historical record versions or contemporaneous publication
archives were retrieved. Future cutoff-safe reads must require trusted receipt
and recording <= cutoff and must not join today's statuses or entity resolutions
into a historical answer. A present-day retrospective event-date baseline can be
useful when labeled honestly; it is not a leakage-free historical backtest.

## First-Market Qualification Gates

All gates remain open unless explicitly limited to the metadata/reachability
checks completed above. These are proposed acceptance requirements, not permission
to start intake or scoring. Each acceptance needs an owner, method version,
dated evidence, reviewer, and recorded limitations.

| Gate | Required evidence before acceptance |
| --- | --- |
| Geography and scope | Written City-only pilot boundary or independently qualified additional issuers; utility service-area crosswalk where power claims are contemplated. |
| Rights and admission | Reviewed source/item-specific rights, attribution, approved field set, privacy suppression, bounded collection plan, and separate operational authorization. CC0 metadata was verified; operational admission was not. |
| Comparable history | Reconcile sparse site years and monthly missingness with publisher evidence. Proposed baseline floor: 36 consecutive complete, comparable months for each admitted series, with versioned category definitions. This is a proposed floor, not a claim of adequacy or existing acceptance. The current commercial filter supplies less than two complete years and cannot pass it. |
| Measured inventory | Approved capture with counts before/after every filter, distinct IDs, null/blank/error rates, pagination reconciliation, raw evidence hashes, schema/query versions, and a completed-month cutoff. Unavailable periods stay unknown, never zero. |
| Lifecycle and dates | Verified stage dictionary; explicit Approved handling; distinction among closed, expired, issued, completed and occupied; future-date disposition; timezone/year consistency tests; correct freshness semantics. |
| Project overlap | Labeled cross-source linkage cases and measured duplicate/unmatched/ambiguous rates; one-to-many relationships retained; no double-counting of projects or valuation. |
| Temporal integrity | Trusted non-backdated receipt/recording; immutable raw evidence; correction/retraction handling; tests proving old event dates and today's graph/status facts cannot leak into earlier cutoffs. |
| Baseline acceptance | Explicit event unit (filings versus issuances), comparable cohorts, missingness policy, seasonality and partial-period handling, minimum sample policy, reproducible numeric outputs and reviewer approval. Available source depth alone is not sufficient. |
| Broader signal evidence | Independent land/construction/infrastructure/utility evidence as required by the selected signal. These two permit sources alone do not qualify a Power Constraint, Capital Stress, or investment-performance claim. |

Recommended next decision: evaluate a bounded **City of Columbus retrospective
permit baseline** only after resolving these gates, with a separately approved
older-commercial-history scope. Keep prospective observation history distinct.
This document does not select or activate Columbus as the first market.

## Reproducible Read-Only Query Specification

Every measured result above came from GET requests to [S3] or [B4], with a
25-second request timeout, `f=json`, and `returnGeometry=false`. No raw row
pagination was used. The six summary queries returned one aggregate row each;
grouped requests used `resultRecordCount=100` and ascending group order. The
server still scans the predicate population: bounded here means fixed request
count and small response, not an `OBJECTID` sample or a truncated historical range.

Exact predicates:

```sql
-- S_types
(B1_PER_TYPE = 'Site Compliance Plan' OR
 (B1_PER_TYPE = 'Lot Split' AND B1_PER_SUB_TYPE = 'Commercial'))

-- S_catalog
B1_ALT_ID IS NOT NULL AND B1_FILE_DD IS NOT NULL
AND SITE_ADDRESS IS NOT NULL
AND (B1_PER_TYPE = 'Site Compliance Plan' OR
     (B1_PER_TYPE = 'Lot Split' AND B1_PER_SUB_TYPE = 'Commercial'))

-- B_types
B1_PER_TYPE = 'Commercial'

-- B_catalog
B1_ALT_ID IS NOT NULL AND SITE_ADDRESS IS NOT NULL
AND B1_PER_TYPE = 'Commercial' AND ISSUED_YEAR >= 2025
```

For each layer, query `1=1`, its type predicate, and its exact catalog predicate.
Use the following `outStatistics`, replacing `EVENT_FIELD` with `B1_FILE_DD`
for site engineering or `ISSUED_DT` for building permits:

```json
[
  {"statisticType":"count","onStatisticField":"OBJECTID","outStatisticFieldName":"row_count"},
  {"statisticType":"count","onStatisticField":"EVENT_FIELD","outStatisticFieldName":"dated_count"},
  {"statisticType":"min","onStatisticField":"EVENT_FIELD","outStatisticFieldName":"min_date"},
  {"statisticType":"max","onStatisticField":"EVENT_FIELD","outStatisticFieldName":"max_date"},
  {"statisticType":"min","onStatisticField":"LAST_STATUS_DT","outStatisticFieldName":"min_status_date"},
  {"statisticType":"max","onStatisticField":"LAST_STATUS_DT","outStatisticFieldName":"max_status_date"},
  {"statisticType":"count","onStatisticField":"B1_ALT_ID","outStatisticFieldName":"id_count"},
  {"statisticType":"count","onStatisticField":"SITE_ADDRESS","outStatisticFieldName":"address_count"},
  {"statisticType":"count","onStatisticField":"B1_PARCEL_NBR","outStatisticFieldName":"parcel_count"}
]
```

Annual/status queries use just count of `OBJECTID` as `n`, plus
`groupByFieldsForStatistics` and `orderByFields=<group> ASC`: `FILED_YEAR` for
`S_types` and `S_catalog`, `ISSUED_YEAR` for `B_types` and `B_catalog`,
`B1_APPL_STATUS` for `S_catalog`, and `PERMIT_STATUS` for `B_catalog`.
The two anomaly queries use `returnCountOnly=true` and append
`AND LAST_STATUS_DT > TIMESTAMP '2026-09-21 18:41:00'` to the parenthesized exact
catalog predicate. No `outStatistics` is sent for those count-only requests.
URL-encode parameters normally; reject JSON `error` or reported transfer-limit
exceedance rather than interpreting them as zero rows. Re-running these live
queries can produce different results; this document records this audit's results,
not a promise of immutable provider responses.

## Official Primary URLs

All accessed **2026-09-19**, with outcomes and times recorded above. Query endpoint
links identify the official operation; the specification above supplies the exact
parameters used for each recorded measurement.

- [S1: Site layer metadata][S1]
- [S2: Site application item and license][S2]
- [S3: Site aggregate query endpoint][S3]
- [S4: Site application configuration and disclaimer][S4]
- [S5: Site web map and year-layer linkage][S5]
- [B1: Building layer metadata][B1]
- [B2: Building application item and license][B2]
- [B3: Building service item, period, update description, and license][B3]
- [B4: Building aggregate query endpoint][B4]
- [B5: Building application configuration][B5]
- [B6: Building web map, including separate historic layers][B6]

[S1]: https://maps2.columbus.gov/arcgis/rest/services/Schemas/BuildingZoning/MapServer/22?f=pjson
[S2]: https://columbus.maps.arcgis.com/sharing/rest/content/items/be5e75e4c59e467faf29b6cd99c39113?f=json
[S3]: https://maps2.columbus.gov/arcgis/rest/services/Schemas/BuildingZoning/MapServer/22/query
[S4]: https://columbus.maps.arcgis.com/sharing/rest/content/items/be5e75e4c59e467faf29b6cd99c39113/data?f=json
[S5]: https://columbus.maps.arcgis.com/sharing/rest/content/items/64246d4e72b2461ea10015af83aceb03/data?f=json
[B1]: https://services1.arcgis.com/9yy6msODkIBzkUXU/arcgis/rest/services/Building_Permits/FeatureServer/0?f=pjson
[B2]: https://columbus.maps.arcgis.com/sharing/rest/content/items/3528275d90d74afa8c14c74d72b04e33?f=json
[B3]: https://columbus.maps.arcgis.com/sharing/rest/content/items/f7a785b863454d96a0fe3f5aa5368e7d?f=json
[B4]: https://services1.arcgis.com/9yy6msODkIBzkUXU/arcgis/rest/services/Building_Permits/FeatureServer/0/query
[B5]: https://columbus.maps.arcgis.com/sharing/rest/content/items/3528275d90d74afa8c14c74d72b04e33/data?f=json
[B6]: https://columbus.maps.arcgis.com/sharing/rest/content/items/ad99db45b9984dbf842796d95a08dbf2/data?f=json
# Local Qualification Run: September 19, 2026

## First-Quarter Reconciliation Extension

Six independent local cohorts now cover January-March 2024 under the exact
source predicates, not all Columbus development activity:

| Month | Commercial issuance | Site filings | Failed rows |
| --- | ---: | ---: | ---: |
| January | 587 | 72 | 0 |
| February | 589 | 70 | 0 |
| March | 665 | 66 | 0 |
| Total source records | 1,841 | 208 | 0 |

All six runs completed with no checkpoint remaining, and their pre/post
provider counts matched inserted counts. The 2,049 total is not a distinct
project count: projects may have multiple permits or appear in both feeds.
These are current snapshots of historical filings, not historical vintages.
Do not use these three months alone as evidence of growth or early detection.

February and March reports are saved beside the ignored local databases as
`columbus-{commercial,site}-20240{2,3}-live.qualification.json`. Each contains
the exact query, hash, timestamps, run ID, and workflow-readiness counts.
The CLI exits with status 2 when reconciliation fails; a failed final provider
count remains in the report without discarding the imported evidence.

All 2,049 records have nonempty parcel references but **zero coordinates** in
this narrow import scope. A parcel reference does not establish an exact
parcel match, ownership, availability, or a nearby acquisition candidate.
The existing permit-detail API exposes events and graph context; nearby search
is deal-centered. The remaining workflow work is a verified parcel/location
join and an evidence-backed opportunity handoff, not another permit import.

Official parcel-source research candidates (not activated or rights-approved):

- [Columbus CSIR parcel layer](https://gis.columbus.gov/arcgis/rest/services/Applications/CSIR_Public/MapServer/3)
  exposes parcel identifiers, site address, and acreage. Its metadata says
  server-side centroid return is unsupported; do not enable that connector
  option blindly. Test identifier formats, address agreement, duplicate units,
  geometry handling, and cross-county parcels before any automatic join.
- [Franklin County Auditor extracts](https://apps.franklincountyauditor.com/GIS_Shapefiles/CurrentExtracts/)
  publish parcel polygons. Prefer bounded source qualification before bulk
  extraction. Public download availability does not by itself qualify
  commercial redistribution, privacy scope, or complete Columbus coverage.

No production database, ingestion enrollment, dashboard, or host policy was
changed by these qualification runs.

The bounded intake module `app.services.ingestion.historical_intake` reuses the
normal connector, normalization, raw evidence, graph, and temporal projection
pipeline. It only creates a **new local SQLite database**, refuses existing
files, and never uses the configured application database for ingestion.
It accepts a completed interval of at most 31 days and at most four pages of
250 requested rows. A full page budget is not proof of completion. Reports
retain scope, scope hash, run ID, capture times, checkpoints, and counts.
The production commercial predicate remains `ISSUED_YEAR >= 2025`.

Verified local runs for January 1 inclusive to February 1 exclusive, 2024:

| Cohort | Provider before/after | Inserted | Failed | Run ID |
| --- | --- | --- | --- | --- |
| Commercial issuance | 587 / 587 | 587 | 0 | e87f5e74-82c2-45b0-8839-1dceea3fba64 |
| Site engineering filings | 72 / 72 | 72 | 0 | 298928f6-0d04-4b7f-ad42-8f8e49d30e4f |

Capture windows (UTC): commercial 19:12:52-19:13:08; site engineering
19:13:29-19:13:31 on September 19, 2026. Both runs completed without a remaining
checkpoint. Local ignored databases are `columbus-commercial-202401-live.db`
and `columbus-site-202401-live.db` in the temporal-foundation worktree.
Commercial retained 587 raw evidence records, 2,642 temporal observations,
1,298 graph entities, and 1,761 relationships. These are pipeline inventory
counts, not unique projects or verified investment opportunities.

Scope SHA-256 values:
- Commercial: `4f81766497687c871f178682869bbfc60cb4aabad84e4f1e076fa0ec22d9b741`
- Site engineering: `edbf502dccf251c5d243a06698f6ac06ccba2bd4e9f4d9800a3f98513a334bcd`

The explicit `Approved` site status now maps to approved; commercial freshness
uses `record_updated_at` for `LAST_STATUS_DT`. Existing Complete/Completed/Closed
interpretations remain unchanged and still require lifecycle qualification.
Do not treat those labels as verified construction completion or opening.

Reproduction (choose a new database filename each time):

```bash
ENVIRONMENT=ci INGESTION_ALLOWED_HOSTS=services1.arcgis.com \
  .venv/bin/python -m app.services.ingestion.historical_intake \
  --source-key columbus_oh_commercial_building_permits \
  --start 2024-01-01 --end 2024-02-01 \
  --database columbus-commercial-new.db --max-pages 4
```

The CLI writes an ignored `.qualification.json` beside subsequent databases.
These development databases use model-created tables, not the production
migration/security gates, and must not be deployed as application databases.
Capture timestamps reflect **now**, not 2024. Current source snapshots cannot
reconstruct historical knowledge or prove detection lead time. Count agreement
is not a frozen snapshot, citywide completeness, or permission to activate a
broader production scope. Neither run has been published to the dashboard.
