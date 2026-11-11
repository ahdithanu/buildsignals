# South Jersey Requested Markets: Bounded Official-Source Qualification

## Superseding November 11 Privacy and Radius Contract

This November 10 qualification is historical. Read
`2026-11-11-nj-retail-radius.md` before using any NJ profile or projection below:
PROP_LOC alone is situs, owner-mail fields and unverified postal fields are
suppressed, NJ opts into strict pre-persistence/canary projection validation, and
scopes are inactive/manual with 0.25..3-mile/2,000-row bounds. The older mailing
projection below is not an activation-ready contract. The newer 161-row public
radius check is not live tenant inventory or a verified production anchor.

- Access date: 2026-11-10 (America/Los_Angeles).
- Checkout: `codex/reviewed-city-expansion`, HEAD `e51e445` at inspection.
- Scope: Swedesboro Borough, Deptford Township, Cherry Hill Township, NJ.
- State: qualification only; no new catalog candidate, activation, ingestion,
  scheduling, production write, deployment, inquiry, account or paid access.
- Ownership: this new document only. Existing dirty research, shared catalog,
  harness and handoff are unchanged; parent integrates the findings.

Implementation update: the follow-up below owns this document plus the new NJGIN
qualifier script/test. The parent removed the municipality-as-zoning mapping and
preserved `PIN_NODUP`. Current qualifier scope permits at most three transient
polygons per municipality for existing local centroid normalization; raw polygons
and private fields never appear in output. The parent's later network-enabled
pass below supersedes the earlier web extraction and sandbox DNS failure.

## Latest Direct-Client Acceptance

Parent invocation on November 10 PST, using the ordinary repository HTTP client
with network permission (not an alternative publisher route):

```sh
OPENROUTER_API_KEY= DATABASE_URL=sqlite:// .venv/bin/python \
  -m scripts.qualify_njgin_markets --live
```

Exit 0; seven logical GET operations, nine sampled rows, `technical_qualification_passed=true`,
`catalog_contract_verified=false`, `is_active=false`. The bounded qualifier
checks a smaller field contract than the full catalog and does not establish
production acceptance. Counts are publisher rows, not deployed inventory:

| Municipality | Native code | Publisher rows | Sampled / unique / valid WGS84 centroids | Sample publication date |
|---|---|---:|---|---|
| Swedesboro Borough | `0817` | 1,046 | 3 / 3 / 3 | 2026-03-26 |
| Deptford Township | `0802` | 13,298 | 3 / 3 / 3 | 2026-03-26 |
| Cherry Hill Township | `0409` | 27,047 | 3 / 3 / 3 | 2025-12-30 |

Total: 41,391 publisher rows. Three samples per municipality do not establish
corpus-wide ID uniqueness, match quality, geometry correctness, currentness,
for-sale availability or coverage completeness. All sampled `PCLLASTUPD` values
were null. Sample publication dates are not recent permit filing dates.

**Correction:** direct JSON metadata contains `PCL_GUID`; all optional fields
were present. The earlier web extraction's omitted GUID was not proof of a
schema removal. Parent restored the original optional GUID projection/grouping
context before checkpointing; canonical identity remains `PIN_NODUP`. Do not
remove source fields based solely on an incomplete web rendering.

Direct flags: `supportsQueryWithDistance=true`, historic-moment flag absent/null,
centroid-return flag absent/null (not true). The sample therefore used bounded
temporary polygons and the existing first-ring centroid transform, not an
unsupported server-centroid request. Actual combined radius-query behavior is
still unverified. The earlier web rendering's explicit centroid `false` is a
separate observation, not a value copied into this direct response.

The operation counter is not a wire-request meter. The shared pinned client can
follow up to five same-host redirects and try multiple resolved addresses;
actual wire attempts were not instrumented. Final reporting names the logical
operation unit, exposes `wire_request_count=null` and retains zero transient
retries. The live pass preceded the final zero-area-ring validation/report-label
hardening; those changes passed offline regressions, not another live invocation.

### Full Catalog Projection Check

A separate read-only check then cloned the actual catalog source for each
municipality, ANDed its existing PIN predicate with the exact `PCL_MUN` code,
set timeout20/retries0, and invoked `validate_source_canary(sample_size=3)`.
All three returned `ok=true`, three fetched/valid, zero failed and zero errors.
This exercised every current projected field and mapping, including the retained
GUID context and corrected no-zoning mapping. It is nine additional sample rows,
not additional inventory. No sample identifiers, addresses or polygons were
printed or persisted. The check used `DATABASE_URL=sqlite://` and no DB session.
Three logical canary invocations are not a measured wire-request count.

Reproduce the scoping with the existing offline catalog model, not a production
source mutation:

```python
from types import SimpleNamespace
from app.services.ingestion.catalog import load_catalog
from app.services.ingestion.health import validate_source_canary

base = next(e for e in load_catalog()
            if e.key == "new_jersey_njgin_statewide_parcels_nearby_narrow")
for code in ("0817", "0802", "0409"):
    entry = base.model_copy(deep=True)
    config = entry.settings["connector"]
    config.update(where=f"({config['where']}) AND PCL_MUN = '{code}'",
                  timeout=20, max_retries=0)
    source = SimpleNamespace(**entry.model_dump(exclude={"field_mappings"}),
                             id="qualification", field_mappings=entry.field_mappings)
    result = validate_source_canary(source, sample_size=3)
    print(code, result.ok, result.records_valid, result.records_failed)
```

This snippet makes public requests: use an explicit `maps.nj.gov` host policy,
no model key, a disposable/local database URL and the same bounded scope. It is
not an application-DB or production-source canary command.

### Inactive Nearby Profile

The parent added this existing reviewed source to `retail_parcel_refresh.FIELDS`
with only `OBJECTID,PIN_NODUP,PAMS_PIN,ST_ADDRESS,PROP_LOC,MUN_NAME,ZIP5,CALC_ACRE`
and temporary geometry for normalization. Existing manual/incremental/inactive
construction, 1-3 mile radius, 2,000-record ceiling, provenance and export policy
remain unchanged. No owner/value/sale/zoning fields or wildcard are requested.
Offline profile/qualification regressions passed 73 tests. The combined live
radius-query behavior and a real tenant retail anchor remain unverified; the
profile does not activate itself or imply verified for-sale status.

No application database session, production source/schedule, model call or
deployment was used. The sandbox-only attempt below failed before reaching the
publisher; the network-enabled pass received actual responses. No publisher
denial was bypassed. Earlier observations below are retained as dated history,
not the latest operational result.

## Decision Summary

| Market | Authority and parcel scope | Planning/permit qualification result |
| --- | --- | --- |
| Swedesboro | Borough, Gloucester County; state municipal code `0817` | Borough planning/zoning; published construction shared-services notice names Greenwich Township (Gibbstown), not Woolwich. Notice currentness and an accessible records/export contract remain unresolved. |
| Deptford | Township, Gloucester County; `0802`, not West Deptford `0820` | Township Planning Board and Construction Department. Official agenda/minute index exists; document retrieval and anonymous permit export remain unverified. |
| Cherry Hill | Township, Camden County; `0409` | Township Planning Board publishes application identifiers and linked materials; strongest next document-connector qualification target. Construction permits remain a separate township function, not established as an exportable feed. |

Reuse `new_jersey_njgin_statewide_parcels_nearby_narrow`; do not create three
parcel sources. Existing admission is documented in
`docs/parcel_source_onboarding_decisions.md` under New Jersey and configured in
`app/services/ingestion/catalog.json`. This research does not establish today's
runtime-job status, stored coverage, parcel counts, or freshness acceptance.

## Evidence Levels and Request Bounds

"Page read" means the web tool returned page content, not an ordinary worker
HTTP-client acceptance receipt. "Indexed" means official-source text surfaced
in search results; it is not a fresh fetch of the underlying document. Retrieval
errors below did not expose HTTP status and do not establish a publisher denial.

There were **16 web-tool operations: five focused search queries, seven first
URL opens, and four rereads of already-returned NJGIN pages**. This is near the
requested approximately 15-operation budget; work stopped after the bounded
count attempt. These are tool-operation bounds, not a claim about hidden search
engine crawling, redirects or tool-internal HTTP attempts.

| Operation | Target / bounds | Result |
| --- | --- | --- |
| 1 | Search `site.historicswedesboro.com planning zoning construction permits board` | Official municipal pages and construction notice indexed. |
| 2 | Search `site.deptford-nj.org planning board construction permits` | Official board, department, directory and agenda pages indexed. |
| 3 | Search `site.chnj.gov planning board construction permits` | Discovery only; no records exported. |
| 4 | Search `site.nj.gov "SWEDESBORO" "DEPTFORD" "CHERRY HILL" codes` | Official Treasury municipality-code document indexed. |
| 5 | NJGIN layer URL below, one metadata page | Page read. |
| 6 | NJGIN parcel landing URL below, one page | Page read. |
| 7 | Swedesboro construction notice PDF below, one document | Web-tool retrieval error; indexed text available from operation 1. |
| 8 | Deptford agenda/minute URL below, one index | Page read; no underlying meeting document fetched. |
| 9 | Search `site.chnj.gov planning board construction permits application documents agendas` | Official Planning Board URL and township application instructions indexed. |
| 10-11 | Reread NJGIN layer and landing page | Cached-page references; partial views. |
| 12 | `https://www.deptford-nj.org/departments/construction`, one public-page attempt | Web-tool retrieval error. Path was not established as canonical; do not configure it as a source. |
| 13-14 | Reread NJGIN layer and landing page | Complete relevant metadata and landing text returned. |
| 15 | Cherry Hill Planning Board URL below, one index | Page read; no linked application, deed, survey or exhibit fetched. |
| 16 | NJGIN documented public query path; one grouped count request for three municipality codes | Web-tool retrieval error, no count payload. No alternate transport or retry. |

No bulk rows, raw parcel geometries, owner/value/sale fields, credentials,
CAPTCHAs, internal APIs or application submissions were requested. No individual
parcel sample was fetched. The grouped count would return at most three
municipality aggregates. Public-page application headings were inspected, not
an applicant-data export. County-specific planning-board services and NJ DCA
permit-report exports were not separately qualified within this budget.

## Municipal Codes and Parcel Filters

The official [NJ Treasury county/municipality code list](https://www.nj.gov/treasury/omb/pdf/forms/municodes.pdf)
was verified through indexed official text, not a successful PDF download.
It assigns `0817` to Swedesboro Borough, `0802` to Deptford Township and `0409`
to Cherry Hill Township. Gloucester and Camden are distinct county groupings.
Do not confuse Greenwich `0807` (construction-service provider in the published
Swedesboro notice) with Swedesboro's parcel jurisdiction.

The current [NJGIN Parcels layer metadata](https://maps.nj.gov/arcgis/rest/services/Framework/Cadastral/MapServer/0)
declares `PCL_MUN` a four-character string. The proposed filters below combine
that field with Treasury codes; **actual matching rows/counts were not returned**.
Code-to-field use is supported by the schema and state coding evidence, but
must still receive a successful bounded aggregate/sample check before acceptance.

```sql
-- Swedesboro Borough
PCL_MUN = '0817' AND PIN_NODUP IS NOT NULL AND PIN_NODUP <> 'XXXNLL'
-- Deptford Township
PCL_MUN = '0802' AND PIN_NODUP IS NOT NULL AND PIN_NODUP <> 'XXXNLL'
-- Cherry Hill Township
PCL_MUN = '0409' AND PIN_NODUP IS NOT NULL AND PIN_NODUP <> 'XXXNLL'
```

Postal city, ZIP and proximity to the municipality are not governing-authority
filters. These codes are not zoning districts. In particular, the existing
catalog at initial inspection mapped `PCL_MUN` into `zoning_code`; that was not
verified land-use zoning. The parent has since removed that incorrect mapping;
no shared mapping was edited by this qualifier's writer.

## Existing NJGIN Parcel Contract

### Current metadata read

The existing endpoint still returns a public layer description for Parcels:
polygon geometry, native spatial reference `102711` / `3424`, maximum 1,000
records, JSON/GeoJSON/PBF, pagination, ordering and statistics. Server-side
geometry centroid return is explicitly unsupported. Relevant fields include
`OBJECTID`, `PIN_NODUP`, `PAMS_PIN`, `PCL_MUN`, block/lot/qualifier, `COUNTY`,
`MUN_NAME`, `PCLLASTUPD` and `PCL_PBDATE`.

**Initial mismatch hypothesis withdrawn:** the web-extracted field list omitted
`PCL_GUID`, but the later direct JSON pass confirmed it is present. The parent
restored the original GUID projection, allowlist and optional group fallback
before checkpointing. `PIN_NODUP` is unchanged. The qualifier can still expose
missing optional fields without replacing identity. The full-catalog canary
receipt at the top supersedes this initial web-only inspection.

### Geometry, reuse and currentness boundaries

The [official NJGIN parcel landing page](https://www.nj.gov/njgin/edata/parcels/)
provides statewide and county download entrypoints, including Camden and
Gloucester parcels/MOD-IV geodatabases and shapefiles. These linked county
assets were not downloaded. The state composite integrates county updates as
received; it is not a daily permit feed. County/municipal stewards maintain
inputs. The page warns that polygons are neither survey data nor legal ownership
boundaries and states that owner names are redacted under Daniel's Law.

Preserve the existing narrow admission: stable PIN identity, permitted parcel
context and polygon-derived centroid for proximity/adjacency. Existing configured
geometry processing requests WGS84 (`outSR=4326`, precision 6); that query result
was not tested here. No raw polygon or source-replacement export is authorized.
Attribution, accuracy/currentness and non-survey notices remain required.
Do not widen rights to owners, mailing/contact data, assessed values, taxes,
deeds or sales, even though some corresponding fields remain in service metadata.
Prior item-metadata rights conclusions are inherited from the admission document,
not newly revalidated item-license findings in this pass.

`PIN_NODUP` remains the admitted record key; `OBJECTID` is transport-only.
Publication/update fields exist, but their latest values, per-county vintages,
update-log contents and changed/deleted-record behavior were not measured.
Presence of geometry and dates is not freshness or lifecycle acceptance.

### Exact bounded aggregate attempt

One GET was attempted against
`https://maps.nj.gov/arcgis/rest/services/Framework/Cadastral/MapServer/0/query`
using these standard public ArcGIS parameters:

```json
{
  "f": "pjson",
  "where": "PCL_MUN IN ('0817','0802','0409') AND PIN_NODUP IS NOT NULL AND PIN_NODUP <> 'XXXNLL'",
  "groupByFieldsForStatistics": "PCL_MUN",
  "outStatistics": [{
    "statisticType": "count",
    "onStatisticField": "OBJECTID",
    "outStatisticFieldName": "parcel_count"
  }],
  "returnGeometry": false
}
```

The web tool reported the URL inaccessible without a publisher status/body.
Counts and municipal row coverage remain **unknown**, not zero. No individual
rows, identifiers, addresses or geometry were requested by this query.

## Swedesboro Borough

### Authority and official entrypoints

- [Municipal forms and applications](https://www.historicswedesboro.com/borough-clerk/forms-permits-and-applications/)
  (indexed): zoning and Planning/Zoning application links, not a filing ledger.
- [Planning/Zoning application instructions](https://www.historicswedesboro.com/wp-content/uploads/2025/02/Planning-Zoning-Board-Application.pdf)
  (indexed): Borough Planning/Zoning Board completeness review and hearing process.
- [Construction shared-services notice](https://www.historicswedesboro.com/wp-content/uploads/2023/05/ConstructionPermitsandCertificateofOccupancyInspection.pdf)
  (indexed; direct retrieval failed): names Greenwich Township (Gibbstown) as
  construction-code office, explicitly replacing Woolwich. Borough accepts
  permit packets. This dated notice is evidence of the arrangement as published,
  not independent confirmation that the agreement is unchanged in November 2026.
- [Borough contact directory](https://www.historicswedesboro.com/contact-us/)
  (indexed): distinguishes Borough zoning/planning roles and Gloucester County
  assessor. No contact details copied or inquiry sent.

### Export contract and blockers

Observed contract is downloadable blank forms/instructions, not an anonymous
permit or planning-application data export. No recurring agenda/minute document
index, stable issued-record ID, status/date schema or GIS filing endpoint was
verified. No count or sample filing was fetched. Blank-form fields do not prove
that completed records are publicly exportable.

Exact next gates: confirm the current construction custodian from an accessible
official page; locate a published records/report or board-document index; inspect
one bounded non-sensitive document for application ID, block/lot, hearing/decision
dates and revision handling; review reuse. Do not substitute neighboring
Woolwich/Logan postal-address records. Application submissions can contain owner
and nearby-owner material; suppress names, contacts, signatures and attachments
unrelated to the project evidence. No new feed is connector-ready.

## Deptford Township

### Authority and official entrypoints

- [Township Planning Board](https://www.deptford-nj.org/boards-committees/planning-board)
  (indexed): identifies the municipal board and a 2026 roster.
- [Township department directory](https://www.deptford-nj.org/government/contacts-directory)
  (indexed): identifies Construction and Planning Board functions within Deptford.
- [Agendas and minutes](https://www.deptford-nj.org/government/agendas-minutes)
  (page read): separates Planning Board and Zoning Board agendas/minutes using
  selectors. The site says publication is limited to materials submitted to the
  webmaster; the clerk retains official copies. It also displayed a November 10
  zoning-hearing cancellation, illustrating that notices can revise scheduling.

### Export contract and blockers

This is a public document-index surface, not demonstrated CSV/JSON permit export.
Underlying document URLs, file IDs, text extraction, application IDs, block/lot,
geometry and archive completeness were not verified. Index reachability or a
current notice does not establish a fresh complete filing feed. The focused
search also surfaced an SDL Account Portal label on official construction text;
anonymous search/export, authentication requirements and service contract were
not tested. Do not invent a vendor endpoint or assume a login gate was observed.

`html_document_index` is a possible discovery adapter **only after** public
document links can be resolved without hidden-API guessing. `planning_documents`
then requires a real document fixture, item-ID rules and privacy suppression.
Public-record availability alone does not establish automated commercial reuse
or document redistribution rights. Keep this a qualification hold; not West
Deptford and not a countywide permit inventory.

## Cherry Hill Township

### Observed planning-document surface

The [Planning Board page](https://www.chnj.gov/113/Planning-Board) was read directly.
It identifies township site-plan, subdivision, conditional-use and change-of-use
jurisdiction. It promises public agendas/exhibits at least two days before
hearings and links application materials and reviews. Visible headings include
application IDs `26-P-0009` and `26-P-0006`, both tied to November 2, 2026; one is
marked adjourned. A notice cancels November 16 for lack of an agenda. These are
publication/hearing facts, not proof of approval or completed construction.

This is an HTML-to-linked-document contract, not a machine-readable filing API.
The page links 2020-current agendas/minutes and older archives. No attachment was
fetched, so file formats, stable attachment IDs, block/lot extraction and geometry
remain unverified. Current headings do not prove archive completeness or an
update watermark. Do not equate an absent future agenda with an empty backlog.

### Permit separation and connector recommendation

[Township Planning Board application instructions](https://www.chnj.gov/DocumentCenter/View/3841/Planning-Board-App?bidId=)
(indexed only) distinguish land-use review/conformance from building permits at
the Construction Department. They do not establish a permit-record export.
The [official zoning application form](https://chnj.gov/DocumentCenter/View/3840)
(indexed only) has block/lot and application/permit-number fields; that is a blank
form schema, not proof those fields are available for completed filings.

Concrete next connector: use the existing `html_document_index` at the verified
Planning Board page for bounded discovery, followed by `planning_documents` for
agenda/minute items once an actual linked file and patterns are validated.
Relevant implementations are `app/services/ingestion/connectors/html_document_index.py`
and `app/services/ingestion/connectors/planning_documents.py`; the latter composes
the former and accepts document-host allowlists, document/page/item limits,
item/file patterns and suppression patterns.

For the next separately scoped check, limit to one index and one linked agenda
or minute, not surveys, deeds, photographs or entire application packets. Verify
the actual document host before allowlisting it; no URL pattern or backend API
was reverse-engineered here. Use municipality + governing board + application
number as a proposed project key, with document URL/hash/page and observation
time as evidence/revision identity. One application can have several documents,
hearings and decisions. Association with a parcel must use explicit block/lot/
qualifier evidence; no automatic geocoding or geometry join was tested.

Rights/privacy hold: review automated reuse and document rights before promotion;
public inspection is not blanket redistribution permission, particularly for
third-party plans/surveys. Suppress natural-person names, contact/mailing fields,
signatures and unnecessary personal information. Retain public business entities
only where supported as project evidence; do not infer ownership. No active
connector or candidate entry was created.

## Parent Integration and Verification

1. Preserve the existing NJGIN source and narrow field/geometry/export policy.
   The parent has corrected the absent `PCL_GUID` projection/fallback and the
   municipal-code-versus-zoning mapping; neither was changed by this writer.
2. Obtain a successful no-PII municipality count or at most three allowlisted
   records through the supported public service before accepting code filters.
   The failed web-tool request is not a reason to bypass a restriction.
3. Prioritize Cherry Hill's document surface, then Deptford's document-link
   resolution. Swedesboro needs current construction-custodian and records-index
   confirmation first. County planning and state permit-report surfaces remain
   unqualified, not absent.
4. Separate rights review, parser tests, bounded canary, activation authorization
   and actual scheduled-run reconciliation. None is implied by this document.

Offline checks: `python3 scripts/agent_status.py` passed; recent Git state and
existing source/adapter patterns inspected. Documentation whitespace and
single-file ownership checked after writing. Product tests were not run because
no executable behavior changed. No commit, shared harness update, or production
acceptance is claimed. This document is the handoff to the parent for this scope.

## Local Qualifier Implementation Follow-Up (2026-11-10)

This follow-up adds only `scripts/qualify_njgin_markets.py` and
`tests/test_qualify_njgin_markets.py`, plus this document. The earlier research
receipt above remains historical. Shared source catalogs, rollout configuration,
runtime jobs and agent harness are owned by the parent and were not edited by
this implementation. Concurrent changes in those files were preserved.

### Implemented Contract

- Default invocation is offline, reports zero requests, and does not construct
  an HTTP client. `--live` is required. Optional repeated `--municipality` accepts
  only distinct codes `0817`, `0802`, `0409`; omitting it selects all three.
- Fixed reviewed layer and query URLs only; 1 MB per-response byte cap,
  `max_retries=0`, 20-second transport timeout, no alternate host or transport.
  At most seven logical requests: one metadata read, one count and at most one
  three-row sample per selected municipality. No pagination continuation.
- Metadata must confirm a polygon layer and the exact required fields/types:
  `OBJECTID` (OID), `PIN_NODUP` (string), and `PCL_MUN` (four-character string).
  No fallback to postal city, county inventory, object ID or optional GUID.
  Missing `PAMS_PIN`, `PCL_GUID`, `PCLLASTUPD` or `PCL_PBDATE` is explicitly
  reported. This is a narrow reviewed schema check, not a full catalog canary;
  `catalog_contract_verified` remains false.
- Safe `metadata_flags` preserves the exact observed booleans from
  `advancedQueryCapabilities` for `supportsQueryWithDistance`,
  `supportsQueryWithHistoricMoment` and `supportsReturningGeometryCentroid`.
  Missing, malformed or unobserved values are `null`, never assumed false/true.
  `metadata_observed` distinguishes a returned metadata response from offline
  mode or a failed request. Flags survive subsequent required-schema failure;
  no publisher metadata text or new request is needed for this reporting.
- Counts use the explicit municipal filter plus non-null/non-placeholder PIN.
  A zero count is an empty-scope blocker, not successful coverage. A transport,
  publisher-error or malformed-response failure stops the pass without retries.
- Per the owner's clarification, samples use existing local polygon-to-centroid
  normalization when server centroids are unsupported. This does not invent a
  server capability: `schema.supports_centroid` remains false and
  `geometry_mode=local_polygon_centroid`. At most three temporary polygon rows
  per municipality are requested; no geometry or row is persisted or printed.
- Samples reuse `ArcGISConnector` with only OID, PIN, municipality and
  metadata-verified date fields, `outSR=4326`, `resultRecordCount=3`, and
  `OBJECTID ASC`. Local mode requests `returnGeometry=true`, never
  `returnCentroid`; metadata-supported server mode instead requests
  `returnCentroid=true`, with the HTTP boundary forcing `returnGeometry=false`.
  Unexpected attributes or geometry outside the selected mode fail before
  connector flattening can discard them.
- Local mode validates WGS84 spatial reference, ring structure, finite numeric
  vertices and coordinate bounds, then reuses `prepare_mapped_record` with the
  existing `arcgis_polygon_centroid` transform. That existing algorithm uses the
  first ring, not a new whole-multipart/hole-weighted or guaranteed-interior
  centroid algorithm. Output names this method explicitly. Derived points are
  proximity context, not survey, legal-boundary or parcel-interior guarantees.
- Strict municipality/identity/uniqueness and WGS84 point checks precede reuse of
  `normalize_parcel`. Output contains local market labels and aggregate counts,
  validity totals and date ranges only: no raw records, parcel IDs, coordinates,
  polygons, addresses, owner/value/sale fields or source-row hashes. Provider
  error bodies and exception messages are never printed. No database connection,
  session, query, persistence, activation or rights expansion is introduced.
  The existing connector package transitively imports `app.db` and constructs
  its lazy SQLAlchemy engine; importing is not a DB-I/O acceptance receipt.
  Tests explicitly forbid opening engines or sessions in either qualifier mode.

CLI exit status is nonzero for failures or technical blockers. Missing optional
fields alone do not replace identity or prevent testing the required schema.
`schema.legacy_optional_fields_missing` explicitly reports absent `PCL_GUID`;
this is not a blocker for the parent's corrected catalog. The broader catalog
contract is never claimed verified by this narrow qualifier. A successful tiny
sample would still not establish publisher completeness, source currentness,
scheduled operation or production acceptance.

### Actual Ordinary-Host Attempt

```sh
.venv/bin/python -m scripts.qualify_njgin_markets
.venv/bin/python -m scripts.qualify_njgin_markets --live
```

- Offline invocation: exit 0, `network_requests=0`, inactive qualification only.
- Live invocation: exit 1, `failure_phase=metadata`,
  `failure_reason=dns_resolution_failed`, `network_requests=1`.
- This was one logical metadata request attempt with the ordinary repository
  HTTP client. DNS failed before any provider response; no count or sample was
  fetched. There were no retries, alternative clients, browser fallbacks or
  further live probes in this implementation increment. This is a local DNS
  access blocker, not an NJGIN HTTP denial or publisher-outage assertion.
- The earlier web-tool metadata observations, including absent `PCL_GUID` and
  unsupported server centroids, were not independently reverified by this run.
  Municipal counts and live sample/normalization acceptance remain unverified.
- The implementation was subsequently updated for the owner's temporary-polygon
  clarification and the parent's catalog corrections; the live attempt was not
  repeated. These additions have offline test receipts, not new live receipts.

### Distance-Profile Metadata and Direct-Probe Status

No additional public request was made for this capability-reporting follow-up.
The already-read [layer metadata HTML](https://maps.nj.gov/arcgis/rest/services/Framework/Cadastral/MapServer/0)
listed the following capabilities during the earlier web research. These are
separate from the later ordinary-client probe, which returned no metadata:

| Exact capability | Earlier web metadata representation | Ordinary-client live probe |
| --- | --- | --- |
| `supportsQueryWithDistance` | `true` (Supports Query With Distance) | Unobserved / `null` |
| `supportsQueryWithHistoricMoment` | Not listed in the returned representation; unknown | Unobserved / `null` |
| `supportsReturningGeometryCentroid` | `false` (Supports Returning Geometry Centroid) | Unobserved / `null` |

Do not seed the script's live report with these earlier web observations: it
reports only flags actually received by that invocation. The existing
`scripts/retail_parcel_refresh.py` uses a WGS84 point, `esriSpatialRelIntersects`,
distance and statute-mile units; it was inspected read-only and not edited or
run. Advertised distance support is useful evidence, but the combined bounded
1-3 mile query contract, resulting geometry/field scope and provider behavior
were not tested. Safe reuse of that profile is therefore **not confirmed**.
Historic-moment support is unknown; no historical/as-of behavior is inferred.

**Earlier sandbox-only probe status (superseded by the successful parent pass above):**
The sole probe already exited 1 at metadata lookup after one logical attempt,
before any count/sample response. No request is pending, and there was no retry
or alternative transport. This status does not establish a publisher denial.

### Offline Verification and Handoff

```sh
.venv/bin/python -m pytest tests/test_qualify_njgin_markets.py tests/test_qualify_ocala_gis.py tests/test_ingestion_connectors.py tests/test_parcel_geometry.py -q
.venv/bin/python -m pytest tests/test_ingestion_catalog.py -k arcgis_polygon_centroid_transform_derives_wgs84_point -q
ruff check scripts/qualify_njgin_markets.py tests/test_qualify_njgin_markets.py
```

Combined targeted tests: **125 passed**. Existing catalog polygon-transform test:
**1 passed, 186 deselected**. Scoped Ruff: **passed**. Whitespace checks on all
three owned files emitted no diagnostics (`git diff --no-index --check
/dev/null <path>` returns 1 for these new-file differences). Final default CLI
invocation again exited 0 with zero requests. Tests use an
injected byte client and real ArcGIS flattening/parcel normalization, never a live
provider or database fixture. Covered cases include offline/CLI defaults, exact
request/row/byte bounds, bad or duplicate municipality selections, metadata field
types, missing optional/primary identity, no identity replacement, unsupported
server centroids with bounded local derivation, count validation,
cross-municipality rows, duplicate IDs, invalid
geometry, unexpected private fields/raw polygons, sanitized failures, disabled
transport retries and absence of database connection/session access. The initial
test-first collection failed because
the new implementation module did not yet exist, then passed after implementation.
Capability-report tests cover true/false/unknown and malformed values, sanitized
output, preservation after schema failure, and no extra request for metadata flags.
Full application suites, live canaries and production/runtime acceptance were
not run. No commit was made.

Final frozen-code root regression: `OPENROUTER_API_KEY= DATABASE_URL=sqlite://
.venv/bin/python -m pytest tests -q` returned **2,440 passed, 70 skipped in
266.68s**. Scoped Ruff and manifest/whitespace checks passed. No PostgreSQL/RLS,
scheduled-run or browser E2E acceptance is inferred from this local suite.
Independent review's zero-area-ring and operation-versus-wire-count findings
were fixed and covered by 133 focused tests. No additional live requests were
made for that hardening. Source/nearby profiles remain inactive/manual.

Next action after the successful parent pass above: verify a live bounded
radius profile and real retail anchor before considering production parcel
acceptance. Keep the separate permit-export and source-currentness gaps visible.
No source activation or scheduled-operation acceptance is implied by this
qualification. The earlier DNS failure is not the current blocker.
