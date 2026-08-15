# Permit Source Onboarding Decisions

## Decision Gate

A production source must pass all of these checks:

1. The publisher is the issuing government or its official open-data platform.
2. The feed exposes applications or a lifecycle broad enough to retain
   pre-approval records, not only issued permits.
3. A row identity is complete and unique in the live snapshot. Business permit
   numbers are retained separately when one permit spans multiple rows.
4. Project text, use, address, or parcel data is sufficient for evidence-backed
   entity and retailer matching.
5. The data is current and has a defensible pagination and reconciliation path.
6. Commercial use and redistribution are affirmatively permitted. Anonymous
   public access alone is not treated as a license.

## Approved

### Boulder Construction Permits

- Official ArcGIS layer: `Construction_Permits/FeatureServer/0`.
- Decision: approved for production catalog onboarding.
- Identity: `PermitID`, a complete and unique city GUID; `PermitNum` remains the
  business application/permit number because the city documents duplicates.
- Lifecycle: application, review, applicant-response, approval, issuance, and
  closeout statuses are retained. `IssuedDate` is the conservative boundary
  between pre-approval and approved records.
- Context: project name, description, work type, valuation, address, and city
  and county parcel identifiers are available. The separate building-use and
  square-footage table is reserved for a later enrichment join on `PermitID`.
- Reliability: same-day data was observed. Because no row-modified cursor is
  published, use a daily full snapshot ordered by `PermitID` and content-hash
  reconciliation.
- Rights: CC0 1.0 under the City of Boulder open-data terms.

### Somerville Applications For Permits And Licenses

- Official Socrata dataset: `nneb-s3f7`, filtered to `Building Permit`.
- Decision: approved for production catalog onboarding with ODbL compliance
  flags.
- Identity: `application_id`, the publisher-designated row identifier;
  `application_number` is not treated as guaranteed unique.
- Lifecycle: received, review, approved/waiting, issued, denied, withdrawn,
  expired, and closeout records are retained. `issue_date` is the conservative
  boundary between pre-approval and approved records.
- Context: project or business description, permit subtype, address, parcel,
  coordinates, valuation, applicant, and contractor are available.
- Reliability: daily refresh with a full snapshot ordered by `application_id`
  because older application statuses mutate.
- Rights: ODbL 1.0 allows commercial reuse with attribution, notice, and
  database share-alike obligations. Preserve attribution and review external
  derived-database exposure before distribution.

### Cleveland Building Permit Applications

- Official ArcGIS layer: `Building_Permit_Application_Tasks/FeatureServer/0`.
- Decision: approved for production catalog onboarding with ODbL compliance
  flags.
- Identity: `PERMIT_ID`, which is complete and unique in the live layer;
  `OBJECTID` remains transport metadata only.
- Lifecycle: pending, rejected/not-issued, and issued applications coexist in
  the same feed. `ISSUE_DATE` is the conservative approval boundary, and the
  raw evidence retains structured active/completed task and status history.
- Context: work and job descriptions, use group, category, plan type, address,
  parcel, valuation, contractor business/name, and contractor license are
  available. The feed is strong for permit and contractor evidence but does
  not publish owner, applicant, architect, or developer parties.
- Reliability: daily full snapshot ordered by `PERMIT_ID` because older tasks
  mutate and no row-level update timestamp is published.
- Rights: ODbL 1.0 with attribution, notice, and database share-alike
  obligations.

### NYC DOB NOW Job Application Filings

- Production source: `new_york_ny_dob_now_job_applications`, the official NYC
  Open Data DOB NOW Build Job Application Filings dataset (`w9ak-ipjd`).
- Lifecycle: `Incomplete`, `Pending Plan Examiner Assignment`, `Plan Examiner
  Review`, `Objections`, `QA Failed`, and `Prof Cert QA Review` remain
  pre-approval. `Approved` and `PAA Approved`, with populated `approved_date`,
  are approval/confirmation context. Issued and completion states are outside
  this narrowed source slice because the current graph permit vocabulary
  distinguishes pre-approval and approved evidence first.
- Retailer signal handling: the feed is noisy, so production selects only
  fields needed for identity, lifecycle, address/parcel, job description,
  business-name parties, valuation, area, coordinates, and lifecycle dates.
  Signage, tenant-work, restaurant, retail, and brand terms are detected in
  downstream brand intelligence rather than hardcoded into the source query.
- Suppression: do not select applicant/owner personal names or raw source
  replacement exports. `applicant_business_name` is often an architect,
  engineer, or filing representative, so it is retained as applicant evidence
  but not assumed to be the tenant.
- Reliability: daily health enforces `current_status_date` with a 96-hour SLA
  and a `current_status_date DESC` freshness probe. A July 18, 2026 live
  canary fetched 25 records, validated 25, and observed 9 pre-approval plus
  16 approved rows.

### New York State SLA Pending Licenses

- Production source: `new_york_state_sla_pending_licenses`, the official New
  York State Liquor Authority Current SLA Pending Licenses dataset
  (`f8i8-k2gm`).
- Decision: admit as statewide pre-opening hospitality/food retail context with
  conservative no-raw-source-export terms because the dataset-specific portal
  license is unspecified.
- Lifecycle: `IntakeComplete`, `Under Review`, and `Reconsideration` map to
  pre-approval/opening-intent evidence. `Conditionally Approved` maps to
  approved/conditional confirmation while still remaining pre-final compared
  with active issued license datasets.
- Context: application ID, license type/class/description, legal name, DBA,
  premise address, city/state/ZIP, county, received date, status, alternate
  address, and georeference support chain matching and graph evidence for
  restaurants, grocery, convenience, liquor, hotel/bar, and hospitality
  openings.
- Reliability: live July 18, 2026 checks found rows received on July 17, 2026
  and status counts across `IntakeComplete`, `Under Review`, `Conditionally
  Approved`, and `Reconsideration`. The Build Signals canary fetched 25 rows,
  validated 25, and observed 18 pre-approval plus 7 approved/conditional rows.
  Production pagination uses `application_id`; health proves currentness with a
  `received_date DESC` freshness probe.
- Red flags: DBA can be blank, so brand detection must inspect both DBA and
  legal name. This is alcohol-license-driven and should not be represented as
  a complete retail-opening feed for non-alcohol concepts. Georeference is
  platform-generated and useful for context, but address remains the
  authoritative premise evidence.

### Washington DC DOB Building Permits 2026

- Official ArcGIS layer: `FEEDS/DCRA/FeatureServer/18`, published through DC
  Department of Buildings and Data.gov as Building Permits in 2026.
- Decision: approved for narrow production onboarding as a construction-focused
  pre-approval-through-approved lifecycle source.
- Scope: retain construction rows for alteration/repair, building, new
  building, addition/alteration/repair, tenant layout, demolition, and signs.
  Exclude home-occupation, supplemental, cancelled, expired, revoked, and other
  inactive rows from active opportunity ingestion.
- Identity: `PERMIT_ID` is the source record identifier. `OBJECTID` is used for
  ArcGIS keyset pagination and `GLOBALID` is preserved as source diagnostics.
- Lifecycle: application screening, payment pending, ready for issuance, and
  contractor-information-missing statuses remain pre-approval. `ISSUE_DATE`,
  `PERMIT ISSUED`, and `COMPLETED` mark approved context while retaining the
  exact `APPLICATION_STATUS_NAME`.
- Context: full address, SSL parcel ID, zoning, description of work, permit
  type/subtype/category, applicant, owner, fees paid, coordinates, ward/ANC,
  neighborhood cluster, BID, and last-modified timestamp support evidence-backed
  retailer, owner, applicant, and parcel matching.
- Reliability: the July 18, 2026 live audit found 26,306 rows and
  `LASTMODIFIEDDATE` through July 16, 2026. Use daily `OBJECTID` keyset
  pages plus periodic full snapshots. Because the layer is year-specific,
  provision a 2027 sibling source or annual rolling strategy before January
  2027.
- Rights: Data.gov metadata links the dataset to CC BY 4.0, and District Data
  terms allow commercial reuse unless otherwise noted. Preserve DC attribution,
  no-endorsement context, source URLs, and retrieval timestamps. Applicant and
  owner names can include individuals, so customer-facing surfaces should
  minimize personal-name exposure unless needed as evidence.

### Washington DC Basic Business Licenses Retail Openings

- Official ArcGIS table: `FEEDS/DCRA/FeatureServer/0`, published by the
  District Department of Licensing and Consumer Protection through Open Data DC.
- Decision: approved for narrow production onboarding as approved-only
  retailer, restaurant, grocery, hotel, fuel, food-establishment, and
  service-retail opening context. This is not construction pre-approval and
  must not replace building permits, but it can reveal chain or local operator
  movement before public announcement or opening.
- Scope: retain active in-DC premise rows where the business or primary
  activity indicates restaurant, grocery, food products, delicatessen, hotel,
  inn/motel, fuel, auto wash, or caterer context. Exclude off-premise
  contractors, residential housing licenses, inactive/closed/expired rows, and
  broad raw license exports from customer surfaces.
- Identity: `CUSTOMERNUMBER` plus `OBJECTID` is the source record identifier
  because one customer can hold multiple activity rows at the same premise.
- Context: entity name, trade name, license subtype, activity, premise address,
  SSL parcel identifier, ward/ANC/neighborhood/BID, MAR ID, coordinates,
  license start/end dates, initial issue date, and data refresh timestamp
  support brand matching, entity resolution, parcel joins, and evidence-backed
  opportunity context.
- Reliability: July 18, 2026 live checks returned fresh rows with
  `DATAREFRESHEDON` on July 17, 2026 and active restaurant/grocery examples
  such as `Maman`, `Springbone Kitchen`, `Wada Lab`, and `Grubb's Care
  Pharmacy`. The Build Signals canary fetched 20 rows, validated 20, mapped all
  as approved opening context, and returned an `OBJECTID` keyset checkpoint.
  Use `OBJECTID` keyset pagination and periodic full snapshots.
- Suppression: do not fetch business-owner names, business-owner addresses,
  billing fields, agent names/entities, X/Y projected coordinates, or raw
  source exports. Customer-facing display should emphasize trade/entity,
  activity, address, parcel, dates, and official evidence.
- Rights: District Data terms state that catalog data is public domain under
  CC0 unless otherwise noted and can be used commercially without permission.
  Data.gov metadata for Basic Business Licenses also lists Creative Commons
  Attribution. Preserve DC attribution and no-endorsement context.

### Cincinnati Building Permits

- Official Socrata dataset: `uhjb-xac9`.
- Decision: approved for narrow production catalog onboarding as a commercial
  pre-approval-through-issued Ohio source.
- Scope: retain OBC commercial rows for building, signs, fire protection, HVAC,
  and plumbing permits when a permit number and address are present. Withdrawn,
  expired, voided, revoked, and denied rows are excluded from the active recent
  snapshot.
- Identity: Socrata `:id` is used as the durable source row identifier.
  `permitnum` is preserved as the public permit/application number and should
  not be the only graph identity until duplicate behavior is monitored across
  monthly full snapshots.
- Lifecycle: `APPLIED`, `ROUTE`, review/hold, and other unissued rows remain
  pre-approval. `APPROVED`, `APRV_NR`, issued, temporary certificate, and
  closed/issued rows map to approved while preserving the exact
  `statuscurrent` and `statuscurrentmapped` text as source evidence.
- Context: description, address, parcel PIN, status, permit/work/use class,
  proposed use, company name, valuation, square footage, units, OPAL source
  link, coordinates, and neighborhood support evidence-backed retailer,
  contractor, and tenant-improvement matching.
- Reliability: official portal metadata and live checks on July 18, 2026 found
  records through July 15, 2026. Use a daily recent snapshot ordered by
  `applieddate DESC` plus periodic full reconciliation because older rows can
  change status.
- Rights: City of Cincinnati open-data metadata lists official provenance and
  Public Domain licensing. Preserve City of Cincinnati attribution in derived
  customer-facing evidence.

### Seattle SDCI Land Use Permits

- Official Socrata dataset: `ht3q-kdvx`.
- Decision: approved for production catalog onboarding as a non-residential and
  multifamily land-use early-warning source.
- Identity: Socrata `:id` is used as the durable row identifier because live
  checks found duplicate `permitnum` values; `permitnum` remains the business
  application or permit number.
- Lifecycle: in-review, intake, corrections, publication, and ready-for-issuance
  rows are retained as pre-approval; `issueddate` and final
  issued/completed/closed statuses mark approved context. `decisiondate` is
  retained as `approved_at` evidence but does not by itself override an active
  pre-issuance status. Terminal canceled, withdrawn, and expired rows are
  excluded from active opportunity ingestion.
- Context: Master Use Permit descriptions expose zoning, SEPA, design-review,
  subdivision, shoreline, development-site, commercial, industrial,
  institutional, multifamily, office, retail, and data-center formation signals
  before building permits are issued.
- Reliability: daily public-domain Socrata feed with no row-modified timestamp;
  use a daily recent snapshot ordered by `applieddate DESC, :id ASC`, with
  Socrata `:id` as durable row identity and content-hash reconciliation.
- Rights: City of Seattle Open Data metadata lists the source as Public Domain.

### Columbus / Franklin County Development Records

- Decision: hold for early-warning production. Cleveland remains the Ohio
  production source.
- Columbus Citizen Access exposes building, planning, and engineering records
  with preliminary plan review, zoning preliminary review, engineering
  preliminary review, plan revisions, permit applications, statuses, related
  records, attachments, and inspections. Franklin County SmartGov exposes
  pending through closed/expired statuses plus selected zoning, preliminary
  plan, subdivision sketch-plan, variance, conditional-use, plat, and replat
  records.
- Coverage is fragmented. Columbus covers city jurisdiction only; Franklin
  County coverage excludes many cities, villages, independent township
  authorities, commercial building permits, plumbing, wells, and septic.
- Identity: preserve Columbus application, permit, or record number plus
  parcel, address, detail URL, and related-record links. Preserve Franklin
  application, permit, or license number plus parcel, address, record type, and
  portal detail URL. Never use address alone.
- Retail signal fields can include project name, business/name fields, owner,
  applicant, primary contact, contractor, licensed professional, parcel, site
  address, project description/use, record type, status, submitted/issued/final
  dates, attachments, and related records.
- Blockers: no published bulk feed, API, or change log; Columbus portal terms
  prohibit commercial use of site materials without prior written permission;
  Franklin provides public access and copying but no affirmative commercial
  reuse or redistribution grant was verified.
- Release condition: written commercial reuse and extraction permissions,
  approved automated retrieval/reconciliation, a complete Franklin jurisdiction
  matrix, and sample-based completeness testing across pre-approval records.

### Portland Development And Building Applications

- Official ArcGIS layer: `Public/BDS_Permit/FeatureServer/22`.
- Decision: approved for production catalog onboarding.
- Scope: commercial and residential building permits, site development, land
  use review, development review, and pre-application conferences.
- Identity: `FOLDERKEY`, complete and unique across the live layer;
  `APPLICATION` remains the public-facing number because it can repeat.
- Lifecycle: application, review, approved, approved-to-issue, issued,
  inspection, decision, recorded, and final stages are retained.
- Context: description, work and folder type, occupancy, address, parcel,
  valuation, floor area, and units are available. Named project parties are
  not published and must come from separate lawful evidence.
- Reliability: daily data with `OBJECTID` keyset transport and periodic full
  reconciliation. Source dates more than 48 hours in the future are
  quarantined from canonical lifecycle fields while raw evidence is preserved.
- Rights: PDDL 1.0 under the PortlandMaps open-data terms.

### Pittsburgh Issued Building Permits

- Official WPRDC CKAN resource: `f4d1177a-f597-4c32-8cbf-7885f56253f6`.
- Decision: approved as an issued-only confirmation and enrichment feed, not a
  Pennsylvania early-warning source.
- Identity: `permit_id`, complete and unique in the live resource.
- Context: work description/type, address, parcel, owner, contractor,
  valuation, and coordinates are available.
- Lifecycle limitation: every live row already has `issue_date`; labels such
  as `In Review` reflect post-issuance or amendment workflow.
- Rights: CC BY 4.0 with source attribution required.

### Montgomery County Commercial Permits

- Official Socrata dataset: `7ate-xrxm`.
- Decision: approved as an issued-only Maryland confirmation source.
- Identity: `permitno`, complete and unique in the live dataset.
- Context: commercial permit type, work/use, description, valuation, building
  area, address, and coordinates are available.
- Lifecycle limitation: every published row already has `issueddate`; there
  are no application-stage records or project parties/parcels.
- Reliability: daily refresh with permit-number keyset pagination and periodic
  full reconciliation.
- Rights: official metadata declares Public Domain.

### Milwaukee Commercial Permit Work Data

- Official CKAN resource: `828e9630-d7cb-42e4-960e-964eae916397` in the City
  of Milwaukee Department of Neighborhood Services dataset `buildingpermits`.
- Decision: narrow admit as an issued-only Wisconsin confirmation source, not
  an early-warning or pre-approval source.
- Identity: `Record ID`, complete and unique in the live resource; CKAN `_id`
  remains transport metadata only.
- Scope: retain commercial alteration and commercial new construction permit
  types. Residential rows are out of scope for commercial signals.
- Context: address, permit type, issued/opened dates, construction cost, use of
  building, and dwelling-unit impact are available. Parcel, applicant,
  contractor, owner, project name, and detailed work descriptions are not
  published in the bulk feed.
- Lifecycle limitation: every live row has `Status` = `Issued` and a `Date
  Issued`; the source cannot detect submitted, under-review, approved-to-issue,
  or denied/withdrawn records.
- Reliability: monthly source update with same-day portal metadata observed.
  Use CKAN datastore pages ordered by `Record ID` or `_id` plus periodic full
  snapshot reconciliation because no row-modified cursor is published.
- Rights: Creative Commons Attribution under the City of Milwaukee open-data
  portal; preserve source attribution and license notice.

### Minneapolis Commercial Construction Code Permits

- Official ArcGIS layer: `CCS_Permits/FeatureServer/0`, service item
  `91d7cc54f31a45b0982fca5117f16a0f`.
- Decision: narrow admit for City of Minneapolis commercial construction
  permits. Hennepin County development review and the Minneapolis planning
  applications dashboard remain holds because no comparable official bulk/API
  feed was verified for those records.
- Scope: retain `permitType = 'Commercial'` rows for building-commercial
  additions, new construction, remodels, roof/window work, unit construction,
  and unit finish. Residential, plumbing, mechanical, site, and wrecking rows
  are out of scope unless separately admitted.
- Identity: use `OBJECTID` as the immutable source row key. Preserve
  `permitNumber` as the public permit/application number, but do not assume it
  is unique because commercial permits can repeat across map points or parcel
  geometries.
- Field mapping: `permitNumber` -> `source_permit_id`; `OBJECTID` ->
  `source_record_id`; `Display` -> `site_address`; `APN` -> `parcel_id`;
  `permitType` + `workType` + `occupancyType` -> `permit_type`/`work_type`;
  `comments` -> `description`; `value` -> `valuation`; `totalFees` ->
  `fees`; `status` + `milestone` -> `raw_status`; `issueDate` ->
  `issued_at`; `completeDate` -> `completed_at`; `applicantName` ->
  `contractor_or_applicant_name`; `fullName` -> `owner_name`;
  `applicantAddress1`/`applicantCity` -> `applicant_address`; `Longitude` and
  `Latitude` -> coordinates; `Neighborhoods_Desc` and `Wards` -> jurisdiction
  context.
- Lifecycle: `In Process`/`Fees` is pre-issuance; `Issued` is approved/issued
  with `issueDate` as the conservative boundary where city metadata says work
  can begin; `Open` is post-issuance inspection/final-inspection activity;
  `Closed` is final/closed; `Denied`, `Withdrawn`, `Cancelled`, `Expired`,
  `Void`, and `Stop Work` map to terminal or exception states and must not be
  promoted as active approvals.
- Reliability: same-day 2026 commercial issued records and one commercial
  `In Process` record were observed in the live layer. The layer exposes
  398k+ total rows, 45k+ commercial rows, `maxRecordCount` 16000,
  `supportsPagination`, and JSON/GeoJSON/PBF query formats. Use daily
  `OBJECTID` keyset or ArcGIS result-offset pages capped below 16000, with
  periodic full snapshot reconciliation because no row-modified timestamp or
  deletion cursor is published.
- Evidence URL: build source evidence links against
  `https://services.arcgis.com/afSMGVsC7QlRK1kZ/arcgis/rest/services/CCS_Permits/FeatureServer/0/query`
  with `where=OBJECTID=<source_record_id>`, `outFields=*`,
  `returnGeometry=false`, and `f=json`.
- Rights: the item metadata says the City of Minneapolis has waived copyright
  and related rights in open data to the extent possible under law. Preserve
  attribution, as-is/no-warranty disclaimers, and downstream privacy
  minimization for named owners and applicants.

### Henderson Commercial Development Permits

- Official ArcGIS layer: `public/OpenDevPermits/MapServer/2`.
- Decision: approved for production early-warning and confirmation ingestion.
- Identity: `GISHISTORYQUEUEID`, a complete source UUID unique within the
  commercial layer; `CASEID` and `CASENUMBER` remain business evidence.
- Lifecycle: pending, hold, awaiting application/final review, issued, done,
  expired, cancelled, and void states are retained. `ISSUEDATE` is the
  conservative approval boundary.
- Context: description, case/work type, address, parcel, owner, project name
  when available, application date, issue date, and last-change date.
- Reliability: daily data with indexed `OBJECTID` keyset transport and full
  snapshot reconciliation by source UUID.
- Rights: public domain under the adopted City of Henderson Open Data Policy.

### Las Vegas / Clark County Permit Sources

- Decision: hold for production permit ingestion. Las Vegas has strong permit
  content and Clark County has rich Accela lookup surfaces, but no current,
  supported, bulk permit API with usable schema and affirmative rights was
  verified across the target market.
- Las Vegas official sources: city ArcGIS `DevelopmentServices/BuildingPermits`
  layer `0`, ArcGIS Online item `84445be9ab0740bd8a75ea8561780cc5` (`Building
  Permits Archived`), and private source service `Building_Permits_MV`.
- Las Vegas schema value: application number/key, status, permit/work type,
  address, parcel, valuation, entered/issue/completion/certificate/inspection
  dates, applicant, ward, subdivision, area, and work descriptions. The older
  public REST layer contains accepted, open, hold, issued, closed, expired,
  cancelled, stop-work, withdrawn, deleted, and blank states, including
  unissued application-stage rows.
- Las Vegas blockers: the full-field public REST layer appears historical; no
  2026 permit numbers were returned in spot checks. The current ArcGIS open-data
  item is an archived public view whose visible public table exposed only
  system `ObjectId`, while its source service requires a token. The open-data
  wrapper is therefore not a sufficient production API despite public-domain
  city open-data policy language.
- July 18, 2026 re-check: the city `DevelopmentServices/BuildingPermits`
  layer still publishes a valuable field schema in HTML metadata, including
  `APNO`, `APKEY`, `STATUS`, `APTYPE`, `APDESC`, `PROPERTY`, `PRCLID`,
  valuation, entered/issue/completion/certificate dates, applicant, address,
  and work descriptions. However, equivalent JSON row queries returned server
  errors, and the ArcGIS Online hosted mirror exposed only `ObjectId` in both
  metadata and row samples. Keep Las Vegas as an operational hold until the
  rich schema is queryable through a stable public endpoint.
- Clark County official sources: Accela Citizen Access and county ArcGIS
  `Accela/ACCELA_XAPO_POINTS` and `Accela/AccelaPoints` services.
- Clark County schema value: ACA search exposes building, planning, fire, and
  public-works record searches by address, contractor/license, parcel, record
  number, project name, type, contact, and date. County ArcGIS Accela services
  expose parcel, owner, address, zoning, jurisdiction, value, and modification
  fields, but not a complete public permit/application header feed.
- Rights: Las Vegas open-data policy places datasets published on the open-data
  portal in the public domain. Clark County public website/GIS terms do not
  grant commercial redistribution; GIS subscription language explicitly says
  purchased data may not be resold.
- Release condition: admit only if Las Vegas republishes the full current permit
  table through its open-data portal/API with the rich permit fields available
  in row queries, or Clark County provides a documented Accela/export API, with
  stable row identity, status taxonomy, historical reconciliation, pagination
  limits, and written permission for automated extraction, enrichment, customer
  display, and redistribution.

### Maryland Early-Warning Sources

- Montgomery County's strongest commercial source is approved separately as a
  confirmation feed, but publishes no unissued applications.
- Baltimore City/County, Prince George's County, and Howard County did not
  expose a stronger verified source meeting both early-stage and licensing
  gates.
- Decision: Maryland remains an early-warning hold.

### Los Angeles Early-Warning Sources

- Decision: narrow City LADBS admit plus County EPIC-LA hold.
- Production source: `los_angeles_ca_building_permits_submitted`.
- Endpoint:
  `https://data.lacity.org/resource/gwh9-jnip.json`. The official LADBS
  submitted-permit feed publishes building permits submitted from 2020 to
  present through the Los Angeles Open Data Socrata API. Live validation on
  July 18, 2026 returned current July 2026 commercial submitted rows with
  `permit_nbr`, address, ZIP, APN, zoning, use/work description, valuation,
  plan-check status, coordinates, and refresh timestamp.
- Admitted lifecycle slice is commercial submitted-through-issued records with
  `status_desc` in submitted, plan-check assigned/in-progress, corrections,
  quality-review, plan-check-approved, ready-to-issue, issued, and CofO-issued
  states. The graph stores `Submitted`, `PC in Progress`, `Ready to Issue`, and
  related detailed statuses as source evidence while canonical
  `approval_stage` remains `pre_approval` until `issue_date`, `Issued`, or
  `CofO Issued` evidence appears.
- Retailer/chain signal value is strongest in `work_desc`, `use_desc`, address,
  APN, zoning, valuation, and later graph enrichment; this normalized feed does
  not expose applicant, tenant legal entity, architect, engineer, or contractor
  names.
- Rights pass is a narrow value-added admission based on the official Los
  Angeles/Data.gov public API and bulk resources, with City attribution,
  retrieval-date/currentness caveats, no warranty claims, and no raw
  source-replacement resale.
- Freshness note: `refresh_time` is selected and required in the production
  query because it is the publisher's refresh timestamp. Do not enforce it as
  `freshness_field` yet: a July 18, 2026 live check found the newest
  `refresh_time` was July 12, 2026, which exceeds the current 96-hour SLA.
  Keep the field visible for operator review and enable strict canary
  freshness once the publisher watermark stabilizes.
- LA County EPIC-LA is the best technical candidate. Its official daily
  FeatureServer contains planning and permit cases with application dates,
  statuses such as online/new/review/waiting-for-applicant/hearing-ready,
  proposed use, descriptions, address, AIN, valuation, and geometry. The audit
  found more than 17,000 permit rows in review.
- EPIC-LA `CASENUMBER` repeats across geometries or historical versions, while
  `OBJECTID` is transport identity and no durable case-version key is published.
  The source also lacks applicant data and an affirmative grant for commercial
  storage, enrichment, customer display, and redistribution.
- County weekly Cases Filed PDFs and City Planning recent filings provide
  excellent filing-day narratives, applicant, parcel, zoning, and entitlement
  evidence, but neither offers a supported historical reconciliation API with
  production reuse rights. They remain manual-review evidence only.
- LADBS interactive lifecycle pages remain out of scope; the admitted path is
  the official Socrata submitted-permit feed, not scraping.
- Re-audit EPIC-LA first if the County documents a stable case-version key,
  deduplication rules, and commercial redistribution permission. Do not replace
  those gates with scraping or inferred identifiers.

Evidence URLs:
`https://data.lacity.org/resource/gwh9-jnip.json`;
`https://catalog.data.gov/dataset/building-and-safety-building-permits-submitted-from-2020-to-present-n`;
`https://data.lacity.org/terms-of-use`;
`https://lacity.gov/government/open-data`.

### Corona Business License Applications

- Decision: hold. CorStat Business Licenses (`ibcd-bv79`) is technically useful
  for pre-opening retailer and service-business detection, but it is stale and
  has a rights conflict.
- Technical value: the Socrata table exposes account, license type, submitted
  date, DBA, business address/city, location type, business type, application
  description, SIC description, business status, and license status. New
  Application rows with pending/taxpayer/gross-receipts/PD-approval/to-be-issued
  statuses would map to pre-approval if admitted.
- Blockers: the official portal metadata reports Public Domain, but the
  dataset description/disclaimer says the data is for public information and
  not for commercial, legal, or other use. The feed also appears stale: a July
  18, 2026 scout found the latest portal/data update and pending rows around
  June 2024.
- Product note: live metadata/top values included recognizable chain concepts
  such as Redbox, MetroPCS, WaBa Grill, Supercuts, Jersey Mike's, Palm Beach
  Tan, Coinstar, and T-Mobile. Revisit only if Corona or HdL publishes current
  rows with written commercial SaaS reuse permission.

### San Francisco Planning Department Non-Project Records

- Decision: admit as a narrow San Francisco planning-entitlement and review
  source for pre-approval-through-approved retailer/development context.
- Production source: `san_francisco_ca_planning_department_non_project_records`.
  The official SF Planning Socrata dataset is exported from Accela, excludes
  parent PRJ records, and includes supplemental child records required to
  review development projects.
- Official endpoint: `https://data.sfgov.org/resource/y673-d69b.json`.
- Rights posture: metadata lists `Public Domain U.S. Government` with City and
  County of San Francisco Planning Department attribution. Preserve attribution,
  retrieval-date/currentness caveats, no endorsement, and no raw
  source-replacement resale.
- Signal filter: the first production slice keeps a narrow record-type set for
  conditional use, discretionary review, preliminary review, variance, zoning
  administrator, planning code amendment, certificate of appropriateness, and
  shadow review. Enforcement, complaint-heavy, withdrawn/cancelled/disapproved,
  and abated/no-violation records are excluded from active opportunity signals.
- Lifecycle handling: `Submitted`, `Accepted`, `Open`, pending, under-review,
  consultation, on-hold, and in-development statuses remain pre-approval.
  `Approved`, `Closed - Approved`, `Closed - Issued`, and
  `Closed - CEQA Clearance Issued` are treated as approved/confirmation, with
  `close_date` retained as approval evidence.
- Admitted fields: record ID, parent ID, record type, record status, open/close
  dates, project name, description, project address, block/lot parcel context,
  building-permit references, applicant organization, and PIM link.
- Product note: July 2026 live samples included submitted Starbucks conditional
  use and discretionary review records for extended operating hours at 3995
  24th Street, 1800 Irving Street, and other San Francisco locations.
- Suppression policy: applicant personal names, assigned planner names,
  enforcement/complaint text, child-record internals, and raw source exports
  remain excluded. Applicant organization is kept as public organization
  context, not as proof of the retail brand by itself.

### Marin County Commercial Building Permits

- Decision: admit as a narrow Marin County commercial building-permit source
  for received-through-issued lifecycle context.
- Production source: `marin_county_ca_commercial_building_permits`. County of
  Marin publishes the Building Permit Socrata dataset with daily updates,
  Community Development / SQL Database provenance, and coverage from January 1,
  2014 to present.
- Official endpoint: `https://data.marincounty.gov/resource/mkbn-caye.json`.
- Rights posture: metadata lists the Open Data Commons Open Database License
  with County of Marin attribution. Preserve attribution and ODbL notices, and
  require share-alike review before customer-facing derived database exports or
  broad API redistribution. Raw source-replacement resale remains excluded.
- Signal filter: the first production slice keeps `COMMERCIAL` permits with
  `received_date` from 2026 forward and either no issued date or a 2026 issued
  date. This captures current received applications while retaining same-year
  issued confirmation rows.
- Lifecycle handling: `issued_date IS NULL` maps to pre-approval because Marin
  describes `received_date` as permit application receipt. Populated
  `issued_date` maps to approved because Marin describes it as the date the
  permit has been fully approved and issued. Simpler on-demand permits may lack
  received dates and should stay approved-only context outside this slice.
- Admitted fields: unique ID, permit tracking ID, permit number, received and
  issued dates, address, parcel number, ZIP/city, commercial type, work class,
  fee-code title, description, contractor name, construction value, latitude,
  and longitude.
- Product note: live July 2026 samples included unissued commercial received
  rows such as a new Stinson Beach fire station and commercial sign/remodel
  work, while the same feed also contains tenant/restaurant/fitness and bank
  descriptions in recent commercial activity.
- Suppression policy: contractor address/license, raw fee-code internals,
  received/issued year buckets, raw location objects, latest issued/received
  convenience field, and raw source export are excluded from production
  mapping.

### NYC DOHMH Restaurant Permit Applicants

- Decision: narrow pre-inspection restaurant/chain signal admit.
- Production source: `new_york_ny_dohmh_restaurant_permit_applicants`.
- Endpoint:
  `https://data.cityofnewyork.us/resource/43nn-pn8j.json`. The official NYC
  Open Data restaurant inspection-results feed contains applicant rows where
  `inspection_date = 1900-01-01T00:00:00.000`; NYC uses this sentinel for
  establishments that have applied for a permit but have not yet been inspected.
  Live validation on July 18, 2026 returned current July 17, 2026 rows with
  DBA, CAMIS, borough, address, ZIP, BIN/BBL, coordinates, and record date.
- Admitted slice is only the pre-inspection applicant state. This is not a
  general building-permit source and should not be used as approval evidence.
  It is valuable as early retailer/chain context because DBAs can appear before
  inspection, grade, or public opening activity.
- Use Socrata `:id` as raw evidence identity and preserve `camis` as the
  establishment/application number for grouping and graph resolution. Suppress
  phone, grade, violation, and post-approval inspection fields from this source
  slice.
- Rights pass is based on NYC Open Data unrestricted public reuse with standard
  no-warranty terms. Build Signals stores the rows as value-added restaurant
  opening intelligence with NYC attribution, retrieval-date/currentness caveats,
  and no raw source-replacement resale.

Evidence URLs:
`https://data.cityofnewyork.us/Health/DOHMH-New-York-City-Restaurant-Inspection-Results/43nn-pn8j`;
`https://data.cityofnewyork.us/api/views/43nn-pn8j`;
`https://opendata.cityofnewyork.us/faq/`;
`https://opendata.cityofnewyork.us/overview/`.

### San Jose Planning And Building Permit Records

- Decision: admit San Jose Planning Permit Applications as
  `san_jose_ca_planning_permit_applications`; keep issued building-permit GIS
  layers as confirmation/hold material rather than early-warning production.
- Production planning source: City GIS ArcGIS
  `PLN/PLN_Geocortex_Public_PRD/MapServer/153`, `Other Development Permits
  (2020-Present)`, under the public `Planning Permit Applications` group. The
  layer includes development, zoning, subdivision, environmental review, and
  related planning permit types and excludes cancelled, denied, expired,
  rejected, withdrawn, dropped, and legacy records.
- Planning lifecycle: `New`, `Under Review`, `Scope of Work Review`, `Review
  Letter Sent`, `Notice Sent`, `Noticed for Hearing`, `Preparing for Hearin`,
  `Decision Pending`, `Pending`, `Tentative Approval`, `Recomd Approval`, and
  `Appealed` map to pre-approval. `Approved`, `Approved/Certified`, `Approved
  with Condit`, `Complete`, and `Pending Closeout` map to approved/confirmation.
  `PERMITISSUE` can read `ISSUED` for review-stage rows, so `PERMITSTATUS` is
  the lifecycle authority.
- Planning identity and context: `FOLDERRSN` is the durable source record ID;
  `REFERENCENUM`, `FOLDERNAME`, `FOLDERNUM`, `ENTERPRISEID`, `GlobalID`, and
  `OBJECTID` are retained as evidence or transport metadata. Address, APN,
  applicant, owner, folder name/description, work description, subtype, permit
  type, zoning, in/issue/final/update dates, and point geometry support
  evidence-backed developer, owner, applicant, parcel, and chain/retail context.
- Reliability: the July 18, 2026 live audit found status counts for both
  pre-approval and approved planning records, including current `Under Review`
  and `Appealed` rows. A Build Signals canary fetched 30 records, validated 30,
  and mapped 7 pre-approval plus 23 approved rows. Production ingestion keeps
  stable `OBJECTID` keyset pagination, while daily health enforces
  `LASTUPDATE` freshness through a tiny `LASTUPDATE DESC` freshness probe.
- Suppression: do not fetch or expose project manager, issuing user, last
  editor, notes, raw geometry export, or raw source replacement exports. Owner
  and applicant names can include people, so customer-facing displays should
  prefer organization evidence and use personal names only when needed for
  provenance.
- Rights: San Jose's Development Data page links to Planning Permits Map, and
  the city Open Data page says data is published in machine-readable format
  under an open license allowing reuse and redistribution. Preserve city
  attribution, source URLs, retrieval timestamps, and no-endorsement context.
- Building permit hold: SJPermits public permit search and the City GIS
  Building Permits group (`340` recent, `341` active, `342` expired) remain
  confirmation-only. Those layers expose issued building-permit records; spot
  checks found `ISSUEDATE IS NULL` returned zero records, and
  `PERMITAPPROVAL` values describe scope/completion labels rather than intake,
  plan-check, approved, or ready-to-issue states.

### Sacramento Building And Planning Records

- Decision: confirmation-only and planning-rights hold. Sacramento publishes
  official applied and issued building-permit ArcGIS layers, and the city also
  exposes planning records through AgencyCounter and e-Planning surfaces.
- Lifecycle: building feeds cover applied, plan-check, processing,
  ready-to-issue, issued, finaled, certificate-of-occupancy, and expired
  records. AgencyCounter exposes richer pre-approval planning states such as
  under consideration, authorized, approved, complete, denied, and withdrawn.
- Identity: use jurisdiction plus the `Application` number for permit feeds;
  `OBJECTID` is transport metadata. Planning record/file numbers appear to be
  natural identities, but no supported machine-readable identity, deletion, or
  lifecycle-transition contract was verified.
- Context: project name, work description, contractor, type/subtype/category,
  address, parcel number, ZIP, valuation, square footage, activity code,
  community-plan area, and council district can support retailer inference.
  Reliable tenant, applicant, owner, parent-chain, and brand fields are not
  present in the building schema.
- Reliability: city permit exports are monthly and include current-year and
  archive layers. Reconcile by `Application`, retain status history, and
  deduplicate annual rollover snapshots. Keep the scope labeled City of
  Sacramento only.
- Rights: city open-data terms allow machine consumption and derivative works,
  but AgencyCounter terms prohibit commercial copying, downloading,
  retransmission, distribution, or exploitation without prior permission.
- Release condition: written commercial rights and a supported export/API for
  AgencyCounter planning records, including stable record identity, update
  timestamps, deletions, and document-link semantics.

### San Diego Development Permit Approvals

- Official source: City of San Diego Open Data Portal `Approvals for
  development projects`, published by Development Services with daily CSV
  downloads for created, active, issued, closed, annual, and all approvals.
- Decision: approved for production early-warning and confirmation ingestion.
- Identity: use jurisdiction plus `APPROVAL_ID` as source identity and retain
  `PROJECT_ID`, `DEVELOPMENT_ID`, `JOB_ID`, and source file URL as evidence.
  In the 2026 created-approvals slice, `APPROVAL_ID` was populated and unique.
- Lifecycle: created/opened, pre-screen, in-queue, payment, in-review,
  recheck/resubmitted/updates-required, reviews-complete, ready-for-issuance,
  approved-upon-final-payment, invoice-paid/all-fees-paid, issued, inspecting,
  inspection-followup, completed/finaled/closed, cancelled, withdrawn, and
  expired states are retained. `APPROVAL_ISSUE_DATE` is the conservative
  approval boundary.
- Context: project title and scope, approval scope, approval type and
  processing code, job address, APN, latitude/longitude, building-code
  description, valuation, floor area, stories, unit counts, permit holder, and
  project dates are available. Contractor and applicant are not published in
  the bulk schema; use `APPROVAL_PERMIT_HOLDER` as the only named party from
  this source.
- Reliability: no row-level API or update cursor was verified. Use daily CSV
  snapshot reconciliation, preferring the current-year created/issued/closed
  slices for incremental checks and full active/all files for periodic
  reconciliation. The portal exposes file downloads rather than a documented
  paginated API, so there are no source-stated page-size or rate-limit
  contracts.
- Rights: dataset metadata links to ODC PDDL, and DataSD terms cover downloaded
  data and derivative works with warranty, liability, indemnity, and
  dataset-specific additional-terms caveats.

### Mesa Commercial Permit Submittals

- Decision: admit as a narrow Arizona commercial permit-submittal source for
  pre-approval-through-approved retailer and tenant-work detection.
- Production source: `mesa_az_commercial_permit_submittals`. The City of
  Mesa's official Data Hub publishes Development Services Permit Submittals and
  Resubmittals Logged In, described as permit applications entered into Accela
  from customer submission.
- Official endpoint: `https://data.mesaaz.gov/resource/kg7m-y6f3.json`.
- Signal filter: the first production slice keeps commercial records opened
  from 2024 forward, with stable row number, record ID, workflow status,
  description, submittal/open/status dates, address, and coordinates. Closed,
  void, canceled/cancelled, and expired statuses are excluded from active
  collection.
- Lifecycle handling: rows are workflow events, not one row per permit. Use
  `row_number` as source identity and `record_id` as application/permit group
  identity. In-review, revisions-required, waiting-for-revisions, pending, and
  accepted-plan-review rows remain pre-approval; `C of C Issued`, issued,
  finaled, complete, and completed statuses are treated as approved/confirmation
  evidence.
- Admitted fields: row number, record/application ID, commercial record type,
  submittal type, record open/status dates, task, description, workflow status,
  status/distribution/submittal dates, permit/street address, longitude, the
  source's misspelled `latitiude` field, and optional geolocation.
- Product note: July 2026 live samples included `Dutch Bros #11114` at
  `3703 S POWER RD` and `Dutch Bros Coffee AZ1645` at `1230 S MESA DR` while
  still in review, plus other named tenant/project examples such as Los Altos
  Ranch Market and Hyatt Place.
- Suppression policy: staff/user workflow names (`assigned_by_name`,
  `action_by_name`), date bucket fields, task completion flags, total-day
  metrics, and raw source replacement exports remain excluded.
- Rights posture: Mesa open-data guidance allows commercial and non-commercial
  use with City attribution and no-warranty/currentness terms. Preserve City of
  Mesa / Development Services attribution and avoid raw feed resale.

### Tempe Building Permits Commercial Context

- Decision: admit as a narrow Arizona commercial/tenant-work permit source for
  pre-approval-through-approved context.
- Production source: `tempe_az_building_permits_commercial_context`. The City
  of Tempe publishes the Building Permits ArcGIS layer through official
  data.gov metadata with public access and CC BY 4.0 licensing.
- Official endpoint:
  `https://services.arcgis.com/lQySeXwbBg53XWDi/ArcGIS/rest/services/building_permits/FeatureServer/0/query`.
- Signal filter: retain records with recent `StatusDateDtm`, permit number and
  address, active or approved lifecycle statuses, and commercial, tenant,
  retail, restaurant, office, hotel, market/food, medical, or similar
  development text. Exclude low-signal water/sewer/street-light permit
  descriptions from the first production slice.
- Lifecycle handling: `Applied`, `Ready for Issuance`, and `Ready to Issue`
  remain pre-approval. `Issued`, `CofO Issued`, `TCO Issued`, `Final`,
  `Finaled`, and `Closed` are approved confirmation. `Expired` and `Revoked`
  are excluded from active opportunity ingestion.
- Identity: use `OBJECTID` as source-row identity and `PermitNum` as
  application/permit number, because related building, engineering, fire, and
  utility rows can share or overlap project context.
- Admitted fields: permit number, project name, description, permit class/type,
  lifecycle status, applied/issued/completed/status dates, address, contractor
  company and license, valuation, square footage, housing units, zone as raw
  evidence, and coordinates. The source does not expose owner, applicant, or
  parcel fields, so it should enrich retailer/development detection rather
  than serve as a complete graph-party source.
- Reliability: the July 18, 2026 live canary fetched 35 rows with 35 valid, 0
  failed, and stage buckets of 8 pre-approval and 27 approved records.
- Suppression policy: contractor phone/email/address and raw source replacement
  exports remain excluded. Treat residential owner-like project names
  cautiously even when they pass text filters.
- Rights posture: CC BY 4.0 permits commercial reuse with attribution. Preserve
  City of Tempe attribution, change/currentness notice, no-endorsement context,
  source URLs, and retrieval timestamps.

### Tucson Commercial Building Permit Hold

- Decision: legal hold for City of Tucson PDSD Commercial Building permits
  despite strong pre-approval signal quality.
- Candidate endpoint:
  `https://gis.tucsonaz.gov/arcgis/rest/services/PublicMaps/PermitsCode/MapServer/81/query`.
- Technical shape: ArcGIS layer `81`, filtered to `TYPE = 'Commercial
  Building'`, `ACTIVE = 'Yes'`, and non-terminal statuses. Page by `OBJECTID`
  ascending or use daily snapshots ordered by `APPLYDATE DESC`; no durable
  row-modified cursor was verified.
- Lifecycle mapping if rights are unlocked: `Submitted`, `Submitted - Online`,
  `Awaiting Submittal`, `In Review`, `Needs Resubmittal`, `In Revision`,
  `Fees Due`, and `Approved - Awaiting Customer Attention` map to
  pre-approval; `Approved`, `Issued`, `Inspections`, and `Inspections Complete`
  map to approved/context.
- Useful fields: `ID`, `NUMBER`, `ADDRESS`, `PARCEL`, `STATUS`, `TYPE`,
  `WORKCLASS`, `APPLYDATE`, `ISSUEDATE`, `VALUE`, `SQUAREFEET`,
  `PROJECTNAME`, `DESCRIPTION`, `PRO_URL`, `LAT`, and `LON`. Use `ID` as
  stable source identity and `NUMBER` as the business permit number.
- Product note: live July 2026 samples surfaced active unissued commercial
  rows such as `TC-COM-0726-01127` at `802 E UNIVERSITY BL` with `Submitted -
  Online` status and the description `Remodel Interior for new tenant - Better
  Buzz Coffee`. This is exactly the kind of retailer/chain signal the pipeline
  wants, but it cannot enter production without rights clearance.
- Suppression policy if unlocked: keep permit number, address, project text,
  status, parcel, valuation, dates, coordinates, and official URL. Do not fetch
  or expose applicant, reviewer, phone/email, or account/contact details from
  linked PRO pages without separate licensing and privacy review.
- Rights blocker: Tucson PRO terms/disclaimer characterize permit/parcel data
  as provided for personal use, and the ArcGIS/open-data layer does not provide
  an affirmative commercial SaaS reuse or redistribution license. Admit only if
  Tucson grants written commercial storage, customer display, redistribution,
  derived database, and bounded export rights or publishes a clear open-data
  license covering this layer.

### Texas Secondary-Market Permit And Development Sources

- Decision summary: Fort Worth is the strongest Texas secondary-market
  pre-approval candidate; Harris County is a narrow issued/project-status
  supplement; Arlington has useful official lifecycle fields but remains a
  shallow-signal and rights-confirmation hold; Dallas, Houston city, San
  Antonio/Bexar, Plano, and Frisco remain holds until supported bulk/API access
  and commercial SaaS rights are explicit. Austin remains the current Texas
  production reference source.
- Fort Worth official source:
  `https://mapit.fortworthtexas.gov/ags/rest/services/CIVIC/Permits/FeatureServer/0`.
  Decision: narrow admit candidate for current commercial permit and development
  signals, subject to final rights review. The public layer supports JSON,
  GeoJSON, PBF, pagination, order-by, statistics, and a 1,000-row page limit.
  Distinct live statuses include `Pending`, `Accepted`, `Plan Review`, `In
  Review`, `Corrections Submitted`, `Awaiting Client Reply`, `Pending Fees`,
  `Administrative Approval`, `Approved`, `Approved w/Conditions`, `Partial
  Approval`, `Issued Without Contractor`, `Issued`, `Finaled`, `Complete`,
  `Denied`, `Withdrawn`, `Void`, and `Expired`. That makes it a true
  pre-issuance signal source.
- Fort Worth ingestion shape: query layer `0` with
  `where=Permit_Type in ('Commercial Building Permit','Commercial Grading Permit','Commercial Accessory Structure')`
  plus optional downstream filters on `Use_Type`, `Specific_Use`,
  `B1_SPECIAL_TEXT`, `B1_WORK_DESC`, `JobValue`, and `SqFt` for retail,
  restaurant, tenant-finish, new-building, grading, major alteration, and
  chain-name matches. Page by `CAPID` keyset or result-offset pages under 1,000
  records; request `outSR=4326`; include geometry when coordinates are missing.
  Evidence URL pattern:
  `.../FeatureServer/0/query?where=CAPID=<source_record_id>&outFields=*&returnGeometry=false&f=json`.
- Fort Worth field mapping: `CAPID` or `Unique_ID` -> `source_record_id`;
  `Permit_No` -> `source_permit_id`; `Permit_Type` -> `permit_type`;
  `Permit_SubType` / `Permit_Category` -> `work_type`; `Current_Status` ->
  `raw_status`; `File_Date` -> `applied_at`; `Status_Date` -> status/update
  evidence; `B1_SPECIAL_TEXT` and `B1_WORK_DESC` -> `description`;
  `Address`/`Zip_Code` -> `site_address`; `Owner_Full_Name` -> owner/evidence
  party; `JobValue` -> `valuation`; `Use_Type`/`Specific_Use` -> proposed use
  or occupancy; `SqFt` -> `square_feet`; `Latitude`/`Longitude` -> coordinates.
  `Permit_No` is not row-unique and must not be the sole identity.
- Fort Worth rights: the official open-data item for development permits is
  labeled CC BY 4.0 and city open-data policy calls for open licenses, but the
  directly queryable CIVIC service has sparse service-level license text. Admit
  only with attribution, source notices, no endorsement, and product/legal
  approval for commercial storage, matching, customer display, and bounded
  export.
- Decision: admit Texas Comptroller Sales Tax Locations as approved-only
  statewide retailer/opening context.
- Production source: `texas_comptroller_sales_tax_locations`. The Texas
  Comptroller of Public Accounts publishes All Permitted Sales Tax Locations
  and Local Sales Tax Responsibility through the official Texas Open Data
  portal with Public Domain metadata. The dataset includes sales-tax outlets
  active during the last four years and inactive outlets with out-of-business
  dates.
- Official endpoint:
  `https://data.texas.gov/resource/3kx8-uryv.json`.
- Lifecycle handling: active locations with `permit_date` and no
  `out_of_business_date` are normalized as approved. `first_sale_date` is
  retained as source evidence because future first-sale dates can reveal
  pre-opening retailer movement, but no application/review stage is present, so
  this source must not be counted as permit pre-approval coverage.
- Admitted fields: composite taxpayer/location identity, taxpayer name,
  organization type, location number/name, location address, jurisdiction/postal
  city, state, ZIP, county code, NAICS, permit date, first-sale date, and
  out-of-business date.
- Suppression policy: taxpayer mailing address fields, ZIP+4 fields, tax
  authority IDs, raw taxpayer export, and raw source export remain excluded.
  Taxpayer number is used only as part of stable source identity and should not
  be emphasized in customer-facing UI.
- Product note: live July 2026 samples included chain rows such as Starbucks
  and Chipotle with permit dates in June/July 2026 and future first-sale dates
  in August/September 2026. Use this as a retailer-opening enrichment and brand
  signal, not as a construction or zoning approval.
- Harris County official source:
  `https://www.gis.hctx.net/arcgishcpid/rest/services/Permits/IssuedPermits/FeatureServer/0`.
  Decision: narrow admit candidate as Harris County unincorporated issued
  permit/project-status context, not a complete Houston city early-warning feed.
  The layer supports JSON/GeoJSON/PBF, pagination, statistics, and 2,000-row
  pages. Live commercial-relevant app types include `Commercial Building (Fire
  Code)`, `Site Development`, `Speculative Lease Space`, `Speculative Lease
  Space Improvement`, and `Small Tenant Improvement Projects`; a live count
  check returned 66k+ records for a conservative commercial subset.
- Harris County ingestion shape: query layer `0` with commercial/development
  `APPTYPE` filters and optional exclusion of tract-home/residential app types.
  Page by `OBJECTID`; use `outSR=4326`; preserve both project and permit rows.
  Evidence URL pattern:
  `.../FeatureServer/0/query?where=OBJECTID=<source_record_id>&outFields=*&returnGeometry=false&f=json`.
  Field mapping: `OBJECTID` -> `source_record_id`; `PROJECTNUMBER` ->
  project/group ID; `PERMITNUMBER` -> `source_permit_id`; `PROJECTNAME` and
  `PERMITNAME` -> `description`; `FULLADDRESS` -> `site_address`; `APPTYPE` ->
  `permit_type`; `PERMITCLASSCODE` -> `work_type`; `PROJECTSUBMITDATE` ->
  `applied_at`; `PROJECTSTATUS` -> project lifecycle context; `STATUS` ->
  permit raw status; `ISSUEDDATE` -> `issued_at`; `DATECREATED` -> source
  created evidence. Treat `STATUS='Issued'` as the approval boundary even when
  `PROJECTSTATUS` contains review-like states, and quarantine impossible or
  future-dated lifecycle combinations.
- Harris County rights: the service is official and publicly queryable, but no
  source-specific commercial SaaS redistribution grant was verified. Keep it as
  a narrow candidate until Harris County confirms storage, display, derived
  matching, and export terms.
- Arlington: hold for production early-warning coverage. The City of Arlington
  publishes an official open-data page and an `OD_Property/MapServer/1` layer
  named `Issued Permits`, described as a three-year view of residential,
  commercial, sign, fence, pool, and certificate-of-occupancy permits updated
  daily Monday through Friday. The layer exposes useful fields including
  `FOLDERYEAR`, `FOLDERSEQUENCE`, `FOLDERTYPE`, `STATUSDESC`, `ISSUEDATE`,
  `FINALDATE`, `SUBDESC`, `WORKDESC`, `FOLDERNAME`,
  `ConstructionValuationDeclared`, `MainUse`, `LandUseDescription`,
  `Structure`, `NameofBusiness`, `FOLDERCONDITION`, `PROPGISID1`, zoning/use
  context, and point geometry. July 18, 2026 live checks confirmed JSON row
  access with a browser-like user agent and statuses including `Pending`,
  `Pending Inspection`, `Issued`, `Issued-Revised`, `TCO Issued`, `Finaled`,
  `Expired`, `Revoked`, `Denied`, `Stop Work`, and `Void`. However, current
  `Pending` rows were limited to sign permits in the quick canary, commercial
  permit rows were mostly issued/finaled, date semantics are confusing because
  the layer describes `ISSUEDATE` as date opened, and the city page provides
  download/no-warranty language rather than explicit commercial SaaS
  redistribution rights. Revisit if Arlington publishes clearer license terms
  and stronger application-stage commercial-building or CO records.
- Dallas: hold for current production coverage. The official Dallas OpenData
  `Building Permits` Socrata dataset (`e7gq-4sah`) is historical; its metadata
  says active permit tracking moved to Dallas Accela Citizen Access. It has
  permit number, permit type, issued date, contractor, valuation, area, work
  description, land use, street address, and ZIP, but lacks current
  application-stage lifecycle, applicant/developer, parcel/project identity,
  update cursor, and deletion semantics. DallasNow/Accela is the valuable
  current source, but no Dallas-published bulk/API feed or commercial
  redistribution grant was verified.
- Houston city: hold. The official Houston permit portal states it is a
  real-time permitting source and can follow progress from submittal to
  issuance, but no supported anonymous bulk/API, stable pagination contract, or
  commercial reuse grant was verified. Harris County issued permits do not
  replace city Houston building-permit coverage.
- San Antonio / Bexar County: hold for current ingestion. BuildSA/Accela
  supports online submittals, plan review, status tracking, payments,
  inspections, related records, and cloud-hosted application workflow, making it
  a high-value early retail/chain target. No supported public bulk/API and
  commercial SaaS rights were verified. Bexar County permit applications are
  form/portal oriented and lack a current reusable bulk feed.
- Plano: hold. The official Plano dashboard exposes aggregate building
  inspection performance measures, permit counts, and plan-review measures, but
  not record-level permit/application data with applicant, parcel, address,
  project description, lifecycle status, or supported pagination. The city site
  routes users to permitting and inspection services rather than an admitted
  open record feed.
- Frisco: hold. The official Plans & Permits / Avolve portal is likely rich for
  submitted commercial permits, project reviews, plan comments, payments, and
  status updates, and public monthly reports include commercial permits and
  project submittals. However, reports are PDF/monthly and the portal has no
  verified supported bulk/API contract, deletion semantics, or commercial SaaS
  rights. Release only with an official export/API or written permission.

### Virginia Beach Building Permit Applications

- Official ArcGIS layer: `Building_Permits_Applications_view/FeatureServer/0`.
- Technical fit: pending and pre-issuance records coexist with issued history,
  plus description, address, parcel, and application/issue/final dates.
- Decision: narrow admit for permit/application context with City-required
  disclaimer and raw table resale blocked. The 2026-07-18 re-audit confirmed a
  public FeatureServer table, Query/Extract support, building permit
  application activity, current status, address, GPIN, application/issue/final
  dates, and status values including `Pending`, `Pending Revisions`,
  `Pre-Issuance`, `Ready To Issue`, `Active`, `Closed`, and `Final`.
- Production source: `virginia_beach_va_building_permit_applications`. Map
  `PermitNumber`, `PermitType`, `ConstructionType`, `WorkType`,
  `ApplicationDate`, `IssueDate`, `FinalDate`, `Status`, `WorkDesc`, `GPIN`,
  and situs address fields. Suppress `CreatedBy`, contact fragments, and raw
  table replacement exports. The service is a table without geometry, so use
  GPIN/address to connect to parcel context rather than expecting direct
  coordinates.
- Lifecycle note: status controls `approval_stage`. `Active`, `Closed`, and
  `Final` are approved/confirmed; `Pending`, `Pending Revisions`,
  `Pre-Issuance`, `Ready To Issue`, `Expired`, and other non-approved statuses
  remain pre-approval/raw lifecycle evidence even when `IssueDate` is populated.
- 2026-07-17 Virginia scout update: Virginia's strongest next permit/development
  candidates are Fairfax DevelopmentTracker, Norfolk Socrata permits plus
  Norfolk CUP planning, Virginia Beach building permits, and Lynchburg
  development projects. VGIN statewide parcels are admitted separately as a
  narrow parcel/proximity spine, not as a permit source. Fairfax appears to be
  the best lifecycle pilot because accepted, in-review, approved, closed, and
  hold statuses are published with parcel/project geometry; Norfolk has the
  cleanest open-data rights language. Loudoun, Prince William, Arlington,
  Henrico, Chesterfield, Alexandria, Chesapeake, and Richmond remain portal,
  rights, or API-contract holds until a supported export path is verified.
- Production source: `fairfax_county_va_development_tracker_site_records`.
  The admitted slice uses DevelopmentTracker layer 2, `Active Site Construction
  - Parcels`, because metadata says records are publicly available, updated
  nightly from accepted PLUS records, refreshed on status changes, and used to
  provide public access to approved plans. Map `RECORDID`, `APPTYPEALIAS`,
  `PROJECT_NAME`, `PARCEL_ID`, `RECORD_STATUS`, status/submitted/approved/closed
  dates, `PROJECT_STATUS`, MAR address, public PLUS link, approved-plan link,
  dwelling-unit count, and parcel geometry/centroid. Suppress inspector names,
  created/edited users, raw document exports, and internal workflow fields.
  Treat submitted/accepted/in-review records as pre-approval and approved/closed
  records as approved/confirmed.
- Production source: `norfolk_va_permits_and_inspections_permit_records`.
  Norfolk's Socrata `Permits and Inspections` dataset is Public Domain, updated
  daily, and contains permit number, application/issue/final dates, status,
  address, parcel GPIN, permit type, use class/type, work type, project cost,
  square footage, and geocoded point. The dataset also includes inspection
  rows, so the admitted query uses `DISTINCT` permit-level fields and excludes
  inspection numbers/statuses in the first production slice. Treat issued,
  finaled, certificate-issued, paid-certificate, and authorized records as
  approved/confirmed; pending, new, additional-information-required, expired,
  cancelled, abandoned, and revoked records remain pre-approval/raw lifecycle
  evidence rather than positive approvals.
- Production source: `norfolk_va_conditional_use_permits`. The Norfolk planning
  FeatureServer is public, queryable, supports Extract, and publishes
  conditional uses that require special review before being appropriate in a
  zoning district. The layer is current and useful for restaurants, ABC
  on-premises uses, extended hours, car washes, tattoo parlors, short-term
  rentals, and other location-specific use approvals. Treat it as approved or
  effective planning context when `EFFECTIVE_DATE` is present, not as a complete
  pending application queue. Suppress editor fields, `NOTES`, and raw PDF
  resale; expose applicant/business, address, use type, effective/expiration
  dates, official link, and point geometry as evidence.
- Production source: `lynchburg_va_development_projects_locations`. The
  Lynchburg OpenData `Development Projects - Locations` layer is a public
  TRAKiT-derived ArcGIS point layer covering Board of Zoning Appeals,
  conditional use permit applications, Design Review Board, historic
  preservation, development projects, rezonings, site plan reviews,
  subdivisions, and right-of-way vacation. It is current enough for
  pre-approval signals: the 2026-07-18 audit found recent site plans,
  subdivisions, public-meeting records, and a named `Wards Road Car Wash`
  site-plan record. Admit narrowly as geocoded development evidence with City
  GIS attribution; suppress contacts, owner/mailing fields, raw table exports,
  and source replacement resale.
- Lynchburg reliability note: the spatial layer says it is not inclusive due to
  join conflicts and points users to the tabular version for all records. The
  first production slice uses the spatial layer for geocoded opportunity
  context; a later reliability pass should reconcile against
  `Development Projects - Tabular` for completeness.

### Alabama Permit And Development Sources

- Montgomery construction permits are the strongest near-term Alabama source.
  Official open-data item:
  `https://www.arcgis.com/home/item.html?id=d0c6eccf4b7748f19248a0adec2895fd&sublayer=0`
  with API layer
  `https://mgmgis.montgomeryal.gov/arcgis/rest/services/HostedDatasets/Construction_Permits/FeatureServer/0`.
  Decision: narrow admit candidate as an approved/issued confirmation source
  for commercial building activity, not a pre-approval source.
- Montgomery fields are production-shaped: `GlobalID`, `OBJECTID`,
  `PermitNo`, `PermitStatus`, `IssuedDate`, `ExpiredDate`, `last_edited_date`,
  `CodeDetail`, `PermitCode`, `PermitDescription`, `ProjectType`, `UseType`,
  `JobDescription`, `PhysicalAddress`, `Address`, `ParcelNo`, `OwnerName`,
  `OwnerAddress`, `ContractorName`, `EstimatedCost`, fees, zoning, council
  district, and point geometry. Live statuses observed on July 17, 2026 were
  `ISSUED`, `COMPLETED`, `APPROVED`, `REQUESTED`, `DENIED`, `VOID`,
  `REVOKED`, `EXPIRED`, and `NON-COMPLIANT`, but sampled recent commercial
  rows had `IssuedDate` populated. Treat `IssuedDate` as the conservative
  approval boundary and do not promote `REQUESTED` to pre-approval until a
  sampled row lacks issued/final evidence and the city confirms lifecycle
  semantics.
- Montgomery mapping for future catalog onboarding: `GlobalID` ->
  `source_record_id`; `PermitNo` -> `source_permit_id`; `PermitStatus` ->
  `raw_status`; `IssuedDate` -> `issued_at`; `last_edited_date` ->
  `source_updated_at`; `CodeDetail`, `PermitCode`, and `PermitDescription` ->
  `permit_type` / `work_type`; `ProjectType` and `JobDescription` ->
  `description`; `UseType` -> `proposed_use_or_occupancy`; `PhysicalAddress`
  or `Address` -> `site_address`; `ParcelNo` -> `parcel_id`; `OwnerName` ->
  `owner_name`; `OwnerAddress` -> `owner_address`; `ContractorName` ->
  `contractor_name`; `EstimatedCost` and fee fields -> valuation/fees; point
  geometry -> coordinates.
- Montgomery filters: retain `UseType = 'Commercial'` and high-signal
  non-residential `PermitDescription` / `CodeDetail` / `ProjectType` rows,
  especially building, grading, signs, additions, alteration/renovation,
  electrical/mechanical/plumbing tied to commercial sites, and descriptions
  mentioning shopping centers, tenant build-outs, restaurants, retail, medical,
  industrial, warehouse, multifamily, hotel, or large valuation work. Exclude
  clearly residential rows and de minimis standalone trade rows unless linked
  to an admitted commercial parent.
- Montgomery paging/evidence: use `OBJECTID` keyset pages up to the 2,000 row
  service limit, `returnGeometry=false` for normal ingest and `outSR=4326` when
  geometry is needed. Evidence URL should query the same layer with
  `where=OBJECTID=<source_record_id>`, `outFields=*`, `returnGeometry=false`,
  and `f=json`. The item says update frequency is weekly and describes use by
  developers, researchers, officials, and the general public; no explicit
  license text is populated, so onboard with a no-raw-feed-resale/export policy
  unless Montgomery publishes broader commercial terms.
- Birmingham is a high-priority hold for pre-approval signal. The official city
  page says Birmingham is moving away from its long-term permitting system into
  the Accela Online Permit Center, where applicants can apply, pay, manage,
  track status, and print permits. The public process and Digital Plan Room are
  valuable early-warning evidence, but no supported bulk/API permit feed,
  durable cursor, deletion semantics, or commercial reuse/export terms were
  verified in the city open-data portal. Unlock through official Accela API
  access or a city-published open dataset covering application-through-issued
  records and plan-review milestones.
- Huntsville is a technical hold despite useful issued-permit GIS. Official
  process pages confirm commercial projects enter ePlans Review, zoning is the
  first step for most building applications, pre-application meetings are
  recommended, and many departments can participate in review. The official GIS
  service
  `https://maps.huntsvilleal.gov/server/rest/services/Licenses/BuildingPermits/MapServer/0`
  exposes issued building permits with `PermitID`, `Permit_Issue_DateTime`,
  occupancy, work type, building size, address, value, and pagination, but the
  service description is "Map of locations issued building permits", metadata
  tags include `Restricted`, and license text is blank. Hold until Huntsville
  grants written commercial SaaS use or publishes open terms; then it can be
  admitted as approved-only, filtered to `OccupancyType = 'Commercial'` plus
  large multifamily/industrial/high-value work.
- Mobile is a portal/API-rights hold. Official Build Mobile pages route permit
  and plan users to Tyler/EnerGov CSS for plans, permits, and code-enforcement
  cases and list predevelopment meetings, permitting, inspections, engineering
  permitting, planning, zoning, and review boards. That is promising
  pre-approval coverage, but no supported public bulk/API endpoint, current
  export, lifecycle dictionary, or commercial reuse grant was verified. Unlock
  through an official Tyler API/export contract or city open-data publication
  with submitted, under-review, issued, void/withdrawn, applicant, contractor,
  owner, parcel/address, valuation, documents, update, and deletion fields.
- Statewide Alabama sources do not currently replace municipal coverage for
  retail/development intelligence. ALDOT and coastal/environmental permit
  services cover transportation, oversize/overweight, environmental, coastal,
  mining, or infrastructure contexts, not municipal building and planning
  filings. Keep them out of the permit catalog unless a separate infrastructure
  signal product is scoped.

### Evansville And Vanderburgh County, Indiana

- Official ArcGIS layer: `BC/BUILDING_COMMISSION_PERMITS/MapServer/0`.
- Decision: operational and legal hold. Schema metadata exposes application
  status, project/use descriptions, parcel, owner, applicant role, contractor,
  valuation, and issued/not-issued records.
- Blockers: every live data query failed at the publisher backend, preventing
  identity, lifecycle, and freshness verification, and no affirmative
  commercial redistribution terms are published.

### Indianapolis / Marion County, Indiana

- Official source: City of Indianapolis/Marion County Accela Citizen Access
  portal for permits, planning/historic-preservation cases, business licenses,
  and enforcement cases. OpenIndy GIS services provide parcel, zoning, address,
  and building-footprint enrichment, but no current building-permit lifecycle
  dataset was verified in the open-data catalog.
- Decision: API, reconciliation, and legal-rights hold. The portal exposes
  strong browser search and reports, but no supported bulk permit/application
  feed, public change cursor, page contract, deletion semantics, or city-issued
  Accela API access terms were verified.
- Search and evidence fields: case or record number, case type, project name,
  filing date range, license type/number, first/last/business name, address
  components, parcel number, business license number, and module-specific
  record detail/report pages. Accela's general API model can represent
  addresses, parcels, contacts, owners, licensed professionals, custom forms,
  and custom tables, but those are not an Indianapolis bulk-access contract.
- Lifecycle value: permit and planning search covers structural, improvement
  location, sign, drainage, right-of-way, wrecking, trade, variance, rezoning,
  vacation, approval, plat, and IHPC records. The public portal indicates
  current case research, but a complete status taxonomy and historical
  transition history are not published as a machine-readable feed.
- Rights: OpenIndy GIS item metadata often grants unrestricted use with
  attribution for GIS downloads/services. That permission does not cover the
  Accela permit portal, whose public pages show access and copyright notices
  but no affirmative commercial storage, derived matching, customer display, or
  redistribution grant for permit records.
- Release condition: admit only after DBNS/IndyGIS provides a licensed recurring
  export or API for permit and planning records, with durable row identity,
  application-through-issued statuses, applicant/contractor/project/work text,
  address/parcel fields, modification and deletion semantics, control totals,
  pagination/rate-limit documentation, historical backfill depth, and written
  commercial reuse/redistribution permission.

### Madison Current Planning Projects

- Decision: admit as a narrow Wisconsin production source for
  pre-approval-through-approved planning intelligence.
- Production source: `madison_wi_current_planning_projects`. Madison Planning
  publishes the Current Planning Projects ArcGIS layer for public Land Use and
  Subdivision applications with durable `RECORD_RecordID` values, project
  aliases, review statuses, submitted/circulated dates, request text,
  descriptions, meeting text, address, parcel, applicant organization, owner
  name, project URLs, Legistar evidence links, and geometry.
- Official endpoint:
  `https://maps.cityofmadison.com/arcgis/rest/services/Planning/Current_Planning_Projects/MapServer/0/query`.
- Lifecycle handling: `Application Under Review`, `In Process`, `Active`, and
  `Referred` remain pre-approval. `Approved, Under Final Review`,
  `Approved, Final Review Pending`, and `Final Approval Granted` are approved
  confirmation. Withdrawn, denied, expired, and cancelled statuses are excluded
  from active opportunity ingestion.
- Reliability: use `ESRI_OID` only for ArcGIS keyset pagination and
  `RECORD_RecordID` for source identity. The July 18, 2026 live canary fetched
  69 records with 69 valid, 0 failed, and stage buckets of 25 pre-approval and
  44 approved records.
- Rights posture: Madison policy treats website data as public information
  generally available to copy/distribute unless otherwise exempted, with
  as-is/no-warranty/discontinuance/no-endorsement caveats. Preserve Madison
  attribution, source URLs, retrieval timestamps, and no raw source-replacement
  resale.
- Suppression policy: planner names, emails, phones, owner mailing blocks, raw
  geometry export, and unrestricted source replacement downloads stay out of
  the production catalog. Applicant organization and owner name are retained
  only as public evidence fields for entity/retailer matching.

### Wisconsin Holds

- Green Bay provides affirmative open-data reuse terms but only a parcel lookup
  application, not a supported bulk building-permit API.
- Milwaukee exposes Accela search and reference GIS layers but no official bulk
  permit application endpoint. The admitted Milwaukee CKAN permit source remains
  issued commercial confirmation rather than early-warning coverage. Brown
  County's permit layers do not cover municipal building development.
- Release condition: admit additional Wisconsin permit/building sources only
  after a jurisdiction publishes a licensed, queryable bulk source with
  lifecycle, durable identity, and freshness metadata.

### Hartford, Connecticut Building Permits

- Official ArcGIS layer: `HartfordOpenDataTables/FeatureServer/0`.
- Decision: admit a narrow commercial lifecycle slice as
  `hartford_ct_building_permits_lifecycle`.
- Technical fit: commercial pending, review, additional-information,
  ready-to-issue, issued, TCO, paid/approved-closeout records with description,
  address, parcel, cost, and lifecycle dates under CC0 1.0. Data.gov metadata
  describes nightly extraction from Accela; the ArcGIS dataset metadata can lag
  row reality, so Build Signals relies on live row canaries rather than item
  modified dates.
- Lifecycle handling: `Accepted`, `Pending`, `In Progress`, `In Review`,
  `Additional Info Required`, `Corrections Required`, `Revisions Required`,
  `Revisions Received`, `Ready to Issue`, and `Pending FMO Review` map to
  pre-approval. `Issued`, `TCO Issued`, `Closed - Paid`, and
  `Closed - Approved` map to approved/confirmation. Active construction,
  completed, denied, withdrawn, expired, hold, duplicate, and incomplete rows
  remain outside the first production slice because the current graph permit
  vocabulary distinguishes pre-approval and approved evidence.
- Identity and joins: use `RECORD_ID` as canonical source record ID and retain
  `GlobalID` as source evidence. Join opportunities through address and
  `PARCEL_ID`; the admitted table response does not provide coordinates, so do
  not fabricate point geometry.
- Suppression: do not fetch or expose `ASSIGNED_TO`, raw source-replacement
  exports, or raw geometry exports. `DateIssued` is supporting confirmation
  only; status controls approval stage because some issued-like rows lack an
  issue date.
- Reliability: a July 18, 2026 live check found current commercial 2026 rows
  through June 29, 2026 plus pre-approval statuses including `Pending`,
  `In Review`, `Additional Info Required`, and `Ready to Issue`. Daily health
  enforces `DATE_OPENED` through a `DATE_OPENED DESC` freshness probe while
  production pagination stays stable on `OBJECTID`.

### New Castle County And Delaware Candidates

- Decision: admit Delaware DNREC stormwater NOI as a statewide pre-approval
  environmental-development signal; hold New Castle County / Wilmington
  commercial permit, planning, and development-review ingestion.
- Production source: `delaware_dnrec_stormwater_noi`. Delaware Open Data
  metadata for `Storm Water Notices of Intent` marks the dataset Public
  Domain and describes it as planned construction activities that may cause
  stormwater discharges. It is statewide, refreshed daily, and exposes
  `permitnumber`, `projectname`, `owneroperator`, `project_location`,
  `datereceived`, `projecttype`, `delegateagency`, `permitstatuscode`,
  latitude/longitude, acreage, and county.
- Lifecycle mapping: non-closed NOI records are pre-approval/development-intent
  context; `Closed` records are retained as historical approved/closed
  environmental coverage. Preserve `permitstatuscode` as raw status and never
  infer final land-development approval from a stormwater NOI alone.
- Production source: `delaware_dnrec_septic_permits_narrow`. Delaware Open
  Data metadata for `Permitted Septic Systems` marks the dataset Public Domain.
  Admit as narrow statewide environmental infrastructure and site-readiness
  context, especially where `permitstatus = Application Received` and
  `appreceiveddate` precede approval. Map permit number, tax parcel number,
  county, septic system type/subtype, construction type, proposed use/capacity,
  contractor, lifecycle dates, and detail URL; suppress owner names, designer
  names, and license numbers from the graph/export layer until privacy review.
- Septic lifecycle mapping: `appreceiveddate` and application-received status
  are pre-approval; `approveddate` or approved/completed construction-report
  statuses are approved/confirmed; denied, withdrawn, expired, and abandoned
  dates remain raw lifecycle evidence rather than positive approval signals.
- Official New Castle County source: the `Open Permits` ArcGIS web application
  at
  `https://nccde.maps.arcgis.com/apps/webappviewer/index.html?id=2ddb756b44db4dac9b42495e85629b36`.
  The web map references `Open Use Permits` at
  `https://gis.nccde.org/agsserver/rest/services/CustomMaps/Open_Use_Permits/MapServer/0`
  with permit number, parcel, permit type/description, application date,
  issue date, certificate-of-occupancy date, and comments. The application
  metadata says there are no restrictions and that the app is freely provided
  for public consumption, but direct layer metadata and query calls return
  `Token Required`, and the public app proxy returned `403` in audit testing.
  No supported anonymous bulk/API path, page cursor, or change feed was
  verified.
- County layer schema value, if unlocked later: `APNO` -> `source_permit_id`;
  `OBJECTID` or `NEW_OID` -> transport/source row id only after publisher
  confirms durability; `PARCELID`/`PRCLID`/`PRCLKY` -> `parcel_id`;
  `APTYPE`/`APDESC` -> `permit_type`; `COMMENTS` -> `description`;
  `DESCRIPTION` -> parcel/address label; `APDTTM` -> `applied_at`;
  `ISSDTTM` -> `issued_at`; `COODTTM` -> `completed_at`/certificate context.
  `ISSDTTM` would be the conservative approved/issued boundary, but no raw
  status field for submitted, under-review, approved-to-issue, denied, or
  withdrawn records was verified.
- Official statewide source: Delaware FirstMap `Delaware Planning Development
  2.0`, item `b138b2dc71a9493ba1ae3ba0c5ef401e`, service
  `https://enterprise.firstmap.delaware.gov/arcgis/rest/services/PlanningCadastre/DE_Planning_Development/FeatureServer`.
  Layer `2` (`Development Applications`) and layer `3` (`Building Permits`)
  are official, bulk-queryable, support Query/Extract, pagination, 2,000-row
  pages, `GLOBALID`, JSON/GeoJSON/PBF, and export formats including CSV and
  GeoJSON. New Castle County counts observed: 1,330 development applications
  and 18,674 building permits; nonresidential counts: 757 and 1,119.
- FirstMap blocker: both layers are stale for current signal use (`P_YEAR`
  spans 2008-2024 while the audit date is 2026-07-17). Their lifecycle is also
  collapsed: development rows have only `RECTYPE = Approved Dev App`, and
  permit rows have only `RECTYPE = Building Permit`. They provide parcel,
  jurisdiction, county, residential/nonresidential flag, units or
  nonresidential square footage, short notes/address text, year, coordinates,
  and optional PLUS number, but no application/permit number, applicant,
  contractor, owner, valuation, detailed work description, submitted,
  under-review, issued, denied, withdrawn, or modification dates.
- Wilmington official sources: the city publishes a transparency portal and
  BuildingBlocks lookup at `https://wilmington-de.tolemi.com/`, and its Land
  Use & Planning page points to the Tyler/Munis permit portal at
  `https://cityofwilmingtondecitizens.munisselfservice.com/citizens/PermitsInspections/Default.aspx`
  for application, issued-permit, inspection, and status lookup. No official
  bulk export, API contract, pagination model, rights grant, or stable record
  evidence URL was verified for either portal.
- Rights notes: New Castle County's app-level metadata is favorable, but the
  underlying secured service cannot be treated as licensed bulk access without
  publisher-approved token/API access. FirstMap's item terms are broad
  as-is/no-warranty terms that mention user downloading, modifying, sharing,
  distributing, and using FirstMap Data, but the stale and lifecycle-collapsed
  data fails the production signal gate regardless of rights.
- Release condition: admit only after a current official New Castle County or
  Wilmington permit/development-review API or recurring export is available
  with durable row identity, application-through-issued statuses, parcel or
  address, project/work text, applicant/contractor where public, evidence URLs,
  documented paging or delta reconciliation, and explicit commercial SaaS
  reuse/redistribution permission.

### New Jersey Construction Permit Data

- Official statewide Socrata dataset: `w9se-dmra`.
- Technical value: 2.75 million permit/certificate records with unique `pk`,
  municipality, block/lot, use group, floor area, cost, units, and monthly
  snapshot support.
- Decision: lifecycle and legal hold. It contains issued permits and
  certificates only, omits address/project/party detail, rolls off older data,
  and publishes no affirmative commercial reuse or redistribution license.
- Jersey City's EnerGov portal exposes plans and permits through browser-facing
  internal services, not a documented licensed bulk API.

### New Orleans Permits - BLDS

- Official Socrata dataset: `72f9-bi28`
- Decision: approved for production catalog onboarding.
- Identity: Socrata `:id`; `permitnum` is not row-unique and remains business
  evidence.
- Lifecycle: unissued rows are pre-approval; `issuedate` confirms approval.
- Reliability: stable row ordering with periodic full reconciliation.
- Rights: CC0 1.0 public-domain dedication in official metadata.

## Hold

### Denver Construction And Development Records

- Decision: confirmation-only admit for issued construction and demolition
  permits; hold for early-warning/application-stage production.
- Official ArcGIS layers: `ODC_DEV_COMMERCIALCONSTPERMIT_P/FeatureServer/317`,
  `ODC_DEV_RESIDENTIALCONSTPERMIT_P/FeatureServer/316`, and
  `ODC_DEV_DEMOLITIONPERMIT_P/FeatureServer/318`.
- Lifecycle: the permit layers are extracted from Accela daily, but publish
  issued/paid permits only. `DATE_ISSUED` is the conservative confirmation
  boundary; `DATE_RECEIVED` may be retained as application context but must not
  promote a record to pre-approval coverage.
- Context: permit number, log number, schedule/parcel number, address, class,
  valuation, units, contractor, received/issued/final/cancel dates, certificate
  of occupancy flags, neighborhood, and geometry are available. Applicant,
  owner, project name, and textual work descriptions are not published in the
  bulk layers.
- Reliability: public FeatureServer query and extract are supported with
  pagination. Use `GLOBALID` as source identity and daily full/content-hash
  reconciliation because no durable row-modified cursor is documented.
- Rights: the Denver Open Data Catalog is CC BY 3.0; preserve attribution to
  the City of Denver Open Data Catalog and license notice.
- Blocker: Denver e-permits/Accela exposes searchable application-stage
  records, parcels, project names, contractors, and plan-review context through
  the public portal, but no supported licensed bulk export, change log, or
  reconciliation API was verified for those pre-issuance records.
- The site-development-plan layer remains supplemental planning evidence only;
  Denver states that plan recording is not building-permit approval.

### Miami-Dade WASD Unincorporated Permit Processes

- Decision: admit as a narrow Florida pre-approval-through-approved commercial
  and use-signal source.
- Production source: `miami_dade_fl_wasd_unincorporated_permits_narrow`.
  Miami-Dade's official WASD `Permits - UNINCORPORATED MIAMI-DADE` ArcGIS
  layer exposes active process records with project owner/name text, use
  description, process number, process status/date, downstream building permit
  number/date/status, certificate dates, geometry, and update timestamps.
- Signal filter: the first production slice keeps active rows whose
  `PROJDESC` indicates retail, package store, office, industrial, commercial,
  or restaurant use. This deliberately favors early retailer/chain and
  commercial-development context over residential volume.
- Lifecycle handling: active `APPLIED` rows with a blank building permit number
  remain `pre_approval`; rows with `BLDPRMNO` or `BLDPRMIDT` are treated as
  approved/issued confirmation; certificate/CO dates are retained as completion
  evidence. Expired or deallocated statuses should be retained as source
  evidence but suppressed from active opportunity alerts.
- Rights basis: Florida Chapter 119, Florida AGO 2003-42, and
  *Microdecisions v. Skinner* support commercial reuse of county GIS public
  records and prohibit local public-record GIS license restrictions. Preserve
  Miami-Dade attribution and the official source URL.
- Suppression policy: do not ingest or expose `MUNICURL` legacy session links,
  ArcGIS `GlobalID`, alternate permit aliases, service-type internals,
  expiration/deallocation internals, raw source-replacement exports, or
  contact/person-heavy downstream details.

### Florida DEP Environmental Resource Permit Applications

- Decision: admit as narrow statewide environmental/site-development context,
  not as a municipal building-permit replacement.
- Production source: `florida_dep_erp_applications_commercial_context`.
  Florida DEP's official ERP from PA ArcGIS layer exposes current application
  numbers, project/site names, applicant company, address/city/ZIP, permit
  type/subtype, received/action/expiration/completion dates, agency action,
  document/report links, and point geometry.
- Signal filter: the first production slice keeps commercial/development
  records whose project/site/description text indicates commercial,
  retail, restaurant, warehouse, industrial, apartment/multifamily, hotel,
  medical, subdivision, shopping, or plaza activity. Live July 2026 examples
  included commercial redevelopment, industrial warehouses, restaurants, hotel
  stormwater work, subdivisions, and pending commercial docking/restaurant
  projects.
- Lifecycle handling: `AGENCY_ACT = Pending` remains `pre_approval`; effective,
  exempt, default, issued, and other agency-action rows are retained as
  approved environmental/site-development context. This source does not prove a
  municipal building permit has been issued.
- Rights basis: Florida Chapter 119, Florida AGO 2003-42, and
  *Microdecisions v. Skinner* support commercial reuse of Florida public GIS
  records. Preserve Florida DEP attribution and official document/report URLs.
- Suppression policy: suppress individual `APP_NAME`, processor, coordinate
  component internals, Corps number, lock/datum/method internals, and raw
  source-replacement exports. Use company/entity names where present; do not
  expose the layer as a bulk document-export substitute.

### Orlando Permit Applications

- Decision: admit as a narrow commercial permit-application source for
  pre-approval-through-approved retailer and tenant-work detection.
- Production source: `orlando_fl_permit_applications`. The City of Orlando's
  official Socrata `Permit Applications` dataset is updated daily and describes
  permit applications received and processed into the economic development
  information system.
- Official endpoint: `https://data.cityoforlando.net/resource/ryhf-m453.json`.
- Signal filter: the first production slice keeps records with a stable permit
  number, a real permit address, `Commercial` plan review, and processed dates
  from 2024 forward. This favors actionable commercial applications over the
  full 1.1M-row historical permit table.
- Lifecycle handling: do not rely on `application_status = Open` by itself,
  because issued rows can remain open. `issue_permit_date`, `final_date`,
  `coo_date`, or `coc_date` promote a row to approved/confirmation; otherwise
  processed, under-review, pending-issuance, hold, and hard-hold commercial
  records remain pre-approval evidence with the raw source status preserved.
- Admitted fields: permit/application number, application type, work type,
  plan-review type, application status, processed/under-review/pending-
  issuance/issue/final/CO/COC dates, project name, permit address, parcel
  number, contractor company, estimated cost, square footage, neighborhood, and
  geocoded point.
- Product note: July 2026 live samples included unissued Publix commercial
  rows such as `PUBLIX 0662` at `1500 E COLONIAL DR` and `PP - PUBLIX 0659`
  at `2015 EDGEWATER DR`. These are strong pre-announcement chain signals
  before final permit issuance.
- Suppression policy: owner names, contractor phone/address, private-provider
  qualifier/company/person fields, raw source replacement exports, and other
  contact-style fields remain excluded from the catalog fetch and mappings.
- Rights posture: public official open-data access plus Florida public-records
  posture supports narrow derived permit intelligence with City of Orlando
  attribution and retrieval-date/currentness/no-warranty caveats. Because the
  Socrata metadata does not publish a dataset-specific license string, avoid raw
  source-feed resale until legal review clears broader use.

### Orlando Planning Applications

- Official Socrata dataset: `bhxy-4rji`.
- Decision: hold despite strong technical fit.
- Identity: `application_number` is complete and unique in the live dataset.
- Lifecycle: `Open`, `Hold`, and `Hardhold` expose actionable pre-approval
  records; approved and closed records preserve later confirmation context.
- Context: project name, narrative comments, application type, applicant,
  address, parcel, geography, action dates, and approval date are available.
- Reliability: the rolling five-year dataset updates daily. Use a daily full
  keyset snapshot with metadata-version checks and tombstone records that leave
  the rolling window.
- Rights blocker: official metadata reports public access but no license or
  rights grant, and the city disclaimer warns that some data may restrict
  redistribution. Obtain written commercial copying, adaptation,
  redistribution, and derived-product permission before onboarding.

### Jacksonville / Duval County Pre-Approval Records

- Decision: confirmation-only and bulk-rights hold for permit/development
  early warning. This does not affect the admitted Duval County parcel source.
- JaxEPICS documents useful pre-issuance states, including not submitted, DSD
  review, agency review, sufficiency review, pending review payment, in review,
  and return-for-corrections, plus issued, active, finalized, cancelled,
  expired, and void states. Public inquiry is available by permit number,
  confirmation number, or address.
- LUZAP and land-development review surfaces expose zoning, land-use, site-plan,
  hearing, ordinance, and document evidence after applications are approved for
  public viewing. Unpaid filings, paper filings, pre-application meetings, and
  some development records are not proven complete online.
- Identity: retain permit number, application number, confirmation number, CDN,
  property key, RE number, LUZAP tracking number, application number, ordinance
  number, and parcel/RE number. Never reconcile by address alone.
- Retail signal fields can include company name, proposed use, permit and
  application type, work type/subtype, structure type, address/unit/ZIP, RE
  number, property key, cost, work area, contractor/design professional
  identifiers, intake/action/issued/final/status dates, planning district,
  council district, public-hearing dates, and attachments. Treat company names
  as candidate evidence because they may identify owners, contractors, LLCs, or
  professionals rather than the retail brand.
- Blockers: no documented complete public bulk API, change-data feed, freshness
  SLA, automation permission, or commercial redistribution grant. Atlantic
  Beach, Neptune Beach, Jacksonville Beach, and Baldwin need separate source
  mappings before countywide coverage claims.
- Release condition: application-stage coverage must be demonstrated across
  lifecycle states, with stable IDs, update fields, redaction rules, written
  reuse and automation terms, and a supported recurring extract or public API.

### Tampa / Hillsborough County Development Records

- Decision: hold for early-warning production. This does not affect the
  admitted Hillsborough County parcel source.
- HillsGovHub, PGM, and Tampa Accela expose pre-approval development evidence,
  including preliminary site/plat, site construction, rezoning, special use,
  variance, land-use, and related applications. The county issued-permit GIS
  layer is confirmation-only and should not be treated as an early-warning feed.
- Identity: portal record numbers are usable business keys, but no public
  cross-system GUID, version key, retirement feed, or lineage contract was
  verified. Use `jurisdiction|record_number` as the canonical candidate key and
  retain `OBJECTID`, permit number, parcel/folio, source URL, and portal module
  as raw evidence.
- Retail signal fields can include project name, trade/business name, record
  type, status, filing/update dates, address, parcel/folio, owner, applicant,
  contact, contractor/license, job title, occupancy/use/class, permit type,
  redevelopment flag, valuation, building/unit counts, square footage, and
  plan/attachment references.
- Freshness path: the county issued layer has a weekly refresh statement and
  can be reconciled with paginated full snapshots, schema hashes, duplicate
  checks, and content diffs. HillsGovHub, PGM, and Tampa Accela have no
  documented bulk export, update cursor, or reconciliation SLA.
- Rights: Tampa terms broadly allow copying and distribution of system data
  while excluding copyrighted material, images, and seals. Hillsborough public
  access and Florida public-records law support inspection and copying, but no
  source-specific commercial redistribution grant was verified.
- Release condition: written Hillsborough rights for commercial storage,
  derived use, customer display, and redistribution; supported bulk/API access
  for pre-approval records; stable update/retirement semantics; exempt-record
  handling; and a clean Tampa/unincorporated-county coverage boundary.

### Boston Article 80 Development Projects

- Decision: narrow development-review admit.
- Production source: `boston_ma_article_80_development_projects`.
- Endpoint:
  `https://gis.bostonplans.org/hosting/rest/services/Hosted/A80_project_points_all/FeatureServer/0/query`.
  The official Boston Planning Department/BPDA Article 80 project-points layer
  is maintained by Planning GIS, exposes ArcGIS pagination, lists `objectid` as
  the object ID field, and live metadata reviewed on July 18, 2026 showed a
  recent `lastEditDate`.
- Admitted fields are project identity, project name, Article 80 status/record
  type, address pieces, neighborhood, filed/board-approved/COO dates, uses,
  gross square footage, total development cost, public project URL, description,
  and coordinates. `Prefile (Default)`, `Letter of Intent`, and `Under Review`
  normalize to `pre_approval`; `Board Approved`, `Permitted / Under
  Construction`, and `Construction Complete` normalize to `approved` while the
  exact source status remains evidence.
- This source is development-review intelligence, not a contractor/applicant-rich
  building-permit feed. Chain and retail detection depends on project name,
  uses, description, public URL, address, and later graph/parcel enrichment.
- Rights pass is based on Boston's Analyze Boston / City open-data posture using
  the Open Data Commons Public Domain Dedication and License by default. Use
  City of Boston / Boston Planning Department attribution, retrieval-date and
  currentness caveats, no endorsement, no warranty, and no raw
  source-replacement resale.

Evidence URLs:
`https://gis.bostonplans.org/hosting/rest/services/Hosted/A80_project_points_all/FeatureServer/0`;
`https://gis.bostonplans.org/hosting/rest/services/Hosted/A80_project_points_all/FeatureServer/0/query`;
`https://data.boston.gov/pages/terms`.

### Sacramento Applied Commercial Building Permits Current Year

- Decision: narrow current-year commercial application admit with rights-review
  caveat.
- Production source:
  `sacramento_ca_commercial_building_permits_applied_current_year`.
- Endpoint:
  `https://services5.arcgis.com/54falWtcpty3V47Z/ArcGIS/rest/services/BldgPermitApplied_CurrentYear/FeatureServer/0/query`.
  The City of Sacramento publishes applied building permit activity through its
  open data / ArcGIS service. Live schema reviewed on July 18, 2026 exposed
  `OBJECTID`, `Application`, `Rpt_Status`, `Current_Status`, `Status_Date`,
  `Parcel_No`, `Address`, `ZIP`, `Project_Sq_Ft`, `Valuation`,
  `Activity_Code`, `Contractor`, `Work_Desc`, and `Project_Name`.
- Admitted scope is commercial records only. Application, plan-check,
  verification, processing, and ready-to-issue statuses normalize to
  `pre_approval`; issued, complete, finaled, certificate-of-occupancy, and
  permit-issued statuses normalize to `approved`. The exact source status is
  retained as evidence for downstream opportunity scoring.
- This is a strong pre-announcement retail and tenant-work source because
  `Category`, `Project_Name`, `Work_Desc`, `Contractor`, valuation, square
  footage, parcel, and address can reveal unannounced cafe, restaurant, retail,
  HVAC, EV charging, and tenant improvement work before final issuance.
- Rights pass is promising but not as clean as CC0/CC-BY. Sacramento's open data
  policy supports access, download, machine retrieval, indexing, reuse, and
  derivative works, while the ArcGIS item has blank license metadata and city
  terms reserve dataset-specific rights where indicated. Use City of Sacramento
  attribution, retrieval-date/currentness caveats, no endorsement, no warranty,
  and no raw source-replacement resale unless legal review clears broader use.
- Operational caveat: the public page describes monthly update cadence, so this
  is valuable context but slower than same-day feeds. Current-year and archive
  tables should eventually be reconciled together for annual rollover.

Evidence URLs:
`https://data.cityofsacramento.org/datasets/applied-building-permits-current-year/explore`;
`https://services5.arcgis.com/54falWtcpty3V47Z/ArcGIS/rest/services/BldgPermitApplied_CurrentYear/FeatureServer/0`;
`https://www.cityofsacramento.gov/community-development/building/permit-services/building-permits-data`;
`https://www.cityofsacramento.gov/content/dam/portal/it/gis/open-data/OpenDataPolicy.pdf`.

### Boston, Cambridge, And Worcester General Permit Feeds

- Decision: hold as core application sources.
- Boston's general feed contains approved permits and excludes applications
  still being processed. Its zoning-appeal tracker is useful supplemental
  evidence but has a narrower scope and no stable row key across all records.
- Cambridge's aggregate feed lacks sufficient project narrative and its
  documented identifiers collide; detailed building feeds publish completed
  applications.
- Worcester publishes daily permit data under affirmative reuse terms, but all
  observed records already had issue dates, so its `Active` state is
  post-issuance rather than pre-approval.

### Raleigh And Other North Carolina Candidates

- Decision: admit Cary Developments as a narrow production pre-approval through
  approved development source.
- Production source: `cary_nc_development_applications`. Town of Cary's
  Developments dataset is published through the Cary Open Data catalog with
  CC0 rights and describes site/subdivision plans that are under review,
  recently approved, or actively being constructed. The ArcGIS layer exposes
  stable application numbers, project names, application/action dates, status,
  review type, use group/category/type, square-footage/acreage scale fields,
  public project/action URLs, and polygon geometry.
- Lifecycle handling: `In Review`, `Active`, blank, denied, withdrawn, and
  expired records are retained as pre-approval/development-intent context;
  `Approved`, `Complete`, and `Closed` are treated as approved. This preserves
  early retailer/chain signals such as mixed-use or retail projects before a
  building permit is issued while avoiding overclaiming final permit approval.
- Suppression policy: internal Salesforce IDs, editor users/timestamps,
  tracking fields, ArcGIS shape metrics, and raw internal workflow identifiers
  remain excluded from ingestion.
- Decision: admit Cary Building Permit Applications as a narrow
  non-residential permit-application source.
- Production source: `cary_nc_building_permit_applications`. The Town of Cary
  Open Data / Data.gov metadata marks this BLDS-style dataset as CC0 and
  explicitly states rows represent applications for permits, not individual
  permits. The first production slice filters to `Non-Residential` records and
  keeps permit/application number, description, status, applied/issued/status
  dates, address, PIN, cost, square footage, owner entity name, contractor
  company name, coordinates, and record URL.
- Lifecycle handling: `issuedate` present, `Permit issued`, and `Occupancy`
  status buckets are treated as approved; in-plan-check, pending, fee/payment,
  and other no-issuedate records remain pre-approval/application evidence.
  Rejected, expired, withdrawn, and cancelled rows are retained as source
  evidence rather than active approvals.
- Suppression policy: contractor phone/address/ZIP and owner mailing address
  fields remain excluded. Residential rows are excluded from this production
  source until privacy and product-value handling is narrowed separately.
- Operational note: Cary can expose source-reported future application dates
  around fiscal-year or express-review workflows. Use source dates as evidence
  with status context, and prefer status/recent canaries for current-market
  monitoring until a generic future-date quarantine transform is added.
- Decision: admit Raleigh Development Plans as a narrow production
  pre-approval-through-approved development-plan source.
- Production source: `raleigh_nc_development_plans`. The City of Raleigh
  publishes the Development Plans ArcGIS layer as public authoritative open
  data and describes it as all submitted development plans that are approved or
  under review, including Preliminary Subdivisions and Administrative Site
  Reviews, with daily updates.
- Official endpoint:
  `https://services.arcgis.com/v400IkDOw1ad7Yad/arcgis/rest/services/Development_Plans/FeatureServer/0/query`.
- Lifecycle handling: `Submitted - Online` and `In Review` are retained as
  pre-approval signals; `Approved` or a populated approved date is treated as
  approved. The production query excludes withdrawn/void records by taking the
  submitted, in-review, and approved status slice only.
- Admitted fields: stable plan number, plan name, status, submitted/approved/
  updated dates, plan type, developer, major street, requested square feet,
  requested units, requested lots, acreage, zoning, and point geometry. Plan
  number maps to source/application/permit identity; plan name and developer
  provide retailer/chain and party context; geometry supports later Wake County
  parcel and nearby-parcel joins.
- Suppression policy: ArcGIS internals and non-essential lifecycle fields such
  as `GlobalID`, submitted year, appeal-period end, sunset date, approved lot
  and unit counts, and missing-middle flags remain excluded. The layer does not
  expose owner, contractor, phone, or email fields.
- Product note: live validation in July 2026 surfaced `DSLC - 7 BREW OF
  RALEIGH` at `9800 Falls Of Neuse Rd` while it was still `In Review`, which
  is exactly the pre-official chain-opening signal this phase is meant to
  capture before final permit approval.
- Rights posture: narrow production use is allowed with attribution and
  currentness/no-warranty/schema-change disclaimers. Do not present this as a
  complete building-permit ledger or resell the raw source feed; use it as
  evidence-backed development intelligence.
- Raleigh's official building-permit layer remains a candidate supplement: it
  contains pending and approved records, project/use text, parcel, owner,
  contractor, valuation, and a record-update date, but is not the admitted
  Raleigh production source in this iteration.
- Decision: admit Charlotte Rezoning Petitions as a narrow production
  pre-approval-through-approved planning source.
- Production source: `charlotte_nc_rezoning_petitions`. Charlotte-Mecklenburg
  Planning publishes the Rezonings ArcGIS layer through the official City of
  Charlotte GIS service for petitions requesting zoning changes. The layer
  exposes durable petition numbers, petitioner names, existing and requested
  zoning, petition type, acreage, received and approved dates, abbreviated
  status, public petition links, proposed-use text when populated, and polygon
  geometry.
- Official endpoint:
  `https://gis.charlottenc.gov/arcgis/rest/services/PLN/Rezonings/MapServer/0/query`.
- Lifecycle handling: rows with `Approved` populated are treated as approved;
  pending rows such as `Status = Pen` with no approved date remain
  pre-approval evidence. `Status` is preserved as source text because the layer
  uses short codes rather than descriptive lifecycle labels.
- Admitted fields: petition number as source/application/permit identity,
  petitioner as developer/applicant context, existing/requested zoning,
  petition type, received/approved dates, official petition URL, acreage
  converted to square feet for site scale, and derived polygon centroid for
  opportunity location. `OBJECTID` is used only for reliable keyset paging.
- Suppression policy: staff/editor fields including `created_user`,
  `last_edited_user`, land-use staff, urban-design staff, rezoning staff, raw
  geometry export, and raw source export stay out of the production catalog.
  The graph may show the official petition URL as evidence but must not expose
  a bulk replacement GIS export.
- Product note: live validation in July 2026 surfaced pending 2026 petitions
  for `Sam's Mart, LLC`, `Hendrick Automotive Group`, `Owl Services`,
  `Barnhardt Manufacturing Co.`, and `C4 Investments, LLC dba Crosland
  Southeast`, which are useful early signals for chain/operator, industrial,
  and developer movement before building permits or public opening
  announcements.
- Rights posture: the source is official City of Charlotte / Charlotte-
  Mecklenburg Planning GIS. Charlotte open-data policy describes public,
  machine-readable reuse and redistribution, while city legal notices provide
  standard as-is, no-warranty, and no-endorsement caveats. Keep attribution,
  currentness checks, source links, and no raw source-replacement resale.

### New Hanover County Commercial Site Plans

- Decision: admit as a narrow North Carolina production source for commercial
  pre-approval-through-approved site-plan intelligence in the Wilmington/New
  Hanover market.
- Production source: `new_hanover_nc_commercial_site_plans`. New Hanover
  County publishes the EnerGov Plans layer through its official GIS REST
  services and public data page. The layer exposes stable plan IDs, plan
  numbers, commercial plan type/work class, lifecycle status, application,
  completion, and expiration dates, public project/description text,
  applicant and owner organization text, zoning, parcel ID, source coordinates,
  and geometry.
- Official endpoint:
  `https://gis.nhcgov.com/server/rest/services/Thematic/EnergovPermitsPlans/MapServer/1/query`.
- Signal filter: keep 2024-forward commercial site-plan rows with active
  `In Review`, `Approved`, or `Approved with Conditions` statuses. Exclude
  expired, void, withdrawn, cancelled/canceled, and rejected rows from active
  opportunity ingestion.
- Lifecycle handling: `In Review` remains pre-approval evidence because it can
  reveal site-design, retailer, fuel/convenience, restaurant, industrial, or
  owner/applicant movement before official approval. `Approved` and
  `Approved with Conditions` are approved confirmation, with `COMPLETE_DATE`
  retained as approval evidence when present.
- Identity and graph context: use `PLPLANID` as stable source identity and
  `PLAN_NUMBER` as the user-facing application/permit number. Preserve `PID`
  as the parcel join key. Use `Lat`/`Lon` as the opportunity point and retain
  source geometry only for canary/evidence validation, not raw polygon export.
- Admitted fields: plan ID/number, plan type, work class, plan status,
  application/completion/expiration dates, project/description, applicant,
  owner, general contractor if populated, square feet, valuation, zoning,
  parcel ID, coordinates, GlobalID, and geometry for validation.
- Suppression policy: assigned staff, owner mailing-address parts, total fee,
  vested-map date, source x/y duplicates, shape metrics, raw geometry export,
  and raw source-replacement export remain excluded.
- Rights posture: New Hanover County's public data page says the county
  publishes and shares datasets, GIS services, recently issued building
  permits, and property sales for public retrieval and economic prosperity.
  Because the page does not grant a broad open-data license, production use is
  narrowed to attributed, value-added planning intelligence with retrieval
  timestamps, no-warranty/currentness notice, and no raw source-replacement
  resale.

### Wake County Commercial Building Permits

- Decision: admit as a narrow North Carolina production source for commercial
  pre-approval-through-approved building-permit intelligence.
- Production source: `wake_county_nc_building_permits_commercial`. Wake County
  publishes Building Permits through official ArcGIS/data.gov distributions
  with BLDS-style fields where appropriate, nightly geocoding, public access,
  and CC BY 4.0 licensing.
- Official endpoint:
  `https://maps.wake.gov/arcgis/rest/services/Inspections/Building_Permits/MapServer/0/query`.
- Signal filter: keep commercial building permits from 2024 forward with active
  or approved lifecycle statuses and retailer, restaurant, tenant, business,
  mercantile, high-square-footage, high-valuation, or recognizable chain text.
  Exclude void, withdrawn, expired, denied, disapproved, inactive, stop-work,
  and under-violation rows from active opportunity ingestion.
- Lifecycle handling: `Submitted`, `Submitted - Online`,
  `Application Incomplete`, `In Review`, `On Hold`,
  `On Hold - Customer Action Required`, and unissued `Approved` rows remain
  pre-approval. `Issued`, `Complete`, populated `ISSUE_DATE`, and populated
  `FINALED_DATE` are approved confirmation.
- Identity and graph context: use `PERMIT_NUMBER` as source/application/permit
  identity and retain `PIN` as the parcel join key into the admitted Wake
  parcel source. `OBJECTID` is transport pagination only. The Tyler EnerGov
  `LINK` is retained as source evidence.
- Admitted fields: permit number, status, application/issue/final/expiration
  dates, description, permit type, work class, proposed use, square feet,
  valuation, contractor business text, parcel PIN, district, evidence link, and
  source-provided longitude/latitude.
- Product note: the July 18, 2026 audit found a pre-approval Michaels signal:
  `CBPR-175796-2026`, `In Review`, `SHOPS AT MIDWAY - ... Michaels-#6725`,
  `327C RETAIL STORE`, parcel `1744652987`, before issuance.
- Reliability: the July 18, 2026 live canary fetched 35 rows with 35 valid, 0
  failed, and stage buckets of 5 pre-approval and 30 approved records.
- Suppression policy: mailing address/city/state/postal fields and raw
  source-replacement exports remain excluded. Contractor text is retained as
  business-context evidence, but owner/applicant fields are not exposed by this
  layer and should be joined from other admitted sources only.
- Rights posture: CC BY 4.0 permits commercial reuse with attribution. Preserve
  Wake County attribution, license notice, source URL, retrieval timestamp,
  change/currentness notice, and no-endorsement language.

### Greensboro Commercial Building Permits

- Decision: admit as a narrow North Carolina production source for commercial
  pre-approval-through-approved building-permit intelligence.
- Production source: `greensboro_nc_building_permits_commercial`. Greensboro's
  official `BuildingPermits_MS` ArcGIS service is described as the city's
  building-permit dashboard source from January 2011 to present.
- Official endpoint:
  `https://gis.greensboro-nc.gov/arcgis/rest/services/EngineeringInspections/BuildingPermits_MS/MapServer/6/query`.
- Rights posture: Greensboro's open-data policy says datasets published on the
  Open Data Portal are public domain with no restrictions or requirements on
  use. Preserve City of Greensboro attribution, retrieval timestamp,
  no-warranty/currentness notice, no-endorsement language, and no raw
  source-replacement resale because the ArcGIS service itself carries
  Greensboro GIS attribution.
- Signal filter: retain commercial rows (`BP_COMM_RESID_MULT = C`) from 2024
  forward with no cancel date and retailer, restaurant, tenant, store, coffee,
  office, business, mercantile, storage, industrial, high-square-footage, or
  high-valuation context.
- Lifecycle handling: unissued `Active` rows remain pre-approval. Populated
  `IssuedDate`, `FinalCODate`, `FinalCO = Y`, or issued statuses are approved
  confirmation. Cancelled rows are excluded from active opportunity ingestion.
- Identity and graph context: use `PermitNum` as source/application/permit
  identity and preserve `PlanReviewNum` as early-review evidence. `OBJECTID` is
  transport pagination only. `AdSakey` is retained as the city address key until
  a parcel/address join is admitted.
- Admitted fields: permit number, plan-review number, application/issue/final
  dates, status, application type, description, occupancy, construction type,
  contractor text, owner business text, full address, valuation, square feet,
  zoning as raw evidence, commercial/residential class, final CO evidence,
  address key, and WGS84 point geometry.
- Product note: the July 18, 2026 audit found active unissued commercial rows
  such as `202612947` / `2026-2088`, office-space renovation, owner
  `CHICKASHA I LLC`, and no issued date.
- Reliability: the July 18, 2026 live canary fetched 35 rows with 35 valid, 0
  failed, and stage buckets of 11 pre-approval and 24 approved records.

### Buffalo Planning, Zoning, And Historic Preservation Approvals

- Decision: admit as a narrow New York production source for positive
  planning, zoning, and historic-preservation approval context.
- Production source: `buffalo_ny_planning_zoning_approvals`. The official City
  of Buffalo / Office of Strategic Planning Socrata feed is updated daily from
  Hansen 8 and publishes approved or conditionally approved review outcomes.
- Official endpoint: `https://data.buffalony.gov/resource/ybhc-xhg4.json`.
- Rights posture: OpenData Buffalo metadata lists the dataset under Public
  Domain U.S. Government terms. Preserve City of Buffalo attribution, source
  URL, retrieval timestamp, currentness notice, no-warranty/no-endorsement
  caveats, and avoid raw source-replacement resale.
- Lifecycle handling: `AppCond` maps to pre-approval/conditional approval
  context because the project has not reached a clean final approval state.
  `Approved` maps to approved planning/zoning entitlement context. Denied and
  truly pending application rows are not published, so this source must not be
  treated as a complete application funnel or conversion-rate source.
- Identity and graph context: use `uniqueid` as source identity; preserve
  `apno`, `apbldgreviewkey`, `apbldgkey`, review type, result, result date,
  address, parcel id, neighborhood, and source coordinates. Parcel ids can link
  to later Erie County/Buffalo parcel evidence when a rights-cleared parcel
  spine is admitted.
- Suppression policy: computed Socrata region fields and raw source-replacement
  exports are excluded. The dataset does not expose applicant, owner, or
  contractor fields, so retailer matching should come from address/parcel joins
  or companion permit, license, lease, and board-material evidence.
- Reliability: future-dated `resultdttm` rows were observed during scouting.
  The production query uses the generic rolling `{utc_today_plus_7}` connector
  placeholder to exclude dates beyond a seven-day tolerance, and the mapping
  drops decision dates more than seven days in the future.
- Canary: the July 18, 2026 live canary fetched 45 rows with 45 valid, 0
  failed, and stage buckets of 16 conditional/pre-approval and 29 approved
  records.
- Suppression policy: owner mailing/contact fields, contractor phone/email, and
  raw source replacement exports remain excluded. Some contractor values are
  workflow placeholders such as `PLAN REVIEW`; downstream graph/entity
  resolution should not promote those as real contractors without corroboration.

### Durham Planning / Site Plan Candidate Hold

- Decision: rights-confirmation hold. Durham's official ArcGIS `Permits`
  service exposes a technically strong `Site Plans and Preliminary Plats`
  planning layer, but July 18, 2026 metadata had blank license/copyright text.
  Do not admit to production until Durham confirms commercial SaaS
  storage/display/API/export and derived-data reuse.
- Candidate endpoint:
  `https://services2.arcgis.com/G5vR3cOjh6g2Ed8E/ArcGIS/rest/services/Permits/FeatureServer/29/query`.
- Technical fit: layer 29 exposes current planning/site-plan cases with
  `A_NUMBER`, `A_TYPE`, `A_DATE`, `A_STATUS`, `A_STATUS_DATE`,
  `A_PROJECT_NAME`, `A_DESCRIPTION`, planner/user fields, and point geometry.
  A July 18, 2026 audit found 6,579 rows and 6,579 distinct `A_NUMBER` values,
  suggesting stable case identity in the live snapshot.
- Lifecycle candidate: `UN_RE`, `PEN`, `REC`, `REV`, `CORR`, `ON_HOLD`, and
  `SUS` appear to be pre-approval/review statuses. `APP`, `APPR_REC`,
  `AP_CON`, `ISS`, and `COM` should be decoded with Durham before mapping to
  approved context. `EXP`, `VOID`, and `WITH` should be terminal/suppressed
  from active opportunity scoring.
- Product value: live samples included `10 Federal Storage` and generator/field
  depot upgrade records, showing useful project-name and description evidence
  before building permit issuance.
- Suppression policy if admitted: suppress `A_USER_ID`, planner/staff fields,
  future emails/phones, raw editor/workflow fields, and raw source-replacement
  exports. Use Durham attribution, retrieval timestamps, no-warranty/currentness
  caveats, and no endorsement language.
- Mecklenburg County's official Building Permit Locations feature service is
  technically admissible only as an issued/complete permit supplement. It has
  ArcGIS query/extract support, 2,000-row default pages, roughly 482k records
  from 1990 through current 2026 updates, and useful project, address, parcel,
  owner, valuation, building, occupancy, and work-description fields. The only
  observed permit states are `Issued` and `Complete`, so it does not satisfy the
  pre-approval/application-stage signal requirement.
- Charlotte's official Land Development Commercial Projects layer exposes
  `UID`, project number/name/type, open date, status, status date, parcel,
  address, category, geometry, and Accela project-detail links for
  pre-submittal/active/approved/closed commercial land-development cases, but
  the live service data verified in July 2026 was stale: latest open/status
  dates were March 2021.
- Charlotte/Mecklenburg AccelaMeck, rezoning registers, project-detail pages,
  and site-plan PDFs add applicant, petitioner, parcel, proposed-use, hearing,
  and attachment evidence, and Mecklenburg has described a near-real-time
  commercial permitting app backed by Accela/GIS processing. However, no
  supported public bulk API, machine-readable reconciliation contract, or
  accessible public feature layer for those application-stage commercial records
  was verified.
- Mecklenburg County's parcel and permit context is useful for reconciliation,
  but GIS/open-data terms remain mixed: Open Mapping describes redistribution
  and derivative rights, while individual metadata and website legal notices
  emphasize as-is use, no warranty, and in some GIS products no secondary
  distribution.
- Decision: keep non-rezoning Charlotte/Mecklenburg commercial development and
  permit sources on legal/operational hold. Admit Mecklenburg Building Permit
  Locations only as a post-issuance supplement after rights review; unlock
  AccelaMeck/commercial-permitting ingestion only with written commercial
  storage, customer display, redistribution, derived database rights, and a
  supported extraction/reconciliation method.
- Greensboro publishes issued permits rather than a meaningful pre-approval
  lifecycle. Durham has review stages but insufficient location/party context
  and blank license metadata.

### Minneapolis And Other Minnesota Candidates

- Minneapolis CCS commercial permits are narrowly admitted above. Do not
  broaden to Hennepin County road/access permits, Hennepin preliminary plat
  review, or Minneapolis planning applications until an official bulk/API feed
  with stable identity, lifecycle status, project/location/party fields,
  reconciliation semantics, and affirmative commercial reuse rights is
  verified.
- Saint Paul is approved-only and stale, while Rochester does not publish a
  sanctioned bulk application API with affirmative redistribution terms.

### Kansas City And Other Missouri Candidates

- Kansas City's CompassKC feed is public domain, detailed, complete on
  `permitnum`, and technically suitable for keyset ingestion.
- Decision: lifecycle and freshness hold. Every row already has an issue date,
  including statuses labeled `In Review`, and live business dates stopped in
  May 2025 despite a nominal daily update schedule.
- Re-evaluate only after current unissued applications appear or another
  Missouri jurisdiction publishes a licensed application-stage source.
- St. Louis, Missouri / St. Louis County decision: NARROW ADMIT for official
  City of St. Louis commercial occupancy applications and City-issued building
  permit confirmations; HOLD St. Louis County.
- City commercial occupancy source: `https://www.stlouis-mo.gov/data/datasets/dataset.cfm?id=110`
  links to live API endpoint
  `https://www.stlcitypermits.com/API/Occupancy/GetCommercialOccupancyInspections`.
  It is official Building Commissioner metadata, live, and includes open and
  issued commercial occupancy applications with parcel/address/project/owner
  context. Map `OccupancyApplicationID` to `source_record_id`;
  `PermitType`/`PermitTypeID` to `permit_type`; `ApplicationDate` to
  `application_date`; `CurrentResultDate` to `status_date`; `CurrentResult` to
  `raw_status`; `ProjectAddress`, `UnitNumber`, `ProjectCity`,
  `ProjectState`, and `ProjectZipCode` to normalized site address;
  `ProjectParcelID`, `ProjectASRParcelID`, and `ProjectHandle` to parcel ids;
  `BusinessType` and `BusinessTypeDescription` to work/project description;
  `OwnerName` and owner address fields to owner party; `ProjectWard`,
  `ProjectNeighborhood`, `ProjectX`, and `ProjectY` to jurisdiction/geospatial
  context; `OccupancyPermitTotalFee` to fees. Status mapping:
  `Open` -> `pre_approval/submitted_or_under_review`; `Issued` and
  `Issued with Minor Violations` -> `approved/issued`; `Major Violations` ->
  `pre_approval/revisions_or_failed_review`; `Deleted` -> `voided/canceled`.
  The endpoint returns a full JSON array with no observed cursor; ingest as a
  snapshot keyed by `OccupancyApplicationID`, using `CurrentResultDate` and
  `ApplicationDate` watermarks plus full reconciliation to detect deletes or
  status changes.
- City issued building permit confirmation source:
  `https://www.stlouis-mo.gov/data/datasets/dataset.cfm?id=1`, especially
  `https://www.stlouis-mo.gov/data/dashboards/building-permits/30-days.cfm`
  and JSON export
  `https://www.stlouis-mo.gov/customcf/endpoints/building-permits/building-permits-30-days-export.cfm?dataType=json&permitType=all`.
  The official dataset is public access, Building Commissioner provided, and
  the dashboard/export verified current 2026 data. It is approved-signal only:
  fields are `ADDRESS`, `APPLICATIONDATE`, `APPLICATIONDESCRIPTION`,
  `DAYSTOISSUE`, `ESTPROJECTCOST`, `ISSUEDATE`, `PROJECTTYPE`, and
  `STRUCTURETYPE`; map to address, application/issue dates, description,
  review duration, valuation, permit/project type, and structure/use subtype.
  All rows in this export are issued; map lifecycle to `approved/issued`.
  No permit number, parcel, applicant, contractor, or stable row id is present
  in the current dashboard export, so generate a conservative source hash from
  address, application date, issue date, project type, structure type, value,
  and description, and treat it as supplemental evidence rather than a primary
  durable permit feed. The older ArcGIS `SLDC/Building_Permits` FeatureServer
  has richer parcel/owner/contractor fields and pagination, but live date
  filtering returned no 2026 rows while the dashboard showed 2026 activity; do
  not rely on it until freshness is revalidated.
- Rights notes: City dataset metadata marks access level public and is exposed
  through official open-data pages; no explicit restrictive commercial-use
  notice was found on those city dataset/API pages, so proceed under public
  open-data posture with attribution and source/evidence URLs retained. St.
  Louis County's official Accela portal is at
  `https://aca-prod.accela.com/SLC/Default.aspx`; it offers permit search, but
  the portal states that commercial use of materials stored on the site is
  prohibited without prior written county permission, and no supported public
  bulk/API feed was verified. Hold county ingestion unless written commercial
  SaaS reuse/storage/display rights and a stable API/export are obtained.

### Detroit Building Plan Reviews And Issued Permits

- Official ArcGIS layers: `bseed_building_permit_plan_reviews` and
  `bseed_building_permits`.
- Decision: legal hold.
- Technical fit: same-day plan-review and issued-permit layers, stable unique
  `task_id` and `record_id`, project/use narrative, address, parcel, valuation,
  units, zoning, and coordinates. `record_id` joins review tasks to later
  issued records.
- Rights blocker: both official items are public and authoritative, but their
  license metadata and copyright fields contain no affirmative commercial use
  or redistribution grant.
- Release condition: a City of Detroit license or written authorization that
  covers both item IDs and downstream normalized redistribution.

### Philadelphia And Pennsylvania Early-Warning Sources

- Philadelphia's fresh permit layer contains issued, denied, and refused
  outcomes but no submitted, pending, intake, or initial-review applications.
  Its city license also does not affirmatively permit commercial use.
- Pittsburgh's licensed feed is approved separately as confirmation data but
  contains only issued permits. Harrisburg's candidate layer is stale and lacks
  lifecycle context.
- Decision: Pennsylvania remains an early-warning hold until Philadelphia
  publishes licensed pending applications or Pittsburgh exposes the upstream
  application table before issuance.

### Tennessee Permit And Development Filing Sources

- Decision summary: narrow Nashville planning-development admit; other
  Tennessee permit feeds remain held. Tennessee has several strong official
  technical candidates, including Nashville planning cases, Shelby County issued
  permits, and Knoxville-Knox County development projects, but only Nashville's
  current Planning Department Development Applications layer currently clears
  the supported public API threshold for limited production use.
- Nashville / Davidson County Development Tracker: narrow admit for
  pre-approval planning and zoning signals.
  Production source: `nashville_tn_planning_development_applications`.
  Official open-data page:
  `https://data.nashville.gov/datasets/planning-department-development-applications-1`.
  Official layer:
  `https://services2.arcgis.com/HdTo6HJqh92wn4D8/arcgis/rest/services/Planning_Department_Development_Tracker_Applications/FeatureServer/0/query`.
  Live checks on July 18, 2026 found public ArcGIS query/extract support,
  `OBJECTID` identity, current item edit metadata, and `PSTAT` lifecycle values
  including `New`, `Pending`, `Active`, and `Complete`.
- Admitted fields are planning case identity, application type, accepted date,
  MPC/ordinance numbers, project name, location, hearing and council-reading
  dates/actions, council district, public application scope, status, MPC action,
  parcel text, acreage, existing/new zoning, community plan, and point geometry.
  `APP_NAME`, representative/contact fields, reviewer email, school-board text,
  raw geometry export, and raw source export are suppressed from the source
  slice. `New` and `Pending` normalize to `pre_approval`; `Complete`, explicit
  MPC approval actions, and passed third-reading evidence normalize to
  `approved`.
- This layer is development-review intelligence, not a building-permit issuance
  feed. It is valuable for early site-plan, rezoning, subdivision, mixed-use,
  industrial, commercial, and large-development signals because project name,
  scope, parcels, zoning context, location, and hearing dates can appear before
  final permit issuance.
- Rights posture remains narrower than CC0/CC-BY. The public item is attributed
  to Nashville Planning Department and exposes public API/query access, but
  item `licenseInfo` is blank. Use Metro Nashville / Nashville Planning
  Department attribution, retrieval-date/currentness caveats, no endorsement,
  no warranty, and no raw source-replacement resale until broader use is cleared.
  The indexed `Codes/BuildingPermits/MapServer` permit layer is not currently a
  live service in Metro's REST directory; treat it as API-availability hold
  until Metro publishes a supported endpoint or bulk export for ePermits/Codes.
- Chattanooga / Hamilton County: hold. The official Chattanooga maps/open-data
  page points users to ChattaData and regional GIS resources, but the legacy
  `All Permits` Socrata endpoint (`tfyc-kggg`) now redirects to an unsupported
  ArcGIS Hub legacy page or returns host errors during API probes. A search hit
  for a current `Permits` FeatureServer was rejected because sampled evidence
  URLs and coordinates referenced Midland, Texas, not Chattanooga. Release
  requires the city or Hamilton County to publish a current official permit or
  land-development layer with durable row IDs, statuses, update timestamps or
  full-snapshot controls, and explicit commercial reuse rights.
- Memphis / Shelby County: narrow admit candidate for approved/issued
  construction context, currently rights/currentness hold and not an early
  warning source. Official Data Midsouth / OpenDataSoft dataset:
  `shelby-county-building-and-demolition-permits`; records API:
  `https://datamidsouth.opendatasoft.com/api/explore/v2.1/catalog/datasets/shelby-county-building-and-demolition-permits/records`.
  Metadata attributes the feed to Shelby County and Develop 901, publisher
  Innovate Memphis, reference `https://aca-prod.accela.com/SHELBYCO/Default.aspx`,
  8,751 records, monthly cadence, and July 1, 2026 processing. Live status
  values were Issued 4,707, Closed - Complete 4,036, and Inspection Phase 8;
  max `date_status` was April 30, 2026, so the feed is not current enough for
  daily early-signal detection.
- Memphis candidate mapping if released: `permit_key` -> `source_record_id`;
  `record_id` -> `source_permit_id`; `permit_class`, `permit_type`, and
  `record_type` -> `permit_type` / `work_type`; `description` -> project text;
  `site_address`, `zip_code`, `lat`, `lon`, and `geo_point_2d` -> location;
  `status` -> `raw_status`; `date_status` -> `issued_at` or status date;
  `estimate_cost` -> valuation; `total_building_sqft` -> square feet; `parid`
  -> parcel ID; `business_name_contact` and `business_name_prof` -> applicant /
  contractor evidence; zoning, property class, land-use, council, commission,
  super-district, and tract fields -> jurisdiction context. Filter to
  non-residential permit classes, commercial/new construction/demolition,
  high-value records, and text containing retail, restaurant, tenant finish,
  store, warehouse, hotel, medical, mixed-use, or chain/brand terms. Page with
  `limit`/`offset` or `where=permit_key > :last_key` if the API supports stable
  key ordering; retain the dataset record URL as evidence. Release requires
  Data Midsouth and/or Shelby County written confirmation that downstream
  commercial SaaS storage/display/API/export is allowed and a fresher cadence or
  direct Develop 901/Accela feed.
- Knoxville / Knox County: narrow admit candidate for development-project
  context, currently legal hold. Official Knoxville-Knox County Planning
  Groundbreakers app:
  `https://maps.knoxmpc.org/groundbreakers/`; source layer:
  `https://services1.arcgis.com/QWaOgwdmpqI9HUzf/arcgis/rest/services/DevelopmentProjects/FeatureServer/0`.
  Live checks found 542 projects, July 2026 edit metadata, and high-value fields
  for `PROJECT`, `TYPE`, `ANNOUNCE_DATE`, `DESCRIPTION`, address, tax ID, owner,
  developer, architect, contractor, units, structure size, parcel size, cost,
  start/completion dates, `MPC_FILENUM`, `STATUS`, `STAGE`, documents, photos,
  and recent-news evidence. Stage codes cover proposed, design review,
  construction, withdrawn, and complete; project types include commercial,
  retail, mixed use, industrial/warehouse, medical, apartment, assisted living,
  and special use.
- Knoxville candidate mapping if released: `OBJECTID` -> `source_record_id`;
  `MPC_FILENUM` -> `source_permit_id` when present; `PROJECT` -> project name;
  `TYPE` -> proposed use; `ANNOUNCE_DATE` -> `applied_at` / signal date;
  `DESCRIPTION` and `STATUS` -> project text; `MPC_ADDRESS`, `LOCATION`,
  `ZIP_CODE`, and geometry -> location; `TAX_ID` -> parcel ID; `OWNER`,
  `DEVELOPER`, `ARCHITECT`, and `CONTRACTOR` -> parties; `COST` -> valuation;
  `STRUCTURE_SIZE` -> square feet; `UNITS` -> units; `STAGE` -> lifecycle
  stage. Filter to retail, commercial, mixed-use, industrial/warehouse, medical,
  and high-value special-use records, especially `STAGE` 1 and 2 for early
  warnings. Page by `OBJECTID` with 1000-row pages and evidence URLs querying
  the same layer. Release requires Knoxville-Knox County Planning license or
  written permission because item metadata lists `licenseInfo: None`.
- Statewide Tennessee: hold. The Tennessee CORE / State Fire Marshal resources
  support residential/electrical permit workflows and searches, but no official
  statewide bulk/API feed for current commercial building permits, municipal
  planning filings, or development-review records was verified. The state
  comptroller publishes land-use and parcel context, not permit lifecycle data.

### Phoenix Plan Review And Permits

- Official service: `Public/Planning_Permit/MapServer`, layers 0 and 1.
- Decision: internal evaluation only; do not add to the production catalog.
- Identity: `PID` is complete but not unique. `OBJECTID` is the only declared
  unique row key and must be retained separately from the permit group ID.
- Lifecycle: the plan-review layer contains mixed document stages. The permit
  layer contains both open/unissued and issued records, so issue-date presence
  is required for approval classification.
- Reliability: same-day entry data was observed, but no publisher update cursor
  or documented refresh cadence exists. Full reconciliation is required.
- Rights blocker: these two layers are not listed in the Phoenix open-data
  catalog and expose blank license metadata. Written confirmation that the
  layers are covered by the city open-data terms is required before commercial
  collection or redistribution.
- July 18, 2026 re-check: the broader Planning and Development tools page
  confirms SHAPE PHX covers commercial permits, plan reviews, and inspections,
  and the `Public/Planning_Permit/MapServer` service exposes plan review,
  permits, proposed zoning, approved zoning, zoning adjustments, and GPA layers.
  However, Phoenix's copyright page still limits site-material downloads to
  personal, non-commercial, not-for-profit purposes, while the GIS service only
  provides attribution/no-warranty language. Keep Phoenix as a written-
  permission target despite its strong technical pre-approval signal.

### Atlanta Building Permit Tracker

- Official ArcGIS sources: `Building_Permit_Tracker/FeatureServer/2`
  (`BuildingPermits_ResComm_AllStatuses_AGOL`) and the static ArcGIS CSV item
  `All Building Permits 2019-2024`.
- Decision: hold for production. The sources are official and contain
  pre-approval statuses, but the live tracker is stale and thin, while the CSV
  archive is static.
- Lifecycle: tracker status values include ACA pending, accepted, additional
  materials/review required, approved/building-only, in progress, invoiced,
  open, posted, ready to issue, revised plans routed, routed for review,
  issued, closed, CO issued, complete/completed, no CO required, and
  terminated. Treat accepted/routed/review/materials/invoiced/open/posted/ready
  and approved-building-only as application-stage; `Issued` as approved/issued;
  closed/CO/complete/no-CO as constructed or closeout; terminated as abandoned.
- Schema: the tracker exposes `FID`, `RecordID`, `Name`, `OrigOpened`, `Opend`,
  `TypeCombo`, `Use_`, `Subtype`, `Group_`, `Address`, `Status_1`,
  `StatusDate`, `JOB_VALUE`, `PARCEL`, `JobValue`, `ACA_Link`, `GrpdStatus`,
  point geometry, and street-view links. It lacks applicant, owner, contractor,
  detailed work description, and document fields. The CSV archive adds
  description, zoning, CDP land use, latitude/longitude, and geocoding fields
  but omits parcel and party fields.
- Identity and access: ArcGIS query supports JSON/geoJSON/PBF, standardized
  queries, count/statistics, `resultOffset`/`resultRecordCount`, create
  replica, and a 2,000-row maximum record count. `FID` is system-maintained
  transport identity. `RecordID` is complete but duplicated in the live tracker,
  so use `FID` plus source snapshot hash for transport and retain `RecordID` as
  the business permit/application number.
- Historical depth and freshness: July 2026 verification found 22,778 live
  tracker rows with opened dates from 2010-12-15 through 2024-11-19 and maximum
  status date 2024-11-20, matching the service data-last-edit timestamp. The
  CSV archive contains 38,107 unique record IDs from 2019-01-02 through
  2024-04-26 and is not a current feed.
- Rights: the Atlanta Open Data Hub item advertises `CC-BY-SA`, but the permit
  tracker service has blank `licenseInfo`/copyright fields and the CSV archive
  has null `licenseInfo`. Admission requires written confirmation that these
  permit items are covered for commercial storage, derived matching, customer
  display, and redistribution, with any share-alike obligations documented.
- Release condition: a current official bulk/API feed or refreshed tracker with
  applicant/contractor/work-description depth, stable row/version semantics or
  documented duplicate handling, a modification cursor or accepted full-snapshot
  reconciliation process, and explicit commercial reuse rights.

### Kentucky Permit Sources

- Louisville Metro's official Active Construction Permits ArcGIS layer is
  current, public, and licensed under ODC PDDL 1.0, but all 23,316 audited rows
  were already issued. The layer also has 16 duplicated permit numbers and no
  verified durable business row key; `ObjectId` is system-managed.
- Decision: Kentucky remains a lifecycle hold for early warning. Louisville is
  eligible only as a future approved-only confirmation source, using complete
  snapshot reconciliation, source row hashes, and preserved duplicate rows.
- Lexington's AgencyCounter, Warren County's SmartGov portal, and Northern
  Kentucky's One Stop Shop expose useful public workflows but no documented,
  affirmatively licensed bulk application API was verified.

### Utah Permit Sources

- Provo's official `DevServ/CurrentProjects/MapServer` is the strongest
  technical source. Planning layer 0 contains fresh incomplete, open,
  under-review, revision, hearing, approval, and appeal stages; building layer
  1 contains pending and plan-check records through issuance and closure.
- Planning `RecordID` was complete and unique across 196 audited rows. Building
  permit numbers were not unique, and the building layer has no documented
  durable business row key; use full ID-manifest snapshots and preserve source
  multiplicity if rights are obtained.
- Decision: legal hold. The official catalog item is public but has null
  `accessInformation`, `licenseInfo`, and `termsOfUse`. Provo's general portal
  says data may be reused but does not affirmatively grant commercial use and
  redistribution.
- Salt Lake City's active-permit layer has stronger parcel, owner, applicant,
  and description fields, but appeared stale and likewise lacks affirmative
  license metadata.

### Alaska Permit Sources

- Anchorage's official permit detail pages expose application screening,
  review, corrections, approval, issuance, inspections, parcel, owner,
  contractor, applicant, and work descriptions under a strong municipal open
  data policy. Decision: technical hold because the system provides point HTML
  lookups rather than a documented bulk dataset or API with testable identity
  and reconciliation behavior.
- Juneau's historical reports directly validate the early-retailer use case: a
  filing described a 2,500-square-foot Starbucks restaurant while still under
  review. The reports became stale after the January 2026 Tyler migration, are
  hashed PDFs rather than a structured feed, and have no verified affirmative
  commercial redistribution grant.
- Decision: Alaska remains hold. Pursue an official Anchorage export/API,
  Juneau EnerGov reporting access and written rights, or a statewide Fire
  Marshal application export; do not crawl sequential internal IDs or automate
  vendor portals.

### Hawaii Permit Sources

- Honolulu's official Socrata dataset `4vab-c87q` contains 432,021 records with
  complete unique `externalid`, strong parcel/address/applicant/contractor/use
  context, and genuine pre-approval statuses including 6,147 unissued plan
  reviews. It is a static snapshot whose latest applications are from June
  2025 and whose official metadata reports a null license.
- Decision: freshness and legal hold. The replacement HNL Build system is the
  current official workflow but exposes no documented bulk API or export.
- Hawaii County explicitly restricts automated and commercial use without an
  agreement; Maui and Kauai expose vendor searches without a licensed bulk
  interface. Do not automate those portals.
- If Honolulu grants rights and a current export, ingest complete snapshots by
  `objectid`, provisionally canonicalize on `externalid`, retain parcel TMK and
  party fields, and retire missing records only after manifest reconciliation.

### Iowa Permit Sources

- Cedar Rapids' official Tyler EnerGov portal exposes true submitted, pending,
  hold, approved, issued, closed, denied, void, and expired stages with project
  name, description, address, parcel, dates, and internal UUIDs.
- Decision: legal and operational hold. The search service is an undocumented
  application backend, anonymous calls are not a stable API contract, exports
  cap at 1,000 rows, no update watermark exists, and the unfiltered total
  exceeds exposed status totals by roughly 353,000 records.
- No affirmative Cedar Rapids commercial reuse and redistribution terms were
  found. Des Moines' official GIS agreement restricts transfer and public
  digital distribution, while Davenport and Iowa City provide point searches
  rather than licensed bulk feeds.
- Statewide DNR/DOR environmental and parcel-adjacent sources do not replace
  municipal permit coverage. DNR floodplain records are issued/confirmation
  evidence, and water/wastewater or air construction datasets are narrow
  environmental-development signals with stale or blank license metadata.
- Release requires written rights, a supported bulk API/export, full UUID
  identity certification, lifecycle-count reconciliation, update/deletion
  watermarks, and permission for SaaS storage, customer display, API output,
  derived exports, and raw-source suppression terms.

### Idaho Permit Sources

- Boise's Development Tracker and High Impact Permit layers are current and
  technically excellent. They expose early planning, applicant revisions,
  hearings, entitlement, review, ready, fee, and issued stages with stable
  `RecordID`; Ada County adds building, planning, preapplication, engineering,
  applicant, parcel, decision, and change-date evidence.
- Both systems directly demonstrate retailer-detection value, including named
  coffee-shop projects before approval. Ada's joined views repeat application
  IDs across party and parcel rows, so canonicalize on `APPRecID` while
  preserving every distinct party/parcel/source-row hash as evidence.
- Decision: legal hold. Boise's custom terms contain disclaimers but no
  commercial copying or redistribution grant; Ada's official metadata has
  empty license and terms fields. Written downstream-product permission would
  make these high-priority onboarding candidates.

### Arkansas Permit Sources

- Decision: NARROW ADMIT candidate for Fayetteville current permits; HOLD for
  Little Rock, North Little Rock, Bentonville, Rogers, and statewide Arkansas
  coverage until freshness, supported bulk access, and commercial SaaS
  storage/display/export rights are confirmed.
- Fayetteville is the strongest production candidate found. Official source:
  `https://maps.fayetteville-ar.gov/server/rest/services/Permits/MapServer/0`.
  The layer is current, queryable without login, and had 57,118 records on
  July 17, 2026. It exposes pre-approval and approved lifecycle states,
  including `Submitted - Online`, `In Review`, `On Hold`, `Conditional
  Approval`, `Approved`, `Issued`, `TCO Issued`, `Complete`, `Expired`,
  `Withdrawn`, `Denied`, `Void`, and `Stop Work Order`. Live commercial
  examples included an unissued `Commercial Building Permit` for a $9.1M
  interior office renovation, a submitted demolition of an old restaurant and
  retail store for a new bank, a future catering-business bathroom buildout,
  and Casey's sign work.
- Fayetteville field mapping candidate: `OBJECTID` -> `source_record_id`;
  `PERMITNUMBER` -> `source_permit_id`; `PM_TYPE` -> `permit_type`;
  `PM_WCLASS` -> `work_class`; `DESCRIPTION` -> `description`;
  `PM_STATUS` -> `raw_status`; `FULLADD` -> `address`;
  `VALUE` -> `estimated_value`; `ISSUEDATE` -> `issued_at`;
  `FINALIZEDATE` -> `finaled_at`; `last_edited_date` -> `last_source_updated_at`;
  `URL` -> `evidence_url`; point geometry requested with `outSR=4326` ->
  coordinates. Lifecycle mapping: submitted, in review, on hold, conditional
  approval, and approved-without-issued-date -> pre-approval/review; issued
  and TCO issued -> approved/active; complete/final -> completed; denied,
  void, expired, and withdrawn -> terminal/non-opportunity unless linked to
  a newer filing.
- Fayetteville query plan for catalog onboarding: connector `arcgis` against
  `/query`, `where=1=1`, `outFields=OBJECTID,PERMITNUMBER,PM_TYPE,FULLADD,DESCRIPTION,PM_STATUS,VALUE,PM_WCLASS,ISSUEDATE,FINALIZEDATE,URL,last_edited_date`,
  `returnGeometry=true`, `outSR=4326`, `f=json`, page by `OBJECTID` keyset
  with `resultRecordCount=2000`, and run periodic full reconciliation because
  no tombstone feed was verified. Commercial filters should include
  `Commercial Building Permit`, demolition, sign, certificate/occupancy, site,
  grading, tenant, addition, alteration, new, interior, restaurant, retail,
  store, bank, grocery, hotel, office, medical, warehouse, industrial,
  distribution, mixed-use, multifamily, and known retailer/chain lexicons.
  Suppress ordinary single-family, duplex, HVAC changeout, plumbing-only,
  electrical-only, and personal accessory permits unless joined to commercial
  project evidence.
- Fayetteville rights note: the city GIS disclaimer permits public use at the
  user's risk but does not affirm raw-feed resale/export. Treat as a narrow
  admit only after counsel/product approval for derived permit/opportunity
  display, attribution to City of Fayetteville, AR, no raw bulk redistribution,
  and evidence-link-back preservation. Official GIS terms evidence:
  `https://www.fayetteville-ar.gov/384/GIS-Interactive-Maps`.
- Little Rock remains a high-value early-retailer hold. Official source:
  `https://maps.littlerock.gov/server/rest/services/Permits/MapServer`, with
  open permits at layer `0` and closed/voided permits at layer `1`. The
  service is imported from the CDR permitting database, supports JSON/GeoJSON
  query, and had 66,185 open rows and 203,561 closed/voided rows on July 17,
  2026. Fields include `PermitNumber`, `ProjectDesc`, `AppDate`,
  `PermitIssueDate`, `PermitStatus`, `PermitMileStone`, `PermitType`,
  `PermitDesc`, `WorkClassMapped`, `PropertyAddress`, `BldUseDesc`,
  `LastModifiedDate`, `DECLVLTN`, `Contractor`, `LICENSENUMBER`, and geometry.
  It directly validates early chain signals: recent commercial samples included
  a Rolex tenant finish/new jewelry store, a yoga studio remodel, and hospital
  renovation filings, with milestones such as `APPLY`, `PERMIT TECH REVIEW`,
  `PAYMENT DUE`, and `INSPECTION`.
- Little Rock blockers: the newest observed open rows were June 18-19, 2026,
  roughly four weeks stale as of July 17, 2026; the public Dynamic Portal
  lookup is search-form oriented rather than a documented supported bulk API;
  and no affirmative city commercial reuse/redistribution grant was verified
  for the MapServer. Release condition: current daily/near-daily refresh,
  written permission or official open-data license covering SaaS storage,
  display, API access, and exports, and a reconciliation plan across both
  open and closed/voided layers. If unlocked, canonicalize on `PermitNumber`
  plus source-layer and source-row hash because fee/trade rows can duplicate a
  permit number.
- North Little Rock remains a monthly-report hold. Official source:
  `https://nlr.ar.gov/departments/planning/nlr-permit-data/`. The city says
  the page contains monthly building permit data, updated the first week of
  each month, with XLSX/CSV files. It can support historical/approved context,
  but it is not a current application-through-approval feed, lacks a stable
  API/watermark/tombstone model, and no commercial reuse/export grant was
  verified.
- Bentonville remains a portal/report hold. Official sources:
  `https://www.bentonville.ar.gov/187/Applications`,
  `https://www.bentonville.ar.gov/180/Permit-Applications`,
  `https://www.bentonville.ar.gov/195/Current-Planning`, and
  `https://www.bentonville.ar.gov/152/Building-Activity-Reports`. The city
  uses eTrakit for permits, projects, large-scale development, plats,
  transportation permits, grading, and floodplain permits, and publishes
  bi-weekly/monthly building activity reports. This is strong signal surface
  area, especially for Walmart-market growth, but no public bulk/API contract,
  status-history export, or commercial SaaS rights were verified.
- Rogers remains a portal hold. Official sources:
  `https://www.rogersar.gov/394/Applications-Forms`,
  `https://www.rogersar.gov/772/Residential-Projects`,
  `https://www.rogersar.gov/1434/Business`, and the official GIS services
  directory at `https://gis.rogersar.gov/gis/rest/services/Public`. Rogers
  says many planning functions are performed through its permitting and
  planning portal, while public GIS services found in this pass expose parcels,
  addresses, subdivisions, and roads rather than a permit/development filing
  layer. Hold until the city or its portal vendor provides a supported permit
  and planning application export/API with rights.
- Statewide Arkansas sources do not replace municipal permit coverage. The
  Arkansas GIS Office publishes statewide planning/cadastre and planning
  development district layers, but these are boundary/parcel context, not
  current permit or development-review filings. Use them only as geography
  context unless a separate official statewide permitting feed is identified.

### Kansas Permit Sources

- Wichita/Sedgwick's official workflow includes submitted commercial plans and
  pre-issuance review, but its enumerable public report is issued/active/final
  HTML with ten-row pages and no supported bulk contract, update watermark, or
  deletion signal. Its planning CSV contains aggregate counts only.
- Overland Park's live ArcGIS layer has unique complete case numbers, parcel,
  description, value, size, dates, and current issued records, but explicitly
  excludes pending applications and has blank license metadata.
- Johnson County's public portal supports application and plan-review tracking
  without a bulk API; county AIMS terms prohibit reproduction for sale and are
  incompatible with the product.
- Decision: Kansas remains hold. Unlock through a licensed Wichita/Sedgwick
  application-through-final export or a licensed pending companion layer from
  Overland Park.

### Maine Permit Sources

- Portland's official Development Review layer exposes submitted, payment
  pending, in-review, hold, approved, expired, withdrawn, and void site-plan
  applications with description, address, parcel, zoning, hearings, geometry,
  and an EnerGov evidence link. `PLPLANID` is the canonical identity; two exact
  duplicate rows prove `OBJECTID` cannot be trusted as unique evidence identity.
- Maine DEP also publishes a real-time, statewide environmental
  application-through-decision layer with applicant, project description,
  status, dates, tax map and lot. It is supplemental environmental evidence,
  not a comprehensive building-permit feed.
- Decision: legal and lifecycle hold. Both official GIS services have blank
  license metadata, and Portland's bulk layer lacks building issuance and
  professional parties. Obtain commercial rights plus a supported Portland
  application-through-issued export before production onboarding.

### Montana Permit Sources

- Billings' legacy GIS permit layer contains 132,552 technically rich rows with
  plan-check, hold, payment-pending, approved, closed, rejected, and void
  statuses plus descriptions, work scope, owner, contractor, parcel, address,
  dates, outstanding reviews/fees, and evidence links.
- Decision: freshness, identity, and legal hold. The bulk layer stopped
  reflecting current ordinary applications after April 2026 while the city
  reported substantial June volume; replacement CityView is point-search only.
  Permit-number uniqueness is uncertified, ArcGIS IDs are not durable, and
  official metadata is unlicensed under an all-rights-reserved city notice.
- Yellowstone County does not issue countywide building permits outside
  Billings. Unlock through a supported CityView export/API plus written
  commercial product and redistribution rights.

### New Hampshire Permit Sources

- Nashua remains a municipal building-permit hold. The official Building Safety
  page accepts commercial and residential permit submittals by email, mail,
  drop box, phone payment, or in-person delivery, and the city GIS viewer is
  parcel/assessment oriented rather than a permit bulk feed. No current
  supported permit API, status history, authoritative control totals, update
  watermark, deletion semantics, or affirmative commercial SaaS reuse/export
  terms were verified. Official sources audited:
  `https://www.nashuanh.gov/275/Building-Safety-Department`,
  `https://www.nashuanh.gov/278/Permits`, and
  `https://nashuagis.nashuanh.gov/`.
- Manchester remains a municipal hold. The official Building and Planning &
  Community Development pages describe building permits, certificates of
  occupancy, zoning, site-plan, subdivision, and stormwater review, but public
  access is through department pages, downloadable/project documents, board
  agendas, and application material rather than a documented structured bulk
  permit/development-review API. Useful pre-approval evidence may exist in
  Planning Board and ZBA project materials, but no machine-readable manifest,
  stable record IDs, commercial reuse grant, or change/tombstone feed was
  verified. Official sources audited:
  `https://www.manchesternh.gov/Departments/Planning-and-Comm-Dev`,
  `https://www.manchesternh.gov/Departments/Planning-and-Comm-Dev/Building`,
  and
  `https://www.manchesternh.gov/Departments/Sewer-and-Stormwater/Stormwater/Stormwater-Resources-for-Site-Development-Construction-Activities`.
- Portsmouth remains a high-value portal hold. The official Inspection
  Department says ViewPoint/OpenGov powers online permitting and lets applicants
  submit, monitor status, and receive review notifications for building,
  tenant fit-up/new-use/change-in-use, temporary structure/use, commercial hood,
  electrical, mechanical, plumbing, fire, and street-encumbrance permits.
  Planning guidance says site plan, subdivision, conditional-use, Technical
  Advisory Committee, Board of Adjustment, Conservation Commission, and Historic
  District Commission submittals go through OpenGov. This is strong
  pre-approval retail/development surface area, but no no-login bulk API,
  supported export, data dictionary, status-history feed, deletion semantics,
  or commercial SaaS storage/display/export permission was verified. Official
  sources audited:
  `https://www.portsmouthnh.gov/inspection/permit-applications`,
  `https://www.portsmouthnh.gov/inspection`, and
  `https://www.portsmouthnh.gov/planportsmouth/residents-guide-land-use-boards`.
- Statewide NHDES Alteration of Terrain is the strongest New Hampshire
  pre-approval source found. The official Land Resources Management Permit
  Planning Tool says AOT layers include applications received by NHDES from
  2009 to present, project names, current permit status, file number, permit
  number, and exportable tables; `Pending` records are visible as active
  pre-decision applications. Direct layer endpoint:
  `https://gis.des.nh.gov/server/rest/services/Projects_LRM/NHDES_Alteration_of_Terrain_Projects_Updated/MapServer/1`.
  Query params for a pilot: `where=Status in ('Pending','Active')`,
  `outFields=OBJECTID,FILENUM,FILENUM_FULL,Action_Typ,PRJNAME,Status,expiration_date`,
  `returnGeometry=true`, `outSR=4326`, `f=json`, page by `OBJECTID` keyset
  with `resultRecordCount=2000`, and run periodic full snapshots because no
  modified timestamp or tombstone feed is published.
- AOT field mapping candidate: `OBJECTID` -> `source_record_id`; `FILENUM_FULL`
  or `FILENUM` -> `source_permit_id`; `Action_Typ` -> secondary permit/action
  number; `PRJNAME` -> `project_name`; `Status` -> `raw_status`; `expiration_date`
  -> `expires_at`; polygon centroid -> coordinates; geometry -> project
  footprint evidence. Lifecycle mapping: `Pending` -> pre-approval /
  under-review; `Active` -> approved/active state permit context; `Denied`,
  `Closed`, and `Expired` -> terminal/non-opportunity states unless a downstream
  municipal permit reactivates the project. Observed status distribution on
  July 17, 2026: 85 pending, 1,254 active, 149 closed, 39 denied, and 1,775
  expired polygon records. Recent pending examples include a proposed medical
  office building, snowplow sales development, condominiums, and excavation /
  grading / reclamation.
- AOT filters for commercial/retail/development relevance: include `Pending`
  and `Active` records whose `PRJNAME` contains commercial, retail, store,
  restaurant, office, medical, warehouse, industrial, distribution, hotel,
  mixed-use, multifamily, condominium, subdivision, site, grading, excavation,
  reclamation, parking, or similar development terms; keep all large polygon
  footprints above a configured area threshold for human review even when
  `PRJNAME` is blank; suppress obvious single-family/dock/shoreland personal-use
  records unless later linked to a commercial entity. Evidence URL should be the
  canonical query URL for the layer with `where=OBJECTID=<source_record_id>`,
  plus the public LRMPPT app
  `https://experience.arcgis.com/experience/0e53b35d807748c1aec40a9a0a5e96d5`
  and OneStop lookup
  `https://www4.des.state.nh.us/DESOnestop/BasicSearch.aspx`.
- Supplemental NHDES layers: Wetlands Permit Points are current and
  queryable at
  `https://gis.des.nh.gov/server/rest/services/Hosted/NHDES_Wetlands_Permit_Points/FeatureServer/0`,
  but the public fields are only file number, project type, global ID, and point
  geometry, so this is evidence/context only unless joined to OneStop details.
  Construction start/finish/inspection notices are queryable at
  `https://gis.des.nh.gov/server/rest/services/Hosted/Construction_Start_Finish_Inspections/FeatureServer/1`
  and include file, project type, reviewer, type code, owner, city, description,
  expired, inspected, construction-start, and construction-finish flags. The
  service description says notices are received by Land Resources Management as
  a wetlands-permit requirement and the layer is updated biweekly. This is
  construction-activity confirmation, not early permit filing.
- Decision: NARROW ADMIT candidate for NHDES AOT as statewide large-development
  pre-approval/approved context, subject to written or policy-confirmed
  commercial SaaS storage/display/API/export rights and no raw-feed resale.
  Keep Nashua, Manchester, and Portsmouth municipal permits/planning in HOLD
  until official bulk/API access and rights are granted. Do not catalog New
  Hampshire production coverage yet; the next unlock is a rights confirmation
  from NHDES/NH GRANIT plus a pilot canary proving stable pagination, status
  mapping, geometry handling, evidence URLs, and blank-project-name quarantine.

### Nebraska Permit Sources

- Omaha's official Planning Board FeatureServer is current and valuable for
  early discovery. It exposes planning cases, applicants, project requests,
  locations, hearing dates, exhibits, geometry, and a populated `globalid`.
  These are applications and hearings, however, not dependable approval or
  building-permit issuance records.
- Omaha's Accela system contains the downstream permit lifecycle but offers no
  documented public bulk API, export, watermark, deletion signal, or durable
  identity contract. Douglas County's SmartGov portal publishes no reports;
  its GIS permit-document layer stopped updating in 2020.
- Lincoln's Planning Application Tracking System / development-review layer is
  admitted narrowly as pre-approval-through-approved planning context. It
  exposes formally submitted applications with application number, subtype,
  status, submission/effective dates, project description, hearing/resolution
  references, and geometry. Catalog mapping keeps submitted/staff-review rows
  as `pre_approval`, treats effective/approved rows as `approved`, and excludes
  raw shape metrics, raw geometry exports, and source-replacement resale.
- Decision: narrow admit for Lincoln / Lancaster PATS development applications;
  hold Omaha planning, Omaha Accela, Douglas County SmartGov, and downstream
  municipal permit issuance until supported bulk/API access and rights are
  granted. Nebraska statewide and county assessor parcel layers are Phase 2
  permission targets only until commercial storage, derived nearby-parcel
  discovery, customer display, API output, exports, retention, attribution, and
  suppression requirements are confirmed in writing.

### Rhode Island Permit Sources

- Decision: HOLD for current Rhode Island / Providence production coverage;
  NARROW ADMIT only for Providence historical backfill, model evaluation, and
  retailer/entity vocabulary learning. The historical feed must not be marketed
  or scored as a current pre-approval source.
- Official historical Providence source: Socrata dataset
  `Department of Inspections and Standards Permits 2009-2018`
  (`https://data.providenceri.gov/Neighborhoods/Department-of-Inspections-and-Standards-Permits-20/ufmm-rbej`),
  API `https://data.providenceri.gov/resource/ufmm-rbej.json`.
  The dataset is publisher-official, PDDL 1.0 licensed, bulk-queryable, and
  currently returns 80,874 records. Metadata shows `rowsUpdatedAt` January 24,
  2020, with permit records effectively ending in 2019.
- Historical field mapping if admitted to a backfill-only catalog:
  `permitnum` -> `source_permit_id` and `source_record_id`; `permittype` and
  `permittypemapped` -> `permit_type`; `permitclass`, `workclass`, and
  `permitclassmapped` -> `work_type` / commercial context; `statuscurrent` and
  `statuscurrentmapped` -> `raw_status`; `description` ->
  `project_description`; `applieddate` -> `submitted_at`; `issueddate` ->
  `issued_at`; `completeddate` -> `completed_at`; `estprojectcost` ->
  `valuation`; `totalsqft` -> `square_feet`; `originaladdress1`,
  `originalcity`, `originalstate`, and `originalzip` -> `site_address`; `pin`
  -> `parcel_number`; `contractorfullname`, `contractorcompanyname`,
  `contractorlicnum`, and `contractorstatelic` -> contractor evidence;
  `geocoded_column.latitude` / `geocoded_column.longitude` -> coordinates.
- Historical query strategy: Socrata offset pages ordered by `permitnum`, with
  `$limit=5000`, `$offset=<n>`, and a content hash because the source is static.
  Evidence URL pattern:
  `https://data.providenceri.gov/resource/ufmm-rbej.json?permitnum=<encoded>`.
  Use commercial/development filters on `permittypemapped`, `permitclass`,
  `workclass`, `description`, `estprojectcost`, and `totalsqft`; keep
  residential rows only for model training or address history, not opportunity
  creation.
- Current statewide/municipal source: Rhode Island Building Code Commission
  statewide e-permitting page
  (`https://ribcc.ri.gov/forms-resources-and-e-permitting/statewide-e-permitting-portal`)
  routes the State Building Commission, Providence, Cranston, Warwick,
  Pawtucket, Newport, East Providence, Woonsocket, and many towns to OpenGov
  portals, including `https://providenceri.portal.opengov.com/` and
  `https://rhodeisland.portal.opengov.com/`. These portals contain the right
  pre-approval shape: submitted applications, workflow steps, locations,
  applicants/guests, attachments, inspections, fees, and issued documents.
- OpenGov technical note: the official OpenGov Permitting & Licensing API is
  hosted at `https://api.plce.opengov.com/plce` and exposes v2 community
  resources such as records, projects, locations, workflow steps, attachments,
  users, fees, and activity logs. It requires an OpenGov account/integration and
  explicit permissions such as `Record Read`, `Workflow Read`, `Location Read`,
  `Record Type Read`, `Files Read`, and for activity logs employee access.
  Public portal HTML also exposes internal ViewPoint/OpenGov GraphQL services,
  but these are application internals and are not an approved production bulk
  contract.
- Current blockers: no anonymous official bulk feed, supported recurring export,
  update watermark, deletion/tombstone protocol, control totals, or commercial
  SaaS storage/display/export license was verified for Providence or the
  statewide OpenGov portals. Rhode Island Division of Statewide Planning's 2025
  Technical Paper 170 says building permit data was not accessible in bulk
  through the State OpenGov portal, only 5 municipalities provided permit files
  in any format, and the files often did not separate new construction,
  renovations, trades, and small work.
- Release condition: admit Rhode Island current coverage only after the State,
  Providence, or OpenGov grants a supported recurring API/export with explicit
  commercial SaaS storage, transformation, display, and redistribution rights;
  durable record IDs; workflow/status history; submitted/issued/final dates;
  record type/form fields; applicant/owner/contractor/architect/engineer roles
  where public; locations/parcels; evidence/detail URLs; page limits; update and
  deletion semantics; and a jurisdiction roster showing which municipalities
  are live in the statewide system. Map lifecycle from workflow and issued
  document evidence, not from display status alone.

### North Dakota Permit Sources

- Fargo publishes complete, current CSV snapshots for commercial plan reviews
  and for permits issued during the prior 90 days. The review snapshot includes
  filed, pending, revisions-needed, and department-review states; permit detail
  pages add establishment, use, cost, area, lifecycle timestamps, and parties.
- This is technically strong early-warning coverage, but department-level
  `Approved` means only that one review has cleared. It must never be promoted
  to permit approval while inspections, engineering, fire, or another review
  remains pending. Disappearance from the open snapshot likewise means only
  “no longer listed” until reconciled with issued records and the detail page.
- Permit number is the durable canonical identity; the opaque detail reference
  is only a retrieval locator. The issued snapshot rolls off after 90 days, so
  every complete snapshot must be retained and reconciled rather than used to
  rebuild history. Byte-identical duplicate export rows should be preserved as
  raw evidence but collapsed for canonical state.
- Cass County has no centralized bulk permit feed. Its official parcel
  FeatureServer is technically valuable for nearby-parcel discovery, but its
  metadata also lacks an affirmative commercial redistribution license.
- Decision: legal hold. Fargo's public-service and website terms provide
  disclaimers, not commercial storage, transformation, paid-product display,
  and redistribution rights. Written city permission would make Fargo a
  high-priority production source and Cass parcels a Phase 2 candidate.

### New Mexico Permit Sources

- Decision: statewide hold for production early-warning ingestion. No audited
  New Mexico candidate currently passes official source, currentness, durable
  identity, lifecycle richness, supported bulk/API, reconciliation, and
  commercial SaaS reuse gates.
- Albuquerque: hold. The official ArcGIS
  `agis/City_Building_Permits/FeatureServer/0` layer is bulk-queryable and
  publishes `PermitNumber`, `GlobalID`, `DateEntered`, `DateIssued`,
  `CalculatedAddress`, work/category/structure fields, valuation, owner,
  applicant, contractor, and work description. It is issued-only in practice:
  `DateIssued IS NULL` returned zero rows, 2026 issued rows returned zero, and
  the latest observed `DateIssued` was January 16, 2025 after the transition to
  ABQ-PLAN. ABQ-PLAN/CSS has application tracking value but no supported bulk
  export/API or redistribution terms were verified. Treat the old ArcGIS layer
  only as stale issued-history evidence, not an approved-only current
  confirmation source.
- Bernalillo County: hold, despite being the best early-warning signal
  candidate. The official `BERNCO/Accela_Permits/MapServer/142` layer is
  current, covers unincorporated county Accela records, and exposes filing,
  review, hearing, approval-with-conditions, issuance, completion, and active
  and closed states through `B1_FILE_DD`, `PERSTATUS`, `PERTASK`,
  `TASKSTATUS`, `PERISSUED`, and `PERCOMPL`. It has strong retail-use fields:
  `PERMIT`, `PERTYPE`, `B1_APP_TYPE_ALIAS`, `PRJ`, `SITEADDRESS`,
  `PARCELNBR`, contractor/licensee names and businesses, contact fields,
  `JOB_VALUE`, and geometry. Blockers are row identity and reconciliation:
  `PERMIT` repeats across workflow/task rows, repeated rows can have identical
  business attributes, `OBJECTID` is the only unique row key, and no immutable
  Accela CAP identifier, row-modified timestamp, deletion feed, or control
  totals are documented. Public GIS access/disclaimer language is not enough
  by itself for paid SaaS storage, enrichment, customer display, and export.
- Las Cruces: hold. The official city page routes building permits, planning
  records, business licenses, application status, inspections, payments, and
  project tracking to Accela Citizen Access. That is lifecycle-rich for manual
  lookup, but no city-published bulk/API feed, durable pagination contract,
  update watermark, deletion semantics, or commercial reuse grant was verified.
- Santa Fe: hold. The city accepts and tracks permits through Tyler/CSS and
  notes that permit review status, holds, invoices, and dashboards are updated
  there; full permit/plan-review visibility requires being a permit contact.
  Public GIS and City Smart surfaces expose maps and non-permit layers, but no
  record-level building/planning permit bulk/API source with reusable terms was
  verified. A promising ArcGIS search result for pending and approved building
  permits was Raleigh, North Carolina, not Santa Fe.
- Rio Rancho: hold. The official
  `City_of_Rio_Rancho_Development_Activity__WFL1/FeatureServer/0` active
  planning-cases layer is queryable and has `OBJECTID`, `GlobalID`, `CASE_`,
  `PROJECT`, `LOCATION`, `PROJECTPHASE`, `DESCRIPTION`, staff contact, and
  geometry, with site-plan, conditional-use, plat, variance, zone-map, and
  master-plan case types. It lacks date fields, applicant/owner/parcel fields,
  lifecycle status normalization, update/deletion semantics, and currentness:
  service edit metadata and sample cases pointed to 2021 activity. The public
  GIS disclaimer does not grant commercial redistribution.
- State-level sources: hold for retailer/development scouting. NMED publishes
  official environmental APIs and an open ArcGIS NPDES service with active and
  pending permit layers, `PERMITNUMBER`, facility name, permit type, status,
  effective/expiration dates, location, coordinates, pagination, and public API
  terms that place public-registrant data in the public domain. The NPDES
  source is too narrow for general retailer/development early warning and lacks
  project/applicant/building context, submission dates, and brand/use fields.
  New Mexico RLD/CID and NMDOT ePermitting provide official permit portals, but
  no anonymous supported bulk/API record feed or commercial SaaS reuse terms
  were verified.
- Release condition: admit only after a jurisdiction publishes or approves a
  normalized Accela, ABQ-PLAN, CSS, or CID export with immutable record and row
  IDs, documented row grain, application/review/approval/issuance/final
  lifecycle, submitted/status/issued/completed dates, parcel/address/project
  and party fields, modification and deletion semantics, control totals,
  stable pagination or snapshots, and written permission for automated
  extraction, storage, enrichment, customer display, attribution, and bounded
  export. Bernalillo County should be re-audited first if those gates are met.

### South Dakota Permit Sources

- Sioux Falls' official building-permit layer is large and bulk-queryable, with
  unique permit numbers, classifications, application/issue/final dates,
  values, units, address, geometry, and contractor. Despite a few historical
  review labels, every row has an issue date and there are no current pre-issue
  2026 records, so it is issued-history enrichment rather than early warning.
- Published GIS counts cannot yet be reconciled to official quarterly totals,
  likely because of trade subpermits, and the layer lacks a modification
  watermark, archive, tombstones, and documented inclusion rules.
- The GIS item references CC BY 4.0 but also says the data is not intended for
  mapping products for resale. Current plans, rezonings, and active permits are
  visible through CSS and Neighborhood Connect without a supported bulk API.
- Decision: lifecycle, reconciliation, and legal hold. Unlock through a
  sanctioned EnerGov export spanning submission through final disposition,
  explicit parent-child and deletion semantics, control totals, and written
  confirmation that commercial Build Signals display and derived products are
  permitted.

### Vermont Permit Sources

- Burlington's official current zoning report is a high-value pre-approval
  signal but remains a production hold. The city report at
  `https://www2.burlingtonvt.gov/OpenGov/Zoning/New/` was current on July 17,
  2026, showed 211 applications received in the prior two months, and exposed
  open workflow states such as `Z Card Posting`, `Application Assessment`,
  `Project Manager Assignment`, `Administrative Decision`, and `Administrative
  Appeal Period`. It also contained retailer/business clues before final action,
  including a July 14, 2026 zoning application for a waterfront visitor center
  and souvenir/snack/ticketing use at `2-8 College Street`.
- Burlington blockers: the city ArcGIS `OpenGov` folder returned `Token
  Required`, guessed building/fire report routes returned 404, and the public
  report is an ASP.NET page with postback pagination rather than a documented
  bulk API, change cursor, deletion feed, or control totals. Evidence links are
  stable-looking OpenGov record URLs such as
  `https://burlingtonvt.portal.opengov.com/records/<id>`, but the vendor page
  exposes internal API configuration only, not a city-authorized extraction
  contract. Burlington website terms reserve rights and restrict automated
  agents. Decision: hold until Burlington/OpenGov provides a supported export
  or API plus written commercial SaaS storage/display/API/export rights.
- Burlington provisional mapping if rights and API access are granted:
  OpenGov record ID -> `source_record_id`; permit number -> `source_permit_id`;
  application date -> `applied_at`; permit type -> `permit_type`; permit status
  and current status -> `raw_status`; street address -> `site_address`;
  description -> `description`; applicant/owner/contractor fields -> parties;
  coordinates/property reference -> location and parcel context; OpenGov record
  URL -> `source_evidence_url`. Filter for zoning/building/sign/change-of-use,
  commercial construction, restaurants, retail, office, industrial, mixed-use,
  lodging, medical, institutional, subdivision, parking, utility/site work, and
  named-chain text; exclude simple residential windows, fences, decks, sheds,
  and like-for-like maintenance unless the description or address is commercial.
- South Burlington / Chittenden municipal sources are useful manual signals but
  also hold. South Burlington publishes recently issued zoning permits and 2026
  Development Review Board application status documents at
  `https://www.southburlingtonvt.gov/231/Current-Application-Status`, maintains
  a CivicEngage agenda center with DRB packets, and links to issued commercial
  permits by address from its developer page. These are current as of July 2026
  and valuable for City Center / commercial review monitoring, but no supported
  bulk API, normalized fields, row-level IDs, update cursor, deletion semantics,
  or explicit commercial redistribution grant was verified.
- Vermont Act 250 is narrowly admitted as secondary statewide
  large-development context, not canonical municipal permit coverage. Official
  API endpoint:
  `https://anrmaps.vermont.gov/arcgis/rest/services/Open_Data/OPENDATA_ANR_ENVIRON_SP_NOCACHE_v2/MapServer/166/query`.
  Use query params `f=json`, `where=1=1`, `outFields=ProjectID,AppNum,AppType,ProjectName,Description,ProjectTown,District,Status,GisLatitude,GisLongitude,LINK`,
  `returnGeometry=false`, `orderByFields=ProjectID ASC`, and keyset pages
  `ProjectID > <last_project_id>` with `resultRecordCount=1000`; run periodic
  full snapshots because no modified timestamp, date received, status-date, or
  tombstone feed is published.
- Act 250 observed fields and mapping: `ProjectID` -> `source_record_id`;
  `AppNum` -> `source_permit_id`; `AppType` -> `permit_type`; `ProjectName` ->
  `project_name`; `Description` -> `description`; `ProjectTown` ->
  `municipality`; `District` -> `jurisdiction_context`; `Status` ->
  `raw_status`; `GisLatitude`/`GisLongitude` -> coordinates; `LINK` ->
  `source_evidence_url`. Lifecycle mapping: `Incomplete`, `Submitted`,
  `Received`, and `Pending (...)` -> pre-approval / under-review;
  `Permit` -> approved; `Denied`, `Withdrawn`, `Dismissed`, `Expired`,
  `Abandoned`, `Revoked`, and `Inactivated` -> terminal non-opportunity states.
- Act 250 quality notes: the layer is bulk-queryable JSON/GeoJSON/PBF with
  8,277 records observed and current pending examples in July 2026, including
  commercial facilities, change-of-use, contractor yards, storage/operations
  buildings, subdivisions, clubs, and infrastructure. The official description
  says base permits only, amendments are not mapped, and statewide coverage is
  approximately 90% complete. The separate Act 250 database search has richer
  lifecycle definitions and document pages but is capped for interactive search,
  so the ArcGIS layer should preserve the `LINK` evidence URL for drill-in
  rather than scrape undocumented database internals.
- Act 250 rights: the Vermont Open Geodata Policy allows direct no-login access
  to open geodata for individuals, businesses, governments, educational
  institutions, and organizations, but prohibits direct, non-value-added resale
  of those data/services/products. Decision: narrow admit only for value-added
  Build Signals evidence/context with attribution, source URLs, no raw-feed
  resale/export, and downstream suppression of full raw source dumps. It does
  not replace Burlington, South Burlington, or other municipal permit feeds.

### Oklahoma Permit Sources

- Oklahoma City remains a hold for commercial building, planning, engineering,
  subdivision, and zoning signals. Its official Accela portal at
  `https://access.okc.gov/ACA/Default.aspx` exposes public searches for filed
  records and the city's guide explicitly describes "submitted building permits"
  searchable by address, type, or date range. That is useful manual evidence for
  pre-approval/submitted signals, but it is a portal workflow rather than a
  supported bulk/API feed: no uncapped record API, exact-total paging, update
  cursor, deletion/tombstone feed, or temporary-to-final identity contract was
  verified. Accela's generic V4 endpoints do not by themselves grant Oklahoma
  City extraction or redistribution rights.
- Oklahoma City's `Data.okc.gov` developer API is official and machine-readable
  for published datasets such as Work Zones, Public Works As-Builts, zoning, TIF,
  land-use, and address layers. It does not currently publish the core building,
  planning, subdivision, or zoning-case application feed needed for Build
  Signals. Live access to the legacy data API and backing ArcGIS service also
  returned Incapsula blocks during audit, which is incompatible with unattended
  production ingestion. The city's current open-data terms also say recipients
  may not redistribute or resell city-provided information, so even adjacent
  datasets remain non-production until rights are clarified.
- Oklahoma City's official Private Development page at
  `https://www.okc.gov/Infrastructure-Development/Public-Works/Private-Development`
  embeds daily Power BI reports for technical review queue placement, completed
  private-development reviews, and prequalified contractors. These reports can
  validate subdivisions, businesses, hotels, restaurants, and civil-review state,
  but they are report embeds rather than documented recurring feeds.
- Tulsa has one high-value development-plan target: the official Open Tulsa item
  `DevPlans_OpenData`, source page
  `https://gis2-cityoftulsa.opendata.arcgis.com/api/search/v1/collections/dataset/items/2368db4b18cc4d27b7377e7bd6170f53`
  and API endpoint
  `https://services2.arcgis.com/XkZ90iCdbTJ9oNXl/arcgis/rest/services/DevPlans_OpenData/FeatureServer/0/query`.
  The layer had 957 development-plan polygons during live audit, supports query,
  extract, order-by, pagination, `GlobalID`, `OBJECTID`, `created_date`, and
  `last_edited_date`, and was edited on July 17, 2026. Current decision: HOLD
  for production until commercial SaaS storage/display/API/export rights and
  raw-resale limits are explicit. If cleared, use it only as a
  planning/development-context source, not a building-permit lifecycle feed.
  Likely mapping would use `GlobalID` as `source_record_id` when stable,
  `ZCASE_NUM`, `PUD`, `SP`, and `Ordinance` as alternate case identifiers,
  `TYPE` as development/review type, `created_date` as filed/source-created
  date, `last_edited_date` as source-updated date, and geometry centroids for
  opportunity context. Lifecycle mapping should remain conservative: rows are
  `pre_approval` / `planning_context` unless a separate official case action or
  ordinance effective date is joined. Page by `OBJECTID`, request selected
  fields only, and preserve source caveats.
- Tulsa permit portal remains a richer but held source. The official Development
  Services pages state that the Tyler/EnerGov self-service portal supports guest
  searches by permit type, address, and date range; commercial permit searches
  can use `BLDC`; building permit applications are reviewed after submission and
  go into a review queue; eReviews supports uploaded plans, failed reviews,
  comments, letters of deficiency, resubmittals, and final issuance. This is the
  pre-approval retailer/chain signal we want, but no supported public bulk API,
  durable cursor, deletion semantics, or commercial SaaS storage/display/export
  grant was verified. Hold until Tyler/API or city-approved export rights are
  available.
- Norman remains a hold. The official CityView portal at
  `https://devnorman.normanok.gov/Portal/` supports applying for construction,
  public works/earth-change, miscellaneous/sign, planning, business-license, and
  property records, and city pages say online inspections expose status detail,
  application fees, permit status, inspection status, plan tracking, and searches
  by application number, address, parcel number, or name. The city's permitting
  statistics page publishes monthly aggregate permit statistics, and its ArcGIS
  basemap exposes zoning/planning overlays, not application records. No
  supported bulk/API feed, current case table, change cursor, evidence URL
  pattern, or commercial redistribution terms were verified.
- Oklahoma County's Planning Commission permit-status search at
  `https://docs.oklahomacounty.org/Planning/PermitStatus.aspx` remains a hold.
  It supports lookup by permit number or street address only and warns that
  information is subject to change and should be verified with Planning. No
  public permit/development-review bulk API, page cursor, update timestamp,
  tombstone semantics, or commercial redistribution license was found.
- Statewide Oklahoma sources do not currently replace municipal coverage. The
  Oklahoma State Fire Marshal plan-review process uses Accela and captures plan
  review lifecycle for covered fire/life-safety projects, but no public bulk/API
  feed or reuse grant was verified. Oklahoma Department of Commerce GIS supports
  incentives, sites, buildings, and CDBG context, not municipal permit filings.
- Oklahoma release path: unlock Tulsa `DevPlans_OpenData`, OKC, Tulsa permit
  CSS, Norman, Oklahoma County, or statewide fire-marshal feeds only with an
  official recurring export or supported API, affirmative commercial SaaS
  storage/display/export rights, immutable source IDs, exact paging totals,
  status/issuance dates, applicant/contractor/owner minimization rules,
  update/delete semantics, raw-resale limits, and a stable evidence URL pattern.

### South Carolina Permit Sources

- Decision: NARROW ADMIT candidate for City of Charleston active permits and
  TRC development-review plans; HOLD Columbia, Richland County, Greenville, and
  Berkeley County for production ingestion until their API and commercial reuse
  positions are clearer.
- Charleston official source: `External/Applications/MapServer` at
  `https://gis.charleston-sc.gov/arcgis2/rest/services/External/Applications/MapServer`.
  Admit layer `20` (`Active Permits`, 18,851 live rows on July 17, 2026) and
  layer `757` (`TRC Plans Point`, 1,042 live rows). The service supports JSON,
  GeoJSON, PBF, standardized queries, order-by, pagination, statistics, and
  5,000-row pages. City open-data pages say public data can be viewed,
  downloaded, transformed, and consumed by API in external applications; use a
  no-raw-resale/export policy and preserve source links and disclaimers.
- Charleston lifecycle: active permits expose `Applied`, `Applied Online`,
  `Needs Review`, `Under Review`, `Issued`, and `Completed`. TRC exposes site
  plan and subdivision statuses including `Applied`, `Applied Online`, `Needs
  Review`, `Needs Correction`, `Payment Pending`, `Pending Final
  Documentation`, `Approved`, `Approved with Conditions`, `Expired`, and
  `Rejected`. This is useful for pre-approval retailer/chain detection.
- Charleston identity and paging: use `OBJECTID` as `source_record_id` because
  `PMPERMITID` / `PERMIT_NUMBER` and `TRC_PLAN_NUMBER` / `PLPLANID` are not
  unique in the live layers. Preserve those fields as business IDs. Ingest with
  `where=1=1`, explicit `outFields`, `returnGeometry=false`, `orderByFields=OBJECTID`,
  `resultRecordCount=5000`, and `resultOffset` pages, plus periodic full
  snapshot reconciliation because no row-modified cursor or deletion feed is
  documented.
- Charleston active permit mapping: `OBJECTID` -> `source_record_id`;
  `PMPERMITID` -> `source_system_id`; `PERMIT_NUMBER` -> `source_permit_id`;
  `PERMIT_TYPE` -> `permit_type`; `WORK_CLASS` -> `work_type`;
  `PERMIT_STATUS` -> `raw_status`; `APPLICATION_DATE` -> `submitted_at`;
  `ISSUE_DATE` -> `issued_at`; `FINALED_DATE` -> `finaled_at`; `DESCRIPTION`
  and `PROJECT` -> `description` / `project_name`; `MAIN_PARCEL_NUMBER` ->
  `parcel_id`; `PERMIT_ADDRESS_LINE1`, `PERMIT_ADDRESS_LINE2`, `ZIPCODE` ->
  `site_address`; `MAIN_ZONE`, `DISTRICT`, `FLD_ZONE` -> jurisdiction context;
  `VALUATION`, `SQUARE_FEET`, and `TOTAL_FEE_AMOUNT` -> valuation, square feet,
  and fees. Evidence URL:
  `https://gis.charleston-sc.gov/arcgis2/rest/services/External/Applications/MapServer/20/query?where=OBJECTID=<id>&outFields=*&returnGeometry=false&f=json`.
- Charleston TRC mapping: `OBJECTID` -> `source_record_id`;
  `TRC_PLAN_NUMBER` -> `source_permit_id`; `PLAN_NUMBER`, `PLPLANID`, and
  `PRPROJECTID` -> alternate source IDs; `PLAN_TYPE` -> `permit_type`;
  `WORK_CLASS` -> `work_type`; `PLAN_STATUS` -> `raw_status`; `APPLY_DATE` ->
  `submitted_at`; `COMPLETE_DATE` -> `completed_at`; `DESCRIPTION` and
  `PROJECT` -> `description` / `project_name`; `MAIN_PARCEL_NUMBER` ->
  `parcel_id`; `MAIN_ADDRESS_LINE1`, `MAIN_ADDRESS_LINE2`,
  `PARCELADDR_LINE1`, and `PARCELADDR_LINE2` -> site address candidates;
  `VALUATION`, `SQUARE_FEET`, `TotalAcres`, `DisturbedAreaAcres`,
  `NumResUnits`, and `BuildingFootprintSqft` -> project metrics. Evidence URL:
  `https://gis.charleston-sc.gov/arcgis2/rest/services/External/Applications/MapServer/757/query?where=OBJECTID=<id>&outFields=*&returnGeometry=false&f=json`.
- Charleston filters: retain commercial/retail/development rows where permit
  or plan type, work class, project, description, zoning, valuation, square
  feet, acres, units, or keyed rooms indicates non-residential construction,
  tenant improvement, commercial alteration, sign work, subdivision, site plan,
  multifamily, hospitality, medical, grocery, restaurant, fuel, warehouse,
  industrial, or named chain/retailer activity. Suppress small residential,
  fence, roof, pool, generator, and repair-only records unless a chain/retailer
  name or commercial use is present.
- Greenville official source: City GIS Building Permits Hub and
  `https://citygis.greenvillesc.gov/arcgis/rest/services/InfoHUB/BuildingPermits_PriorTwoYears/MapServer/0`
  expose 3,697 prior-two-year permit rows with permit number, type, issue date,
  address, valuation, owner, contractor, and comments. HOLD because the layer is
  issued/closed only (`BP_STATUS` `IS` / `CL`), its hub child item is
  permission-gated, the license text is a no-warranty disclaimer rather than an
  affirmative commercial SaaS reuse/export grant, and no pre-approval lifecycle,
  update cursor, or deletion feed was verified.
- Columbia / Richland County: HOLD. Columbia's official Planning and
  Development pages route commercial and multifamily permits to a Tyler Access
  Portal or email intake; public Tyler routes are application-search backends,
  not documented bulk feeds. Columbia GIS content is map/zoning context with
  resale restrictions. Richland County eTRAKiT exposes permit/project/property
  workflows, but public access is portal/login oriented and no supported bulk
  API, commercial reuse grant, status-history export, update cursor, or deletion
  semantics were verified.
- Berkeley County: HOLD. Official permitting pages and builder portal confirm
  commercial construction, sign, PAC, and development-review applications, and
  county GIS exposes public ArcGIS folders including `energov` and Building
  Berkeley. The verified public services are capital-project, parcel, or map
  context rather than a licensed current permit/development filing feed with
  durable IDs, status history, evidence URLs, and commercial reuse/export
  rights.
- Statewide South Carolina: HOLD for municipal retail/development signals.
  SCDES ePermitting covers environmental regulatory workflows and SC.GOV
  hosts digital services, but no statewide official bulk/API feed was verified
  for municipal building permits, zoning permits, site plans, or development
  review applications.

### Mississippi Permit Sources

- Jackson's official OpenGov workflows contain strong pre-issuance and issued
  commercial evidence, including proposed use, work description, address,
  owner, applicant, contractor, cost, area, and documents. The raw `Active`
  status spans both application and issued states, so lifecycle must be derived
  from the document inventory rather than status alone.
- Public search is capped, protected against automated access, and exposes no
  authoritative total, supported export, modification watermark, or deletion
  feed. Numeric route IDs are useful retrieval locators but are not documented
  durable identities across migrations, merges, and amendments.
- Southaven moved to Tyler EnerGov in October 2024, but the public surface is
  login-oriented and no anonymous permit search API, bulk export, stable public
  record URL, lifecycle reconciliation contract, or commercial SaaS license was
  verified. DeSoto County monthly reports are document-center/aggregate
  evidence, not row-level application feeds.
- Gulfport, Biloxi, Hattiesburg, Tupelo, and Meridian publish relevant forms,
  site-plan/development workflows, or vendor portals, but no machine-readable
  case register with durable public IDs, status history, pagination/change
  semantics, and commercial reuse rights was found.
- MDEQ enSearch, EPD activity, enSite, NPDES, and MDMR coastal wetlands notices
  are high-value environmental/development early-warning candidates. They
  expose concepts such as permit applications received, NOIs, public notices,
  draft permits, issued coverages, facility/project names, counties, activity
  dates, and linked documents, but reviewed surfaces are dynamic pages, stale
  issued/compliance layers, geocoded facility enrichment, or HTML/PDF notices
  rather than supported complete permit lifecycles.
- Hinds County and state fallbacks provide portals, limited confirmation, and
  environmental data, not licensed complete permit lifecycles. MARIS parcel
  services are useful geospatial enrichment but not permit evidence.
- Decision: high-priority legal and technical hold. Unlock through official
  OpenGov/Jackson and MDEQ licensed API or export access and written commercial
  rights, with full workflow exports, durable IDs, timestamps, status/document
  history, deletion semantics, control totals, evidence URLs, and raw-document
  resale limits. Personal party data must be minimized downstream.

### Wyoming Permit Sources

- Cheyenne's official OpenGov system contains current pre-applications, site
  plans, changes of use, signs, tenant finishes, commercial building records,
  parties, proposed use, and evidence documents. Public search is sampled and
  capped without totals, export, or a supported API contract.
- Individual application statuses cannot be promoted directly to the parent
  project lifecycle: a linked administrative adjustment can be `Complete`
  while its site plan remains active. Native and legacy records also coexist
  after the 2025 building-system migration.
- Laramie County's SmartGov activity requires registration and offers only
  individual permit reports. State bulk layers cover mining or infrastructure,
  not a useful retail development lifecycle, and are unlicensed.
- Decision: legal, technical, and reconciliation hold. Unlock through licensed
  supported city/county exports with parent-child records, status history,
  authoritative control totals, tombstones, and identity crosswalks across
  migrated and legacy numbers. Do not build on undocumented portal internals.

### West Virginia Permit Sources

- Charleston's official Tyler portal exposes current submitted, review, fee,
  hold, issued, completed, void, and expired permit states with unique observed
  UUIDs/numbers, descriptions, addresses, parcels, values, contacts, and review
  evidence. Named retailers can appear before issuance.
- The visible set is small and appears tied to a recent ERP rollout. Planning
  class coverage is incomplete relative to historical city workload, project
  names are empty, and no authoritative totals, modification cursor, deletion
  feed, supported API, or full cutover history are documented.
- Status and dates can conflict; issued date is the approval boundary and raw
  status alone must not promote a record. Postal codes and zero floor areas also
  require validation and quarantine rules.
- Decision: legal-rights and completeness hold. Unlock through written city
  product rights plus a supported recurring export, backfill, data dictionary,
  durable identity guarantee, modification/deletion semantics, and control
  totals across every permit/plan class. County, Fire Marshal, and WVDEP sources
  remain separate rights or enrichment holds.

### Louisville / Jefferson County Construction And Planning Sources

- Official construction-permit source:
  `https://www.arcgis.com/home/item.html?id=0251a88cefdc4ab3a0d85943074e6d7b`
  with API layer
  `https://services1.arcgis.com/79kfd2K6fskCAkyg/arcgis/rest/services/active_construction_permits/FeatureServer/0`.
- Decision: narrow admit as a current issued/active construction-permit
  confirmation source for Louisville Metro / Jefferson County, not an
  early-warning pre-approval source.
- Scope: retain commercial construction-related rows from `PERMIT_TYPE`,
  including commercial alteration, commercial building, electrical commercial,
  fire suppression, mechanical, signs, wrecking, and similar non-residential
  permit classes. Exclude purely residential and non-development specialty rows
  unless separately admitted.
- Identity and evidence: use `ObjectId` as `source_record_id`; preserve
  `PERMIT_NUMBER` as `source_permit_id`. Evidence URLs should query the same
  layer with `where=ObjectId=<source_record_id>`, `outFields=*`,
  `returnGeometry=false`, and `f=json`.
- Field mapping: `PERMIT_NUMBER` -> `source_permit_id`; `ObjectId` ->
  `source_record_id`; `PERMIT_TYPE` -> `permit_type`; `WORK_TYPE` ->
  `work_type`; `CATEGORY_NAME` -> `proposed_use_or_occupancy`; `PERMIT_STATUS`
  -> `raw_status`; `ISSUE_DATE` -> `issued_at`; `ADDRESS`, `CITY`, `STATE`,
  and `ZIPCODE` -> `site_address`; `LATITUDE`/`LONGITUDE` -> coordinates;
  `ZONING`, `DISTRICT`, and `NEIGHBORHOOD` -> jurisdiction context;
  `PROJECT_COSTS` -> `valuation`; `SQFT` -> `square_feet`; `PERMIT_FEE` ->
  `fees`; `CONTRACTOR` -> `contractor_name` when nonblank.
- Lifecycle mapping: the live layer currently exposes only `Issued` statuses
  across 23k+ active rows, so all admitted rows map to approved/issued with
  `ISSUE_DATE` as the conservative approval boundary. The feed must not be used
  for submitted, intake, under-review, denied, withdrawn, or approved-to-issue
  stages unless Louisville later publishes those statuses in the same licensed
  bulk feed.
- Reliability: item metadata and sampled rows were current on July 17, 2026;
  the layer supports query/extract, pagination, order-by, JSON/GeoJSON/PBF, and
  no-geometry pages up to the service limits. Use daily `ObjectId` keyset pages
  or result-offset pages below 1000 records, plus periodic full snapshot
  reconciliation because no row-level modified timestamp or deletion cursor is
  published. Treat future-dated or blank `ISSUE_DATE` values as quarantine
  cases until confirmed.
- Planning and pre-approval hold: the official `Louisville Metro KY - PDS Case
  History` layer (`a4ecc829124c48cc970f3901b460faf3`) has useful case,
  project, address, processed, approved, cost, comment, and status fields, but
  its service data last edit is 2022 and no 2024+ processed records were
  observed. The Louisville Metro Business Portal / Accela ACA search exposes
  permits and Planning & Zoning applications, but no supported public bulk API,
  durable cursor, deletion semantics, or commercial extraction contract was
  verified for production ingestion.
- Rights: Louisville Metro's open-data terms publish datasets under ODC PDDL
  1.0, expressly allowing sharing, use, products/services, adaptation, and no
  copyright or attribution requirement. Preserve source/version/modification
  notice when republishing or incorporating the dataset into applications, and
  respect possible rate limiting and as-is/no-warranty terms.

### Provo Current Projects Building And Planning Applications

- Official ArcGIS service:
  `https://gispublicweb.provo.org/arcgis/rest/services/DevServ/CurrentProjects/MapServer`.
  Decision: admit as the Utah early-warning production source for Provo
  building permits and planning applications.
- Scope: use layer 1, `Building Permits`, for building-permit applications and
  layer 0, `Planning Application`, for planning/project-plan, subdivision, site
  plan, hearing, and public-notice context. Retain commercial and other
  retailer-relevant rows by building use/type/status and planning summary.
- Identity: use `OBJECTID` as the source row key for each layer and preserve
  `xxClient_BP_Applications_View_PermitNumber` or
  `xxClient_Planning_Application_View_PermitNumber` as the public permit or
  application number. Preserve planning `Record ID` as a secondary native ID.
- Lifecycle: building statuses include `Pending`, `Submittals Incomplete`,
  `In Plan Check`, `Returned for Correction`, `Ready for Issuance`,
  `Permit(s) Issued`, `Issued`, `Closed`, `Closed - Approved`, `Closed -
  Denied`, `Expired`, `Withdrawn`, `Canceled`, and `VOID`. Planning statuses
  include `Complete Application` with received, hearing, revision, appeal,
  expiration, closed, and last-modified dates. `Date Issued` is the
  conservative building approval boundary; planning applications remain
  pre-permit evidence unless closed/approved records are explicitly mapped.
- Field mapping: building name/project, type, building use, street address,
  zone land, unit count, valuation, contractor name, status, date entered,
  date issued, and date finalized are useful for retailer detection and
  lifecycle evidence. Planning application name, permit number, location,
  address, public notice summary, status description, received/date-entered,
  CRC printed, revisions received, hearing dates, appeal deadline, expiration,
  closed, and last-modified dates provide early site-plan and zoning context.
- Reliability: the official city Building page describes the map as current
  and past building permits updated weekly, and sampled rows on July 17, 2026
  included July 2026 `Pending` building permits and `Complete Application`
  planning records. The service supports JSON/GeoJSON/PBF query, pagination,
  order-by, statistics, and pages up to 5000 records. Use daily `OBJECTID`
  keyset or result-offset pages plus periodic full snapshot reconciliation
  because no deletion feed is published.
- Evidence URL: query layer 1 or layer 0 with
  `where=OBJECTID=<source_record_id>`, `outFields=*`,
  `returnGeometry=false`, and `f=json`.
- Rights: Provo's Transparency Portal links the City open data portal for the
  public to explore, download, and reuse publicly available datasets. Preserve
  City of Provo attribution, source URLs, and as-is context. Minimize or
  suppress personal contact data in downstream SaaS surfaces unless a separate
  legal review approves exposure.
- Utah holds: Salt Lake City Accela GIS layers are official and rich but the
  building layer sampled in July 2026 had max applied/opened dates in April
  2025 after the city's Accela cloud migration; Utah County's countywide
  building-permit map layer returned direct `401` metadata access; Greater Salt
  Lake Municipal Services District `e360_Data` is rich but sampled building
  dates were stale after 2022; Lehi and St. George expose application portals
  or searchable maps without a verified official bulk/API reuse contract; Utah
  DEQ/UDOT/statewide sources are environmental, right-of-way, or issued-only
  confirmation context rather than retailer building/planning early-warning
  sources.

### Maine DEP Land Applications And Permits

- Official ArcGIS table:
  `https://gis.maine.gov/mapservices/rest/services/dep/Land_Licensing/MapServer/6`.
  Decision: narrow admit as a statewide Maine environmental/development
  early-warning source, not a municipal building-permit replacement.
- Scope: land licensing, Site Law, NRPA, stormwater, PBR/MCGP, and related DEP
  application/permit records. Use for retailer-relevant site-development,
  subdivision, stormwater, shoreland, and environmental approval context where
  applicant/project text supports matching.
- Identity: use `GIS_OBJECTID` plus `ATS_NUMBER` as the durable source record
  identity. Retain `OBJECTID` as transport metadata and `LICENSE_NUMBER` as
  downstream license evidence when present.
- Lifecycle: received, in process, locked for review, action required,
  returned/incomplete/deficient, completed, implicitly accepted, denied,
  cancelled, and withdrawn states are retained. `ACCEPTED_DATE` is acceptance
  into DEP review; `CONCLUSION_DATE` is the conservative completion/approval or
  terminal-decision boundary.
- Context: town, applicant name, project description, waterbody, tax map, tax
  lot, ATS number, license number, received date, accepted date, conclusion
  date, and status. The source is strong for developer/applicant and project
  narrative evidence but weak for exact site address, tenant, contractor, and
  local zoning context.
- Reliability: the DEP public page says the table is real-time, reflects the
  prior three years, includes recently entered pending applications, and
  includes agency action dates. A July 17, 2026 check found July 2026 received
  and in-process records. The ArcGIS table supports JSON/PBF, pagination,
  order-by, statistics, distinct values, and 12,000-row pages. Use daily
  received-date windows plus periodic full snapshot reconciliation because no
  deletion or row-modified cursor is published.
- Evidence URL: query layer `6` with
  `where=GIS_OBJECTID='<source_record_id>'` and/or
  `ATS_NUMBER='<source_application_id>'`, `outFields=*`,
  `returnGeometry=false`, and `f=json`.
- Rights: Maine DEP publishes the table through official Maine GIS
  infrastructure. Maine GeoLibrary statute prohibits the board or data
  custodians from fixing copyright or licensing restrictions on information
  made available through the GeoLibrary, while Maine.gov and DEP pages carry
  as-is/no-warranty and accuracy/timeliness disclaimers. Preserve attribution
  to Maine DEP, source URLs, retrieval timestamps, and no-endorsement/as-is
  notices; do not expose confidential application materials not present in the
  public table.

### Louisiana Permit Sources

- Decision: admit East Baton Rouge Building Permits as approved-only
  commercial confirmation coverage.
- Production source: `east_baton_rouge_la_building_permits`. East Baton Rouge
  Parish publishes the Building Permits dataset through the official
  `data.brla.gov` open-data portal with Public Domain metadata and Permits and
  Inspections attribution. The dataset is described as all construction and
  occupancy permits issued in East Baton Rouge Parish.
- Official endpoint:
  `https://data.brla.gov/resource/7fq7-8j7r.json`.
- Lifecycle handling: all production rows are treated as approved because the
  source is issued/occupancy permits and includes populated issued dates.
  `creationdate` is retained as filed/opened evidence, and `issueddate` is the
  approval/issuance confirmation boundary. This source must not be counted as
  pre-approval coverage.
- Admitted fields: permit ID, permit number, permit type, commercial
  designation, project description, square footage, valuation, creation/issued
  dates, address, city/state/ZIP, parish, owner, applicant, contractor,
  latitude, and longitude.
- Suppression policy: contractor address, permit fee, lot number, subdivision,
  and raw source export are excluded from the production catalog. Residential
  records are excluded from the first slice.
- Product note: live validation in July 2026 found current commercial permits
  issued through July 17, 2026 with owner, applicant, contractor, valuation,
  address, and coordinate context. Use this to confirm downstream activity and
  enrich relationship evidence around New Orleans/Louisiana opportunities, not
  to flag pre-approval retailer movement.

### Washington Permit And Development Sources

- Seattle SDCI building permits remain admitted through the existing
  `seattle_wa_issued_building_permits` source key, which now points at the
  inclusive daily building-permit dataset rather than an issued-only surface.
  Application dates without issue dates are treated as pre-approval/review
  context; issued, completed, closed, and related terminal post-approval states
  remain confirmation context.
- Seattle SDOT street-use public notices are admitted as
  `seattle_wa_street_use_public_notices`. They expose application number,
  application type, address, business, public-comment window, size, and point
  location under Seattle public-domain terms. Treat them as narrow
  public-comment/pre-decision evidence for curb, cafe, street-use, and
  public-space signals, not as a general building-permit feed.
- Washington Ecology SEPA Register is admitted as
  `washington_ecology_sepa_register` for statewide environmental pre-approval
  context. It exposes SEPA register ID, SEPA number, proposal/project text,
  lead agency, lead-agency file number, site address/city/ZIP/parcel,
  coordinates, document type, county/region, publish/issue dates, and evidence
  links. Suppress lead-agency contact names/emails/phones, applicant contact
  blocks, raw document bodies, sensitive site locations, and raw document
  resale because dataset metadata lists no formal license and document-level
  restrictions may vary.
- Pierce County PALS permits are admitted as
  `pierce_county_wa_pals_permits` for unincorporated county permit/development
  context. The public layer exposes application number, type, status, parcel,
  work/building/housing types, area, valuation, department, application,
  submittal, approval, issued, and final dates, address, project name,
  description, online permit URL, and point geometry. Use `OBJECTID` only as a
  transport cursor and `applicationNumber` as source identity. `Accepted`,
  `Hold`, `Pending Payment`, suspended/stopped states, and other non-approved
  rows remain `pre_approval`; approval/issued/final/closed statuses or dates
  map to `approved`.
- Pierce County rights controls: preserve county attribution, no-endorsement
  and no-warranty notices, link the terms of use, and avoid raw bulk resale or
  unrestricted API passthrough. Utility fields, raw coordinate fields, and raw
  application documents are suppressed from the production catalog.
- Bellingham non-residential building permits are admitted as
  `bellingham_wa_nonres_building_permits` from the official Development
  Dashboard backing `Permits/MapServer/0` layer. The dashboard describes
  non-residential permits in application, under construction/issued, and
  finaled status, and the backing layer exposes permit number, class/category,
  application/approval/issue/final/expiration dates, status, site address,
  public description, job value, floor area, parcel APN, zoning, dashboard
  lifecycle bucket, and point location.
- Bellingham lifecycle handling: `New Construction Applied not yet Issued (in
  last year)` maps to pre-approval because it includes `IN REVIEW` and
  `REQUEST FOR INFO` non-residential building work before issuance. `New
  Construction Issued not yet Finaled` and `New Construction Finaled Last 6
  months`, or populated issue/final dates, map to approved/confirmation.
- Bellingham suppression and rights controls: owner, applicant, contractor,
  owner-mailing, fee, census/code, raw geometry export, and raw source export
  fields are not fetched in the first production slice. The City of Bellingham
  metadata provides Planning and Community Development attribution and
  no-warranty/user-risk terms, not a broad raw resale license, so production
  use is limited to attributed value-added permit intelligence with source
  currentness checks and no raw source-replacement export.
- Washington State LCB Local Authority Letters are admitted as statewide
  pre-opening context for restaurants, grocery, liquor, and cannabis operators.
  The official Data.WA dataset `vgcw-qfjm` is published by the
  Washington State Liquor and Cannabis Board with Public Domain metadata and
  fields such as license, UBI, application date, local-authority posted date,
  application type, licensee/trade name, address, city, county, ZIP, and
  privilege descriptions. Treat new license applications, location changes,
  and added privileges as pre-opening/opening-intent context. A privacy-limited
  5-row canary passed on August 1, 2026, followed by successful production
  ingestion. The publisher exposes a changing current-letter window, so ingest
  it as a daily rolling-window incremental source: retain prior filings and
  evidence when they age out rather than interpreting disappearance as a
  withdrawal. A live scheduled test on August 2 fetched 20 current rows and
  proved that full-snapshot retirement would incorrectly retire 45.9% of the
  previously observed records. Suppress
  designated-signee, applicant birth-date text, phone, mailing, and other
  contact-like fields; keep this separate from building-permit coverage. The
  reviewed definition is checked into the production catalog with 500-row
  pages, so clean deployments recreate the source without manual promotion.
- Everett Planning Application Notices are admitted from the City's official
  Planning Public Notices RSS feed. Only `Notice of Application` and `Notice of
  Application and Public Hearing` items are retained as pre-approval evidence;
  legislative public hearings and director interpretations are filtered out.
  The August 1, 2026 canary fetched five notices, accepted two project
  applications, skipped three unrelated announcements, and had zero failures.
  The first production run inserted both accepted applications, including a
  Verizon Wireless tower proposal, and projected evidence-backed permit,
  property, and city relationships into the graph. The reviewed definition is
  checked into the production catalog with 100-item reads, so clean deployments
  recreate the source and its seven mappings without manual promotion.
- Everett RSS controls: use the stable feed GUID as source identity and retain
  only title, official link, publication timestamp, and short RSS description.
  Do not fetch enclosures, linked PDF bodies, applicant/planner contacts, or
  raw document exports. Feed entries may age out, so use stable upserts and do
  not interpret disappearance from the recent RSS window as project withdrawal.
  The generic RSS connector can be reused for other official CivicPlus notice
  feeds, but each category still requires lifecycle filters and rights review.
- San Marcos, Texas Planning Application Notices moved from a freshness hold to
  a runnable no-write candidate on August 14, 2026. Its legacy CivicPlus RSS
  category remains empty, but the official NewsFlash archive published fresh
  applications on August 10-12 with stable article IDs, canonical links,
  posted dates, and project summaries. A generic archive connector now reads
  only that bounded current window and suppresses email addresses and phone
  numbers before emitting records. It does not follow detail pages or linked
  documents. A 10-record no-write canary passed with 10 valid pre-approval
  records and zero failures. The Build Signals owner approved the bounded,
  contact-suppressed scope, so San Marcos is now a daily production source.
  Taylor's Development Notices
  feed resumed and published PZ 2026-2715
  on August 7, and its bounded August 14 canary validated one pre-approval row
  with zero errors. The Build Signals owner approved the minimized production
  scope, so Taylor is now a daily production source retaining stable GUID,
  title, publication time, extracted PZ case number, short RSS description,
  and official link only. It does not fetch linked documents, contacts,
  enclosures, or raw replacement exports.
- Bellevue, Tacoma, and Spokane expose technically strong pre-approval permit
  or permit-activity layers, but remain rights holds. Bellevue explicitly
  prohibits commercial use or sale without written authorization; Tacoma and
  Spokane need written confirmation covering paid storage, display, API access,
  exports, and raw resale limits.
- Spokane near-miss detail: the official Permit Activity Map layer at
  `https://services.spokanegis.org/arcgis/rest/services/Permit/Permit_WM_Dynamic2/MapServer/0`
  exposes building/planning/engineering permit activity with `SpokanePermitID`,
  `PermitModule`, `PermitType`, `OpenDate`, `Status`, `MapStatus`,
  `ParcelNumber`, `FullAddress2`, `DetailShortNotes`, `SearchText`,
  `LastUpdate`, and geometry. If rights are unlocked, use `MapStatus = 'In
  Review'` as pre-approval and `MapStatus = 'Issued'` as approved while
  preserving exact `Status` values such as `Pending`, `Plan Review`, and
  `Paid`. Live July 2026 rows included `B2610714BLDC`, opened July 14, 2026,
  with `Pending` status and `Starbucks Coffee Co COU/TI` at `322 N SPOKANE
  FALLS CT`.
- Spokane suppression and pitfalls: suppress planner/permit-manager names and
  emails, raw `SearchText` exports, and raw feed replacement downloads.
  `DateRange` is a relative bucket rather than a durable cursor, and
  `DetailShortNotes` may truncate evidence. The blocker is rights: Spokane's
  GIS pages make datasets available free of charge, but city website terms
  limit downloading to personal non-commercial use and prohibit scraping or
  reposting without written permission.
- King County public notices, Snohomish County PDS, and Vancouver WA remain
  structured-source holds. Public notices/reports are valuable evidence but are
  HTML/PDF or aggregate/report surfaces rather than complete bulk/API feeds with
  durable application identity, status history, and reconciliation semantics.

### Bend, Oregon Planning And Permit Applications

- Bend Planning Applications, Permit Applications Point, and Permit
  Applications Line are approved production sources as of August 2, 2026.
  Final lifecycle canaries validated 30 rows per source with zero failures and
  explicitly observed both pre-approval and approved records.
- Planning approval is derived from `DecisionDate`; permit approval is derived
  from `IssueDate`. Exact publisher statuses remain canonical evidence rather
  than being collapsed into the lifecycle stage.
- Production retains application identity, dates, project/use descriptions,
  address, tax lot, public owner, valuation, size, units, and licensed geometry
  where the layer supports it. The line layer rejects centroid requests, so it
  carries address/tax-lot corridor context without invented coordinates.
- City of Bend attribution and source links are required. Editor/planner fields,
  global IDs, raw geometry export, and raw source-replacement export are
  suppressed. Build Signals approved commercial storage, analysis, and
  customer-facing derived intelligence under these controls.
- The official layers contain 21,079 planning rows, 164,858 point-permit rows,
  and 403 line-permit rows at activation. Backfills are bounded and resumable;
  source leases, snapshot checkpoints, health SLAs, and retirement guards stay
  active throughout reconciliation.

## Operating Rule

Held sources may have draft mappings outside the production catalog, but must
not be synchronized as active ingestion sources. Re-evaluate a hold only with
new official metadata, written permission, or a replacement official dataset.
