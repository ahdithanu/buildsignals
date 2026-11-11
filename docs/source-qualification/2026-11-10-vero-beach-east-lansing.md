# Vero Beach FL and East Lansing MI: Bounded Source Qualification

## Scope and Decision

- Qualification date: November 10, 2026, America/Los_Angeles. Session clock
  receipt: `2026-11-11T07:03:39Z` (November 10 locally).
- Checkout: root `/Users/ahdithebomb/Desktop/DealSignal`, branch
  `codex/reviewed-city-expansion`, HEAD `e51e445`.
- Authorization: official-source discovery and metadata/pages only; this new
  document is the sole owned file. Existing dirty work is preserved.
- Request budget used: **12 focused operations: five discovery search queries
  and seven page/metadata opens, including one failed open. Zero sample queries,
  zero record samples, zero bulk downloads.** Search engines can return multiple
  indexed results; this is not a count of their underlying publisher fetches.
- These are dated web-tool observations, not direct ingestion-client HTTP tests,
  canaries, current production measurements, or evidence of publisher completeness.

| Market / source family | Result of this pass | Disposition, not a catalog change |
| --- | --- | --- |
| Vero Beach planning / permits | Official City planning services and application forms found; no supported recurring record export qualified | Technical/contract and rights hold |
| Indian River parcel geometry | Property Appraiser advertises GIS shapefiles and CAMA extract/dictionary; artifacts not fetched | Schema, freshness, jurisdiction and reuse hold |
| East Lansing planning / permits | Indexed municipal permit material and a vendor municipal portal found; department page retrieval failed | Supported export, lifecycle, identity and rights hold |
| East Lansing parcel geometry | Official City polygon-layer schema readable | Query execution, durable identity, freshness, extent and rights hold |

No catalog entries, harness files, schedules, production databases or source
activation changed. No accounts, payments, inquiries, authentication workarounds,
internal APIs, reverse engineering or model calls. No source is admitted by this
document. A parcel is not a verified sale listing.

## Actual Web Receipts

All operations below ran during this dated session using `web.run`. Successful
opens returned readable extracted pages; the tool did **not** expose origin HTTP
statuses, headers or exact response bytes. Do not relabel them HTTP 200 receipts.
Search crawl dates and relative publication labels are not source-update dates.

### Discovery Queries (1-5)

1. `site.covb.org building permits planning GIS Indian River County public records`
2. `site.cityofeastlansing.com building permits BS&A GIS parcel data download`
3. `site.covb.org "permit" "Planning"`
4. `site.ircpa.org GIS downloads parcel shapefile`
5. `site.cityofeastlansing.com "Ingham" "Clinton" "development"`

Only municipal/county material supports the findings below. Unrelated Accela
tenants, neighboring counties, third-party aggregators, metro proxies and state
historical reports returned by search were not used to qualify either market.

Discovery-only leads, **not opened or sampled**:

- [City's permit application instruction guide](https://www.cityofeastlansing.com/DocumentCenter/View/8272/Apply-for-a-Permit-Online-Instruction-Guide-for-Homeowners-PDF):
  indexed City instructions describe address/parcel search. The older guide is
  not a current export specification.
- [City's online permit/payment/inspection instructions](https://www.cityofeastlansing.com/DocumentCenter/View/10273/Online-Permit-Payment-and-Inspection-Request-Processes-PDF):
  indexed excerpt mentions a City profile and BS&A account. It does not establish
  that anonymous record search requires an account; neither flow was exercised.
- [BS&A municipal home, uid=138](https://www.bsaonline.com/Home/MunicipalityHome?uid=138):
  search result identifies City of East Lansing and building-record search. This
  is vendor-hosted discovery, not a tested export or verified current City
  backlink. No session-bearing application URL was followed or retained.
- [Indian River County address-viewer help](https://indianriver.gov/Document%20Center/Services/Planning-and-Development/Planning%20Division/Zoning%20Maps/Map_Help_GIS.pdf):
  indexed County guide describes countywide addresses, including incorporated
  municipalities, and reference-only parcel boundaries supplied by the Property
  Appraiser. This is older documentation, not a current geometry/license contract.

### Page and Metadata Opens (6-12)

| Operation | Exact source / navigation | Actual result |
| --- | --- | --- |
| 6 | [Vero Beach Planning & Development](https://www.covb.org/248/Planning-Development) | Readable HTML extraction, 203 lines. City planning services, agendas and GIS/residency links visible. |
| 7 | [Indian River Property Appraiser Pro Tools](https://www.ircpa.org/site-links/pro-tools-page/) | Readable HTML extraction, 67 lines. Public distribution links advertised; no extract downloaded. |
| 8 | [East Lansing Site Selection / GIS](https://www.cityofeastlansing.com/397/Site-Selection-GIS) | Readable HTML extraction, 91 lines. City links interactive parcel/zoning GIS. |
| 9 | [East Lansing PARCELS layer 0](https://gis2.cityofeastlansing.com/arcgis/rest/services/Parcels/MapServer/0) | Readable REST-directory extraction, 122 lines; schema and capabilities only. |
| 10 | Operation 6, Planning Department Forms link -> [Vero Beach Application Forms](https://www.covb.org/254/Application-Forms) | Readable HTML extraction, 138 lines. Blank application links, not submitted application records. |
| 11 | Operation 8, Community and Economic Development link -> [department page](https://www.cityofeastlansing.com/2615/Community-and-Economic-Development) | **Failed:** tool reported `Failed to fetch ...: Cache miss`. No page body or origin status. No retry, bypass or alternate API attempt. |
| 12 | Operation 7, Terms of Service link -> [Property Appraiser terms](https://www.ircpa.org/site-links/terms-of-service/) | Readable HTML extraction, 42 lines. Disclaimer reviewed below. |

Failure 11 is a web-tool retrieval failure, not proof of publisher downtime,
denied access, missing records or an HTTP 403/404. No other source-access failure
was observed. Untested downloads, query operations and portal functions remain
untested, not successful.

## Vero Beach: Authority and Record Contract

The [City planning page](https://www.covb.org/248/Planning-Development) describes
code-compliance certification, site-development review, zoning-map maintenance
and annexation. Its residency-map link explicitly distinguishes City from County.
Operational rule: do not assign City jurisdiction from a Vero Beach postal city
or ZIP. Verify municipal boundaries and the authority for each record type.
Countywide parcel availability would not establish City permit coverage.

The [forms index](https://www.covb.org/254/Application-Forms) lists major/minor
site plans, plats, variances and zoning changes, with several 2026 labels. These
are application templates, not a public intake export. It also links an Indian
River County fire-prevention form; that does not establish general building-
permit delegation. The building authority and City/County handoff remain
unqualified. Agendas/minutes are a possible evidence channel, not a demonstrated
complete pending-case inventory.

For planning/permits, **native case/permit IDs, row grain, status vocabulary,
filing/decision/update dates, parcel-reference format, export pagination and
status-exit/deletion semantics are unknown**. No record freshness observation
was made. A 2026 form label is not a recent filing receipt. Neither a recurring
CSV/API nor permission for commercial retention/display/export was established.

### Indian River Parcel Distribution

The [Property Appraiser's Pro Tools](https://www.ircpa.org/site-links/pro-tools-page/)
advertises `CAMA Extract`, `Web Export Data Dictionary` and `IRCPA Shapefiles`;
extract/shapefile links point to the official site's Schneider-hosted provider.
This is an explicit publisher distribution lead, not a guessed GIS endpoint.
The linked artifacts and dictionary were not fetched. Native parcel key,
geometry type/CRS, multipart/condominium grain, site versus mailing fields,
municipal classification, snapshot date, refresh cadence and split/merge
relationships therefore remain unknown. Do not invent field mappings or use
county-office addresses as jurisdiction evidence.

The [published terms](https://www.ircpa.org/site-links/terms-of-service/) describe
reference-only/as-is data, no accuracy/currentness/completeness warranty,
possible changes without notice, user risk and indemnification. They recommend
original recorded documents for legal transactions and warn about public-record
email disclosure. They do not establish an explicit commercial automation,
storage, derived-map display or redistribution grant for the linked artifacts.
Artifact-specific terms were not inspected. This is a rights-review hold, not a
legal conclusion that reuse is prohibited or that public records are licensed
for unrestricted resale. No email or inquiry was sent.

## East Lansing: Authority and Record Contract

The [City GIS page](https://www.cityofeastlansing.com/397/Site-Selection-GIS)
advertises interactive parcel and zoning information, not a supported export
contract. The department navigation failed as recorded above. No current
municipal planning-case register, downloadable permit report, lifecycle extract
or documented public API was qualified. BS&A's indexed municipal heading alone
does not settle county coverage. A current City/county boundary crosswalk was
not retrieved; **do not hard-code a single county or treat an East Lansing
postal address as City jurisdiction**. County portions and parcel authority
must be established from current official boundary/source documentation.

Planning/permit native IDs, grain, lifecycle, source timestamps, historic
revisions and export rights remain unknown. Indexed application instructions
do not establish anonymous export access, freshness or recurring completeness.
No account was created and no application/payment flow was entered.

### City Parcel Metadata

The [City PARCELS metadata](https://gis2.cityofeastlansing.com/arcgis/rest/services/Parcels/MapServer/0)
reports polygons, spatial reference `2253`, maximum 1,000 records, JSON/GeoJSON/PBF,
pagination and ordering support. Query is advertised; execution was not tested.
Server centroid return is unsupported. `OBJECTID_12` is the OID;
`OBJECTID_1`/`OBJECTID` are integers. `PAR_NO` and `ParcelNum` are distinct string
fields, not established equivalent durable IDs. `UNIT_NO`, `Parent_Par` and
`Split_YR` suggest grain/history questions, not verified lineage. No date-typed
update field is listed; valuation-year fields are not refresh timestamps.
Description/copyright are blank, not a license. Scope, currency, uniqueness,
geometry validity and commercial reuse remain unverified. Exclude `Owner`,
`OwnerAddr`, `OwnerCity`, `OwnerState`, `OwnerZip` and free-text `Notes` from
future probes and raw persistence. No features or owner data were retrieved.

## Concrete Next Contracts (Recommendations Only)

No source is unblocked for activation. The next **documentation-only** work can
continue without changing the product, under a fresh bounded research budget:

1. **East Lansing parcel contract first:** follow the public layer's published
   Iteminfo/Metadata links and the City's GIS documentation to establish data
   owner, municipal/county extent, business-key definition, update cadence and
   commercial storage/display/export terms. The known public Query operation is
   the next technical candidate, not an internal vendor API. If subsequent access
   and privacy review allow a tiny probe, use the existing `arcgis` connector:
   `page_size=3`, `out_fields=OBJECTID_12,PAR_NO,ParcelNum,UNIT_NO`,
   `order_by_fields=OBJECTID_12 ASC`, `include_geometry=false`,
   `include_centroid=false`. This configuration was **not run**. An OID may order
   a bounded snapshot but must not become a durable business identity. Do not
   deduplicate by an assumed parcel key before verifying row grain. Geometry
   sampling/reprojection and topology acceptance are separate later gates.
2. **Vero Beach parcel contract:** inspect only the publisher-linked dictionary
   and download metadata/terms, not the bulk files. Establish parcel key and
   City-boundary selection, geometry/CRS, snapshot/update semantics and permitted
   derived use before considering an extract adapter. Do not invent a query API
   or treat the general disclaimer as artifact-specific reuse approval.
3. **Vero Beach planning/permit contract:** trace the City's published agendas
   and permit guidance to the actual issuing authority and an explicitly
   supported anonymous report/export. Require a native case ID, source evidence
   URL, status/date definitions, parcel references and revision reconciliation.
   Until found, qualify document evidence separately from structured intake.
4. **East Lansing planning/permit contract:** restore ordinary access to the
   linked department documentation in another approved pass, establish the
   current City-linked portal and supported export, then qualify identity,
   lifecycle and county extent. Do not inspect browser traffic, guess vendor API
   routes, create accounts or infer an export from a public search screen.

For either market, unknown dates remain unknown; retrieval time cannot fill a
publisher-update field. Require native statuses and separate filed, issued and
decision dates. Reconcile revisions and status exits explicitly; an issue-date
window is not a complete pending-application feed. Require named publisher
attribution and reviewed retention/derived-display/export boundaries before use.
Suppress personal ownership, mailing/contact, applicant-person, signature and
unneeded free-text fields before persistence, including raw evidence snapshots.
No full ownership extracts or raw source-replacement exports are proposed.

## Repository Fit and Local Verification

Read `docs/agent-handoff.md`, `docs/agent-onboarding.md`,
`docs/requested-market-queue.md`, the relevant coverage/acquisition guidance and
`docs/parcel-reference-resolution.md`. Existing patterns inspected:

- `app/services/ingestion/connectors/arcgis.py` and `connectors/factory.py`:
  explicit field selection, optional geometry/centroid, bounded pages,
  API-error rejection and checkpointed pagination. Defaults such as `*` and
  1,000 rows are not an acceptable qualification probe by themselves.
- `app/services/ingestion/catalog.json` (Pierce/Bellingham examples) and
  `candidate_catalog.json` (held Ocala example): separate rights, suppression,
  lifecycle and operational gates; a public interface does not grant activation.
- `tests/test_ingestion_connectors.py`: read the relevant ArcGIS test definitions
  for geometry, centroid configuration, keyset behavior and public headers.
- `app/services/parcel_geometry.py` and ingestion `parcel_readiness.py`:
  boundary-display policy gating; configuration is not measured inventory.
- `docs/source-qualification/2026-10-18-loudoun-lola.md`: qualification format
  only; its source-specific permissions and samples do not transfer here.

`python3 scripts/agent_status.py` passed offline; branch, recent commits, dirty
status and relevant diffs inspected. Initial local lookups of
`app/services/ingestion/source_candidates.json` and `tests/test_arcgis_connector.py`
failed because those paths do not exist; corrected to the existing candidate
catalog and connector test file. No code or product tests were run for this
documentation-only change. No implementation, merge or production verification
is claimed. Shared harness/handoff files deliberately remain untouched under
the explicit single-file ownership instruction; this document is the handoff
for the bounded research task.

Final local receipt: `git diff --no-index --check /dev/null
docs/source-qualification/2026-11-10-vero-beach-east-lansing.md` emitted no
whitespace diagnostics (exit 1 denotes the new-file difference). Tracked dirty
diff sizes remained unchanged: handoff 74 additions/2 deletions and MarketSignals
2 additions. A concurrent untracked South Jersey qualification document appeared
during this task and was left untouched. No commit or Git staging was performed.
