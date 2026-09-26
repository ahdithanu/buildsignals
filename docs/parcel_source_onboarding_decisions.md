# Parcel Source Onboarding Decisions

This ledger applies the same admission standard as permit ingestion: official
provenance, structured bulk access, stable identity, complete reconciliation,
current evidence, and affirmative commercial reuse and redistribution rights.
Public visibility alone is not sufficient.

## Alaska Statewide DNR Parcel Composite

**Decision: admitted narrowly for attributed derived parcel context.**

- Production source: `alaska_dnr_statewide_parcels_narrow`.
- Alaska DNR publishes the statewide composite for statewide applications and
  permits public use with source attribution and disclosure of modifications.
- `GlobalID` is canonical source identity and `OBJECTID` is the keyset cursor.
  The production slice retains contributing local government, generalized use,
  processing date, and polygon-derived proximity.
- Owner, alternate owner, mailing, land/building/total value, sale, raw source
  file, and raw geometry replacement exports are excluded.
- A bounded no-write canary normalized 5 of 5 live records with zero failures.
  This connector supplies parcel context, not statewide permit coverage.

Evidence: `https://www.arcgis.com/home/item.html?id=458be3d8aafa47cd882af05cee983f6b`.

## Hawaii Statewide TMK Parcels

**Decision: admitted narrowly under the state public-domain designation.**

- Production source: `hawaii_statewide_tmk_parcels_narrow`.
- `tmk_txt` is canonical source identity and `objectid` is the keyset cursor.
  The production slice retains county/island divisions, TMK grouping, GIS
  acreage, county evidence link, and polygon-derived proximity.
- Owner, mailing, assessed/land/improvement value, sale, legal description, raw
  source file, and raw geometry replacement exports are excluded.
- A bounded no-write canary normalized 5 of 5 live records with zero failures.
  County vintages vary and parcel geometry is not a legal survey boundary.

Evidence: `https://www.arcgis.com/home/item.html?id=579b8dcb7a8e44c1af201e1b3cdf655f`.

## Idaho ITS Participating-County Parcel Framework

**Decision: admitted narrowly for participating counties.**

- Production source: `idaho_its_statewide_parcels_narrow`.
- `FP_ID` is canonical source identity, `PARCEL_ID` is the parcel grouping, and
  `OBJECTID` is the keyset cursor. The production slice retains steward/county,
  extract date, acreage, generalized assessment category, and geometry.
- Mailing-list fields, owner, legal description, values, exemptions, sales, raw
  source files, and raw geometry replacement exports are excluded.
- A bounded no-write canary normalized 5 of 5 live records with zero failures.
  Participating-county coverage must not be represented as all 44 counties.

Evidence: `https://www.arcgis.com/home/item.html?id=65a3f7c6d4ca404ba6ab677913953b35`.

## New York City, New York

**Decision: admitted to production.**

- DCP PLUTO 26v1 is the authoritative monthly attribute snapshot. The
  production Socrata slice contains 858,602 unique BBL records with near-total
  owner, lot-area, assessed-value, building-area, and coordinate coverage.
- Canonical identity is the zero-padded ten-character `BBL`. Preserve borough,
  block, lot, release version, and raw evidence because mergers, subdivisions,
  condos, air lots, and billing-lot changes can replace that identity over time.
- Prefer DCP's supplied latitude and longitude. For the small point-missing
  population, use `ST_PointOnSurface` from the matching MapPLUTO polygon; do not
  discard PLUTO-only records. MapPLUTO and the DOF digital tax map remain
  supplemental geometry sources rather than competing parcel identities.
- Poll monthly and run a guarded full snapshot. Retain release version, raw
  export checksum, row count, schema fingerprint, and an independent diff;
  tombstone a BBL only after a complete successor snapshot validates.
- Commercial reuse and redistribution pass under NYC Administrative Code
  section 23-502(d) and the official Open Data policy. Attribute NYC DCP, retain
  the City disclaimer, and treat `OwnerName` as assessment evidence rather than
  verified title or beneficial ownership.

Production source: `new_york_ny_pluto_parcels`. Primary dataset:
`https://data.cityofnewyork.us/d/64uk-42ks`.

## Denver / Denver County, Colorado

**Decision: admitted to production.**

- Denver Assessment Division's parcel FeatureServer has 240,353 live polygons,
  a unique populated `SCHEDNUM` for every row, 99.18% owner coverage, 99.77%
  land-area coverage, 99.19% appraised-value coverage, and effectively complete
  use descriptions.
- Use `SCHEDNUM` as durable snapshot identity; `OBJECTID` is only the pagination
  cursor. Request output in EPSG:4326 and preserve the server-computed parcel
  centroid as the nearby-search point. Polygon point-on-surface and exact
  boundary distance are the future production geometry path.
- Run daily guarded full snapshots in deterministic 2,000-row keyset pages.
  Stop on duplicate/null schedule numbers or geometry failures, warn below the
  audited coverage floors, and retire a parcel only after a validated complete
  snapshot. Preserve split/merge lineage instead of transferring old IDs.
- The exact dataset is marked `PUBLIC_DOMAIN` and official in Colorado's data
  catalog. Archive that rights record with Denver's ArcGIS item metadata and
  recheck quarterly because the ArcGIS item itself contains disclaimers rather
  than the affirmative grant.
- Values are assessor appraisals, not current market estimates. Owner records
  remain public-record evidence and require downstream privacy and suppression
  controls.

Production source: `denver_co_assessor_parcels`. Rights evidence:
`https://data.colorado.gov/Government/Denver-Parcels/tsdg-z9uy`.

## Colorado Statewide Public Parcel Composite

**Decision: admitted narrowly to production for derived Phase 2 nearby-parcel
context.**

- Colorado's Governor's Office of Information Technology GIS Team publishes the
  statewide public parcel composite from county, regional, and local government
  sources. The July 18, 2026 scout count returned 2,599,760 rows.
- Canonical identity is `countyFips:parcel_id` because parcel IDs are not
  guaranteed unique statewide. `OBJECTID` is transport-only. Rows without
  `parcel_id` or `countyFips` are excluded from the production slice.
- Use polygon-derived centroids for radius search and parcel adjacency
  discovery. The source is an annual or irregular composite, so run guarded full
  snapshots, enforce low retirement fractions, and expect heterogeneous county
  quality and missing fields.
- The state open-data posture supports use, modification, and sharing with
  disclaimers, but the parcel service notice says resale of this data is
  strictly forbidden. Production use is therefore limited to derived proximity
  context and customer-facing intelligence, not raw parcel replacement exports.
- Suppressed fields include owner names, owner mailing fields, legal
  descriptions, sale dates/prices, assessed/appraised values, raw polygon
  export, shape metrics, and raw source export.
- The admitted slice keeps county, statewide parcel identity, situs address and
  city/ZIP, acreage-derived land area, generalized land-use/zoning context,
  source URL, update date, and derived centroid.
- Live canary on July 18, 2026 fetched 35 rows with 35 valid, 0 failed, and 35
  `parcel_snapshot` records.

Production source: `colorado_statewide_public_parcels_nearby_narrow`.
Endpoint:
`https://gis.colorado.gov/public/rest/services/Address_and_Parcel/Colorado_Public_Parcels/FeatureServer/0`.

## New Jersey NJGIN Statewide Parcels Joined With MOD-IV

**Decision: admitted narrowly to production for derived Phase 2 nearby-parcel
context.**

- NJGIN publishes the official statewide parcels joined with MOD-IV through the
  Framework/Cadastral MapServer and NJGIN parcel landing page. Hosted parcels
  and tax-list products redact owner names under Daniel's Law.
- Canonical identity is `PIN_NODUP`, with `PAMS_PIN` and `PCL_GUID` retained as
  grouping/evidence context where useful. Placeholder/null IDs such as `XXXNLL`
  are excluded. `OBJECTID` remains the transport cursor only.
- Use polygon-derived centroids for nearby-parcel radius search and adjacency
  discovery. NJGIN explicitly warns that parcels are not legal boundaries or
  survey data; use them for planning/proximity intelligence, not title or legal
  ownership determinations.
- Rights posture is narrow but workable: NJGIN is an official state geospatial
  sharing network, the parcel page provides streaming/download access, metadata
  lists no access constraints, and use constraints are attribution plus
  currentness/accuracy/non-survey disclaimers. Preserve those notices and avoid
  raw source-replacement exports.
- Suppressed fields include owner name, land/improvement/net values, taxes,
  deed book/page/date, sale code/price, GIS/old IDs that could bypass
  redaction policy, shape metrics, raw polygon export, and raw source export.
- The admitted slice keeps PAMS/PIN identity, municipality/county, property
  class, situs address, ZIP, land-description text, acreage-derived land area,
  publication/update dates, GUID, and derived centroid.
- Live canary on July 18, 2026 fetched 35 rows with 35 valid, 0 failed, and 35
  `parcel_snapshot` records.

Production source: `new_jersey_njgin_statewide_parcels_nearby_narrow`.
Endpoint:
`https://maps.nj.gov/arcgis/rest/services/Framework/Cadastral/MapServer/0`.

## Maryland Statewide iMAP / SDAT Parcel Points

**Decision: admitted narrowly to production.**

- The official MD iMAP / Maryland Property Data Parcel Points layer exposes
  statewide point records with stable jurisdiction/account IDs, situs address,
  owner-mailing address, zoning/use, structure area, assessed values, transfer
  date/consideration, publication dates, and SDAT detail links.
- Canonical identity is `JURSCODE:ACCTID`, not `ACCTID` alone, because SDAT
  account numbers can be meaningful only within the local jurisdiction/county
  coding context. `OBJECTID` remains the ArcGIS pagination cursor.
- Use the publisher point geometry for Phase 2 radius search. Parcel-boundary
  polygons from the companion layer can later enrich map rendering and exact
  boundary-distance calculations without replacing the point source identity.
- Rights pass under Maryland Open Data Public Domain metadata for parcel
  points, with metadata preservation and State acknowledgment for derived data.
  The owner-name asset is explicitly held because Maryland notes a separate
  user license agreement for owner-name access.
- Suppress legal descriptions, deed/liber/folio fields, plat fields, raw parcel
  replacement exports, and bulk geometry resale. Values are assessment evidence,
  not market value or title evidence; sale consideration can be sparse and must
  be treated as source-reported public-record context.
- July 18, 2026 live checks observed 2,396,022 parcel/account points and
  `SDATDATE=2026MAY` in the scout sample/count pass.

Production source: `maryland_imap_sdat_parcel_points`. Primary layer:
`https://mdgeodata.md.gov/imap/rest/services/PlanningCadastre/MD_PropertyData/MapServer/0`.

## Massachusetts Statewide MassGIS Level 3 Property Tax Parcels

**Decision: admitted narrowly to production.**

- MassGIS Level 3 property tax parcels cover all 351 Massachusetts
  municipalities and join assessor parcel polygons to assessor records in a
  statewide FeatureServer.
- Canonical row identity is `GlobalID`; the physical parcel grouping key is
  `TOWN_ID:MAP_PAR_ID` because parcel IDs are safest when scoped by
  municipality and can repeat across multiple source polygons. `OBJECTID`
  remains the ArcGIS pagination cursor.
- Use publisher-computed centroids for the first Phase 2 radius-search slice.
  Do not expose raw polygon bulk output as a source replacement; recorded deeds
  and surveys remain authoritative boundary evidence.
- Rights pass under MassGIS public-domain language: MassGIS says public GIS data
  can be used by anyone for any purpose, with requested source credit to MassGIS
  / Commonwealth of Massachusetts EOTSS.
- Suppress owner mailing address fields, deed/book/page fields, registry fields,
  source/survey/boundary-check metadata, raw geometry, and raw polygon export.
  Owner names are retained only as public-record assessor context with source
  attribution and retrieval date.
- Values, zoning, lot size, and sale facts must be shown with fiscal year/source
  context and must not be presented as current market value, title evidence, or
  survey evidence.

Production source: `massachusetts_massgis_l3_property_tax_parcels`. Primary
layer:
`https://services1.arcgis.com/hGdibHYSPO59RG1h/arcgis/rest/services/Massachusetts_Property_Tax_Parcels/FeatureServer/0`.

## Portland / Multnomah County, Oregon

**Decision: ownership-evidence hold.**

- Metro RLIS is a strong quarterly geometry/value spine with 282,974 unique
  Multnomah `TLID` records, complete area/value/generalized-use coverage, and an
  open commercial license requiring attribution.
- The open dataset intentionally omits owner names and addresses. The paid
  ownership dataset prohibits transferring source data and revealing individual
  owner names to third parties, so it cannot support the customer-facing owner
  evidence required by this phase.
- `LANDUSE` and `PROP_CODE` are generalized and must not be presented as
  parcel-specific determinations. `TLID` is the snapshot identity;
  `PRIMACCNUM` and `ORTAXLOT` are not unique, and multi-account rows require a
  child-record model.

Admit only as a supplemental geometry/value spine after a separately licensed,
redistributable owner source is approved, or after written Metro/Multnomah
permission covers customer display and redistribution.

## Chicago / Cook County, Illinois

**Decision: redistribution-rights hold.**

- The official current parcel universe is technically excellent: 1,863,530
  unique PIN14 records, 99.934% coordinate coverage, and 99.994% owner-name
  coverage, with companion assessed-value, improvement, commercial-use, address,
  and PIN10 polygon datasets.
- Use zero-padded PIN14 plus tax year for assessor facts and PIN10 for base-parcel
  geometry. Condo/unit ownership records must not be collapsed into the shared
  PIN10 polygon; discovery should group or exclude the target PIN10 to avoid
  zero-distance unit floods.
- County GIS rules allow commercial use of open GIS data combined with other
  data, but the assessor feeds lack an explicit redistribution license. The
  assessor commercial agreement also prohibits publishing, distributing,
  sublicensing, or deriving another database from its database.

Admission requires written Cook County and CCAO confirmation that the current
universe, address, value, improvement, commercial, and geometry feeds may be
stored, enriched, displayed to customers, and redistributed commercially.

## San Francisco, California

**Decision: ownership and sale-evidence hold.**

- DataSF's active/retired parcel layer and historical secured property-tax roll
  pass official provenance, structured SODA access, freshness, identity,
  geometry, assessment, and commercial redistribution gates under PDDL.
- Join parcel `blklot` to roll `parcel_number` as text, preserving leading zeroes
  and suffixes. Use `mapblklot` as the physical-site group because condominium
  APNs can share one footprint. The active layer contains 226,877 APNs across
  155,110 physical sites, with 99.89% polygon/centroid coverage.
- The certified roll has complete use and land/improvement assessment values,
  but no owner person/entity name or mailing address. It has a last-sale date,
  but no consideration, document identifier, grantor/grantee, or transaction
  history. `percent_of_ownership` is not owner identity.
- Daily parcel snapshots may later serve as a geometry/lifecycle spine. Use
  polygon distance and `ST_PointOnSurface`; reconcile active secured APNs to the
  latest annual certified roll and preserve non-secured classifications.

Admit only after an official structured owner and sale-evidence source passes
commercial reuse and redistribution review, or after Phase 2 is explicitly
narrowed to geometry, situs, assessment, characteristics, and last-sale date.
Do not fill the gap by scraping assessor or recorder websites.

## Los Angeles County, California

**Decision: owner/data-sales rights hold.**

- The official LA County Assessor parcel services are technically useful but
  incomplete for customer-facing nearby parcel discovery. The countywide parcel
  FeatureServer exposes AIN/APN, situs, use, building characteristics, roll
  year, roll land/improvement values, legal description, centroid fields, and
  polygon geometry, with 2,000-row ArcGIS pages and centroid-return support.
- The public Assessor PAIS sales layer exposes AIN, formatted AIN, situs,
  sale date, sale price, size, bedrooms, bathrooms, year built, use code/type,
  and polygon geometry, but it is a recent-sales display layer, not a complete
  sale-history feed. The Assessor help page says public recent sales are
  unverified single-parcel sales, refreshed weekly, and limited to 24 months.
- Owner data fails the open-source gate. The Assessor states owner information
  is available in person or through Property Data Sales, but is not provided on
  the public website because of privacy laws. The owner-bearing DS04/Secured
  Basic File Abstract appears to be a paid data-sales product, and no reviewed
  public terms affirm commercial SaaS storage, customer display/API output,
  redistribution, derived databases, retention, or sublicensing.
- The annual parcel display, weekly detail updates, and weekly recent-sales
  refresh are operationally workable only after a licensed bulk source is
  approved. Scraping the public portal is not an acceptable substitute for a
  bulk/data-sales agreement.
- City of Los Angeles parcel and APN datasets are useful CC0 supplements inside
  city limits, but they are not countywide assessor owner/value/sale sources and
  cannot carry Los Angeles County admission.

Admit only after LA County Assessor Property Data Sales or County Counsel
confirms written rights for the Secured Basic File Abstract/DS04 and parcel
geometry covering commercial storage, derived nearby results, customer display
and export, redistribution/API output, refresh cadence, retention, and privacy
suppression requirements. If admitted, use `AIN` as canonical tax identity,
preserve formatted `APN` for display, group condominium/shared-footprint records
by geometry/centroid plus situs unit, retain each AIN as a separate tax/owner
fact, use county polygons/centroids for distance, and treat public PAIS recent
sales as supplemental unverified sale evidence only.

## San Diego County, California

**Decision: narrow geometry/situs admit; owner, value, and sale hold.**

- San Diego County's rich assessor FeatureServer is the strongest technical
  candidate. It exposes APN, parcel ID, owner names, owner mailing address,
  situs, land use, zoning, land/improvement/total assessed values, acreage,
  living area, coordinates, document type/number/date fields, and polygon
  geometry.
- The official SanGIS/SANDAG public parcel layer is an admissible
  geometry/situs spine for nearby parcel discovery when ingested with a
  field-level allowlist only. Use APN, APN_8, PARCELID, situs components,
  acreage, land-use/zoning approximation fields, coordinates, and polygon
  geometry. Suppress assessed-value, owner-occupancy, document, transfer,
  sale-like, and residential-characteristic fields from customer display,
  API output, and exports until written rights are approved.
- The SanGIS/SANDAG parcel metadata documents stacked condominium,
  possessory-interest, and mobile-home parcel patterns that must remain
  separate tax identities.
- Use APN as canonical tax identity and `PARCELID` as secondary geometry
  identity. A physical group can be derived from identical geometry, area, and
  centroid for stacked records, but every APN must retain independent owner,
  value, and raw-evidence history.
- Sale evidence is not production-ready. County and SanGIS document fields are
  transfer indicators, not complete sale events with consideration or verified
  arms-length status, and the recorder index does not expose a stable
  parcel-linked bulk sale feed.
- City of San Diego PDDL datasets are useful supplements for APN-address,
  zoning, city-owned parcels, and city boundary clipping, but they are not an
  assessor owner/value/sale source.
- Rights pass only the narrowed geometry/situs discovery gate. SANDAG says the
  public Regional GIS Data Warehouse layers are free to download after
  accepting the disclaimer, and SanGIS discourages but does not prohibit
  redistribution of released public GIS data with attribution/disclaimer
  expectations. This is not enough for owner, assessed-value, document,
  transfer, sale, unrestricted customer export, or source-data redistribution
  admission. The richer County assessor API remains excluded absent an
  affirmative commercial redistribution grant and bulk cadence.

Admission is limited to internal storage and customer display of derived
nearby-parcel geometry/situs facts with SanGIS/SANDAG attribution and no raw
source-data export. Broader admission requires written County/SANDAG/SanGIS
permission for value/document/transfer fields, unrestricted customer
display/API output, source redistribution, snapshot retention beyond internal
audit needs, and any lawful owner-bearing source.

## Santa Clara County, California

**Decision: assessor-rights and owner/value/sale hold.**

- The County GIS/Open Data parcel layer is a useful geometry and situs-address
  supplement. It publishes FY2025 land and air/condominium parcel polygons with
  `APN`, tax-rate area, situs address/unit/city/state/ZIP, situs-address count,
  area, length, ArcGIS/Socrata API access, GeoJSON/JSON/PBF output, and
  5,000-row ArcGIS pages. It does not include owner, assessed value, sale, deed,
  land-use, or improvement facts.
- The Assessor is the authoritative source for those missing attributes, but
  bulk access is a paid/order-form process rather than an open feed. The order
  page lists assessment-data products including the property characteristic
  file, Secured Master File with or without use codes, Property Situs File,
  Legal Description File, key-change files, subdivision tract, Record of Survey
  file, and Parcel Control Index.
- Preserve `APN` as canonical tax identity and treat `OBJECTID` only as a page
  cursor. Keep air/condominium polygons and situs unit fields as separate tax
  identities, deriving a physical parcel group only from shared/parent geometry
  and address evidence after assessor-file samples validate the relationship.
- Refresh can use the annual August GIS parcel release for geometry, plus
  guarded full snapshots of any licensed assessor files with schema
  fingerprints, duplicate/null APN checks, and explicit key-change handling.
- Rights fail the production gate today. County GIS pages provide warranty
  disclaimers and general public-domain website language, while the parcel
  service item says all rights reserved; the paid assessor data pages do not
  affirm commercial SaaS storage, derived nearby-parcel scoring, customer
  display/export/API output, redistribution, sublicensing, retention, refresh
  cadence, privacy suppression, or termination rights.

Admission requires a signed Santa Clara County Assessor/GIS agreement or
written County authorization covering the exact assessor bulk files and parcel
geometry for commercial storage, derived nearby results, customer display/API
output, redistribution/export, historical retention, refresh cadence, fees,
attribution, and privacy/suppression requirements.

## Boston / Suffolk County, Massachusetts

**Decision: rights and freshness hold.**

- Boston's current parcel and FY2026 assessor services are technically strong,
  but the City data license permits internal business use while prohibiting sale,
  distribution, marketing, export, or transfer. That fails customer-facing
  commercial redistribution.
- MassGIS provides structured statewide parcel and assessor layers under
  affirmative public-domain terms that allow commercial use and resale. However,
  its Boston assessment population is still FY2023, while Chelsea, Revere, and
  Winthrop are FY2026. The Boston vintage fails the freshness gate.
- The future MassGIS model should separate physical identity `(TOWN_ID, LOC_ID)`
  from assessment identity `(TOWN_ID, PROP_ID)` because condo assessments can
  share one polygon. Preserve owner, site, use, value, improvements, sale
  document, fiscal year, and registry evidence independently.
- Compute `ST_PointOnSurface` from EPSG:26986 polygons, return one nearby result
  per physical parcel, aggregate condo assessment records explicitly, poll
  monthly, reject vintage regressions, and retain identity/geometry tombstones.

Admit when MassGIS publishes a current Boston fiscal year that reconciles to the
City source, or when Boston grants written commercial redistribution and derived
output rights. The current Chelsea, Revere, and Winthrop slices remain candidates
for separate source admission rather than evidence that Boston itself is current.

## Philadelphia, Pennsylvania

**Decision: redistribution-rights hold.**

- Nightly OPA assessor files and weekly Department of Records polygons pass the
  official-source, structured-access, freshness, ownership, value, improvement,
  sale, and geometry gates. OPA publishes 583,720 rows with strong core-field
  completeness; DOR publishes active and retired deed-derived polygons.
- Use unique `pin` as ingestion identity and retain nine-digit `parcel_number`
  as an official account alias. The release contains 16 duplicated parcel
  numbers across unrelated addresses, so those accounts must be quarantined
  rather than forced together. Join OPA to DOR on `pin`, never by address.
- Use active DOR polygons for exact distance and adjacency, deriving
  `ST_PointOnSurface` in EPSG:2272. Version inactive parcels, subdivisions,
  consolidations, condo hosts, unmatched records, and OPA/DOR freshness
  independently.
- The catalog labels the data public and free, but the governing City terms
  reserve database rights and do not affirmatively grant commercial derivative
  database or customer redistribution rights.

Admission requires written CityGeo or Law Department authorization covering
commercial use, derived databases, customer display/API output, redistribution,
attribution, and downstream terms.

## Miami-Dade County, Florida

**Decision: admitted to production.**

- The official Property Appraiser property/sales layer and paid weekly bulk
  files pass provenance, structured access, identity, owner, use, assessment,
  improvement, sale, freshness, and commercial redistribution gates. The live
  property layer contains 929,448 active non-reference records.
- Preserve the 13-character `FOLIO` as tax-account identity. Set physical parcel
  group to `COALESCE(PARENT_FOLIO, FOLIO)` so condo child accounts sharing one
  footprint produce one nearby-search candidate while retaining each account's
  raw owner and assessment evidence.
- Use County point geometry in WGS84 for the first production slice. The
  companion EPSG:2236 parcel layer is the future exact-distance source; derive
  `ST_PointOnSurface` from those polygons and reconcile by physical folio.
- Current 2026 value columns were null during admission, so mappings
  deterministically fall back to certified 2025 and then 2024 values. Preserve
  assessment-year fields as raw evidence and promote current-year values only
  after a completeness threshold passes.
- Poll and reconcile weekly with folio counts, active/cancelled transitions,
  parent-child integrity, schema fingerprints, raw-file hashes, and geometry
  coverage. Zero improvement values are valid vacant-land evidence.
- Florida public-records law, County public-domain/CC0 policy, and
  *Microdecisions v. Skinner* support commercial use and redistribution of the
  County GIS public records. Retain the court opinion and County policy as
  rights evidence; attribute Miami-Dade as a conservative product practice.

Production source: `miami_dade_fl_property_appraiser_parcels`. Authoritative
bulk source: `https://bbs.miamidade.gov/`.

## Florida Statewide FDOR Cadastral

**Decision: admitted as a statewide parcel-proximity spine.**

- Production source: `florida_fdor_statewide_cadastral_parcels`. The official
  Florida GIO / FDOR cadastral FeatureServer exposes statewide 2025 parcel
  polygons with stable `STATE_PAR_`, county number, parcel ID, owner/mailing,
  situs, DOR/use code, land area, value, sale-summary, and centroid-capable
  geometry.
- Use `STATE_PAR_`, falling back to `PARCEL_ID`, as canonical identity. Use
  `OBJECTID` only for ArcGIS keyset pagination. County-specific admitted feeds
  remain preferred where they provide fresher geometry, richer assessment
  fields, or better local reconciliation.
- The first production slice stores owner, owner mailing address, situs,
  DOR/property-appraiser use code, land square feet, living/improvement area,
  land value, just value, latest sale price summary, public-land flag, and
  publisher centroid. Legal descriptions, deed book/page, clerk numbers,
  fiduciary fields, tax-authority fields, raw polygons, and raw source exports
  are suppressed.
- The statewide release is annual with midyear maintenance, so use it for
  statewide coverage and proximity fallback, not as a live title, zoning, or
  complete sale-history source. Preserve assessment year, source date, county
  attribution, and public-record/currentness disclaimers.
- Rights pass under Florida Chapter 119, AGO 2003-42, and *Microdecisions v.
  Skinner*, which support commercial reuse and redistribution of property
  appraiser GIS public records after statutory redactions.

## Dallas / Dallas County, Texas

**Decision: rights and sale-evidence hold.**

- DCAD's countywide appraisal ZIPs and EPSG:2276 parcel shapefiles pass official
  provenance, bulk access, parcel identity, owner, address, use, land, value,
  improvement, geometry, and freshness gates. The audited release contains
  861,946 accounts and 696,560 polygons.
- Preserve 17-character `ACCOUNT_NUM` and `GIS_PARCEL_ID` plus appraisal year;
  model condo/shared parcels as many accounts to one physical footprint and
  version split/merge lineage. The City ArcGIS layer is a useful cross-check,
  not the system of record.
- DCAD provides deed-transfer date and instrument text but no consideration or
  qualified-sale indicator. That evidence must not be labeled a sale price or
  arms-length transaction.
- DCAD marks its materials all rights reserved, the archives contain no
  affirmative commercial redistribution grant, and the City layer repeats
  appraisal-district copyright language. Texas public-record access can coexist
  with copyright restrictions.

Admission requires written DCAD permission for commercial ingestion, derived
products, customer display, and redistribution, plus either acceptance of deed
transfer as a narrower fact or a separately licensed official sales source.

## Atlanta / Fulton County, Georgia

**Decision: rights and evidence-scope hold.**

- Fulton County's official 2026 Tax Parcels service is technically strong with
  373,099 unique populated parcel IDs, complete polygon geometry, near-complete
  owner/address/mailing evidence, land use, class, and acreage. A companion
  official viewer layer supplies land/improvement/total appraisal and assessment
  values for 99.98% of records.
- Use tax-year plus raw `ParcelID` as source identity and version split/merge
  lineage. Join valuation on exact parcel ID, derive `ST_PointOnSurface` in
  EPSG:2240, retain polygons for exact distance, and treat the midyear digest as
  mutable until certified.
- The official APIs omit sale date, price, deed, validity, and detailed building
  characteristics. The linked qPublic vendor site is interactive and expressly
  prohibits automated extraction, so it is not an ingestion fallback.
- County item license and attribution fields are blank. Georgia open-records
  inspection/copying access does not itself provide an affirmative commercial
  derivative-product and redistribution grant.

Admission requires written Fulton County authorization for commercial storage,
derived nearby results, customer display, and redistribution, plus an official
bulk CAMA/sales extract or a formally narrowed evidence gate.

## Raleigh / Wake County, North Carolina

**Decision: admitted to production.**

- Production source: `wake_county_nc_parcels`. Wake County's official parcel
  catalog and ArcGIS parcel layer pass provenance, bulk access, stable identity,
  owner, situs, mailing, value, sale, geometry, freshness, and commercial
  redistribution gates.
- Preserve `PIN_NUM` as canonical parcel identity. Retain `REID`, `PARCEL_PK`,
  `MAP_NAME`, and `OLD_PARCEL_NUMBER` as aliases and split/merge lineage
  evidence. `OBJECTID` is transport pagination only.
- The source exposes owner, mailing and site address, city/ZIP, land and
  building values, total assessed value, calculated area, deed acreage, latest
  sale price/date, deed book/page/date, and polygon geometry in North Carolina
  State Plane. Use server centroids in WGS84 for initial radius search and
  retain polygon evidence for future exact-boundary distance.
- Preserve every `PIN_NUM`/`REID` tax account independently. For duplicate or
  stacked geometries, group into a physical-parcel candidate for nearby
  discovery while retaining separate owner, value, sale, and evidence facts.
- Poll nightly with a guarded full snapshot: row count, duplicate/null identity
  checks, schema fingerprint, checksum, geometry validation, extent regression,
  and prior-snapshot diff. Retire missing parcels only after a complete
  validated successor snapshot. Treat sale fields as assessor sale evidence,
  not complete deed history or sale intent.
- Rights pass under CC BY 4.0. Preserve Wake County attribution, license link,
  change notice, source retrieval date, and public-record disclaimers.

Official catalog: `https://catalog.data.gov/dataset/parcels-d1495`.
Structured source: `https://maps.wake.gov/arcgis/rest/services/Property/Parcels/MapServer/0`.

## Indianapolis / Marion County, Indiana

**Decision: narrow owner/value/geometry admit; sale-evidence hold.**

- Production source candidate: `indianapolis_marion_county_in_parcels`.
  IndyGIS publishes an official MapIndy parcel layer sourced from IndyGIS
  Parcels and Marion County Assessor information. The live layer exposes 347,051
  polygon records with populated parcel identifiers, owner names, owner mailing
  fields, situs fields, property class, land/improvement/total assessed values,
  legal description, acreage, and CAMA parcel ID.
- Use `STATEPARCELNUMBER` as canonical tax identity and retain `PARCEL_C`,
  `PARCEL_I`, `PARCEL_TAG`, `CAMAPARCELID`, `OBJECTID`, and source geometry in
  raw evidence. `OBJECTID` is pagination/transport evidence, not canonical
  identity. Derive WGS84 centroids from EPSG:2244/2965 polygons for radius
  search and retain polygons for exact-distance work.
- The official item license says there are no restrictions on data provided by
  download, map, or service, and requires derived data to acknowledge the City
  of Indianapolis/Marion County, IN. Preserve that item-level rights record,
  source date, disclaimer, and attribution with every snapshot.
- Refresh with guarded full snapshots using 1,000-row ArcGIS pages or
  `returnIdsOnly` batches. Block publication on empty snapshots, schema drift,
  null canonical IDs, unexpected row-count changes, geometry failures, or
  duplicate state parcel numbers once a full distinct-ID audit is implemented.
- Sale evidence is not admitted. The parcel layer has no sale date, sale price,
  deed instrument, validity, or arms-length fields, and the reviewed tax-sale
  and property-card surfaces are not a complete parcel-linked bulk sale-history
  source.
- Condo/unit handling must preserve one record per `STATEPARCELNUMBER`. Use the
  separate Apartments and Condos layer only as supplemental complex/unit-count
  context; group shared-footprint or complex records for nearby discovery only
  after validating geometry/address relationships, and never collapse owner,
  value, or assessment facts across unit/tax identities.

Structured source:
`https://gis.indy.gov/server/rest/services/MapIndy/MapIndyProperty/MapServer/10`.
Rights evidence:
`https://www.arcgis.com/home/item.html?id=0d28e222479743baa97f8f4456da7bb4`.

## Charlotte / Mecklenburg County, North Carolina

**Decision: redistribution-rights hold.**

- Mecklenburg GIS/POLARIS and Open Mapping parcel products are technically
  strong. Tax parcels with CAMA expose PID/NC PIN identities, owner and mailing
  fields, situs address, land/improvement/market/assessed values, sale
  price/date, sale-validity code, deed references, acreage, legal description,
  and authoritative polygon geometry.
- Preserve one record per parcel/PID. Do not merge overlapping condominium,
  townhouse, air-rights, parent/child, common-area, residual, road, or
  non-billable records by address or geometry. Use `CONDO_TOWN_FLAG` and
  `PARCEL_TYPE` as explicit candidate/exclusion classes.
- Poll county data daily and reconcile by PID/NC PIN plus deed book/page. Use
  NC OneMap only as statewide fallback or cross-check, comparing county FIPS,
  revision dates, transform dates, geometry, and identity against Mecklenburg.
  Recorded instruments may appear after 3-10 days, while parcel/map changes can
  lag 30-60 days, so freshness and quarantine rules must preserve that delay.
- Rights fail the production gate. County metadata describes useful public
  access, but both parcel metadata records state that Mecklenburg County does
  not support secondary distribution. NC OneMap points users back to county
  stewards for authoritative verification.

Admission requires written Mecklenburg GIS authorization for commercial
storage, derivative nearby-parcel results, customer display/API output,
redistribution, retention, attribution, source dates, and disclaimers.
Document condo/stacked-parcel exclusion behavior before enabling ordinary
nearby-candidate results.

## Orlando / Orange County, Florida

**Decision: admitted to production.**

- OCPA's official nightly parcel polygons pass identity, geometry, owner,
  address, land/use, value, improvement, sale, freshness, and commercial
  redistribution gates. The live layer contains 494,407 polygon rows and
  493,642 distinct 15-character parcel IDs.
- Preserve `PARCEL` with leading zeroes as tax-account identity and set physical
  group to `COALESCE(PARENT_ID, PARCEL)`. Retain condo, non-contiguous, floor,
  feature, and parent flags in raw evidence; polygon multiplicity must not create
  duplicate nearby candidates.
- Use official latitude/longitude for indexed search and display. Preserve
  polygon area as measured land context; the future boundary store should union
  multipart records and use polygon edge distance plus `ST_PointOnSurface`.
- Poll nightly with row/distinct-ID counts, schema hash, duplicate report, and
  prior-snapshot diff. Treat October-through-July values as draft and establish
  a certified baseline after July 1. Confirm removals in a second snapshot.
- Florida public-records law, *Microdecisions v. Skinner*, and AGO 2003-42
  affirm commercial use and redistribution. Exclude OCPA branding, photos,
  third-party imagery, and site design; preserve source attribution and dates.

Production source: `orange_county_fl_property_appraiser_parcels`.

## Tampa / Hillsborough County, Florida

**Decision: admitted with bulk-source reconciliation.**

- Production source: `hillsborough_county_fl_property_appraiser_parcels`. The
  City of Tampa's official Hillsborough County Tax Parcel FeatureServer exposes
  parcel polygons, stable `FOLIO` identity, ownership, situs, use, assessment,
  improvement, and latest-sale evidence. The live audit counted 531,133 rows.
- Use `FOLIO` as canonical parcel and physical-group identity; preserve `PIN`
  and `STRAP` in raw evidence. Convert `ACREAGE` to square feet, request the
  server centroid in EPSG:4326 for candidate indexing, and retain polygon
  evidence for a future point-on-surface and exact-boundary distance pass.
- Poll daily, but treat the dated HCPA public-download manifest as the freshness
  and reconciliation authority. Discover rotating filenames instead of
  hardcoding them. The county-hosted comparison layer was roughly 9,000 parcels
  behind and had parcel-level sale evidence no newer than February 2024.
- Block publication on unexpected bulk/API count divergence, duplicate folios,
  invalid geometry, stale newest-sale dates, or retirement above 2%. Preserve
  snapshot dates and split/merge lineage when folios retire.
- Florida public-records law, *Microdecisions v. Skinner*, and AGO 2003-42
  permit commercial reuse and redistribution of agency-created county GIS
  records. Preserve source attribution and do not present assessment ownership
  as a title determination.

Authoritative bulk portal: `https://downloads.hcpafl.org/Default.aspx?subfolder=`.
Structured source: `https://arcgis.tampagov.net/arcgis/rest/services/BaseMaps/ParcelsInfo/FeatureServer/0`.

## Jacksonville / Duval County, Florida

**Decision: admitted with monthly bulk reconciliation.**

- Production source: `duval_county_fl_property_appraiser_parcels`. Use the
  official City of Jacksonville parcel MapServer for geometry and current
  parcel context, and the Property Appraiser's rotating monthly tax-roll and
  sales files as the value and transaction system of record.
- Use the ten-character `RE_NOSPACE` account as canonical and physical-group
  identity, preserving formatted `RE`, bulk `STRAP`, and component `OBJECTID`
  in raw evidence. Dissolve multipart components before future exact-boundary
  distance calculations; never sum repeated account values across components.
- The ArcGIS layer provides owner, situs, land use, acreage, land value, and
  building value. Do not label `CAMA_VAL` as assessed value: it is latest-sale
  consideration. Certified assessed/just values and qualified transaction
  history must come from the monthly bulk files.
- Discover dated bulk URLs from the official Data Offerings page, archive each
  file with retrieval time and checksum, and run monthly full-snapshot guards
  for duplicate IDs, component/value disagreement, schema drift, and retirement
  above 2%.
- *Microdecisions v. Skinner* and Florida AGO 2003-42 permit commercial reuse
  of the underlying public records. Exclude site copy, logos, imagery,
  basemaps, and third-party overlays; retain attribution and source disclaimers.

Structured source: `https://maps.coj.net/coj/rest/services/CityBiz/Parcels/MapServer/0`.
Bulk discovery: `https://www.jacksonville.gov/departments/property-appraiser/data-offerings`.

## Palm Beach County, Florida

**Decision: operational hold.**

- The official property table is current and evidence-rich, and Florida AGO
  2003-42 specifically supports commercial redistribution of Palm Beach County
  GIS public records. The available parcel geometry service is nevertheless
  under a `/test/` path with no documented SLA or cadence.
- The property table has roughly 662,000 accounts while the test geometry layer
  has roughly 481,000 polygons. `PARCEL_NUMBER` and polygon `PARID` do not have
  a documented condo-to-physical-parcel grouping rule, so admitting it now could
  collapse or misplace condominium accounts.
- Admit only after PAO/CWGIS confirms a stable production geometry endpoint or
  bulk geometry URL, the parcel-to-physical-group rule, refresh cadence, and
  retained commercial derivative use. Until then, preserve the source audit but
  do not expose it in customer parcel discovery.

## Fort Lauderdale / Broward County, Florida

**Decision: admitted through the Florida DOR release pipeline.**

- Production source: `broward_county_fl_dor_parcel_centroids`. Filter the
  official statewide 2025 DOR cadastral-centroid layer to county number 16 and
  preserve each annual NAL/SDF/PAR release immutably. Reconcile against the
  Broward BCPA polygon layer, which is refreshed more often but omits individual
  condominium polygons.
- Use text `PARCEL_ID` as account identity and preserve `STATE_PAR_`, split
  flags, assessment year, and release identifier in raw evidence. For DOR use
  code 004 condos, group nearby candidates by unit-stripped physical address;
  every unit remains a separate canonical record and graph entity.
- The 2025 final NAL audit found 754,371 unique accounts with essentially full
  owner, address, use, just-value, and land-value coverage. The live polygon
  layer had 556,416 folios; condo and multi-parcel effects explain much of the
  gap. Mark address-grouped condo coordinates as parent-level spatial evidence.
- Store DOR centroids for initial radius search. Future polygon ingestion should
  compute `ST_PointOnSurface` in EPSG:2236 and use exact polygon distance. Select
  Fort Lauderdale by spatial containment, not the mailing or situs city string.
- DOR explicitly publishes the rolls as Chapter 119 public records after
  removing confidential owners. Florida AGO 2003-42 and *Microdecisions v.
  Skinner* support commercial reuse and redistribution. Preserve source,
  assessment year, retrieval date, and not-a-survey disclaimers.

## Lakeland / Polk County, Florida

**Decision: admitted with guarded bulk reconciliation.**

- Production source: `polk_county_fl_property_appraiser_parcels`. The official
  Property Appraiser FeatureServer exposes 437,807 distinct populated parcel
  IDs with owner, situs, use, acreage, land/building/extra-feature values,
  assessed value, tax district, and polygon geometry. Use the PAO's daily bulk
  files as the long-term system of record and the API as the live query surface.
- Preserve the 18-digit `PARCELID` as text. Ordinary physical groups use that
  ID; use-code 0400 condo accounts group by normalized situs excluding unit.
  Retain each unit's owner, values, and evidence independently. Missing-address
  condo groups must be quarantined or reconciled to the bulk plan key before
  customer display.
- Poll daily with a 36-hour SLA and a guarded full snapshot. Archive bulk file
  timestamps, checksums, schema fingerprints, row counts, and tax year. Values
  can reflect the prior certified roll even when ownership, address, and sales
  are nightly-current, so never infer value vintage from retrieval time.
- Florida Chapter 119, AGO 2003-42, and *Microdecisions v. Skinner* permit
  commercial reuse of the underlying public records. Preserve statutory
  redactions, PAO attribution, and not-title/not-survey/not-zoning disclaimers.

## St. Petersburg / Pinellas County, Florida

**Decision: admitted for the bulk-file cohort.**

- Use the official PCPAO raw database catalog and parcel/label-point shapefiles
  as the production manifest. Discover generated CSV links each run rather than
  hardcoding dated URLs. The application-coupled Accela parcel MapServer is a
  reconciliation canary, not the sole production snapshot.
- Preserve the zero-padded 18-character `STRAP` account identity. Condo/co-op
  units group by the first 11 characters only after validating exactly one
  official parent condo polygon; quarantine ambiguous or missing parents.
- Poll the manifest weekly and ingest only coherent table releases. Retain roll
  year, retrieval date, source timestamps, checksums, split/combine successors,
  and all unit-level evidence. Future-land-use fields are not zoning evidence.
- Rights pass under Florida Chapter 119, AGO 2003-42, and *Microdecisions*.
  Exclude logos, imagery, basemaps, site copy, and third-party overlays.

## Houston / Harris County, Texas

**Decision: redistribution-rights hold.**

- HCAD's official CAMA ZIP extracts and parcel shapefiles are technically
  production-capable. The audited sources contain 1,626,749 real-property
  accounts and 1,538,086 unique parcel polygons, with 99.976% GIS-to-CAMA join
  coverage and strong owner/address/use/value/improvement evidence.
- Preserve the 13-digit `acct`/`HCAD_NUM`, leading zeroes, tax year, stacked
  flag, low parcel ID, and `parcel_tieback` lineage. Group stacked geometries for
  nearby search, then retain every account's evidence independently.
- Deeds provide recorded transfer date and instrument IDs but no consideration;
  private-source Texas sale prices are confidential. Label this transfer
  evidence, not verified sale-price evidence.
- HCAD publishes no affirmative commercial redistribution grant and marks its
  site all rights reserved. Texas public-record access does not by itself grant
  customer-facing redistribution or archived derivative-database rights.

Admission requires written HCAD permission for commercial use, spatial
derivatives, customer display/redistribution, and retained snapshots, or a
counsel-approved rights basis covering the exact CAMA and GIS files.

## Austin / Travis County, Texas

**Decision: legal hold.**

- Travis County's official TCAD parcel MapServer is technically
  production-capable, with 386,682 polygon features and 373,524 distinct
  populated `PROP_ID` values. Nearly every identified parcel has owner, land
  use, acreage, market value, and land/improvement value context.
- Use `PROP_ID` as canonical identity and preserve `geo_id` as an alias. Null-ID
  polygons must be quarantined. Multipart rows sharing a `PROP_ID` should be
  dissolved only after attribute agreement checks; `OBJECTID` is snapshot row
  identity, not durable parcel identity.
- Native geometry is EPSG:2277. Compute the union and centroid before
  transforming to EPSG:4326, and use point-on-surface for radius discovery when
  a concave or multipart parcel's centroid falls outside its boundary.
- The layer has no trustworthy incremental watermark or history. Run monthly
  full snapshots using an ID manifest and 1,000-row chunks, retain raw snapshots,
  and require stable manifests, at least 350,000 identified parcels, null-ID
  rate below 5%, core fact completeness above 95%, and total change below 5%.
- The exact layer has attribution and accuracy disclaimers but no reuse grant.
  County open-data language, an all-rights-reserved footer, TCAD public-domain
  language, and a separate no-data-mining statement conflict. Written County
  and TCAD permission for bulk access, commercial storage, derived scoring,
  customer display, and redistribution is required before admission.

Owner values are assessment evidence, not title-insurance-grade ownership.
Texas is non-disclosure, deed dates are empty in this layer, and no sale-price
inference should be fabricated from missing data.

## Washington - Statewide, Seattle / King County, And Focus Counties

**Decision: geometry-first Phase 2 path, with owner/taxpayer/sales/raw export
fields held pending source-specific written permission. No Washington parcel
source is added to the production catalog in this pass because the final field
scope needs a separate schema/terms review across statewide and county layers.**

- King County's public parcel FeatureServer is current, authoritative, and
  technically strong, with 636,197 weekly refreshed polygons and no null
  ten-character `PIN` values. It exposes lot area, land and improvement values,
  assessment year, zoning, present use, addresses, and geometry.
- The API supports ordered 1,000-row pagination, EPSG:4326 output, and
  server-computed centroids. Configure the ArcGIS connector with
  `include_centroid: true`; map `centroid.x` and `centroid.y` through
  `object_path` transforms. Preserve polygon evidence and use point-on-surface
  in PostGIS when a centroid falls outside a concave parcel. Never deduplicate
  stacked interests by geometry; use `PIN`.
- Run weekly full snapshots with a fresh manifest, minimum 600,000-row guard,
  2% maximum retirement fraction, and monitoring for tax year, schema, item,
  license, count, and publication-date regressions. PINs may be reused after
  segregation, so future split/merge lineage needs explicit treatment.
- The public layer omits taxpayer names. Owner-bearing assessor downloads add
  legal restrictions on commercial use of lists of individuals, and the GIS
  license prohibits reproduction or redistribution without written approval.
  Mailing address without a taxpayer name is not sufficient ownership evidence.
- Washington State Parcels Project is the likely statewide technical baseline,
  but not a production source yet. It exposes normalized parcel IDs, situs
  address/city/ZIP, DOR land-use code, land and improvement values, county,
  source link, file date, and polygons, but no owner in the current layer and
  no reliable zoning, building area, or sales fields. Its current metadata says
  some counties restrict parcel use to State of Washington business only and
  directs requests back to the appropriate county, so commercial SaaS admission
  requires OCIO/Geoportal plus county-level permission confirmation.
- Pierce County, Spokane County, and Clark County are viable geometry or
  non-personal attribute candidates after field-level review. Pierce publishes
  tax parcels daily and includes parcel number, acreage, use code/description,
  land/improvement/taxable values, and address fields, while noting address
  accuracy limitations and commercial-list restrictions. Spokane and Clark
  support spatial parcel/taxlot lookup, but owner, characteristic, and sales
  enrichment must remain held until written terms are clear.
- Snohomish County remains a hold because its parcel dictionary explicitly
  prohibits commercial use of lists or data from which lists may be compiled.
- Washington public-records law and several county terms restrict lists of
  individuals for commercial purposes. Suppress owner names, taxpayer names,
  mailing addresses, owner lists/exports, sales history/prices, building
  characteristics, raw files, bulk downloads, unrestricted API passthrough, and
  exact customer-facing parcel-boundary display unless separately licensed.

Evidence URLs:
`https://app.leg.wa.gov/rcw/default.aspx?cite=42.56.070`;
`https://services.arcgis.com/jsIt88o09Q0r1j8h/ArcGIS/rest/services/Current_Parcels/FeatureServer`;
`https://www.arcgis.com/home/item.html?id=2b603a599a0842a3b2284c04c8927f35`;
`https://gisdata.kingcounty.gov/arcgis/rest/services/OpenDataPortal/property__parcel_area/MapServer/439`;
`https://gismaps.kingcounty.gov/ArcGIS/rest/services/Property/KingCo_Parcels/MapServer/0/query`;
`https://info.kingcounty.gov/assessor/DataDownload/default.aspx`;
`https://www5.kingcounty.gov/sdc?Layer=parcel_extr`;
`https://services2.arcgis.com/1UvBaQ5y1ubjUPmd/ArcGIS/rest/services/Tax_Parcels/FeatureServer`;
`https://services2.arcgis.com/1UvBaQ5y1ubjUPmd/ArcGIS/rest/services/Tax_Parcels/FeatureServer/0`;
`https://matterhorn.piercecountywa.gov/GISmetadata/pdbparc_taxparcel.html`;
`https://services6.arcgis.com/z6WYi9VRHfgwgtyW/ArcGIS/rest/services/Parcels/FeatureServer/0`;
`https://www.snohomishcountywa.gov/DocumentCenter/View/101955/Parcels-Data-Dictionary`;
`https://gismo.spokanecounty.org/arcgis/rest/services/Assessor/Parcels/MapServer/0`;
`https://cp.spokanecounty.org/SCOUT/propertyinformation/Summary.aspx?PID=00.006921`;
`https://gis.clark.wa.gov/arcgisfed/rest/services/Hosted/TaxlotsPublic_Singlepart/FeatureServer`.

## Salt Lake County / Salt Lake City, Utah

**Decision: owner/sale-rights hold.**

- UGRC Salt Lake County parcels and Salt Lake City parcel services provide useful
  geometry, parcel identity, address, and value context. County and city parcel
  fields include `PARCEL_ID`, `PARCEL_PIN`, `PARCEL_PIN10`, `PARCEL_SID`, and
  LIR `SERIAL_NUM`; county address fields such as `PARCEL_ADD`/`PARCEL_CITY`;
  city address and ZIP fields; LIR market and land values; and polygon
  geometry.
- Public county layers expose generalized ownership type rather than full owner
  evidence. County Assessor CAMA reportedly contains owner name, final/land/
  building/taxable values, condo unit attributes, and sales, but production use
  requires purchase/sample confirmation, schema review, and license review.
- No public parcel-layer sale date/price path was verified. Recorder data terms
  allow use in derivative work products but prohibit further distribution or
  reproduction without written authorization, making owner/sale redistribution
  the blocker.
- Treat each tax parcel or unit as a separate record keyed by parcel ID plus
  unit or serial where available. Preserve shared footprints and do not dissolve
  stacked condominium units. Quarantine unmatched condo units until CAMA and
  geometry joins are validated.
- LIR is an annual tax-year product and the basic layer is a snapshot. A future
  production design should reconcile county geometry/address, assessor CAMA
  value/owner/sale fields, recorder identifiers, `CURRENT_ASOF`, retrieval
  timestamps, and split/merge transitions.

Admission requires written Salt Lake County Recorder and Assessor authorization
for commercial storage, owner/sale fields, derived nearby results, customer
display/API output, and redistribution; CAMA sample validation; refresh cadence
and SLA; and a repeatable sale date/price path. Otherwise this can only be a
geometry/address/value discovery spine with owner and sale fields unavailable.

## Las Vegas / Clark County, Nevada

**Decision: rights and access-contract hold.**

- Clark County's official Assessor paid data files are the strongest attribute
  source. AOEXTRACT supplies parcel, owner and mailing address, situs address,
  land use, document, sale price/date/type, acreage, fiscal-year values, and
  prior-year values. Commercial extraction files add building/use detail for
  commercial structures, AOSales supplies transaction history back to about
  1994, AOEtal covers extended ownership, and AO_XY supplies parcel points.
- The public GISMO AssessorMap parcel layer is a useful geometry spine with
  polygon geometry, 10,000-row ArcGIS pages, JSON/GeoJSON/PBF output, distance
  queries, APN, assessed/calculated acreage, tax district, parcel type, and
  explicit Parcel, Condo, and Air Rights type classes. It does not include
  owner, value, or sale fields and cannot carry Phase 2 by itself.
- Preserve `PARCEL`/`APN` as the canonical assessor identity, retaining
  formatted APN, tax district, parcel type, label class, fiscal year, sale
  document fields, and raw file checksums. Treat `OID` as a page cursor only.
  Keep condo and air-right records as separate tax identities and derive a
  physical-parcel group from shared/parent geometry only after extract samples
  validate the relationship.
- The Assessor page says paid files are complete replacement extracts updated
  each weekend and require a signed request or subscription for access to the
  Assessor Data Site. Production would need guarded weekly full snapshots,
  schema fingerprints, duplicate/null APN checks, geometry validation, and
  explicit reconciliation between AOEXTRACT, AOSales, AOEtal, AO_XY, and GISMO
  polygons.
- Rights are not yet production-clear. The County data notice contemplates
  customer/subscriber use and dissemination, but it is not an affirmative SaaS
  product license for storage, derived nearby results, customer display/export,
  API output, sublicensing, redistribution, retention, fees, and attribution.
  The public GIS disclaimer provides warranty limits rather than reuse rights.

Admission requires a signed Clark County Assessor/GIS agreement or written
County authorization covering the exact paid extracts and GISMO geometry for
commercial storage, derived nearby-parcel scoring, customer display/API output,
redistribution/export, retention, refresh cadence, fees, attribution,
confidential-data handling, and termination effects.

## City of St. Louis / St. Louis County, Missouri

**Decision: City of St. Louis admit; St. Louis County rights hold.**

- City of St. Louis is strong enough for Phase 2 nearby parcel context. The
  Assessor parcel MapServer exposes 127,063 polygon parcel records with
  `ParcelId`, `Handle`, situs address, owner names and mailing address,
  assessor/property class, land-use, zoning, assessed/appraised/billed values,
  land area, residential sale date/price, owner/update dates, and polygon
  geometry. The City open-data catalog also publishes current parcel shapefiles,
  parcel-joining CSV, land-record DBF, parcel tax-record MDB, and parcel-sales
  MDB; the download page reported current parcel, zoning, tax-record, land
  record, and parcel-sales updates on 2026-07-16.
- Use the City ArcGIS parcel layer as the primary API source and the downloadable
  tax-record, land-record, and sales files as optional reconciliation inputs
  after schema sampling. The public address/property search confirms address or
  parcel-ID lookup for ownership, assessment value, land use, zoning, sale
  information, tax history, permits, and related records, but bulk ingestion
  should prefer the published open-data distributions and ArcGIS service.
- Field mapping: `ParcelId` maps to canonical parcel ID; `Handle` maps to
  secondary geometry/join identity; `CityBlock`, `Parcel`, `OwnerCode`,
  `ColParcelId`, `ColCityBlock`, and `ColParcel` map to alternate assessor
  identifiers; `SITEADDR`, low/high address number, street direction/name/type,
  suffix direction, `StdUnitNum`, `ZIP`, and `Location` map to situs address;
  `OwnerName`, `OwnerName2`, `OwnerAddr`, `OwnerCity`, `OwnerState`,
  `OwnerCountry`, `OwnerZIP`, and `OwnerRank` map to owner and mailing evidence;
  `AsrClassCode`, `PropertyClassCode`, `AsrLandUse1`, `AsrLanduse2`,
  `CDALandUse1`, `CDALandUse2`, and `Zoning` map to use/class/zoning evidence;
  `LandArea`, `SQFT`, `NbrOfUnits`, `NbrOfApts`, `NbrOfBldgsRes`,
  `NbrOfBldgsCom`, `FirstYearBuilt`, and `LastYearBuilt` map to parcel/building
  characteristics; `AsdLand`, `AsdImprove`, `AsdTotal`, `BillLand`,
  `BillImprove`, `BillTotal`, `AprLand`, `AprComLand`, and `AprComImprove` map
  to valuation facts; `ResSalePrice`, `ResSaleDate`, `RecDailyDate`,
  `RecDailyNum`, `RecBookNum`, and `RecPageNum` map to sale/recording evidence
  with residential-sale caveats; `OwnerUpdate`, `FirstDate`, `LastDate`, and
  `PriorAsdDate` map to source/update/lifecycle evidence.
- Geometry handling: request polygon geometry from the City parcel query
  endpoint with `outSR=4326`, store the source boundary for exact radius
  distance, and derive a point-on-surface centroid for radius indexing. Retain
  `Shape.STArea()`/`Shape.STLength()` and source area fields for quality checks.
  Preserve each `ParcelId` as the tax/owner/value identity. Use shared
  geometry, `Handle`, `LowerParcelId`, condominium/subparcel flags, and unit
  fields only to derive physical-parcel groups; do not collapse separate tax
  accounts.
- Page the City MapServer in guarded 2,000-row snapshots using
  `where=OBJECTID > {last_objectid}`, `orderByFields=OBJECTID`,
  `resultRecordCount=2000`, selected `outFields`, `returnGeometry=true`,
  `outSR=4326`, and `f=geojson` or JSON. Treat `OBJECTID` as transport state,
  validate the 127,063-record count, non-null/unique canonical IDs, geometry
  validity, schema fingerprint, row-count drift, duplicate stacked geometry, and
  vintage/update fields before retiring missing parcels.
- Rights notes for the City: the open-data terms say the City provides
  government-produced, machine-readable datasets free of charge, with
  no completeness/accuracy warranty and awareness that raw extracts can contain
  errors. The Assessor page says data is provided as a public service and does
  not allow name searches, so downstream surfaces should keep attribution and
  public-record caveats, avoid owner-name reverse search, honor future
  suppression rules, and avoid raw source-data resale unless rights are
  rechecked.
- St. Louis County should stay on hold. County parcel services are technically
  useful and expose about 400,787 hosted parcel polygons with `LOCATOR`,
  `PARENT_LOC`, tax year, situs address/ZIP, land-use, zoning, acres, assessed
  and appraised value fields, and commercial/multifamily/industrial derived
  context. Another County ArcGIS layer lists owner, mailing, deed, sale/date
  string, appraised/assessed values, zoning, land use, and geometry, but returned
  a 403 during query testing. County metadata states that data, or portions of
  it, may not be shared without St. Louis County GIS Service Center consent and
  separately directs GIS data requests to the GIS Service Center. That blocks
  commercial storage, derived customer display/API output, export, and
  redistribution without written County authorization.

Production source: `st_louis_mo_city_parcels`. Primary endpoint:
`https://maps8.stlouis-mo.gov/arcgis/rest/services/ASSESSOR/Assessor_Public_Parcels/MapServer/11`.
Query endpoint:
`https://maps8.stlouis-mo.gov/arcgis/rest/services/ASSESSOR/Assessor_Public_Parcels/MapServer/11/query`.
Download page:
`https://dynamic.stlouis-mo.gov/opendata/downloads.cfm`. Dataset page:
`https://www.stlouis-mo.gov/data/datasets/dataset.cfm?id=82`. Terms:
`https://dynamic.stlouis-mo.gov/opendata/terms.cfm`. Assessor property-search
evidence:
`https://www.stlouis-mo.gov/government/departments/assessor/who-owns-a-property.cfm`.
County hold evidence:
`https://services2.arcgis.com/w657bnjzrjguNyOy/ArcGIS/rest/services/STLCO_STC_Parcels_SFD/FeatureServer/0`,
`https://services2.arcgis.com/w657bnjzrjguNyOy/arcgis/rest/services/STLCO_2050_ECR___Home_Values_WFL1/FeatureServer/2/metadata?f=html&format=default`,
and
`https://maps.sccmo.org/scc_gis/rest/services/agol/Genetec_URL/MapServer/220`.

## Allegheny County / Pittsburgh, Pennsylvania

**Decision: admitted narrowly to production for geometry-first Phase 2 nearby-
parcel context.**

- Allegheny County GIS publishes parcel boundaries through the official
  `OPENDATA/Parcels` ArcGIS service. The Pennsylvania open-data catalog lists
  the county GIS open-data portal under Public Domain, with Allegheny County
  GIS as the data provider.
- Canonical parcel identity is `PIN`; `MAPBLOCKLOT` supports grouping and
  display, while `OBJECTID` remains the transport cursor only. The production
  query excludes null PINs and uses deterministic `OBJECTID` keyset paging.
- The admitted slice is intentionally geometry-first: PIN, map/block/lot,
  municipality code, calculated acreage, modified timestamp, GlobalID, polygon
  geometry, and derived centroid. It does not include situs address, owner,
  value, sale, deed, legal-description, notes/comments, editor, raw polygon
  export, or raw source-replacement output.
- The WPRDC property-assessment table is a strong future enrichment candidate
  with `PARID`, situs, class/use, values, sales, tax year, and `ASOFDATE`.
  Admission is deferred until full-population `PARID` to parcel-layer `PIN`
  matching is audited and field-level suppression for owner/contact and
  residential details is reviewed.
- Use the WGS84 polygon-derived centroid for radius search now. Future exact
  boundary-distance ranking can use retained geometry inside controlled
  backend workflows, but customer exports should remain derived context rather
  than raw parcel replacement data.
- Live canary on July 18, 2026 fetched 35 rows with 35 valid, 0 failed, and 35
  `parcel_snapshot` records.

Production source: `allegheny_county_pa_parcels_nearby_narrow`. Endpoint:
`https://gisdata.alleghenycounty.us/arcgis/rest/services/OPENDATA/Parcels/MapServer/0`.
Rights evidence:
`https://data.pa.gov/Geospatial-Data/Allegheny-County-GIS-Open-Data-Portal/qri8-9kju`.

## Maricopa County / Phoenix, Arizona

**Decision: commercial-rights hold.**

- Maricopa County Assessor is the authoritative countywide parcel source and is
  technically strong for Phase 2. The live parcel MapServer exposes 1,759,416
  polygon features with populated `APN`, owner name and mailing address, situs
  address, latitude/longitude, deed and sale fields, land size, subdivision,
  construction year, living space, current/previous full cash and limited
  property values, property use code, legal class, jurisdiction, zoning, floor,
  and suite/unit fields. The service supports JSON/GeoJSON/PBF, pagination, and
  spatial queries, with 1,000-row pages.
- The Assessor Data Downloads page also publishes free ZIP downloads for
  secured, residential, commercial, apartment, sales affidavit, notice/value,
  land, rental, parcel spatial, and parcel point files. These are better suited
  to guarded bulk snapshots than scraping the public parcel viewer.
- Use normalized `APN` as canonical tax identity and retain dashed `APN_DASH`
  for display. Treat `OBJECTID` only as a page cursor. Preserve `FLOOR`,
  `PHYSICAL_SUITE`, shared geometry, and identical centroid/area evidence for
  condominium or stacked-unit grouping; do not dissolve units into a single
  owner/value record.
- Sale evidence is present but should remain assessor/affidavit evidence:
  `SALE_DATE`, `SALE_PRICE`, `DEED_NUMBER`, `DEED_DATE`, and the separate Sales
  Affidavits download need reconciliation and null/zero/withheld-price handling
  before customer display.
- Rights fail the production gate until clarified. The free-download FAQ says
  available files can be downloaded without a form, but the site footer reserves
  rights, the data page places responsibility on users for access/use/sharing,
  and Arizona's commercial-purpose public-record statute requires disclosure of
  commercial purpose and creates liability for undisclosed or different
  commercial use. The County GIS disclaimer is indemnity/warranty language, not
  an affirmative redistribution license.
- City of Phoenix parcel services are only supplemental. The city-owned parcel
  service covers Phoenix-owned parcels, while the municipal Phoenix parcel layer
  is a dated hosted layer and does not replace the countywide Assessor source.

Admission requires written Maricopa County Assessor/County confirmation that
the parcel MapServer and Data Downloads files may be stored commercially,
refreshed in bulk, enriched into nearby-parcel results, displayed/exported to
customers, redistributed through API/output, and retained with historical
snapshots, including any required attribution, privacy suppression, and
commercial-purpose filing language.

## Travis County / Austin, Texas

**Decision: commercial-redistribution rights hold.**

- Travis Central Appraisal District is the authoritative appraisal source and
  publishes current appraisal-roll exports plus an export layout. The layout
  confirms fields for `prop_id`, `geo_id`, property type, owner names and
  mailing addresses, situs address and unit, confidential/address-suppression
  flags, legal description, acreage, land/improvement/market/appraised/assessed
  values, deed book/page/number/date, ownership percentage, land segments,
  improvement details, mobile homes, entities, and sketches.
- Travis County TNR publishes a countywide `TCAD Parcels` ArcGIS layer obtained
  from TCAD and assembled monthly. The layer exposes 386,682 polygons with
  1,000-row ArcGIS pages, JSON/GeoJSON/PBF output, pagination, spatial queries,
  `PROP_ID`, `geo_id`, situs fields, owner name, land type, acreage,
  market/appraised/assessed values, deed fields, legal description, lot fields,
  polygon geometry, and optional centroid fields. Its copyright text remains
  Travis Central Appraisal District.
- Use `PROP_ID` as the canonical assessor property identity and preserve
  `geo_id` as the parcel/map reference. Treat `OBJECTID` only as a page cursor.
  If admitted, reconcile the TCAD appraisal-roll export as the owner/value/deed
  authority and the Travis County monthly parcel layer as the geometry spine,
  deriving centroids from polygons when `CENTROID_X`/`CENTROID_Y` are null.
- Do not collapse multi-owner, condominium, situs-unit, mobile-home, or shared-
  footprint records. The export layout states that multiple owner records can
  exist for one property/owner context and provides `partial_owner`,
  `udi_group`, `ownership_pct`, `prop_owner_sequence`, `situs_unit`, mobile-home
  fields, and confidential/suppression flags that must be preserved as separate
  evidence.
- Sale evidence is limited to assessor deed indicators (`deed_num`,
  `deed_book_id`, `deed_book_page`, `deed_dt`/`deed_date`) and does not include
  verified consideration or arm's-length transaction history. Use it only as
  deed/tenure evidence unless a recorder or licensed sale source is approved.
- Rights are not production-clear. TCAD labels map information public domain
  with warranty disclaimers, but the same maps page prohibits data mining and
  directs users needing complete maps to order them from the district. The
  appraisal-roll exports are public information, and the county open-data page
  describes open data as freely available and reusable, but no reviewed source
  grants commercial SaaS storage, customer display/export/API output,
  redistribution, sublicensing, historical retention, or derived database rights
  for TCAD owner/value/deed fields and parcel geometry.

Admission requires written TCAD and Travis County authorization covering the
appraisal-roll exports, any purchased GIS shapefile, and/or the county ArcGIS
`TCAD Parcels` layer for commercial storage, bulk refresh, derived nearby
parcel scoring, customer display/API/export, redistribution, retention, privacy
suppression flags, attribution, and termination effects.

Primary sources reviewed: TCAD Public Information
`https://traviscad.org/publicinformation/`; TCAD Maps
`https://traviscad.org/maps`; Travis County TCAD Parcels ArcGIS layer
`https://gis.traviscountytx.gov/server1/rest/services/Boundaries_and_Jurisdictions/TCAD/MapServer/0`;
Travis County Open Data Portal
`https://www.traviscountytx.gov/open-data-portal`.

## Texas secondary markets parcel spine

**Decision: Collin County narrow admit; Dallas, Tarrant, Harris, and Bexar
rights hold.**

Collin Central Appraisal District is the best first Texas secondary-market
parcel spine for Plano, Frisco, McKinney, Allen, and countywide nearby-parcel
discovery. CCAD publishes official GIS downloads and a queryable ArcGIS parcel
FeatureServer, and its open-data page says the exported information is public
domain and provided as-is. The live parcel layer returned `436,519` polygon
records on July 17, 2026 and advertises nightly refreshed appraisal data joined
to parcel geometry.

Primary admitted candidate: `collin_county_tx_parcels_nearby_narrow`.
Official service:
`https://services2.arcgis.com/uXyoacYrZTPTKD3R/ArcGIS/rest/services/CCAD_Parcel_Feature_Set/FeatureServer`.
Primary query endpoint:
`https://services2.arcgis.com/uXyoacYrZTPTKD3R/arcgis/rest/services/CCAD_Parcel_Feature_Set/FeatureServer/4/query`.
Layer: `Parcels` (`4`). Geometry type is polygon in EPSG:2276. Use
`returnGeometry=true` with `outSR=4326` for initial centroid derivation and
retain source polygons for future exact-distance work.

Admitted field mapping: `PROP_ID`/`propID` as canonical property ID;
`geoID`, `gisPropID`, `GlobalID`, `propYear`, and `dataDate` as source aliases
and currentness evidence; `situsBldgNum`, `situsStreetPrefix`,
`situsStreetName`, `situsStreetSuffix`, `situsUnit`, `situsCity`, `situsZip`,
`situsConcat`, and `situsConcatShort` as situs/location evidence; polygon
geometry and derived point-on-surface centroid as spatial evidence; `propType`,
`propSubType`, `propCategoryCode`, `propUseCode`, `comPropFlag`,
`landSizeAcres`, `landSizeSqft`, `legalAbsSubName`, `legalAbsSubBlock`,
`legalAbsSubLot`, `mapID`, `nbhdCode`, `marketAreaCode`, and selected entity
codes as nearby-parcel context. Because CCAD's public-domain notice covers the
exports broadly, owner and valuation fields are technically eligible, but the
first production slice should still suppress them until customer-display UX,
privacy flags, and Texas non-disclosure sale handling are reviewed.

Suppressed fields for the first slice: `ownerID`, `ownerName`,
`ownerNameAddtl`, `ownerAddrLine1`, `ownerAddrLine2`, `ownerAddrCity`,
`ownerAddrState`, `ownerAddrZip`, `ownerAddrCountry`, `taxAgentID`,
`taxAgentName`, all `currVal*`, `prevVal*`, and `noticeVal*` fields,
`deedTypeCd`, `deedNum`, `deedBook`, `deedPage`, `deedEffDate`,
`deedFileDate`, `legalDescription`, improvement/detail fields such as
`imprvYearBuilt`, `imprvClassCd`, `imprvMainArea`, `imprvUnits`,
`imprvCategoryCodes`, raw geometry blobs, `OBJECTID`, editor/creator fields,
and shape-measure fields. Treat deed fields as deed/transfer indicators only;
do not infer sale price in Texas.

Paging strategy: ArcGIS keyset pages with
`where=OBJECTID > {last_objectid}`, `orderByFields=OBJECTID`,
`outFields=PROP_ID,propID,geoID,gisPropID,propYear,dataDate,situsBldgNum,situsStreetPrefix,situsStreetName,situsStreetSuffix,situsUnit,situsCity,situsZip,situsConcat,situsConcatShort,propType,propSubType,propCategoryCode,propUseCode,comPropFlag,landSizeAcres,landSizeSqft,legalAbsSubName,legalAbsSubBlock,legalAbsSubLot,mapID,nbhdCode,marketAreaCode,entityCodes,entitySchoolCode,entityCityCode,entityMUD,entityTIF,entitySBCL,udiPropFlag,udiGroupID,ecoGroupID,propSplitFromPID,GlobalID,OBJECTID`,
`returnGeometry=true`, `outSR=4326`, and `resultRecordCount=1000`. The layer
advertises a `2000` max record count and supports JSON, GeoJSON, and PBF, but
the production connector should keep pages smaller and shard by city or
bounding box for backfills around Plano/Frisco retail opportunities.

Export policy:
`derived_nearby_parcel_context_only_no_raw_collin_cad_resale`. Customer-facing
display/export may include parcel/property ID, situs/location, city, property
type/use, acreage/square-foot land size, derived centroid and distance,
source/currentness dates, and CCAD attribution. Do not expose raw countywide
extracts, owner mailing lists, tax-agent data, valuation tables, deed fields,
legal descriptions, improvement details, or bulk polygon downloads until the
Texas owner/value UX and privacy review explicitly admits those fields.

Dallas County / Dallas remains HOLD. Dallas Central Appraisal District publishes
official 2026 GIS parcel ZIPs and appraisal-roll data, and the City of Dallas
has a Socrata parcel shapefile item under an attribution license, but DCAD's
GIS and data-product pages retain all-rights-reserved footer language. The
city item is also city-limited and not the countywide system of record. Use as
a rights-negotiation target, not production ingestion, until DCAD or counsel
confirms commercial SaaS storage, derived proximity output, display/API/export,
redistribution, and retained snapshots.

Tarrant County / Fort Worth remains HOLD. The official county ArcGIS service
`https://mapit.tarrantcounty.com/arcgis/rest/services/Dynamic/TADParcels/MapServer/0/query`
is technically strong, returned `758,633` polygon records on July 17, 2026,
and exposes `TAXPIN`, `ACCOUNT`, owner, situs, legal, acreage, deed, appraisal,
land/improvement/total value, and geometry fields. The service metadata and
county pages point back to Tarrant Appraisal District as source, but no
affirmative commercial SaaS redistribution grant was verified. Admit only after
TAD/Tarrant grants rights or a bounded no-raw-export policy is approved.

Harris County / Houston remains HOLD. Harris Central Appraisal District's
public data page provides property and GIS downloads and says GIS files update
quarterly, with CAMA and shapefile products that are already documented as
production-capable in the earlier Houston section. The site footer remains all
rights reserved, and no reviewed page grants commercial redistribution,
customer-facing API/export, sublicensing, or retained derivative-database
rights. Continue to treat HCAD as a high-priority licensing target.

Bexar County / San Antonio remains HOLD. Bexar County's own ArcGIS item says
the county does not create or maintain the definitive parcel dataset and points
to Bexar County Appraisal District. The legacy county parcel service
`https://maps.bexar.org/arcgis/rest/services/Parcels/MapServer/0/query`
returned `705,976` records but its metadata references older annual refresh
cadence. The SARA-hosted BCAD production layer
`https://gis.sara-tx.org/ags1/rest/services/FW_Bexar/BCAD_Parcels_PROD/MapServer/0/query`
returned `710,772` records and says the data was requested from BCAD in
December 2025, but the copyright text remains Bexar County Appraisal District
and commercial SaaS storage/display/export rights were not affirmative.

Texas statewide fallback: NARROW HOLD. TxGIO's Land Parcels program is useful
for coverage discovery and county-gap analysis because it compiles appraisal
district parcel data into a statewide schema and provides downloads at no cost.
The same page says county appraisal districts or vendors remain the creators,
refresh cadence varies by county, some attributes may be missing, and the site
content is copyrighted unless otherwise noted. Use TxGIO for scouting and
backfill planning, but do not ingest it as a production nearby-parcel spine
until the exact DataHub license/package for the target counties is reviewed.

Evidence URLs:
`https://collincad.org/open-data-portal/`;
`https://collincad.org/category/gis-downloads/`;
`https://services2.arcgis.com/uXyoacYrZTPTKD3R/ArcGIS/rest/services/CCAD_Parcel_Feature_Set/FeatureServer`;
`https://services2.arcgis.com/uXyoacYrZTPTKD3R/arcgis/rest/services/CCAD_Parcel_Feature_Set/FeatureServer/4`;
`https://www.arcgis.com/home/item.html?id=d49fd61e35f34b53b2982f50220875cb`;
`https://ww.dallascad.org/GISDataProducts.aspx`;
`https://dallascad.org/DataProducts.aspx`;
`https://www.dallasopendata.com/Geography-Boundaries/Parcel-Shapefile/hy5f-5hrv/about`;
`https://mapit.tarrantcounty.com/arcgis/rest/services/Dynamic/TADParcels/MapServer/0`;
`https://hcad.org/hcad-online-services/pdata/`;
`https://hcad.org/pdata/pdata-gis-downloads.html`;
`https://maps.bexar.org/arcgis/rest/services/Parcels/MapServer`;
`https://gis.sara-tx.org/ags1/rest/services/FW_Bexar/BCAD_Parcels_PROD/MapServer/0`;
`https://www.sanantonio.gov/GIS/GISdata`;
`https://www.arcgis.com/home/item.html?id=41dbc36ff1ab4554b54b5f0bb138bf73`;
`https://geographic.texas.gov/stratmap/land-parcels.html`.

## Tennessee / Nashville / Chattanooga / Memphis / Knoxville parcel spine

Decision: NARROW ADMIT for the Tennessee Comptroller IMPACT parcel layer as a
derived nearby-parcel spine for counties maintained by the state. HOLD local
Nashville/Davidson, Chattanooga/Hamilton, Memphis/Shelby, and Knoxville/Knox
parcel feeds until each publisher grants explicit commercial SaaS storage,
display, API output, export, and no-raw-resale rights. Tennessee is not a single
statewide production spine for the target metros because the Comptroller parcel
download page says Chester, Davidson, Hamilton, Hickman, Knox, Montgomery,
Rutherford, Shelby, and Williamson are not maintained by the Comptroller and
must be sourced locally.

Primary admitted candidate:
`tennessee_comptroller_impact_parcels_nearby_narrow`. Official service:
`https://maps.cot.tn.gov/server3/rest/services/IMPACT/Parcels/FeatureServer`.
Primary query endpoint:
`https://maps.cot.tn.gov/server3/rest/services/IMPACT/Parcels/FeatureServer/0/query`.
Live count check on July 17, 2026: `2,172,472` statewide polygons. Use this
source for nearby-parcel discovery in state-maintained counties only, not for
Davidson, Hamilton, Knox, Shelby, or other explicitly excluded counties.

Admitted field mapping: `GISLINK` as canonical parcel ID, `GISLINK2` and
`GlobalID` as source aliases, `COUNTY_ID` and `PARCELWP` as county/work-paper
context, `PARCEL_TYPE` as high-level parcel class, `CALC_ACRE` as acreage, and
polygon geometry in `outSR=4326` as spatial evidence. Suppressed fields until
rights are expanded: any owner, mailing, assessed/appraised value, sale/deed,
legal-description, tax-account, raw bulk geometry export, edit/upload fields,
`OBJECTID`, and shape-measure fields. The layer currently exposes a lean parcel
geometry schema, which fits derived proximity context better than owner/value
evidence.

Paging strategy: ArcGIS keyset pages with
`where=OBJECTID > {last_objectid}`, `orderByFields=OBJECTID`,
`outFields=OBJECTID,GISLINK,GISLINK2,COUNTY_ID,PARCELWP,PARCEL_TYPE,CALC_ACRE,GlobalID`,
`returnGeometry=true`, `outSR=4326`, and `resultRecordCount=2000`. Shard by
`COUNTY_ID` for full-state backfills and skip the Comptroller exclusion counties
unless the local publisher separately authorizes ingestion.

Export policy:
`derived_nearby_parcel_context_only_no_raw_tennessee_comptroller_resale`.
Customer-facing output may include parcel ID, county, acreage, high-level parcel
type, derived centroid/distance, currentness/source attribution, and links back
to the official source. Do not expose raw statewide extracts, bulk geometry
dumps, owner/value/sale data, or county-local assessor fields without
publisher-specific written permission.

Nashville / Davidson County: HOLD. MetroGIS publishes an official `Ownership
Parcels` layer at
`https://maps.nashville.gov/arcgis/rest/services/Cadastral/Parcels/MapServer/0/query`;
live count check on July 17, 2026 remained `286,754` polygons. The layer is
technically excellent, with `APN`/`STANPAR`, situs fields, owner/mailing,
zoning, acreage, appraisal/assessment, sale, and polygon geometry. It supports
pagination and a 10,000-row max record count. Rights remain the blocker:
Nashville's Open Data Executive Order supports public open-data publication but
also says Metro does not grant any right or title to intellectual-property
rights it may have in Open Data, and the reviewed ArcGIS item/license text is
blank. Admit only after Metro Nashville confirms commercial SaaS storage,
derived proximity scoring, customer display/API/export, attribution, retention,
and whether raw geometry may be redistributed.

Chattanooga / Hamilton County: HOLD, with a narrow-admit candidate if rights are
confirmed. Official parcel endpoint:
`https://mapsdev.hamiltontn.gov/hcwa03/rest/services/Live_Parcels/MapServer/0/query`.
Live browser-style count check on July 17, 2026: `168,930` polygons. Candidate
fields: `TAX_MAP_NO`, `GISLINK`, `PBA_NUM`, `MAP`, `GROUP_`, and `PARCEL` as
parcel/source IDs; `STNUM`, `DIRPFX`, `STNAME`, `TYPESFX`, and `ADDRESS` as
situs evidence; `CALCACRES`, `LUCODE`, `CURRENTUSE`, `PROPTYPE`, `DISTRICT`,
`NEIGHCODE`, and `NEIGHBOR_1` as context; polygon geometry as spatial evidence.
Suppress `OWNERNAME1`, `OWNERNAME2`, mailing fields, `LANDVALUE`, `BUILDVALUE`,
`APPVALUE`, `ASSVALUE`, sale date/consideration/book/page fields,
`LEGALDESC1`, `RecordsOnl`, raw geometry blobs, `OBJECTID`, and shape-measure
fields. The service is queryable and current-looking, but the service item has
blank license/access text and Hamilton's GIS disclaimer is an as-is/no-warranty
notice, not an affirmative commercial redistribution grant.

Memphis / Shelby County: HOLD. Official Shelby/ReGIS parcel layer:
`https://gis.shelbycountytn.gov/arcgis/rest/services/Parcel/CERT_Parcel/MapServer/0/query`.
The REST directory describes `Shelby County Assessor of Property Parcels` and
exposes `PARID`, `PARCELID`, owner/mailing, situs, land-use, zoning, longitude,
latitude, tax year, and polygon geometry. Live scripted query attempts were
blocked by Cloudflare on July 17, 2026, and the official iteminfo says the data
is owned by Shelby County Government for ReGIS participants and authorized
agents, may be displayed publicly, and may not be sold or transferred to another
entity without written consent. Do not ingest until ReGIS/Shelby County grants
written commercial SaaS storage/display/API/export permission.

Knoxville / Knox County: HOLD. KGIS exposes official parcel information through
the KGIS/Geocortex stack and references
`https://www.kgis.org/arcgis/rest/services/Maps/GlobalSearch/MapServer`, with a
parcel layer containing `PARCELID`, address, owner, acreage, sale, deed, value,
mailing, status, and geometry fields. Live direct query to the ArcGIS endpoint
returned `401 Unauthorized` on July 17, 2026. KGIS terms prohibit obtaining
materials or information through means not intentionally made available and
reserve rights not expressly granted; the public site is useful for evidence
links and manual verification, but not bulk ingestion or commercial parcel-spine
storage without written KGIS/Knox County/KUB authorization.

Evidence URLs:
`https://maps.cot.tn.gov/server3/rest/services/IMPACT/Parcels/FeatureServer/0`;
`https://comptroller.tn.gov/office-functions/pa/gisredistricting/parcel-data-stewardship.html`;
`https://comptroller.tn.gov/office-functions/pa/gisredistricting/redistricting-and-land-use-maps/parcel-data.html`;
`https://services.arcgis.com/rD2ylXRs80UroD90/arcgis/rest/services/TN_County_Parcel_Map/FeatureServer`;
`https://maps.nashville.gov/arcgis/rest/services/Cadastral/Parcels/MapServer/0`;
`https://maps.nashville.gov/ParcelViewer/`;
`https://www.nashville.gov/departments/planning/mapping-and-gis/map-and-data-sales`;
`https://www.nashville.gov/departments/metro-clerk/legal-resources/executive-orders/mayor-freddie-oconnell/fo018`;
`https://gis.hamiltontn.gov/mapping.html`;
`https://mapsdev.hamiltontn.gov/hcwa03/rest/services/Live_Parcels/MapServer/0`;
`https://gis.hamiltontn.gov/Dev/mapplications.htm`;
`https://assessor.hamiltontn.gov/`;
`https://gis.shelbycountytn.gov/arcgis/rest/services/Parcel/CERT_Parcel/MapServer/0`;
`https://gis.shelbycountytn.gov/public/rest/services/Parcel/CERT_Parcel/MapServer/info/iteminfo`;
`https://www.shelbycountytn.gov/68/Assessor-of-Property?nid=68`;
`https://property.knoxcounty.org/departments/mapping/`;
`https://www.kgis.org/arcgis/rest/services/Maps/GlobalSearch/MapServer`;
`https://www.kgis.org/portal/terms.aspx?portalid=0`.

## South Carolina Parcels: Greenville, Charleston, Richland, Berkeley

**Decision: NARROW ADMIT for Greenville County only; HOLD for Charleston,
Berkeley, Richland/Columbia, and statewide South Carolina until rights or access
improve.**

Primary admitted candidate: `greenville_county_sc_parcels_narrow`.

August 28, 2026 production update: the county endpoint documented below was
stopped. The source now uses the official City of Greenville parcel layer at
`https://citygis.greenvillesc.gov/arcgis/rest/services/GeneralData/GeneralData_WGS84/MapServer/2/query`.
The city describes this layer as weekly county-GIS parcel coverage for the city
and a two-mile buffer. The narrower footprint is explicit; field suppression and
the derived-nearby-parcel-only export policy remain unchanged.

Endpoint:
`https://www.gcgis.org/arcgis/rest/services/GreenvilleJS/Map_Layers_JS/MapServer/52/query`.
Service iteminfo:
`https://www.gcgis.org/arcgis/rest/services/GreenvilleJS/Map_Layers_JS/MapServer/info/iteminfo`.

Live check on July 17, 2026: `243,750` polygon records. The official Greenville
County GIS service is public, queryable, and technically production-ready for a
bounded nearby-parcel spine. The service advertises JSON/geoJSON output, 5,000
record pages, standardized queries, statistics, ordering, pagination, and
polygon geometry. Iteminfo identifies the publisher as `Greenville County GIS
Division, Greenville, South Carolina` and lists `licenseInfo: Public Access`.
Greenville County's public GIS site says the system supports real estate tax
assessment, economic development, planning/land development, emergency services,
and citizen access to GIS data via the Internet.

Field mapping:
- Parcel ID: `PIN`.
- Situs/location: combine `STRNUM` and `LOCATE`; retain `JURIS`, `DIST`,
  `MKTAREA`, `LANDUSE`, `PROPTYPE`, `IMPROVED`, and `SUBDIV` as bounded context.
- Acreage: `TACRES`.
- Geometry: polygon `SHAPE`, transformed to WGS84 for storage; derive
  point-on-surface centroid for radius indexing and nearby-parcel ranking.
- Currentness/provenance: service endpoint, iteminfo URL, source retrieval
  timestamp, `OBJECTID` transport key, and Greenville County attribution.

Suppressed fields for narrow admit: `OWNAM1`, `OWNAM2`, `STREET`, `CITY`,
`STATE`, `ZIP5`, `NAMECO`, `POWNNM`, `DEEDDATE`, `CUBOOK`, `CUPAGE`, `PLTBK1`,
`PPAGE1`, `DESCR`, `SLPRICE`, `FAIRMKTVAL`, `TAXMKTVAL`, `TOTTAX`, `PAIDDATE`,
`SQFEET`, `BEDROOMS`, `BATHRMS`, `HALFBATH`, raw geometry blobs, `OBJECTID`,
and shape-measure fields. Owner, mailing, deed, value, tax, sale, and detailed
residential-improvement attributes require a stronger written commercial SaaS
storage/display/export grant before customer-facing use.

Paging strategy: ArcGIS keyset pages using
`where=OBJECTID > {last_objectid}`, `orderByFields=OBJECTID`,
`outFields=PIN,STRNUM,LOCATE,JURIS,DIST,MKTAREA,LANDUSE,PROPTYPE,IMPROVED,SUBDIV,TACRES,OBJECTID`,
`returnGeometry=true`, `outSR=4326`, and `resultRecordCount=5000`. Use `PIN` as
canonical parcel identity; use `OBJECTID` only as transport state.

Export policy:
`derived_nearby_parcel_context_only_no_raw_greenville_county_sc_resale`.
Customer-facing output may include parcel ID, situs/location, acreage,
property/use class context, derived centroid, distance/radius relationship,
source attribution, and retrieval timestamp. Do not expose owner names, mailing
addresses, deeds, values, taxes, sale prices, raw county extracts, bulk geometry
downloads, or raw GIS/CAMA fields without a written Greenville County license.

Charleston County / Charleston: HOLD. The official county CONNECT map service
has a technically useful parcel-boundary layer at
`https://gisccapps.charlestoncounty.org/arcgis/rest/services/CONNECT/CONNECT_MAP/MapServer/6/query`.
Live check on July 17, 2026: `197,284` polygon records with `PID`, `PRCCD`,
`ACRES_CAL`, polygon geometry, `CREATED_DATE`, `LAST_EDITED_DATE`, `GlobalID`,
and shape measures; the service supports JSON/geoJSON/PBF, ordering,
statistics, and pagination. However, iteminfo has blank license terms, and a
related official Charleston County parcel item states the parcel layer is
updated weekly and that data may not be shared without permission. Charleston's
public viewer disclaimer also limits the map to illustrative/reference use.
Do not ingest until Charleston County GIS grants commercial SaaS
storage/display/API/export rights, or admit only after a specific no-raw-export
license is received.

Berkeley County: HOLD. The official Berkeley County GIS internet service
contains a queryable `TMS Numbers` polygon layer at
`https://gis.berkeleycountysc.gov/arcgis/rest/services/internet/MapServer/6/query`.
Live check on July 17, 2026: `122,179` polygon records with
`O_TMS_NODASH`, `Section_`, `DevAgreement`, `WindDebrisArea`, and geometry.
The county GIS site says the public internet database is updated weekly, while
the advanced map says data updates nightly; Berkeley's pricing page separately
lists `Parcels with Attributes` as digital data available by contacting the GIS
office, and the public viewer disclaimer frames the data as public-service
reference material. A separate ArcGIS Online `parcels_berkeley_county`
FeatureServer advertises December 2024 parcels but returns `Token Required` to
anonymous queries. Hold production ingestion until Berkeley County provides
written commercial SaaS storage/display/export permission or an explicit public
data license for a bounded geometry-only feed.

Richland County / Columbia: HOLD. Richland County's official GIS page confirms
county GIS supports the Tax Assessor, Planning, Zoning, and related county
functions, and its Dataviewer includes parcels, addresses, zoning, tax
districts, and other datasets. The public direct service is a cartographic WMS
at `https://geoserver.richlandmaps.com/geoserver/wms?tiled=true&`; the county
page says GIS data is available for purchase subject to a data licensing
agreement. The corresponding WFS capabilities probe at
`https://geoserver.richlandmaps.com/geoserver/ows?service=WFS&version=2.0.0&request=GetCapabilities`
returns `Service WFS is disabled`, so there is no official anonymous feature
pagination path for parcel polygons and attributes. The Columbia city GIS
services are useful planning overlays but are not a countywide parcel/CAMA
substitute and include resale/product-sharing restrictions. Admit only from a
licensed Richland County GIS/Assessor extract.

Statewide South Carolina: HOLD. No official statewide parcel polygon/CAMA feed
was verified. South Carolina Revenue and Fiscal Affairs publishes authoritative
GIS, mapping, county-boundary, district, imagery, and local-government property
tax summary resources, and SCDNR publishes authoritative natural-resource GIS
data, but neither reviewed state source exposes a statewide parcel spine with
parcel IDs, situs, geometry, and a bulk commercial SaaS reuse grant. Continue
using admitted county feeds as the parcel spine and revisit RFA/SCDNR if a
state cadastral program is published.

Evidence URLs:
`https://www.gcgis.org/Index.html`;
`https://www.gcgis.org/arcgis/rest/services/GreenvilleJS/Map_Layers_JS/MapServer`;
`https://www.gcgis.org/arcgis/rest/services/GreenvilleJS/Map_Layers_JS/MapServer/52`;
`https://www.gcgis.org/arcgis/rest/services/GreenvilleJS/Map_Layers_JS/MapServer/info/iteminfo`;
`https://citygis.greenvillesc.gov/arcgis/rest/services/AddressSearch/Property/MapServer/3`;
`https://www.charlestoncounty.gov/departments/gis/`;
`https://gisccapps.charlestoncounty.org/arcgis/rest/services/CONNECT/CONNECT_MAP/MapServer`;
`https://gisccapps.charlestoncounty.org/arcgis/rest/services/CONNECT/CONNECT_MAP/MapServer/6`;
`https://gisccapps.charlestoncounty.org/arcgis/rest/services/CONNECT/CONNECT_MAP/MapServer/info/iteminfo`;
`https://gisccweb.charlestoncounty.org/public_search/`;
`https://911gis.charlestoncounty.org/server/rest/services/CDC_GIS/Critical_Infrastructure_SC_House_Members/FeatureServer/0/iteminfo`;
`https://gis.berkeleycountysc.gov/`;
`https://berkeleycountysc.gov/bcgis-websites/`;
`https://gis.berkeleycountysc.gov/pages/prices/`;
`https://gis.berkeleycountysc.gov/pages/faq/`;
`https://gis.berkeleycountysc.gov/arcgis/rest/services/internet/MapServer/6`;
`https://services7.arcgis.com/bXXSr0Lm29B0aD4l/ArcGIS/rest/services/parcels_berkeley_county/FeatureServer/0`;
`https://www.richlandcountysc.gov/Property-Business/Mapping-and-Records/Geographic-Information-Systems`;
`https://geoserver.richlandmaps.com/geoserver/wms?tiled=true&`;
`https://geoserver.richlandmaps.com/geoserver/ows?service=WFS&version=2.0.0&request=GetCapabilities`;
`https://www.richlandcountysc.gov/Property-Business/Mapping-and-Records/Property-Search`;
`https://gis.columbiasc.gov/`;
`https://rfa.sc.gov/mapping`;
`https://rfa.sc.gov/data-research/local-government/property-tax`;
`https://www.dnr.sc.gov/gis.html`.

## Milwaukee / Milwaukee County, Wisconsin

**Decision: commercial-redistribution-rights hold.**

- Milwaukee County GIS and Land Information publishes an official countywide
  `Parcels_w_Officials` FeatureServer with 280,759 live parcel polygons in the
  reviewed count and complete `Taxkey` coverage. The layer exposes municipality,
  tax key, owner name fields, owner mailing address, parcel/situs address,
  acreage, legal description, assessed value, land value, improvement value,
  fair-market value, tax year, gross/net tax, assessment description, zoning
  description, parcel ZIP, property-information links, and polygon geometry.
- The API is technically production-capable for a guarded full snapshot. It
  supports JSON, GeoJSON, and PBF query output, standardized queries,
  statistics, order-by, distinct, pagination, distance queries, datum
  transformation, and 2,000-row pages. Request `outSR=4326`, page by
  `OBJECTID`/result offset only as transport state, and use `Taxkey` as the
  canonical parcel identity. The reviewed coverage counts were 280,377
  non-null `Owner_1`, 280,351 non-null `Parcel_Addr`, 253,137 non-null
  `AssessedValue`, and complete `Zoning_Desc`.
- Geometry is adequate for nearby parcel discovery. Store county polygons for
  exact boundary distance and derive `ST_PointOnSurface` centroids for radius
  indexing because the service does not advertise server-returned geometry
  centroids. Preserve condominium and stacked parcel behavior: the county item
  says there is one polygon per `TAXKEY` and that stacked polygons represent
  condominium parcels, so do not collapse shared footprints into a single owner
  or value record.
- The City of Milwaukee MPROP service is a useful city-only supplement but not
  a countywide substitute. It exposes 159,964 city parcel records in the
  reviewed count, with owner, assessment, conveyance date, zoning, land-use,
  situs, owner mailing, and polygon fields, and the City download page says
  parcel outlines are updated weekly. It should remain supplemental for city
  zoning/land-use corroboration only after rights are cleared.
- The Wisconsin Statewide Parcel Map V12 service is also only a fallback
  supplement for geometry and normalized statewide schema. It is current as of
  the June 30, 2026 release path and exposes parcel ID, owner, mailing and site
  address, assessed/fair-market value, property class, acres, latitude,
  longitude, and polygon geometry. The State Cartographer page says local land
  information sites should be consulted for the most current and comprehensive
  data, so Milwaukee County remains the preferred source.
- Rights are the blocker. The Milwaukee County ArcGIS item is public and
  authoritative, but its license text is a reference-use disclaimer and warranty
  limitation; it does not grant commercial SaaS storage, derived nearby-parcel
  scoring, customer display/API/export, source redistribution, sublicensing,
  historical retention, or downstream terms for owner/value/tax fields. The
  City GIS download page similarly provides accuracy and no-liability
  disclaimers, not an affirmative reuse or redistribution grant. The Wisconsin
  statewide page says the data is free of charge but does not supply an exact
  license covering commercial redistribution of Milwaukee owner/value records.

Admission requires written Milwaukee County GIS/Land Information authorization,
or an exact public open-data license, covering the county parcel FeatureServer
and assessor-derived owner/value/tax/zoning fields for commercial storage, bulk
refresh, derived nearby-parcel scoring, customer display/API/export,
redistribution, sublicensing, historical retention, privacy suppression,
attribution/disclaimer requirements, and termination effects. If licensed, map
`Taxkey` to canonical parcel ID, `MuniName` to municipality, `Parcel_Addr` and
`Parcel_Zip` to situs address, `Owner_1`/`Owner_2`/`Owner_3` and `Owner_Addr`
to owner evidence, `AssessedValue`/`LandValue`/`ImpValue`/`Fair_Mkt_Val` and
`Tax_Yr` to valuation facts, `Assessment_Descrip` to use/class, `Zoning_Desc`
to zoning description, `Acres`/`Shape__Area` to area, `Parcel_Info_Link` to
source evidence URL, and polygon geometry to parcel boundary with a derived
point-on-surface centroid.

Primary sources reviewed: Milwaukee County parcel layer
`https://lio.milwaukeecountywi.gov/arcgis/rest/services/PropertyInfo/Parcels_w_Officials/FeatureServer/0`;
Milwaukee County ArcGIS property-information item
`https://www.arcgis.com/sharing/rest/content/items/e321f4be5b5d410fa62d9ca63001925f?f=pjson`;
Milwaukee County cadastral item
`https://www.arcgis.com/sharing/rest/content/items/8a869fc8d3bf4aa09264976d4b3899d1?f=pjson`;
City of Milwaukee MPROP service
`https://milwaukeemaps.milwaukee.gov/arcgis/rest/services/property/parcels_mprop/FeatureServer`;
City of Milwaukee GIS download/disclaimer page
`https://city.milwaukee.gov/mapmilwaukee/DownloadMapData3497`;
Wisconsin Statewide Parcel Map data page
`https://www.sco.wisc.edu/parcels/data/`;
Wisconsin V12 parcel service
`https://services3.arcgis.com/n6uYoouQZW75n5WI/arcgis/rest/services/Wisconsin_Statewide_Parcels_DB/FeatureServer/0`.

## Minneapolis / Hennepin County, Minnesota

**Decision: admitted to production.**

- Hennepin County's official County Parcels layer is a production-grade parcel
  source for nearby parcel discovery. It contains taxed and tax-exempt parcel
  polygons, including stacked multi-PID parcels that share geometry but retain
  different parcel IDs and tax attributes. The layer is compiled monthly by
  Hennepin County GIS from Survey Division parcel geometry and monthly property
  tax system extracts.
- Commercial reuse rights pass for the county parcel source. Hennepin County
  has publicly described its GIS open data as free for public use without a
  license, and MetroGIS documents Hennepin's adopted open-data resolution in
  the seven-county open geospatial data program. Retain Hennepin attribution,
  source URLs, and the county disclaimer that data is provided as-is, without
  warranty, and is not legal, engineering, or survey evidence.
- Use the Hennepin `PID` as canonical parcel identity and preserve `PID_TEXT`
  as the display/legacy text form. Do not collapse stacked multi-PID parcels:
  use a derived physical-parcel group for identical geometry/centroid records,
  while keeping each `PID` as a separate tax, owner, value, and sale fact.
- Field mapping: `HOUSE_NO`, `FRAC_HOUSE_NO`, `STREET_NM`, `CONDO_NO`,
  `MUNIC_NM`, and `ZIP_CD` map to situs address components; `OWNER_NM` maps to
  owner name evidence; `TAXPAYER_NM` through `TAXPAYER_NM_3`,
  `MAILING_MUNIC_NM`, and `ZIP_CD` map to taxpayer/mailing evidence when
  displayed under public-record controls; `SALE_DATE`, `SALE_PRICE`,
  `SALE_CODE`, and `SALE_CODE_NAME` map to latest-sale evidence; `MKT_VAL_TOT`,
  `TAXABLE_VAL_TOT`, `NET_IMPRV_AMT`, `LAND_MV1` through `LAND_MV4`,
  `BLDG_MV1` through `BLDG_MV4`, and `TOTAL_MV1` through `TOTAL_MV4` map to
  valuation facts; `PR_TYP_CD1` through `PR_TYP_CD4` and `PR_TYP_NM1` through
  `PR_TYP_NM4` map to property-use/classification evidence; `BUILD_YR`,
  `PARCEL_AREA`, `MUNIC_CD`, `SCHOOL_DIST_NO`, `TIF_PROJECT_NO`, and
  `PROPERTY_STATUS_CD` map to parcel characteristics and jurisdiction facts;
  `DIV_STATUS_DATE`, `DIV_PEND_IND`, `CO_OP_IND`, `PRI_SEC_CODE`, legal
  description fields, and `TORRENS_TYP` map to lifecycle/title/legal evidence.
- Geometry handling: request polygon geometry from the county layer with
  `outSR=4326`, store the source boundary for exact distance, and use supplied
  `LAT`/`LON` as the radius-search centroid. If centroid fields are missing or
  outside the polygon, fall back to `ST_PointOnSurface` from the stored polygon.
  Retain `Shape.STArea()`, `Shape.STLength()`, and `PARCEL_AREA` for quality
  checks rather than as legal acreage.
- Page the ArcGIS layer through deterministic 2,000-row guarded full snapshots.
  Use the query endpoint with `where=OBJECTID > {last_objectid}`,
  `orderByFields=OBJECTID`, `resultRecordCount=2000`, selected `outFields`,
  `returnGeometry=true`, `outSR=4326`, and `f=geojson` or JSON. Treat
  `OBJECTID` only as transport state; validate unique non-null `PID`, duplicate
  stacked-geometry behavior, geometry validity, row counts, schema fingerprint,
  and source metadata before retiring missing parcels.
- City of Minneapolis sources are supplemental. The city open-data policy
  supports public reuse and API/bulk download, and the city's primary zoning
  FeatureServer and overlay FeatureServer are useful for spatial zoning
  enrichment inside Minneapolis. They do not replace the county parcel source
  because they are zoning polygons/overlays, not countywide tax parcel owner,
  value, sale, and PID records. Spatially intersect county parcel polygons with
  Minneapolis zoning layers for city-only zoning facts, retaining city
  disclaimer and update evidence.
- Owner, taxpayer, value, tax, and sale facts are public-record evidence, not
  title verification or market estimates. Downstream product surfaces should
  keep source attribution, show assessment/sale caveats, honor suppression or
  privacy controls if the county changes publication rules, and avoid raw bulk
  source-data export unless the current rights record is rechecked.

Production source: `hennepin_mn_county_parcels`. Primary endpoint:
`https://gis.hennepin.us/arcgis/rest/services/HennepinData/LAND_PROPERTY/MapServer/1`.
Query endpoint:
`https://gis.hennepin.us/arcgis/rest/services/HennepinData/LAND_PROPERTY/MapServer/1/query`.
Optional Minneapolis zoning supplements:
`https://services.arcgis.com/afSMGVsC7QlRK1kZ/ArcGIS/rest/services/msvcCPED_PrimaryZoning_20170126/FeatureServer/0`
and
`https://services.arcgis.com/afSMGVsC7QlRK1kZ/arcgis/rest/services/Planning_Zoning_Overlay/FeatureServer`.
Rights evidence: Hennepin GIS open-data announcement
`https://content.govdelivery.com/accounts/MNHENNE/bulletins/b33f46`;
MetroGIS parcel/open-data pages
`https://metrogis.org/how-do-i-get/parcel-data/` and
`https://metrogis.org/projects/free-open-data.aspx`; City of Minneapolis open
data policy
`https://www.minneapolismn.gov/government/charter-and-code-of-ordinances/city-policies/open-data-policy/`.

## Oklahoma / Oklahoma County / Tulsa / Cleveland County parcel spine

Decision: HOLD for production ingestion until publisher rights are explicit.
Oklahoma has several technically strong parcel services, but none passed the
current Phase 2 commercial SaaS storage, display, API/export, redistribution,
sublicensing, and historical-retention gate. Treat Oklahoma County and Tulsa
County as high-priority permission targets; treat Cleveland County/Norman as a
manual/local-contact target unless a countywide public parcel API with clear
rights is later published.

Oklahoma County / Oklahoma City: HOLD. The public Oklahoma County tax parcel
FeatureServer is technically production-ready: live check on July 17, 2026
returned `336,992` polygon records, 2,000-row pages, query support, parcel and
account identifiers, situs/location, owner and mailing fields, values, taxes,
legal/subdivision context, acreage, sale/transfer fields, and polygon geometry.
The ArcGIS item is tagged as Oklahoma County tax parcels and says no special
restrictions are provided, but the item metadata has blank `licenseInfo`,
`accessInformation`, description, and copyright text. The Assessor site provides
accuracy/no-warranty and non-survey disclaimers plus paid assessment-roll,
ownership, sales, and GIS geodatabase copy procedures, but no affirmative grant
for commercial Build Signals storage, customer display/API/export, or resale.

If Oklahoma County grants written permission, onboard
`oklahoma_county_ok_parcels_permissioned`. Endpoint:
`https://services8.arcgis.com/euhkr1dAJeQBIjV0/arcgis/rest/services/TaxParcelsPublics_view/FeatureServer/0/query`.
Map `accountno` as canonical parcel/tax account ID; preserve `propertyid`,
`PARCELNB_1`, `pin`, `mapnumber`, `parentaccount`, and `globalid` as aliases;
map `location` and `locationcity` to situs evidence; map polygon geometry in
`outSR=4326` and derive point-on-surface centroids for radius search. Suppress
until licensed: `name1`, `name2`, `name3`, `mailingaddress1`, `city`, `state`,
`zipcode`, `currentmarket`, `currentassessed`, `currenttaxable`, `netassessed`,
`landvalue`, `saledate`, `SalePrice`, `RecordedDate`, `TransferId`,
`SalesValidity`, `legal`, raw geometry exports, and shape-measure fields. Use
ArcGIS keyset pages: `where=OBJECTID > {last_objectid}`,
`orderByFields=OBJECTID`, selected `outFields`, `resultRecordCount=2000`,
`returnGeometry=true`, `outSR=4326`, and JSON/geoJSON. Permissioned export
policy: `permissioned_oklahoma_county_parcel_context_no_raw_resale_unless_granted`.

Tulsa County / Tulsa: HOLD, with two official-looking technical candidates.
The current INCOG/Tulsa County Assessor parcel layer at
`https://map11.incog.org/arcgis11wa/rest/services/TCSO_CAD_SDE_feature_layers/MapServer/16/query`
returned `283,307` polygons on July 17, 2026 and is labeled "Tulsa County
Parcels. Last updated October 10, 2025" with `Tulsa County Assessor`
attribution. It exposes account/parcel numbers, situs/property address,
business name, owner and mailing fields, legal fields, sale fields,
classification/context, and polygon geometry. Its license text is a disclaimer
for illustrative use, no warranty, and independent verification; it includes
`Copyright 2015 INCOG` but not commercial SaaS redistribution rights. The older
hosted layer at
`https://services6.arcgis.com/afI6w4ZBSVtA8tmF/arcgis/rest/services/Tulsa_County_Parcels/FeatureServer/3/query`
returned `278,881` polygons but has a 2023 data edit date and blank license
metadata, so it is a fallback evidence source only.

If Tulsa County/INCOG grants written permission, onboard
`tulsa_county_ok_parcels_permissioned` from the INCOG MapServer layer. Map
`AccountNo`/`ACCT_NUM` as tax account identity and `ParcelNo` as parcel alias;
map `PropertyAddress`, `PropertyCity`, `PropertyZIP`, `SiteCity`, and address
components to situs evidence; map polygon geometry in `outSR=4326` and derive
centroids; map `PropertyGroup`, `AcctType`, `UseCode`, `Neighborhood`,
`PropertyType`, `Quality`, and `Condition` only as assessor context. Suppress
until rights are expanded: `Name1`, `Name2`, `Owner`, mailing fields,
`BusinessName` if treated as taxpayer/occupant evidence, `SaleDate`,
`DocumentDate`, `ReceptionNo`, `DeedType`, sale confirmation/validity fields,
legal descriptions, value fields discovered in schema, raw geometry exports,
`OBJECTID`, and shape-measure fields. Page by `OBJECTID` with 2,000-row keyset
pages. Permissioned export policy:
`permissioned_tulsa_county_parcel_context_no_raw_resale_unless_granted`.

Cleveland County / Norman: HOLD. Cleveland County's official Assessor page says
the county maintains roughly `115,000` parcels and its general-information page
states the assessor lists and maintains taxable real and personal property, but
no supported countywide public bulk/API parcel feed with commercial reuse terms
was verified. The City of Norman GIS page says the city maintains GIS layers
including property ownership patterns and provides an open data/mapping site;
Norman's website policy says public information is generally available to copy
or distribute except artwork, logo, and third-party applications. That is not
enough to admit county assessor parcels without a verified parcel endpoint,
source steward, refresh/currentness, and field-level rights. The Moore parcel
FeatureServer is only a narrow city/damage-assessment-era layer: live check
returned `7,649` polygons, the item references Cleveland County Assessor data,
and its license text says "For damage assessment"; do not use it as the
Cleveland County/Norman parcel spine.

Statewide Oklahoma: HOLD. OGI's `Statewide Parcels-2/1/2026` metadata says PRP
compiled county assessor parcel polygons for OGI distribution and that the most
current production version remains with each county. It also says the data is
distributed free to the public for view-only access, has no download
functionality, access constraints are restricted, and is for viewing or OGC WMS
only. This cannot support Build Signals parcel storage, enrichment, proximity
queries, customer display, or export.

Oklahoma City municipal layers remain supplemental only. The OKC data portal
and ArcGIS zoning/lots services expose zoning, non-zoning parcels, overlays,
and platted lots, but they are not countywide assessor owner/value/sale parcel
sources and city terms previously reviewed do not clear redistribution/resale.

Release condition for Oklahoma: obtain written authorization or an exact public
license from Oklahoma County Assessor/GIS, Tulsa County Assessor/INCOG, or
Cleveland County/Norman covering commercial storage, scheduled bulk refresh,
derived nearby-parcel scoring, customer display/API/export, redistribution or
no-raw-export limits, sublicensing/contractor use, retention/takedown,
attribution, disclaimers, and privacy suppression. Until then, Oklahoma parcel
work should stay in the source-target list, not the production catalog.

Evidence URLs:
`https://services8.arcgis.com/euhkr1dAJeQBIjV0/arcgis/rest/services/TaxParcelsPublics_view/FeatureServer/0`;
`https://www.arcgis.com/sharing/rest/content/items/244ff1c03cf34c459092e10142b13b01?f=pjson`;
`https://www.oklahomacounty.org/elected-offices/assessor/search`;
`https://oklahomacounty.org/Elected-Offices/Assessor/PageYear8068/2037/PageMonth8068/3`;
`https://ogidev.okmaps.org/OGI/RestDataAccessItem.aspx?UUID=7c55e990-048e-499d-a20c-58fc5b730562`;
`https://map11.incog.org/arcgis11wa/rest/services/TCSO_CAD_SDE_feature_layers/MapServer/16`;
`https://map11.incog.org/arcgis11wa/rest/services/TCSO_CAD_SDE_feature_layers/MapServer/16/iteminfo`;
`https://services6.arcgis.com/afI6w4ZBSVtA8tmF/arcgis/rest/services/Tulsa_County_Parcels/FeatureServer/3`;
`https://www.arcgis.com/home/item.html?id=a420c60d63084ee7b004f3c333b34c69`;
`https://www.clevelandcountyok.com/129/County-Assessor`;
`https://clevelandcountyok.com/350/General-Information`;
`https://www.normanok.gov/your-government/departments/planning-and-community-development/gis-services`;
`https://www.normanok.gov/your-government/departments/information-technology/conditions-and-use-policy`;
`https://services.arcgis.com/DO4gTjwJVIJ7O9Ca/ArcGIS/rest/services/Moore_Parcels/FeatureServer/0`.

## Louisville / Jefferson County, Kentucky

**Decision: narrow geometry/situs/zoning admit; owner, value, and sale hold.**

- LOJIC's official open parcel layer is an admissible geometry and parcel-ID
  spine for nearby parcel discovery. It exposes 293,219 polygon records with
  `PARCELID`, `LRSN`, `PARCEL_TYPE`, `GLOBALID`, `PIN`, `SHAPE.AREA`, and
  `SHAPE.LEN`; the data.gov record says the parcels are maintained by the
  Jefferson County Property Valuation Administrator, updated daily, and that
  `LRSN` is the unique parcel identifier. Boundary data is explicitly not legal
  survey accurate.
- Use `LRSN` as the canonical source identity when populated, with `PARCELID`
  as the canonical display parcel number and join key to LOJIC address points.
  Preserve `GLOBALID`, `PIN`, `PARCEL_TYPE`, `OBJECTID`, source service URL,
  source item ID, and snapshot metadata as raw evidence. Keep right-of-way and
  indeterminate-land parcel types out of customer-facing nearby opportunity
  scoring unless the product explicitly wants non-tax parcel context.
- Geometry is suitable for radius search after normalization. Request parcel
  polygons with `returnGeometry=true` and `outSR=4326`, store the polygon for
  exact distance, and derive a point-on-surface centroid for coarse radius
  indexing because the parcel layer does not support server-returned geometry
  centroids. Retain `SHAPE.AREA` and `SHAPE.LEN` only as source QA facts, not
  legal acreage.
- LOJIC address points are admitted as a situs/context supplement, not as a
  replacement parcel universe. The official address service exposes 450,447
  point records with `PARCELID`, `LRSN`, `FULL_ADDRESS`, parsed house/street/unit
  fields, `ZIPCODE`, `MUNI_NAME`, `NH_NAME`, `ZONE_NAME`, `ZONING_CODE`,
  `LATITUDE`, `LONGITUDE`, `STATE`, and point geometry. Join active address
  points to parcels by `LRSN` and `PARCELID`, keeping one-to-many address
  evidence rather than collapsing multi-address parcels.
- LOJIC zoning is an admitted optional enrichment. The official zoning layer has
  4,891 polygons with `ZONING_CODE`, `ZONING_NAME`, `ZONING_TYPE`, and geometry.
  Prefer spatial intersection against parcel polygons for parcel-level zoning
  evidence; use address-point `ZONING_CODE`/`ZONE_NAME` only as address-level
  context and retain the source/date because zoning can differ within or near
  parcel boundaries.
- Page each ArcGIS layer through deterministic guarded full snapshots:
  `where=OBJECTID > {last_objectid}`, `orderByFields=OBJECTID`,
  `resultRecordCount=2000`, selected `outFields`, `returnGeometry=true`,
  `outSR=4326`, and `f=geojson` or JSON. Treat `OBJECTID` only as transport
  state; validate row counts, non-null/unique `LRSN` coverage in the parcel
  layer, duplicate geometry behavior, geometry validity, schema fingerprint,
  service item IDs, and source metadata before retiring missing parcels.
- Rights pass only for LOJIC open data under the published PDDL-compatible terms.
  LOJIC says partner data, including Jefferson County PVA partner data, may be
  copied, distributed, stored, used for derivative works, publicly displayed,
  and made available to end users, with "Mapping Data Source: LOJIC" citation
  encouraged and no warranty or indemnity. Keep attribution/disclaimer evidence
  with every source snapshot and recheck rights quarterly because terms may
  change without notice.
- Owner, assessed-value, land/improvement value, detailed assessment history,
  sale/deed history, photos, sketches, property tax facts, and detailed
  characteristics remain on hold. The Jefferson County PVA subscription pages
  describe those richer fields, but the subscription terms restrict contents to
  personal/internal business use, prohibit copying or storing for other than
  personal noncommercial use without prior written consent, and prohibit
  reproducing, duplicating, selling, reselling, or exploiting the service without
  express written permission. Do not scrape the PVA search/subscription portal or
  use subscription exports for customer display/API/export unless written PVA
  permission grants commercial SaaS storage, derived nearby results, customer
  display, redistribution/API output, retention, refresh, privacy suppression,
  and termination rights.

Production source: `louisville_jefferson_ky_lojic_parcels_narrow`.
Primary parcel endpoint:
`https://gis.lojic.org/maps/rest/services/LojicSolutions/OpenDataPVA/MapServer/1`.
Parcel query endpoint:
`https://gis.lojic.org/maps/rest/services/LojicSolutions/OpenDataPVA/MapServer/1/query`.
Address supplement:
`https://gis.lojic.org/maps/rest/services/LojicSolutions/OpenDataAddresses/MapServer/0`.
Zoning supplement:
`https://gis.lojic.org/maps/rest/services/LojicSolutions/OpenDataDevelopment/MapServer/15`.
Catalog and rights evidence:
`https://catalog-old.data.gov/dataset/jefferson-county-ky-parcels-c8c6c`;
`https://www.lojic.org/data/liability-statement`; PVA rights and field-gap
evidence:
`https://jeffersonpva.ky.gov/faq/why-do-i-need-to-subscribe-to-the-pva/` and
`https://jeffersonpva.ky.gov/terms-and-conditions/subscription-terms-of-service/`.

## New Castle County / Wilmington, Delaware

**Decision: narrow admit for Delaware FirstMap parcel proximity; county
assessor owner/value/sale sources remain on commercial redistribution-rights
hold.**

- Production source: `delaware_firstmap_statewide_parcels_narrow`. Delaware
  Open Data metadata for `Delaware FirstMap Endpoints` marks the endpoint
  catalog Public Domain, with Department of Technology and Information
  attribution. Use the official statewide `DE_StateParcels` polygon layer for
  parcel PIN, acreage, county, source update date, polygon geometry, and
  server-returned centroid.
- Field mapping: `PIN` -> canonical parcel/source identity and physical parcel
  group; `COUNTY` -> county; `ACRES` -> land area in square feet; `UPDATED` ->
  observed/source update date; publisher `centroid.x`/`centroid.y` -> WGS84
  radius-search point. Request `returnGeometry=true`, `returnCentroid=true`,
  `outSR=4326`, selected `outFields`, and keyset pages ordered by `OBJECTID`.
- Export policy:
  `derived_nearby_parcel_context_only_no_raw_delaware_firstmap_resale`.
  Customer display/export may include parcel ID, county, acreage, derived
  centroid/distance, boundary relationship, currentness, and FirstMap
  attribution. Suppress owner, situs/mailing address, valuation, sale/deed,
  legal description, zoning, raw parcel extracts, and bulk geometry/source-file
  resale.

- New Castle County GIS has a strong technical candidate for countywide parcel
  context, including Wilmington. The public hosted FeatureServer item
  `NCCDE Static Tax Parcels - 3-13-2026` is sourced to New Castle County GIS,
  is public, has 203,678 polygon records, and describes the data as tax parcels
  with ownership in New Castle County as of March 13, 2026. The layer has
  complete `PRCLID` and `ADDRESS` coverage in the audited count check, with
  only one null `CNTCTLAST` owner-name row.
- The layer exposes parcel identity, situs, owner mailing, land-size, parcel
  class, municipality/hundred, subdivision, frontage/depth, and polygon
  geometry. Candidate canonical mappings would be `PRCLID` or `PARCELNO` to
  `external_parcel_id`, `ADDRESS` plus parsed `STNO`/`PREDIR`/`STNAME`/
  `SUFFIX`/`POSTDIR`/`PROPCITY`/`PROPSTATE`/`PROPZIP` to situs address,
  `CNTCTLAST` to owner name, `OWNADDR`/`OWNADDR2`/`OWNCITY`/`OWNSTATE`/
  `OWNZIP`/`OWNCOUNTRY` to owner mailing address, `LOTSZ` to land acres,
  `LOTDPTH` and `LOTFRONTAG` to parcel dimensions, `PROPCLASS` to property use
  class, and `TAXAREA`/`INCORP`/`SUBDIV` to jurisdiction/context facts.
- Geometry is production-usable if rights are cleared. Request the polygon
  layer with `outSR=4326` and `returnGeometry=true`; store polygons for exact
  distance and derive an internal point-on-surface centroid. The service also
  supports `returnCentroid=true`, pagination, order-by, and GeoJSON/PBF output.
  Use guarded full snapshots with `where=OBJECTID > {last_objectid}`,
  `orderByFields=OBJECTID`, `resultRecordCount=2000`, selected `outFields`, and
  `f=geojson` or JSON. Treat `OBJECTID` only as cursor state, not identity.
- The county's separate live parcel boundary MapServer remains a useful
  fallback geometry/source-link layer. It exposes `PRCLID`, `CORP_ID`,
  `ParcelDetails`, `BuildingSketch`, and polygons with 1,000-row pages, but it
  omits situs, owner, value, sale, and zoning attributes.
- New Castle County's published GIS data dictionary confirms downloadable
  parcel products, including `Owners.gdb.zip`, parcel boundaries, parcel
  points, address points, and zoning. The dictionary describes the ownership
  dataset as tax parcel addresses with ownership details and property class, and
  its zoning layer as revised quarterly but not necessarily official-current.
- Assessed values, land/improvement values, and sale consideration are not in
  the reviewed parcel FeatureServer or county GIS dictionary. The county parcel
  search/tax pages may expose tax and assessment details for individual parcels,
  but no official reviewed bulk/API source with commercial reuse rights was
  found. Do not scrape parcel-search or tax-bill pages to fill these gaps.
- Rights fail the production gate. The ArcGIS item has `licenseInfo: null` and
  no attribution text. New Castle County's official disclaimer provides data
  "as is" and reserves the right to discontinue data feeds and require
  termination of displaying, distributing, or otherwise using data. Public
  access and downloadable files are not enough for commercial SaaS storage,
  customer display/API output, export, redistribution, derived databases,
  retention, or sublicensing.
- Delaware FirstMap does not replace the county owner/situs parcel source. The
  reviewed state parcel layer exposes only `PIN`, `ACRES`, `COUNTY`, `UPDATED`,
  and geometry; its centroid layer adds location and district context.
- Wilmington-specific sources do not cure the countywide parcel-source gap. The
  city map/transparency pages and zoning map may support future zoning or code
  context inside city limits, but they are not a current, countywide assessor
  parcel owner/value/sale feed with affirmative commercial redistribution
  rights.

Admission requires written New Castle County GIS/Assessment/Treasury permission
covering commercial storage, derived nearby-parcel results, customer display,
API/export output, redistribution or no-raw-source-export boundaries, snapshot
retention, refresh cadence, attribution/disclaimer text, termination handling,
and privacy/suppression requirements. If rights are granted without value/sale
terms, admit only parcel identity, geometry, situs, owner/mailing, acreage,
property class, and zoning/context fields; keep assessed value and sale evidence
on hold.

Candidate source: `new_castle_de_static_tax_parcels_hold`. Primary item:
`https://www.arcgis.com/home/item.html?id=0d9dc54b33f24a8b91868159fe3b92a8`.
Primary service:
`https://services6.arcgis.com/iiIgE8mTDBf4z99T/arcgis/rest/services/NCCDE_Static_Tax_Parcels_-_3-13-2026/FeatureServer`.
Primary query endpoint:
`https://services6.arcgis.com/iiIgE8mTDBf4z99T/arcgis/rest/services/NCCDE_Static_Tax_Parcels_-_3-13-2026/FeatureServer/0/query`.
Fallback parcel-boundary endpoint:
`https://gis.nccde.org/entserver/rest/services/Foundation/Base_Layers/MapServer/9`.
Data dictionary and rights evidence:
`https://ssl02.nccde.org/gisfiles/images/help/NCCDE_GISServices_DataDictionary.html`;
`https://www.newcastlede.gov/1140/Disclaimer-and-Privacy-Policy`.
Supplemental FirstMap endpoint:
`https://enterprise.firstmaptest.delaware.gov/arcgis/rest/services/PlanningCadastre/DE_StateParcels/FeatureServer/0`.

## Virginia Statewide VGIN Parcels

**Decision: narrow admit for derived nearby-parcel discovery; raw assessor,
owner/mailing, sale, and bulk parcel replacement exports remain held.**

- Production source: `virginia_vgin_statewide_parcels_narrow`. The official
  Virginia parcel FeatureServer exposes statewide polygon geometry with
  `VGIN_QPID`, `FIPS`, `LOCALITY`, `PARCELID`, `PTM_ID`, `LASTUPDATE`, `GPIN`,
  `PIN`, optional situs address fields, and server-returned centroids. The
  layer supports JSON, GeoJSON, PBF, pagination, statistics, distance queries,
  and returned geometry centroids.
- Field mapping: use `VGIN_QPID` as preferred parcel/source identity, falling
  back to `PARCELID`, `GPIN`, or `PIN`; preserve `LOCALITY` as county/locality,
  optional `Address`/`City`/`Zip` as situs context, `LASTUPDATE` as currentness,
  and publisher centroid as the radius-search point. Request
  `returnGeometry=true`, `returnCentroid=true`, `outSR=4326`, selected
  `outFields`, and keyset pages ordered by `OBJECTID`.
- Rights basis is narrow. The service is official and public, and Virginia's
  Open Data Portal describes API access for building applications, but the
  parcel layer's copyright text is blank. Therefore admit only value-added
  proximity context with VGIN/Commonwealth attribution. Do not offer a raw
  parcel-data replacement product or bulk geometry/source export.
- Suppressed fields: `Owner1`, `Owner2`, `M_Address`, `M_City`, `M_State`,
  `M_Zip`, valuations, sales, deeds, legal descriptions, raw geometry exports,
  and any locality-specific owner/assessor fields not needed for nearby-parcel
  scoring.

## Burlington / Chittenden County / Vermont

**Decision: narrow admit for value-added nearby parcel discovery; raw source
resale/export hold.**

- Vermont's statewide standardized parcel FeatureServer is the best production
  candidate for Burlington, Chittenden County, and statewide parcel discovery.
  It is an official VCGI/Vermont Open Geodata item compiled from Vermont
  municipalities, licensed surveyors, and the Vermont Department of Taxes. The
  hosted layer reported 343,708 statewide records, 59,849 records across the
  Chittenden-town audit set, and 11,225 Burlington records in the live check.
  Burlington itself reported 11,038 matched parcel records and 10,818 records
  with populated `OWNER1`.
- The statewide layer exposes parcel identity, town, property type, source
  name/type/date, edit date, match status, owner names, owner mailing address,
  property description/category, emergency-911 situs address, acres, land and
  improvement listed values, homestead/non-residential values, exemption/current
  use context, and polygon geometry. Burlington's city parcel FeatureServer is
  useful for comparison and has situs/use fields, but the statewide VCGI layer
  is preferred because it has statewide coverage and portal-level open-geodata
  policy evidence.
- Field mapping: `SPAN` is the canonical Vermont parcel/account identity when
  populated; preserve `GLIST_SPAN`, `PARCID`, and `MAPID` as official aliases.
  Map `TOWN`/`TNAME` to jurisdiction, `PROPTYPE` to parcel/ROW/water type,
  `E911ADDR` and `LOCAPROP` to situs/location, `OWNER1`/`OWNER2` to owner
  evidence, `ADDRGL1`/`ADDRGL2`/`CITYGL`/`STGL`/`ZIPGL` to owner mailing
  address, `DESCPROP` and `CAT` to property class/use, `ACRESGL` to acreage,
  `REAL_FLV`/`HSTED_FLV`/`NRES_FLV`/`LAND_LV`/`IMPRV_LV` to listed assessment
  facts, and `SOURCENAME`/`SOURCETYPE`/`SOURCEDATE`/`EDITDATE`/`MATCHSTAT` to
  source provenance and freshness facts.
- Geometry is suitable for radius search. Request polygons from the statewide
  FeatureServer with `outSR=4326`, `returnGeometry=true`, and
  `returnCentroid=true` when available. Store polygons for exact distance and
  derive an internal point-on-surface centroid for concave or multipart parcels.
  Do not collapse stacked polygons caused by one-to-many parcel-to-Grand-List
  relationships; retain each `SPAN`/Grand List record as separate owner/value
  evidence and derive a physical-parcel group from shared geometry only.
- Paging strategy: use guarded full snapshots with `where=OBJECTID >
  {last_objectid}`, `orderByFields=OBJECTID`, `resultRecordCount=2000`,
  selected `outFields`, and JSON/GeoJSON output. Treat `OBJECTID` only as page
  cursor state. Filter customer-facing nearby discovery to `PROPTYPE='PARCEL'`
  and prefer `MATCHSTAT='MATCH'` for owner/value facts; retain unmatched
  geometry as lower-confidence parcel-boundary evidence.
- Rights pass only a bounded value-added SaaS use case. Vermont's Open Geodata
  Policy covers data, services, and products provided through the Vermont Open
  Geodata Portal; it gives direct no-cost access to individuals, businesses,
  governments, educational institutions, and other organizations, and recognizes
  integration of multiple resources into analytical data sets. It prohibits
  direct, non-value-added reproduction of those data/services/products with
  intent to sell. Therefore Build Signals may store, refresh, enrich, score,
  and display derived nearby-parcel context with attribution and disclaimers,
  but must not sell or export raw statewide parcel/source files or offer a raw
  parcel-data replacement product.
- Suppressed fields for ordinary customer exports/API output:
  `EQUIPVAL`, `EQUIPCODE`, `INVENVAL`, `HSDECL`, `HSITEVAL`, `VETEXAMT`,
  `EXPDESC`, `ENDDATE`, `STATUTE`, `EXAMT_HS`, `EXAMT_NR`, `UVREDUC_HS`,
  `UVREDUC_NR`, `GLVAL_HS`, `GLVAL_NR`, `CRHOUSPCT`, `MUNGL1PCT`, `AOEGL_HS`,
  `AOEGL_NR`, raw geometry blobs, raw source files, and any field not required
  for nearby parcel identity, location, owner, acreage, property class, or
  high-level assessed-value context.
- Export policy:
  `derived_nearby_parcel_context_only_no_raw_vcgi_source_resale`. Customer
  display/export may include parcel identity, situs/location, derived distance,
  owner evidence, acreage, use/class, high-level listed values, and source
  attribution. Raw statewide extracts, bulk geometry dumps, and direct
  non-value-added resale remain blocked unless VCGI grants written permission.
- Sale evidence is not admitted from this source. No parcel-linked sale date,
  sale price, deed instrument, grantor/grantee, or arms-length transaction
  feed was verified in the reviewed statewide/Burlington parcel services. Do
  not scrape municipal property lookup pages to fill that gap.

Candidate source: `vermont_vcgi_statewide_parcels_narrow`. Primary item:
`https://www.arcgis.com/home/item.html?id=09cf47e1cf82465e99164762a04f3ce6`.
Primary service:
`https://services1.arcgis.com/BkFxaEFNwHqX3tAw/arcgis/rest/services/FS_VCGI_OPENDATA_Cadastral_VTPARCELS_poly_standardized_parcels_SP_v1/FeatureServer`.
Primary query endpoint:
`https://services1.arcgis.com/BkFxaEFNwHqX3tAw/arcgis/rest/services/FS_VCGI_OPENDATA_Cadastral_VTPARCELS_poly_standardized_parcels_SP_v1/FeatureServer/0/query`.
Metadata and rights evidence:
`https://maps.vcgi.vermont.gov/gisdata/metadata/CadastralParcels_VTPARCELS.htm`;
`https://files.vcgi.vermont.gov/other/policies/vermont-open-geodata-policy.html`.
Supplemental Burlington parcel endpoint:
`https://maps.burlingtonvt.gov/arcgis/rest/services/Reference_Data_for_VUEWorks/FeatureServer/0`.

## Providence / Rhode Island

**Decision: narrow admit for statewide derived parcel proximity; Providence
owner/value/sale hold.**

- Rhode Island's official statewide tax-parcel MapServer is the safest near-term
  parcel spine for Providence and statewide Phase 2 radius discovery. The live
  service reported 394,167 polygon records, 2,000-row query pages, JSON/GeoJSON
  and PBF output, order-by pagination, polygon geometry, and statewide extent.
  It is published by Rhode Island DEM/RIGIS with access information credited to
  "RI State, 37 Towns." Its fields are intentionally thin: `PlatLot`, `Acres`,
  `TownCode`, E911 improvement/type facts, `IMP_sqft`, `Last_UPD`, and several
  environmental overlay percentages/flags.
- Field mapping: `TownCode || ':' || PlatLot` is the canonical snapshot parcel
  key because `PlatLot` is only locally unique. Preserve `PlatLot` as the
  display parcel/plat-lot ID, `TownCode` as jurisdiction code, `Acres` as
  acreage, `E911Desc`/`E911_Type` as weak property/improvement context,
  `IMP_sqft` as source improvement square-foot evidence when populated, and
  `Last_UPD` as source freshness when present. Do not map owner, situs address,
  assessed value, sale price/date, deed, or mailing fields from this source
  because they are not present in the statewide layer.
- Geometry is adequate for nearby parcel discovery. Request polygons from
  `Tax_Parcels/MapServer/0/query` with `outSR=4326`,
  `returnGeometry=true`, selected `outFields`, and JSON/GeoJSON output. The
  layer does not advertise server-returned geometry centroids, so derive an
  internal `ST_PointOnSurface` centroid and use polygons for exact radius and
  boundary-distance work. Treat `OBJECTID` only as the paging cursor.
- Paging strategy: guarded full snapshots with `where=OBJECTID >
  {last_objectid}`, `orderByFields=OBJECTID`, `resultRecordCount=2000`, and a
  selected allowlist of parcel-spine fields. Validate row count, non-null
  `PlatLot`, non-null `TownCode`, geometry parse rate, and service metadata
  before retiring missing parcels.
- Rights are narrow, not broad. RI.gov and DEM website policy say compiled
  public information may be distributed or copied with credit, but the parcel
  service item itself lists `licenseInfo: semi-restricted` and credits 37 towns.
  Therefore admit only derived nearby-parcel context with attribution and no
  raw source-data export/resale. Do not offer bulk Rhode Island parcel extracts,
  raw geometry downloads, or a parcel-data replacement product without written
  RIGIS/DEM/town permission.
- Suppressed fields for ordinary customer exports/API output: raw geometry
  blobs, raw source files, `OBJECTID`, environmental overlay flags and
  percentages (`OverDW`, `PWS_Wshed`, `GW_Acquifer`, `GW_Recharge`, `CWHPA`,
  `EPA_Sole`, `PctImp`, `PctDev`, `PctOS`, `PctForest`), and any field not
  needed for parcel identity, town, acreage, derived distance, geometry-backed
  location, or high-level E911 improvement context.
- Export policy:
  `derived_nearby_parcel_context_only_no_raw_ri_tax_parcel_resale`. Customer
  display/export may include parcel key, plat-lot ID, town code, acreage,
  derived centroid/distance, high-level improvement context, source attribution,
  and evidence URL. Owner, situs address, assessed value, and sale evidence
  remain unavailable from this statewide source.
- Providence's current `Parcels with CAMA` FeatureServer is technically strong
  but stays on hold. It exposes 44,161 polygon records, current CAMA/zoning
  fields, `map_par_id`, `pin`, `propid`, situs address, owner names/mailing
  fields, assessed values, sale price/date, land/building characteristics, use
  fields, zoning, and query/sync/extract capabilities. However, the current
  ArcGIS service has blank copyright/license text in the REST metadata, and no
  reviewed city page granted commercial SaaS storage, customer display/API
  output, export, redistribution, or resale rights for this exact current layer.
  Do not ingest owner, assessed-value, sale, or mailing fields from the current
  Providence service until written city permission or an explicit open-data
  license is tied to that exact service.
- Providence's older Socrata/Data.gov `PVD_Parcels` dataset is public and
  PDDL-licensed, but it is described as current only as of Winter 2017. It can
  serve as historical license evidence and a stale comparison layer, not as the
  production Providence parcel spine for nearby acquisition discovery.

Candidate source: `rhode_island_statewide_tax_parcels_narrow`. Primary service:
`https://risegis.ri.gov/hosting/rest/services/RIDEM/Tax_Parcels/MapServer`.
Primary query endpoint:
`https://risegis.ri.gov/hosting/rest/services/RIDEM/Tax_Parcels/MapServer/0/query`.
Item/rights evidence:
`https://risegis.ri.gov/hosting/rest/services/RIDEM/Tax_Parcels/MapServer/info/iteminfo`;
`https://dem.ri.gov/disclaimer`;
`https://www.ri.gov/policies/copyright/`;
`https://planning.ri.gov/planning-areas/data-center/rhode-island-geographic-information-system-rigis`.
Providence current hold source:
`https://webgis.providenceri.gov/server/rest/services/Hosted/Parcels_wZoning_HFL/FeatureServer/0`.
Providence older PDDL source:
`https://catalog.data.gov/dataset/pvd_parcels`.

## New Hampshire / Nashua / Manchester / Portsmouth

**Decision: narrow admit for statewide derived nearby-parcel discovery; richer
city owner/value/sale feeds remain hold unless explicit commercial SaaS rights
are tied to the exact service.**

- New Hampshire's statewide parcel mosaic is the best production candidate for
  Nashua, Manchester, Portsmouth, Hillsborough County, Rockingham County, and
  statewide Phase 2 nearby-parcel discovery. It is compiled and managed by the
  NH Department of Revenue Administration and distributed through NH GRANIT.
  Live checks on July 17, 2026 showed 617,124 parcel polygons statewide, 27,042
  parcel polygons across Nashua, Manchester, and Portsmouth, and 253,043 parcel
  polygons across Hillsborough and Rockingham county IDs `6` and `8`.
- The official metadata says the dataset contains NH parcel boundaries and
  associated attributes for communities, is compiled to support property-tax
  equalization, includes a GIS parcel mosaic and linked CAMA database, and has
  "Use Constraints: None." The metadata also credits NH DRA and lists NH GRANIT
  as distributor. Treat that as enough for a bounded value-added parcel spine,
  but not enough for raw source resale or a parcel-data replacement product.
- Field mapping: `nh_gis_id` is the canonical statewide parcel identity; keep
  `parceloid`, `u_id`, `pid`, `displayid`, and `oid_1` as official aliases.
  Map `town`, `townid`, and `countyid` to jurisdiction; `streetaddress` to
  situs/location; `slu`, `sluc`, `slum`, `localnbc`, and `nbc` to land-use or
  property-class context; `name` only as source display text/evidence; and
  polygon geometry plus returned centroid to location evidence. Join the CAMA
  table by the service relationship or shared `parceloid`/`nhgis_id` only for
  allowed fields.
- CAMA table mapping if ingested under the same narrow policy: `localcamaid`,
  `rawid`, `altid`, `displayid`, `u_id`, and `nhgis_id` as aliases;
  `streetaddress`, `streetnumber`, and `streetname` as situs evidence;
  `townname`, `townid`, `countyname`, and `countyid` as jurisdiction evidence;
  `slu`, `sluc`, `sluc_desc`, `slum`, `localnbc`, and `nbc` as use/class
  evidence; `camayear`, `camaoid`, `cardcount`, and `camacount` as provenance
  and reconciliation facts. Owner, valuation, sale price/date, deed, and mailing
  fields were not present in the reviewed NH GRANIT CAMA table.
- Geometry/page strategy: query
  `CAD_ParcelMosaic/FeatureServer/1/query` with `outSR=4326`,
  `returnGeometry=true`, `returnCentroid=true`, selected `outFields`,
  `where=objectid > {last_objectid}`, `orderByFields=objectid`, and
  `resultRecordCount=2000`. Store polygons for exact distance and an internal
  point-on-surface fallback for multipart or concave parcels. Treat `objectid`
  only as a page cursor, not parcel identity.
- Suppressed fields for ordinary customer exports/API output: raw geometry
  blobs, raw source files, `objectid`, `Shape__Area`, `Shape__Length`, any
  append/edit metadata, and any CAMA or related-table field not needed for
  parcel identity, jurisdiction, situs/location, acreage/area-derived context,
  use/class context, derived distance, or evidence URL. If a future city feed
  includes owner, mailing, value, sale, building characteristics, deed, or photo
  fields, suppress those until the exact source has affirmative commercial
  storage/display/export rights.
- Export policy:
  `derived_nearby_parcel_context_only_no_raw_nh_parcel_mosaic_resale`. Customer
  display/export may include parcel ID, town/county, situs/location, derived
  centroid/distance, high-level land-use/class context, source attribution, and
  evidence URL. Raw statewide extracts, bulk geometry dumps, and direct
  non-value-added resale remain blocked unless NH DRA/NH GRANIT grants written
  permission.
- Nashua has strong supplemental official/official-publisher sources, but the
  statewide NH GRANIT layer remains preferred for consistency. The City of
  Nashua GIS page links the public GIS viewer and says it provides residential
  and business usage plus direct property-record-card access, but its disclaimer
  is warranty/liability language rather than a commercial redistribution grant.
  The NRPC FeatureServer exposes Nashua parcel polygons with `COMPOSITE_PID`,
  `LAB_PID`, `LOCATION`, `Par_Subtype`, `LAT_DD`, `LON_DD`, and a related CAMA
  lookup table with `accountunique`, `siteaddress`, `sitecity`, `ownername`,
  and MapGeo URL; however, NRPC's description says CAMA is refreshed one or two
  times per year and no explicit customer export/API redistribution grant was
  found. Use NRPC/Nashua as QA or city-specific evidence only until rights are
  confirmed.
- Manchester's official parcel MapServer is technically rich and current enough
  for future onboarding. A live check showed 33,983 parcel records and fields
  for `ParcelID`, `ParcelSearchID`, `GISLINK`, situs address, owner/mailing
  name/address, sale date/price/book-page, land/building/total valuation,
  commercial/condo/vacant flags, land use, building characteristics,
  `ParcelLastUpdatedDate`, and `RecordAsOfDate`. It stays on hold for
  owner/value/sale/building facts because the REST layer has blank copyright
  text and no reviewed city policy granted commercial SaaS storage, customer
  display/API output, export, or redistribution for the exact service. A later
  written city permission could make Manchester a high-value enrichment source.
- Portsmouth is a hold for production parcel ingestion from city sources. The
  official city GIS/Assessor pages point users to MapGeo and Vision property
  lookup, but no supported bulk/API source with affirmative commercial
  redistribution rights was verified. The city MapGeo disclaimer says data are
  reference-only, boundaries and owner information may not reflect recent
  changes, and use is subject to MapGeo privacy/terms. Do not scrape MapGeo,
  Vision, or PDF tax maps to fill owner/value/sale gaps.
- No county-run Hillsborough County or Rockingham County NH parcel spine was
  verified as a better official bulk source than NH DRA/GRANIT. The statewide
  mosaic should be the county coverage spine; municipal feeds can later enrich
  high-priority markets after source-specific rights review.

Candidate source: `new_hampshire_dra_granit_parcel_mosaic_narrow`. Primary
service:
`https://granit24a.sr.unh.edu/hosting/rest/services/Hosted/CAD_ParcelMosaic/FeatureServer`.
Primary parcel query endpoint:
`https://granit24a.sr.unh.edu/hosting/rest/services/Hosted/CAD_ParcelMosaic/FeatureServer/1/query`.
CAMA table endpoint:
`https://granit24a.sr.unh.edu/hosting/rest/services/Hosted/CAD_ParcelMosaic/FeatureServer/3/query`.
Metadata and download evidence:
`https://www.arcgis.com/sharing/rest/content/items/46ef5d95fd1848498d8bfb95b1010a34/info/metadata/metadata.xml?format=default&output=html`;
`https://ftp.granit.unh.edu/GRANIT_Data/Vector_Data/Administrative_and_Political_Boundaries/ParcelMosaic/`.
Supplemental Nashua/NRPC source:
`https://services6.arcgis.com/2ZriDy2NFXltCIFR/ArcGIS/rest/services/NRPC_Open_Data_Nashua_v2/FeatureServer`.
Supplemental Manchester hold source:
`https://ags.manchesternh.gov/agsgis7/rest/services/Community/Parcels/MapServer/0`.
Portsmouth hold evidence:
`https://www.portsmouthnh.gov/publicworks/gis`;
`https://portsmouthnh.mapgeo.io/`;
`https://www.portsmouthnh.gov/assessors`.

## Alabama / Birmingham / Montgomery / Huntsville / Mobile

**Decision: narrow admit only for derived nearby-parcel discovery in selected
local feeds; no statewide Alabama parcel spine was verified. Owner, mailing,
value, sale, deed, and building facts remain hold unless source-specific
commercial SaaS storage/display/export rights are granted in writing.**

- Alabama's state ArcGIS services directory does not expose a statewide parcel
  service. The official `maps.alabama.gov/algogis` root only listed counties and
  sample services during review, so Phase 2 Alabama coverage must be assembled
  from county/city publishers unless the state or Alabama Department of Revenue
  later publishes a current statewide cadastral feed with reuse terms.
- Birmingham / Jefferson County is technically strong but legally constrained.
  The City of Birmingham public parcel layer is queryable and returned 148,282
  polygon records in a live count on July 17, 2026. It includes `PARCELID`,
  component parcel fields, situs fields (`HSENO`, `STREET`, `TYPE`, `DIR`,
  `CITY`, `ZIPP`, `ADDR`), owner/mailing fields (`NAME1`, `NAME2`, `ADDRESS`,
  `CITYSTATE`, `ZIP`, `INCAREOF`), deed/sale fields, land-use code `LU`,
  jurisdiction/subdivision fields, valuation fields, and polygon geometry.
  However, Birmingham's website terms expressly prohibit commercial use without
  prior written permission and prohibit commercial distribution or republication
  without permission. Treat this source as a hold for production ingestion until
  permission is secured. If permission is granted, use only parcel ID, situs,
  jurisdiction, derived centroid/distance, high-level class/use, and evidence
  fields unless the permission also covers owner/value/sale display and export.
- Montgomery County / City of Montgomery is the best Alabama near-term narrow
  admit candidate for a parcel spine, but still bounded. The City-hosted
  `Parcels/FeatureServer/0` layer returned 106,111 polygon records in a live
  count on July 17, 2026, supports pagination, and supports returned geometry
  centroids. Montgomery County's Revenue Commission GIS page says cadastral and
  parcel data are integral to the county GIS/appraisal process and the county
  GIS division is custodian of spatial data. The reviewed county/city pages did
  not provide an affirmative commercial SaaS redistribution or raw-export grant,
  so ingest only a value-added nearby-parcel spine unless written permission is
  obtained.
- Huntsville / Madison County is technically rich but the rights language blocks
  resale-like use. The City of Huntsville tiled Madison County parcel layer
  returned 205,175 polygon records in a live count on July 17, 2026 and includes
  parcel IDs, situs, owner, mailing, tax district, acreage, values, deed facts,
  and assessor URL fields. Huntsville's Data Depot terms say the data is
  copyrighted by the city and that repackaging or reselling the data is strictly
  prohibited. Do not ingest this as a raw parcel-data product. A narrow derived
  proximity spine may be acceptable only if we store/display parcel identity,
  location, distance, and attribution as value-added context and suppress the raw
  owner/value/sale/deed/mailing feed; get written approval before exposing
  customer exports or API output from this source.
- Mobile County has two official publisher services with the same live record
  count, but currentness and rights keep it narrow. The City of Mobile
  `EG_CSS_MS/MapServer/1` parcel layer says it is Mobile County Revenue
  Commission parcel boundaries with a last update of January 2017 and returned
  213,603 polygons. The ArcGIS Online `PARCEL_DETAILS/FeatureServer/0` service
  is labeled "DATA SHARE ONLY," credits Mobile County Revenue Commission, also
  returned 213,603 polygons, supports pagination, and supports returned geometry
  centroids. The FeatureServer is the better technical candidate, but no
  affirmative commercial SaaS storage/display/export or raw redistribution grant
  was found on the reviewed county/city pages. Use only under a derived
  nearby-parcel policy and prefer direct written permission from Mobile County
  Revenue Commission before production.

Candidate source: `montgomery_al_parcels_nearby_narrow`. Primary service:
`https://gis.montgomeryal.gov/server/rest/services/Parcels/FeatureServer`.
Primary query endpoint:
`https://gis.montgomeryal.gov/server/rest/services/Parcels/FeatureServer/0/query`.
Field mapping: `ParcelNo` as canonical parcel ID; `PID` as source alias;
`PropertyAddr1`, `PropertyCity`, `PropertyState`, and `PropertyZip` as situs
evidence; `Calc_Acre` as acreage; `AssessmentClass` and `Neighborhood` as
high-level class/context; `MunicipalityCode` and `FireDist` as jurisdiction
context; polygon geometry plus `returnCentroid=true` as location evidence;
`RecordYear` as tax-roll currentness; `OBJECTID` only as page cursor. Suppressed
fields: `OwnerName`, `OwnerName2`, all `Mail*` fields, `TotalLandValue`,
`TotalImpValue`, `TotalValue`, `InstNbr`, `InstDate`, `Book*`, `Page*`, raw
geometry blobs, `OBJECTID`, `Shape__Area`, `Shape__Length`, and any edit or
append metadata. Paging strategy: `where=OBJECTID > {last_objectid}`,
`orderByFields=OBJECTID`, selected `outFields`, `returnGeometry=true`,
`returnCentroid=true`, `outSR=4326`, `resultRecordCount=2000`.

Candidate source: `mobile_al_parcel_details_nearby_narrow`. Primary service:
`https://services3.arcgis.com/AcvBA1fcgucsFQvO/arcgis/rest/services/PARCEL_DETAILS/FeatureServer`.
Primary query endpoint:
`https://services3.arcgis.com/AcvBA1fcgucsFQvO/arcgis/rest/services/PARCEL_DETAILS/FeatureServer/0/query`.
Field mapping: `parcel` as canonical parcel ID; `keyx`, `keyx_num`, `pid`, and
`ptext` as source aliases; `address`, `zipcode`, and `jurisdiction` as
situs/location context; `acreage` as acreage; `class`, `classcode_desc`,
`muncode`, `muncode_desc`, `nbh`, and `nbhname` as class/jurisdiction context;
`lat_y`, `long_x`, `stateplane_x`, and `stateplane_y` as point-location
evidence; polygon geometry plus `returnCentroid=true` as spatial evidence.
Suppressed fields: `name`, all `mail_*` fields, `total_land_value`,
`total_improv_value`, `appraised_value`, `sq_feet`, exemption/disability fields,
raw geometry blobs, `objectid`, `Shape__Area`, `Shape__Length`, and downstream
district fields not needed for nearby acquisition discovery unless separately
licensed. Paging strategy: `where=objectid > {last_objectid}`,
`orderByFields=objectid`, selected `outFields`, `returnGeometry=true`,
`returnCentroid=true`, `outSR=4326`, `resultRecordCount=2000`.

Supplemental hold source: `birmingham_jefferson_al_parcels_hold`.
Endpoint:
`https://gisweb.birminghamal.gov/arcgis/rest/services/Parcel/MapServer/0/query`.
Release condition: written Birmingham/Jefferson permission for commercial SaaS
storage, display, API output, and export; otherwise no production ingest.
Suppressed fields if later admitted: `NAME1`, `NAME2`, `ADDRESS`, `CITYSTATE`,
`ZIP`, `INCAREOF`, deed/date/amount fields, `PRICE`, `LAND`, `BLDG`, `OTHER`,
assessed-value fields, raw geometry blobs, `OBJECTID`, `GlobalID`, and
shape-measure fields.

Supplemental hold/narrow source: `madison_huntsville_al_parcels_hold`.
Endpoint:
`https://maps.huntsvilleal.gov/server/rest/services/Tiled/MadisonCountyParcels/MapServer/0/query`.
Release condition: written city/county permission clarifying that derived
nearby-parcel SaaS context is not prohibited repackaging/resale and defining
whether any customer export/API output is allowed. Suppressed fields if later
admitted: `PropertyOwner`, `PreviousOwners`, `AccountOwner`, `MailingAddress`,
all value fields, deed fields, `PropertyDescription`, raw geometry blobs,
`OBJECTID`, and shape-measure fields.

Export policy for all Alabama narrow admits:
`derived_nearby_parcel_context_only_no_raw_alabama_local_parcel_resale`.
Customer display/export may include parcel ID, situs/location, derived centroid
and distance, acreage, high-level class/jurisdiction context, source
attribution, and evidence URL. Raw parcel extracts, bulk geometry dumps,
owner/mailing lists, valuation/sale/deed datasets, and direct source-data resale
remain blocked without written permission from the exact publisher.

Evidence URLs:
`https://maps.alabama.gov/algogis/rest/services`;
`https://gisweb.birminghamal.gov/arcgis/rest/services/Parcel/MapServer/0`;
`https://www.birminghamal.gov/terms-use`;
`https://www.birminghamal.gov/gis-permitting-systems-support-division`;
`https://gis.montgomeryal.gov/server/rest/services/Parcels/FeatureServer/0`;
`https://www.mc-ala.org/departments/appraisal/gis`;
`https://www.mc-ala.org/departments/appraisal/gis/online-services`;
`https://maps.huntsvilleal.gov/server/rest/services/Tiled/MadisonCountyParcels/MapServer/0`;
`https://www.huntsvilleal.gov/development/building-construction/gis/data-depot/`;
`https://www.madisoncountyal.gov/departments/tax-assessor`;
`https://services3.arcgis.com/AcvBA1fcgucsFQvO/arcgis/rest/services/PARCEL_DETAILS/FeatureServer/0`;
`https://maps.cityofmobile.org/arcgis/rest/services/EG_CSS_MS/MapServer/1`;
`https://www.mobilecountyal.gov/gis-mapping/`;
`https://www.mobilecountyal.gov/privacy-and-security/`.

## Arkansas / Pulaski, Benton, Washington parcel spine

Decision: NARROW ADMIT for the official Arkansas GIS Office statewide
cadastral layer as a derived nearby-parcel discovery spine. HOLD richer
county/city owner, value, and sale feeds until each publisher grants explicit
commercial SaaS storage, display, API output, and export rights. The statewide
service is the best first production source for Little Rock/Pulaski,
Bentonville/Rogers/Benton County, Fayetteville/Washington County, and statewide
parcel proximity because it is official, queryable, statewide, and already
normalizes county assessor parcel attributes into the Arkansas cadastral
standard.

Primary admitted candidate: `arkansas_statewide_parcels_nearby_narrow`.
Official service:
`https://gis.arkansas.gov/arcgis/rest/services/FEATURESERVICES/Planning_Cadastre/FeatureServer`.
Primary query endpoint:
`https://gis.arkansas.gov/arcgis/rest/services/FEATURESERVICES/Planning_Cadastre/FeatureServer/0/query`.
Layer: `PARCEL_CENTROID_CAMP` (`0`). Geometry type is point in the
FeatureServer and polygon/shape-backed in the MapServer view; use the
FeatureServer point geometry first for centroid-driven nearby discovery and
retain the MapServer layer only as a future polygon enrichment candidate after
rights and connector behavior are verified. Live count check on July 17, 2026:
`2,117,780` statewide records; target county checks: Pulaski `180,264`, Benton
`174,098`, Washington `113,655`.

Admitted field mapping: `parcelid` as canonical parcel ID; `countyfips`,
`countyid`, `county`, `sourceref`, and `globalid` as source identifiers and
aliases; `adrnum`, `predir`, `pstrnam`, `pstrtype`, `psufdir`, `adrcity`,
`adrzip5`, and `adrlabel` as situs/location evidence; point geometry in
`outSR=4326` as centroid evidence; `parceltype`, `subdivision`, `nbhd`,
`section`, `township`, `range`, `str`, `taxcode`, `taxarea`, `camaprov`,
`dataprov`, `sourcedate`, `camadate`, and `pubdate` as provenance and
high-level context. Suppressed fields until rights are expanded:
`ownername`, `assessvalue`, `impvalue`, `landvalue`, `totalvalue`, `camakey`,
`parcellgl`, raw legal descriptions, raw geometry blobs, `objectid`,
shape-measure fields, and any sale/deed/mailing fields discovered in county
supplements.

Paging strategy: ArcGIS keyset pages with
`where=objectid > {last_objectid}`, `orderByFields=objectid`,
`outFields=parcelid,countyfips,countyid,county,sourceref,sourcedate,adrnum,predir,pstrnam,pstrtype,psufdir,adrcity,adrzip5,adrlabel,parceltype,subdivision,nbhd,section,township,range,str,taxcode,taxarea,camaprov,dataprov,camadate,pubdate,globalid,objectid`,
`returnGeometry=true`, `outSR=4326`, and `resultRecordCount=200`. The service
advertises pagination and JSON/geoJSON/PBF output, but the max record count is
low, so keep pages conservative and shard by county for high-volume backfills.

Export policy:
`derived_nearby_parcel_context_only_no_raw_arkansas_cadastral_resale`.
Customer-facing display/export may include parcel ID, county, situs/location,
derived centroid and distance, source attribution, currentness dates, and
high-level parcel type/context. Do not expose raw statewide extracts, owner
lists, valuation fields, CAMA keys, legal descriptions, bulk geometry dumps, or
county-local sale/deed data without an affirmative license from the publishing
agency.

Official state evidence: the Arkansas GIS Office describes ASDI/GeoStor as the
state geospatial clearinghouse and says it coordinates, publishes, and promotes
GIS data for Arkansas across government and private-sector stakeholders. The
parcel layer iteminfo says the dataset was compiled under the Arkansas GIS Board
as a statewide cadastral resource and may be used for cartographic display,
base-map/reference use, geographic analysis, and numerous other applications.
The layer metadata also warns that county submissions are snapshots, may update
semi-annually, are not legal boundary descriptions, and can have incomplete
county coverage; production versions remain with counties.

Local supplemental source: `little_rock_pulaski_ar_parcels_hold`.
Endpoint:
`https://maps.littlerock.gov/server/rest/services/Tax_Parcel_Boundary/MapServer/0/query`.
Live count check on July 17, 2026: `180,301` records. Technically strong for
Little Rock/Pulaski polygon geometry and assessor-like fields. HOLD because
commercial reuse/export rights were not affirmative in the service metadata.
If later admitted, map `PIN`/`CAMA_PIN` as parcel IDs, `ADR*` and `ADRLABEL` as
situs evidence, polygon geometry as spatial evidence, `PARCELTYPE`, `NBHD`,
`DST_NAME`, `SOURCEDATE`, and `CAMADATE` as context/currentness; suppress
`OWNERNAME`, `OWNER_ADD*`, `OWNER_ZIP`, `ASSESSVAL`, `IMPVALUE`, `LANDVALUE`,
`TOTALVALUE`, `TOTEFFVAL`, `PARCELLGL`, `PROPLOOKUP`, raw geometry blobs,
`OBJECTID`, and shape-measure fields.

Local supplemental source: `benton_county_ar_parcels_hold`.
Official app:
`https://gis.bentoncountyar.gov/parcels/index.html`. Official download page:
`https://gis.bentoncountyar.gov/downloads/index.html`. Cadastral service:
`https://gis.bentoncountyar.gov/arcgis/rest/services/Basemaps/Cadastral/MapServer`.
Benton's parcel app terms say the GIS layers are intended for informational
purposes and not commercial purposes, so the county-local feed is HOLD even
though it is technically useful and current enough for Bentonville/Rogers.
Use the statewide Arkansas layer for Benton County proximity until written
commercial permission is obtained.

Local supplemental source: `washington_county_ar_parcels_hold`.
Endpoint:
`https://arcserv.co.washington.ar.us/server/rest/services/PlanningDatabase/Parcels/MapServer/0/query`.
Technically strong for Fayetteville/Washington County polygon geometry, with
parcel ID, situs, acreage, owner, value, and edit/currentness fields. HOLD until
rights are explicit; the service metadata has blank license/copyright fields.
If later admitted, map `parcel_id` and `PIN` as parcel IDs; `ph_add`,
`ph_rd_num`, `ph_pre_dir`, `ph_rd_nam`, `ph_rd_typ`, `ph_suf_dir`,
`ph_cty_nm`, and `ph_zip` as situs evidence; `CALC_ACRES`/`acre_area` as
acreage; polygon geometry as spatial evidence; `parcel_type`, `Sub_Name`,
`Subdivision`, `Tax_District`, `srce_date`, `ow_src_dat`, and `assess_dat` as
context/currentness. Suppress `ow_name`, `ow_name2`, `ow_add`, `ow_add1`,
`ow_add2`, `ow_city`, `ow_state`, `ow_zip`, `assess_val`, `land_val`,
`imp_val`, `total_val`, `parcel_lgl`, notes/edit-user fields, raw geometry
blobs, `OBJECTID`, and shape-measure fields.

Evidence URLs:
`https://gis.arkansas.gov/programs/arkansas-spatial-data-infrastructure-previously-geostor/`;
`https://gis.arkansas.gov/help/connecting-to-geostors-arcgis-server-services/`;
`https://gis.arkansas.gov/arcgis/rest/services/FEATURESERVICES/Planning_Cadastre/FeatureServer/0`;
`https://gis.arkansas.gov/arcgis/rest/services/FEATURESERVICES/Planning_Cadastre/FeatureServer/0/iteminfo`;
`https://gis.arkansas.gov/arcgis/rest/services/FEATURESERVICES/Planning_Cadastre/MapServer/layers`;
`https://maps.littlerock.gov/server/rest/services/Tax_Parcel_Boundary/MapServer/0`;
`https://gis.bentoncountyar.gov/parcels/index.html`;
`https://gis.bentoncountyar.gov/downloads/index.html`;
`https://gis.bentoncountyar.gov/arcgis/rest/services/Basemaps/Cadastral/MapServer`;
`https://arcserv.co.washington.ar.us/server/rest/services/PlanningDatabase/Parcels/MapServer/0`;
`https://arcserv.co.washington.ar.us/server/rest/services/Assessor/Parcel_Sales/MapServer/info/iteminfo`.

## Kansas / Sedgwick, Johnson, Wyandotte, Shawnee, statewide parcel candidates

Decision: NARROW ADMIT for Sedgwick County/Wichita as a derived
nearby-parcel geometry and parcel-identity spine only. HOLD Johnson County,
Wyandotte County/Kansas City KS, Shawnee County, and statewide Kansas ORKA/DASC
parcel candidates until written rights cover commercial SaaS storage, customer
display/API output, exports, and redistribution or until an official open
parcel layer with an affirmative reuse grant is found.

Primary admitted candidate: `sedgwick_county_ks_parcels_nearby_narrow`.
Official landing pages:
`https://www.sedgwickcounty.org/gis/` and
`https://www.sedgwickcounty.org/gis/data-layers/?altTemplate=gisdatalayer&id=6`.
Official ArcGIS Hub item:
`https://www.arcgis.com/home/item.html?id=8ec61bb649314a56bdfda742b45fbe43&sublayer=4`.
Primary query endpoint:
`https://services7.arcgis.com/McLat6HlPl45bNBv/ArcGIS/rest/services/Sedgwick_County_Land_Records/FeatureServer/4/query`.
Adapter family: ArcGIS FeatureServer guarded snapshot, with keyset paging on
`OBJECTID`.

Admitted field mapping: use `PIN` as the display parcel key, `AIN` as the
canonical tax/assessment identity where populated, `GEOCODE`, `RDParDocID`,
multi-unit fields, `ParcSqFTC`, `ParcAcresC`, `ParcAreaTP`, and `EditDT` as
parcel context/currentness, and polygon geometry in `outSR=4326` for
point-on-surface and distance calculations. The public Hub layer has no owner,
situs-address, assessed-value, or sale fields; the older/cached county parcel
services and tax/appraiser applications expose richer owner/address/value/sale
attributes, but those fields are explicitly excluded from production admission.

Sample query shape:
`where=OBJECTID > {last_objectid}`,
`orderByFields=OBJECTID`,
`outFields=OBJECTID,PIN,AIN,GEOCODE,RDParDocID,MultUnitTP,MultSubNO,RDMulDocID,MultBldgNO,MultUnitNO,UnitLevel,UnitStatus,ParcSqFTC,ParcAcresC,ParcAreaTP,EditDT`,
`returnGeometry=true`, `outSR=4326`, and `resultRecordCount=2000`. Snapshot
guards must stop on duplicate/null `AIN` plus `PIN` identity keys, geometry
failures, or schema drift. Last reviewed July 17, 2026; the Hub item reported
data/schema updates on July 6, 2026, while the live FeatureServer layer reported
last edit/schema/data edit timestamps on July 17, 2026.

Rights and export policy:
`derived_nearby_parcel_context_only_no_raw_sedgwick_resale`. Sedgwick County
publishes the parcel layer through its official GIS/open-data channels as
downloadable countywide data and says GIS data/services are provided to
citizens, public/private organizations, and county/municipal staff, but the
reviewed evidence is disclaimer-heavy rather than an affirmative commercial
redistribution license. Customer-facing use is therefore limited to derived
nearby-parcel context: parcel ID, acreage/area, derived centroid/distance,
geometry-derived relationship, currentness, and Sedgwick County/SCGIS
attribution. Do not expose raw parcel extracts, bulk geometry downloads,
owner names, mailing/situs address lists, assessed values, sale facts, legal
descriptions, or tax/appraiser records. Kansas K.S.A. 45-220(c)(2) also requires
care around any public-record list of names or addresses; owner/address-bearing
sources remain out of scope unless counsel and the source agency approve the
exact Phase 2 use.

Johnson County/AIMS decision: HOLD. AIMS has official current property data and
nightly property-information updates, but the property map service is secured,
full property data is licensed/purchased through data partner or Data on Demand
channels, and AIMS states that AIMS-sourced data must be licensed. Admission
requires a signed Johnson County AIMS/RTA agreement that permits storage,
derived nearby scoring, customer display/API output, exports, and retention.

Wyandotte County/Kansas City KS decision: HOLD. The official ArcGIS parcel layer
is technically strong, with polygon geometry, `PARCEL`, `PARCEL_NBR`,
`STATE_ID`, owner name, address components, land use, and ORION ID, and supports
JSON/GeoJSON/PBF paging. Rights fail production: parcel metadata asserts UG
copyright, says unauthorized redistribution is not permitted, and says certain
datasets are subject to a GIS Data Transmittal and Confidentiality Agreement.
Do not use the service for commercial SaaS output without written UG permission.

Shawnee County/Topeka decision: HOLD. The county maintains current ownership
information for about 75,000 parcels and provides property search/map access,
but countywide data requests route through the Appraiser GIS office for
availability and pricing. The real-estate search terms include the Kansas Open
Records Act name/address certification. No stable public bulk/API parcel layer
with commercial SaaS reuse rights was admitted.

Statewide Kansas DASC/ORKA decision: HOLD. DASC is the state GIS clearinghouse
and the ORKA services provide partial statewide property resources and
county-hosted parcel services, but the reviewed ORKA parcel evidence is
county-by-county/partial and lacks an affirmative commercial redistribution
grant. Use only as discovery evidence for future county-specific onboarding,
not as a production statewide parcel source.

Evidence URLs:
`https://www.sedgwickcounty.org/gis/`;
`https://www.sedgwickcounty.org/gis/data-layers/?altTemplate=gisdatalayer&id=6`;
`https://www.arcgis.com/home/item.html?id=8ec61bb649314a56bdfda742b45fbe43&sublayer=4`;
`https://services7.arcgis.com/McLat6HlPl45bNBv/ArcGIS/rest/services/Sedgwick_County_Land_Records/FeatureServer/4`;
`https://gismaps.sedgwickcounty.org/arcgis/rest/services/Map/Op_Parcel_Cached_SP/MapServer/layers`;
`https://aims.jocogov.org/AIMSData/default.aspx`;
`https://aims.jocogov.org/AIMSData/aimsonline.aspx`;
`https://aims.jocogov.org/AIMSData/DataPrices.aspx`;
`https://aims.jocogov.org/faq.aspx`;
`https://gisweb.wycokck.org/arcgis/rest/services/UGMAPS/UGMAPS_4_V02_Default/MapServer/0`;
`https://gisapp.wycokck.org/gisdata/shp/parcel_py_metadata.htm`;
`https://www.wycokck.org/Departments/Maps-and-GIS`;
`https://snco.gov/ap/mapping.php`;
`https://ares.sncoapps.us/BasicSearch/`;
`https://services.kansasgis.org/arcgis3/rest/services/forka/KS_ORKA_Extras/MapServer`;
`https://storymaps.arcgis.com/stories/a6b88f1d9ac34e96abd52ef68588486c`;
`https://www.ksrevisor.gov/statutes/chapters/ch45/045_002_0020.html`.

## Utah - Salt Lake, Utah, Washington, Davis, and Weber Counties

**Decision: narrow derived nearby-parcel admit for UGRC/SGID parcels; county
assessor owner, sale, and paid extract sources remain on hold.**

The official production candidate is the Utah Geospatial Resource Center
state/county SGID parcel program, not county portal scraping. UGRC publishes
county parcel polygon FeatureServers and SGID query tables for each Utah county,
plus annual Land Information Record (LIR) parcel layers where counties provide
tax-roll attributes. The five focus counties are all Big 5 monthly basic-parcel
targets: Utah and Washington basic parcels were updated in July 2026; Davis and
Weber in June 2026; Salt Lake in May 2026. LIR parcels for Salt Lake, Utah,
Washington, Davis, and Weber are 2025 tax-year layers.

Adapter family:
`arcgis_feature_service_snapshot` with optional `open_sgid_sql_crosscheck`.
Use the county-level UGRC FeatureServers rather than mixed county app services:
`Parcels_SaltLake`, `Parcels_Utah`, `Parcels_Washington`, `Parcels_Davis`, and
`Parcels_Weber`, with matching `*_LIR` services for annual tax-roll context.
The statewide UGRC parcel FeatureServer can be retained as a discovery/index
source, but county-level services give clearer currentness and schema evidence.

Identity, fields, and geometry:
use county plus normalized `PARCEL_ID` as the canonical tax/parcel identity and
preserve `ACCOUNT_NUM`/`SERIAL_NUM` where supplied as secondary source keys.
`OBJECTID` is only a page cursor. Basic parcel fields admitted for derived
nearby context are `PARCEL_ID`, `PARCEL_ADD`, `PARCEL_CITY`, `PARCEL_ZIP`,
`OWN_TYPE`, `RECORDER`, `ParcelsCur`, `ParcelsRec`, `ParcelsPub`,
`ParcelYear`, `ParcelNotes`, `CoParcel_URL`, and polygon geometry. LIR fields
admitted for limited context are `CURRENT_ASOF`, `PARCEL_ID`, `SERIAL_NUM`,
`PARCEL_ADD`, `PARCEL_CITY`, `TAXEXEMPT_TYPE`, `TAX_DISTRICT`,
`TOTAL_MKT_VALUE`, `LAND_MKT_VALUE`, `PARCEL_ACRES`, `PROP_CLASS`,
`PROP_TYPE`, `PRIMARY_RES`, `HOUSE_CNT`, `SUBDIV_NAME`, `BLDG_SQFT`,
`FLOORS_CNT`, `BUILT_YR`, `EFFBUILT_YR`, and polygon geometry. There is no
admitted official sale feed. Suppress owner-name fields, including Utah County
basic `OWNERNAME`, until UGRC and the contributing county confirm SaaS display,
export, and redistribution rights for owner-bearing data.

Sample query shape:
`/FeatureServer/0/query?where=OBJECTID>{last_objectid}&orderByFields=OBJECTID&outFields=OBJECTID,PARCEL_ID,PARCEL_ADD,PARCEL_CITY,PARCEL_ZIP,OWN_TYPE,RECORDER,ParcelsCur,ParcelsRec,ParcelsPub,ParcelYear,ParcelNotes,CoParcel_URL,ACCOUNT_NUM&returnGeometry=true&outSR=4326&f=geojson&resultRecordCount=2000`;
for LIR replace `outFields` with the admitted LIR allowlist above. Open SGID
crosschecks can use
`select * from cadastre.{county}_county_parcels limit 10` and
`select * from cadastre.{county}_county_parcels_lir limit 10`.

Rights and export policy:
`derived_nearby_parcel_context_only_no_owner_or_raw_assessor_resale`. UGRC's
parcel page states there are no constraints or warranties on the dataset and
encourages attribution to State of Utah, SGID. That is enough for narrow
commercial use of derived nearby-parcel context with attribution: parcel ID,
situs/address text where present, generalized ownership type, acreage/area,
assessor market/land value from LIR, generalized class/type, derived centroid,
distance, and boundary relationship. Do not expose raw bulk parcel extracts,
source geodatabases, owner names, mailing addresses, sale facts, or county paid
assessor products in customer exports/API output without written permission from
UGRC and the relevant county.

Candidate decisions:
Salt Lake County - NARROW ADMIT via UGRC basic/LIR only. Salt Lake Assessor's
2025 CAMA database is available for purchase and includes `OWNER_NAME`,
coordinates, property characteristics, and other assessor fields, but the
reviewed purchase page does not grant commercial SaaS redistribution or customer
export rights. Hold full assessor ingestion pending written terms.

Utah County - NARROW ADMIT via UGRC basic/LIR only. Utah County's official GIS
site and parcel map/service provide live parcel mapping, but reviewed public map
terms are warranty/disclaimer language, not affirmative reuse permission. Utah
County owner fields in UGRC basic parcels are excluded until rights are clarified.

Washington County/St. George - NARROW ADMIT via UGRC basic/LIR only. Washington
County sells parcel subscriptions and says detailed owner and mailing data are a
separate Public Extract/Assessment Roll purchase through IT Services. The county
page does not grant resale/SaaS redistribution rights, so county-paid extracts
remain on hold.

Davis County - NARROW ADMIT via UGRC basic/LIR only. Davis County property
search exposes owner, ownership history, recorded documents, tax information,
and REDI-Web subscriptions, but no reviewed stable bulk/API terms permit
commercial storage, display, export, or redistribution of owner/recorder facts.

Weber County - NARROW ADMIT via UGRC basic/LIR only; HOLD for the direct rich
county parcel service. Weber's official parcel MapServer exposes polygon
geometry, `PARCEL_ID`, owner name, situs/mailing address, market/taxable value,
tax year, property description, land acreage, improvement and use-code fields,
and JSON/GeoJSON/PBF paging, but no affirmative commercial reuse or
redistribution grant was found. Use it only as future licensing evidence unless
County permission is obtained.

Evidence URLs:
`https://gis.utah.gov/products/sgid/cadastre/parcels/`;
`https://gis.utah.gov/documentation/sgid/`;
`https://parcels.utah.gov/`;
`https://services1.arcgis.com/99lidPhWCzftIe9K/ArcGIS/rest/services/Parcels_SaltLake/FeatureServer/0`;
`https://services1.arcgis.com/99lidPhWCzftIe9K/ArcGIS/rest/services/Parcels_SaltLake_LIR/FeatureServer/0`;
`https://services1.arcgis.com/99lidPhWCzftIe9K/ArcGIS/rest/services/Parcels_Utah/FeatureServer/0`;
`https://services1.arcgis.com/99lidPhWCzftIe9K/ArcGIS/rest/services/Parcels_Utah_LIR/FeatureServer/0`;
`https://services1.arcgis.com/99lidPhWCzftIe9K/ArcGIS/rest/services/Parcels_Washington/FeatureServer/0`;
`https://services1.arcgis.com/99lidPhWCzftIe9K/ArcGIS/rest/services/Parcels_Washington_LIR/FeatureServer/0`;
`https://services1.arcgis.com/99lidPhWCzftIe9K/ArcGIS/rest/services/Parcels_Davis/FeatureServer/0`;
`https://services1.arcgis.com/99lidPhWCzftIe9K/ArcGIS/rest/services/Parcels_Davis_LIR/FeatureServer/0`;
`https://services1.arcgis.com/99lidPhWCzftIe9K/ArcGIS/rest/services/Parcels_Weber/FeatureServer/0`;
`https://services1.arcgis.com/99lidPhWCzftIe9K/ArcGIS/rest/services/Parcels_Weber_LIR/FeatureServer/0`;
`https://www.saltlakecounty.gov/assessor/parcel-data/`;
`https://is.utahcounty.gov/gis`;
`https://maps.utahcounty.gov/arcgis/rest/services/Assessor/Assr_Parcels/MapServer`;
`https://www.washco.utah.gov/departments/gis/data-request/`;
`https://www.daviscountyutah.gov/recorder/property-search`;
`https://maps.webercountyutah.gov/arcgis/rest/services/gis/parcels_geogizmo2/MapServer/0`.

## Maine - Portland, Biddeford, Bangor, Lewiston-Auburn, and statewide parcels

**Decision: narrow derived nearby-parcel admit for Maine GeoLibrary organized
town parcels; HOLD full assessor owner/value/sale resale and most direct
municipal rich assessor feeds.**

Primary production candidate:
`maine_geolibrary_organized_towns_parcels_nearby_narrow`. Official landing
pages: `https://storymaps.arcgis.com/stories/75f60604771f4c348c4f6ad5056a989f`
and `https://www.arcgis.com/home/item.html?id=28e35c8fcf514d2685357b78bdd0b246`.
Primary FeatureServer:
`https://services1.arcgis.com/RbMX0mRVOFNTdLzd/ArcGIS/rest/services/Maine_Parcels_Organized_Towns/FeatureServer`.
Adapter family: ArcGIS FeatureServer guarded snapshot with keyset paging on
`OBJECTID`, plus table join to layer 9 only for the admitted allowlist.

Use county plus `GEOCODE` plus normalized `STATE_ID` when populated, otherwise
`MAP_BK_LOT`, as the parcel identity; preserve `TOWN`, `COUNTY`, `CNTYCODE`,
`PARENT`, `FMSRCORG`, `FMUPDORG`, and per-record `FMUPDAT` for lineage and
currentness. Geometry is parcel polygon in EPSG:26919, converted to EPSG:4326
for point-on-surface and distance calculations. Admitted derived nearby fields
are parcel identity, town/county, `PROP_LOC`, `TYPE`, `LAND_USE`,
`LAND_USE_D`, `LOT_SIZE`, `LOT_UNITS`, `RES_AREA`, `CI_AREA`, land/building
value flags or values only when `FMUPDAT` passes the currentness gate, parcel
area, derived centroid, distance, and boundary relationship. Suppress
`OWNER1`, `OWNER2`, owner mailing fields, raw sale price/date/book/page,
source bulk extracts, and raw polygons in customer exports/API output until
written rights and currency standards are approved for those fields.

Sample query shape:
`/FeatureServer/10/query?where=OBJECTID>{last_objectid}&orderByFields=OBJECTID&outFields=OBJECTID,TOWN,COUNTY,CNTYCODE,GEOCODE,STATE_ID,MAP_BK_LOT,PARENT,PROP_LOC,TYPE,FMUPDORG,FMUPDAT,FMSRCORG&returnGeometry=true&outSR=4326&f=geojson&resultRecordCount=2000`;
join related records or page table 9 with
`outFields=OBJECTID,MAP_BK_LOT,GEOCODE,STATE_ID,LAND_VAL,BLDG_VAL,LOT_SIZE,LOT_UNITS,LAND_USE,LAND_USE_D,RES_AREA,CI_AREA`
only when the feature record has an acceptable `FMUPDAT`. Reject or quarantine
records with missing parcel identity, stale/blank `FMUPDAT`, duplicate
town/identity keys, geometry failures, or schema drift.

Rights and export policy:
`derived_nearby_parcel_context_only_no_owner_or_raw_assessor_resale`. Maine
GeoLibrary and MaineIT GIS publish the layer publicly and Maine law says
copyright or licensing restrictions may not be fixed on information made
available through the Maine Library of Geographic Information. That supports
narrow commercial SaaS use with Maine GeoLibrary/MaineIT GIS attribution and
source/currentness disclaimers. The source itself warns that organized towns
update voluntarily on a non-regular basis, many parcels can be several years
old, and Maine GeoLibrary does not maintain or verify municipal ownership.
Therefore customer output must be derived nearby context, not full assessor
resale, title evidence, owner marketing lists, or legal/conveyance-grade parcel
data.

Candidate decisions:

Portland/Cumberland County - NARROW ADMIT only as a city supplemental
geometry/situs/land-use source where Portland records are fresher than
GeoLibrary. Official endpoint:
`https://gis.portlandmaine.gov/maps/rest/services/planningCadastre/Parcels/MapServer/8`.
Use `IAS_PARCEL_ID` as city parcel identity, polygon geometry, `ST_NUM`,
`ST_NAME`, `UNIT_NUM`, `TYPE`, `LAND_USE`, `SQFT`, `UNITS`, `STORIES`,
`YRBLT`, and `URL_ASSESSOR`; suppress `OWN` and owner mailing fields. The
assessor public-access terms describe electronic public records and periodic
updates but do not grant assessor database resale or bulk customer export
rights.

Biddeford/York County - NARROW ADMIT only as a city supplemental
geometry/tax-map/zoning context source. Official landing pages:
`https://biddefordmaine.org/2691/GIS` and
`https://biddefordmaine.org/2806/GIS-Map-Room`; endpoint:
`https://services5.arcgis.com/QWn8PC1cSwbsBBh6/ArcGIS/rest/services/Biddeford__Online_Tax_Map__Parcels_and_Buildings_Related_Tables/FeatureServer/3`.
Use `Vision_PID` plus map/block/lot as identity, polygon geometry,
`Property_Location`, `Polytype`, `LUZone`, overlay flags, `Updated`, and
`TM_update_YR`. The city says GIS data is available as-is with no guarantee of
accuracy or currency and the parcel app is for planning purposes, so no raw
source export or assessor-owner/value/sale display is admitted.

Bangor/Penobscot County - HOLD. The city has an official GIS page and
Parcel/Property Viewer, and 2025 tax maps are public, but the reviewed evidence
did not identify a durable official parcel FeatureServer with field schema,
commercial SaaS rights, and export limits suitable for production ingestion.

Lewiston/Androscoggin County - NARROW ADMIT only as a city supplemental
geometry/commitment-context source. Official landing page:
`https://storymaps.arcgis.com/stories/c2a2cad0315e460b8e19a5ddf9b6180d`;
endpoint:
`https://maps2.lewistonmaine.gov/arcgis/rest/services/Public/LewParcels_public_recs/MapServer/0`.
Use parcel polygon geometry, public parcel identity/address fields, and 2025
tax-commitment currentness evidence; suppress assessor card, owner, value, and
sale facts unless separately licensed. Lewiston says GIS/CAD data is available
on request for surveyors, engineers, and developers, which is not enough for
unrestricted commercial SaaS resale.

Auburn/Androscoggin County - HOLD for the rich direct parcel service despite
strong technical fields. The public FeatureServer exposes `pid`, `parcelid`,
address, owner names, owner mailing address, land use, building
characteristics, sale date/price, grantor, prior sale fields, land/building
values, total value, and polygon geometry, but no reviewed official terms grant
commercial storage, customer display/API output, exports, or redistribution.
Use only after written city permission or another official rights record is
approved.

Statewide unorganized-territory parcels - HOLD for these focus markets. Maine
Revenue Services/LUPC unorganized-territory parcels are official for
unorganized territories but are outside the Portland, Biddeford, Bangor, and
Lewiston-Auburn organized-municipality targets. The source also warns that town
and plantation owner information can be as much as five years out of date and
must be paired with MRS auxiliary resources for up-to-date ownership.

Evidence URLs:
`https://services1.arcgis.com/RbMX0mRVOFNTdLzd/ArcGIS/rest/services/Maine_Parcels_Organized_Towns/FeatureServer`;
`https://services1.arcgis.com/RbMX0mRVOFNTdLzd/ArcGIS/rest/services/Maine_Parcels_Organized_Towns/FeatureServer/10`;
`https://services1.arcgis.com/RbMX0mRVOFNTdLzd/ArcGIS/rest/services/Maine_Parcels_Organized_Towns/FeatureServer/9`;
`https://legislature.maine.gov/statutes/5/title5sec2005.html`;
`https://legislature.maine.gov/statutes/5/title5sec1995.html`;
`https://gis.portlandmaine.gov/maps/rest/services/planningCadastre/Parcels/MapServer/8`;
`https://assessors.portlandmaine.gov/Search/Disclaimer.aspx?FromUrl=..%2Fsearch%2Fcommonsearch.aspx%3Fmode%3Daddress`;
`https://biddefordmaine.org/2691/GIS`;
`https://biddefordmaine.org/2806/GIS-Map-Room`;
`https://services5.arcgis.com/QWn8PC1cSwbsBBh6/ArcGIS/rest/services/Biddeford__Online_Tax_Map__Parcels_and_Buildings_Related_Tables/FeatureServer/3`;
`https://www.bangormaine.gov/351/Geographic-Information-Systems-GIS`;
`https://www.bangormaine.gov/186/Tax-Maps`;
`https://storymaps.arcgis.com/stories/c2a2cad0315e460b8e19a5ddf9b6180d`;
`https://maps2.lewistonmaine.gov/arcgis/rest/services/Public/LewParcels_public_recs/MapServer/layers`;
`https://www.lewistonmaine.gov/m/faq?cat=25`;
`https://auburnmaine.gov/departments/assessing/index.php`;
`https://services6.arcgis.com/HvbabY0grzgZwGW1/ArcGIS/rest/services/Auburn_Maine_Parcels/FeatureServer/0`;
`https://gis.maine.gov/mapservices/rest/services/mrs/Maine_Parcels_Unorganized_Territory/MapServer`.

## Iowa - Statewide and Focus-County Parcels

**Decision: hold Iowa parcels for production SaaS reuse. Woodbury County /
Sioux City is the closest geometry-only Phase 2 candidate, but no Iowa parcel
source enters the active catalog until commercial storage, derived scoring,
customer display, API output, export, retention, attribution, suppression, and
raw-resale terms are confirmed in writing.**

- Statewide Iowa DOR `Properties` covers all 99 counties in WGS84 and exposes
  county name, situs address, city, total/historical value fields, URL, and
  geometry, but it is a 2019-edited snapshot, lacks a durable parcel ID, owner,
  acreage, building area, sale fields, and published commercial reuse terms.
  Do not use `OBJECTID` as parcel identity.
- Statewide HSEMD `Iowa_Parcels_2017` is rejected for production because the
  service is deprecated, no longer routinely maintained, and represents parcels
  updated no later than November 2, 2017.
- Polk County / Des Moines, Cedar Rapids, Scott County / Davenport, Johnson
  County / Iowa City, and Story County / Ames are technically useful but rights
  holds. Reviewed services expose combinations of stable parcel IDs, polygons
  or parcel points, situs addresses, owner/mailing fields, property classes,
  acreage, values, buildings, deed/sale layers, centroids, pagination, and
  spatial queries, but no affirmative commercial SaaS storage/display/API/export
  or raw-resale permission was verified.
- Woodbury County / Sioux City polygon parcels expose `PIN`, parcel-fabric
  identifiers, stated/calculated area, validation/edit dates, and current
  geometry with a public-use statement. The layer does not expose owner, situs,
  value, zoning, building, or sale fields, and commercial resale rights remain
  ambiguous. If written terms are granted, admit only geometry-derived nearby
  context first.
- Default suppression until explicit permission: owner names, mailing
  addresses, deed holders, deed history, tax delinquencies, exemptions, legal
  descriptions, document links, assessed/taxable values, sale price/date, raw
  polygons, raw parcel extracts, and customer-requested bulk parcel exports.
- Permission priority: Woodbury geometry-only pilot, Polk County, Cedar Rapids,
  Scott County, Story County, Johnson County, then Iowa DOR statewide snapshot.
  Permission must cover storage, derived nearby-parcel scoring, customer display,
  API responses, exports, retention period, attribution, field suppression, and
  raw resale separately.

Evidence URLs:
`https://services.arcgis.com/vPD5PVLI6sfkZ5E4/ArcGIS/rest/services/Properties/FeatureServer`;
`https://services.arcgis.com/vPD5PVLI6sfkZ5E4/ArcGIS/rest/services/Properties/FeatureServer/0`;
`https://services3.arcgis.com/kd9gaiUExYqUbnoq/arcgis/rest/services/Iowa_Parcels_2017/FeatureServer`;
`https://gis.polk-county.net/server/rest/services/Map_Property_Appraiser/FeatureServer`;
`https://gis.polk-county.net/server/rest/services/Map_Property_Appraiser/FeatureServer/1`;
`https://www.linncountyiowa.gov/assessor`;
`https://gis.linncountyiowa.gov/apps/real-estate/land-records/`;
`https://gis.linncountyiowa.gov/ags/rest/services`;
`https://crgis.cedar-rapids.org/arcgis/rest/services/Parcels/FeatureServer/1`;
`https://services.arcgis.com/ovln19YRWV44nBqV/arcgis/rest/services/Cadastral/FeatureServer`;
`https://services.arcgis.com/ovln19YRWV44nBqV/arcgis/rest/services/Cadastral/FeatureServer/3`;
`https://www.scottcountyiowa.gov/it/gis-map-service`;
`https://services.arcgis.com/kd1jFI4TM5bZHeP8/arcgis/rest/services/parcel_polygon_feature/FeatureServer`;
`https://services.arcgis.com/kd1jFI4TM5bZHeP8/arcgis/rest/services/parcel_polygon_feature/FeatureServer/0`;
`https://www.arcgis.com/home/item.html?id=9dcdef61b4ff4ad8950f5576707ce594&sublayer=0`;
`https://www.arcgis.com/home/item.html?id=328629b5277f431d862acfd2a236ce5b`;
`https://gis.johnsoncountyiowa.gov/arcgis/rest/services/Land_Records/MapServer`;
`https://gis.johnsoncountyiowa.gov/arcgis/rest/services/PDS/MapServer`;
`https://gis.johnsoncountyiowa.gov/arcgis/rest/services/CityAssessor/Land_Records_IC/MapServer`;
`https://gis.johnsoncountyiowa.gov/arcgis/rest/services/CityAssessor/Iowa_City_Assessor_Data/MapServer`;
`https://apps.storycounty.com/arcgis/rest/services/parcels/FeatureServer`;
`https://apps.storycounty.com/arcgis/rest/services/parcels/FeatureServer/0`;
`https://iowalandrecords.org/terms-of-service/`.

## Mississippi - MARIS/MDEQ and Focus-County Parcels

**Decision: hold Mississippi parcels for production SaaS reuse pending written
commercial-use permission. MARIS/MDEQ's 2024 cadastral framework is the
technical baseline for nearby-parcel discovery, but customer-facing display,
API output, exports, long-term retention, and raw resale remain disabled until
rights are confirmed.**

- MARIS/MDEQ statewide 2024 cadastral data covers all 82 counties with East and
  West downloadable parcel shapefiles plus a statewide REST MapServer. It
  provides parcel polygons/centroids, county layers, 40+ attributes, annual or
  periodic update evidence, JSON/GeoJSON/PBF query support, spatial queries,
  and 2,000-record REST caps. Use official downloads for statewide bulk
  evaluation rather than repeated REST scans.
- Rights blocker: MARIS states the files are not legal data, may not be current
  or complete, and directs users to county assessors for authoritative records.
  No affirmative commercial SaaS license was verified for storage, derived
  nearby-parcel scoring, customer display, API responses, exports, retention,
  or raw parcel resale.
- Hinds/Jackson, Harrison/Gulfport-Biloxi, DeSoto/Southaven,
  Forrest/Hattiesburg, Lee/Tupelo, and Lauderdale/Meridian are all holds.
  Reviewed layers expose combinations of `PARNO`, `PPIN`, situs, owner,
  acreage, values, tax year, sales history, land-use fields, zoning in some
  county services, centroids, spatial queries, and local parcel services. DeSoto
  is the strongest local attribute source and advertises pagination/distance
  queries, but still needs assessor permission.
- Internal key if unlocked: `ms:{county_fips}:{normalized_source_parcel_id}`.
  Prefer `PPIN` where stable, then county `PARNO`/CAMA identifiers. Preserve
  raw identifiers exactly and never use `OBJECTID` or `FID` as the durable
  business key.
- Default admission target after rights: parcel key, county, source release/tax
  year, internal polygon geometry, validated WGS84 centroid, situs address,
  city/state/ZIP, GIS and tax acreage with labels, land-use/classification,
  assessed/land/improvement/total values with source year, sale date/amount as
  low-confidence enrichment only where licensed, source attribution, and viewer
  URL.
- Default suppression until explicit permission: owner/co-owner names, mailing
  addresses, care-of fields, deed references, document links, legal
  descriptions, raw assessor exports, full polygon downloads, personal-property
  or exemption details, unvalidated zoning, sales as market-value claims, and
  building area unless independently confirmed.
- Coordinate validation: request `outSR=4326`; verify longitude approximately
  `-91.74` to `-88.09` and latitude `30.10` to `35.01`; compare centroids
  against `LATDEC`/`LONGDEC` or `INSIDE_X`/`INSIDE_Y`; reject projected-foot
  coordinates, swapped coordinates, invalid rings, null geometry, and centroids
  outside Mississippi or outside the parcel.

Evidence URLs:
`https://maris.mississippi.edu/HTML/DATA/data_Cadastral/CadastralFramework.html`;
`https://maris.mississippi.edu/MARISdata/Parcels/`;
`https://gis.mississippi.edu/server/rest/services/Cadastral/MS_Parcels_Aprl2024/MapServer`;
`https://gis.mississippi.edu/server/rest/services/Cadastral/MS_Parcels_Aprl2024/MapServer/11`;
`https://gis.cmpdd.org/arcgis/rest/services/Hosted/City_of_Jackson_Feature_Layer/FeatureServer/11`;
`https://arcgis.jacksonms.gov/arcgis/rest/services/Maps/NewJxnMap/MapServer/6/query`;
`https://gis.mississippi.edu/server/rest/services/Cadastral/MS_Parcels_Aprl2024/MapServer/51`;
`https://geo.co.harrison.ms.us/server/rest/services/External/parcelsPublic/MapServer`;
`https://data.mmcp.ms.gov/dataset/Approved-Parcels/quj8-9rcw`;
`https://gis.desotocountyms.gov/arcgis/rest/services/CountyWebMap/Tax_Assessors_County_Web_Map/MapServer/29`;
`https://maps.desotocountyms.gov/arcgis/rest/services/Preliminary_2025_Landroll_Parcels/MapServer`;
`https://desotocountyms.gov/205/GIS-Maps-Data`;
`https://forrestcountyms.us/forrest-county-tax-office/`;
`https://gis.mississippi.edu/server/rest/services/Cadastral/MS_Parcels_Aprl2024/MapServer/47`;
`https://gis.mississippi.edu/server/rest/services/Cadastral/MS_Parcels_Aprl2024/MapServer/61`;
`https://gis.mississippi.edu/server/rest/services/Cadastral/MS_Parcels_Aprl2024/MapServer/59`.

## Nebraska - Statewide and Focus-County Parcels

**Decision: hold all reviewed Nebraska parcel sources for production SaaS
reuse pending written commercial storage, derived-data, customer-display, API,
export, retention, attribution, and suppression terms. Lincoln / Lancaster PATS
development applications are admitted separately as a permit/development source,
not as parcel coverage.**

- Highest-priority permission target: `ne_statewide_assessor_parcels`. The
  Nebraska statewide parcel FeatureServer covers the state with county-local
  parcel identifiers, situs address components, acreage, zoning/classification,
  assessed value, sale fields, update dates, polygons, pagination, spatial
  queries, Extract capability, and server centroids. However, reviewed metadata
  describes the layer as compiled for official/internal use and credits county
  assessors; it is not an affirmative commercial SaaS redistribution grant.
- Douglas County/Omaha, Lancaster County/Lincoln, Sarpy County/Bellevue, Hall
  County/Grand Island, and Buffalo County/Kearney are technically useful Phase 2
  targets but remain holds. Public layers or viewers expose combinations of
  parcel geometry, parcel IDs, situs addresses, owner/mailing fields, values,
  legal descriptions, building characteristics, deed/sale context, or parcel
  points, but reviewed terms are informational, permission-gated, stale, or
  explicitly block secondary dissemination.
- If rights are granted, production should suppress owner names, owner mailing
  addresses, legal descriptions, assessed values, sale/deed fields, raw
  polygons, and raw parcel exports unless the permission explicitly covers
  those fields. Use stable parcel IDs such as `State_PID`, `Parcel_ID`, `PIN`,
  or `PARCELID`; do not use mutable `OBJECTID` as durable parcel identity.
- Technical priority order for written permission: statewide Nebraska parcels,
  Douglas County, Lancaster County, Sarpy County, Hall County, then Buffalo
  County. The strongest eventual Phase 2 slice is statewide coverage enriched
  by Douglas/Lancaster/Hall local source confirmation.

Evidence URLs:
`https://giscat.ne.gov/enterprise/rest/services/StatewideParcelsExternal/FeatureServer/0`;
`https://dcgis.org/server/rest/services/vector/Parcels_public/MapServer/0`;
`https://gis.lincoln.ne.gov/public/rest/services/Assessor/TaxParcels/MapServer/0`;
`https://www.lancaster.ne.gov/1485/GIS`;
`https://www.sarpy.gov/187/Geographic-Information-System-GIS`;
`https://geodata.sarpy.gov/arcgis/rest/services/Cadastral/LandRecordsDynamic/MapServer`;
`https://gis.grand-island.com/arcgis/rest/services/County/ParcelOwners/MapServer/0`;
`https://gis.grand-island.com/arcgis/rest/services/PublicWorks/Parcels_Addresses_PW/MapServer/9`;
`https://buffalocounty.ne.gov/county-offices/assessor/buffalo-county-gis`.

## North Dakota - Statewide Parcels and Fargo/Bismarck Permit Candidates

**Decision: narrow derived nearby-parcel admit for Cass County; statewide North
Dakota parcel layer remains a rights-confirmation hold. Bismarck development
activities are admitted as a narrow permit/development source, while Fargo
permit reports remain a permit-source candidate pending final onboarding.**

- Production source candidate: `cass_county_nd_parcels_nearby_narrow`. The
  official Cass County Tax Parcels FeatureServer exposes queryable parcel
  polygons covering Fargo, West Fargo, and Cass County with `MaxRecordCount=2000`
  and North-Dakota coordinates. The County GIS FAQ says digital data downloads
  are free and tax/assessment data in the interactive site is refreshed nightly
  and may be up to two days old.
- Use `GISPIN`, falling back to `PIN`, `DASHPIN`, `ALTPIN`, or `UNIQUEID`, as
  canonical parcel identity. `OBJECTID` is only a transport cursor. Query with
  `outSR=4326`, derive centroids for radius search, and retain geometry for
  future exact-boundary distance. Condo/mobile-home rows can duplicate geometry,
  so downstream physical-parcel grouping should prefer `GISPIN`.
- Admitted fields are parcel geometry, `GISPIN`, parcel/address aliases,
  jurisdiction, school/district context, subdivision/plat/source codes, acreage,
  commercial/residential class, situs city/state/ZIP, and stable source
  evidence. Owner names, owner mailing fields, legal descriptions, value fields,
  sale facts, raw extracts, and bulk geometry resale are not admitted in the
  first production slice.
- Rights pass only for a narrowed nearby-parcel context with Cass County GIS
  attribution and no-warranty/currentness disclaimers. Do not imply
  title-quality boundaries or use this source as sale/assessed-value evidence.
- North Dakota GIS Hub statewide parcels remain a technical fallback and rights
  hold. The public authoritative FeatureServer covers the state and was updated
  July 6, 2026, but counties remain primary custodians, the tax-roll join is a
  separate table, and the reviewed metadata is not an affirmative commercial
  SaaS redistribution grant.
- Fargo's OneStop commercial plan-review report remains a high-value permit
  candidate because it exposes filed projects, addresses/parcels, descriptions,
  and review statuses across departments. It is current and exportable to CSV,
  but the public help page caps exports at 200 records and no affirmative
  commercial SaaS reuse grant was found.
- Bismarck's open development activities layer is admitted as
  `bismarck_nd_development_activities`. It contains pre-approval through
  approved/finalization statuses, project names, descriptions, applicants,
  developers, parcel/address, dates, links, and geometry. Exclude fees,
  internal editor/audit fields, legal descriptions, raw geometry exports, and
  source replacement resale. The separate Building Permit Activities ArcGIS
  layer remains a future approved/recent-activity confirmation candidate.
- Grand Forks, Minot, and West Fargo remain holds because reviewed public pages
  expose search portals, monthly archives, forms, or deadlines rather than a
  bulk/API application register with clear reuse rights.

Evidence URLs:
`https://www.gis.nd.gov/`;
`https://www.arcgis.com/home/item.html?id=ac6da1176038457db16e8debe3f1abaf`;
`https://services1.arcgis.com/GOcSXpzwBHyk2nog/arcgis/rest/services/NDGISHUB_Parcels/FeatureServer/0`;
`https://www.casscountynd.gov/our-county/gis`;
`https://www.casscountynd.gov/our-county/gis/faqs`;
`https://gisweb.casscountynd.gov/arcgis/rest/services/OpenData/OpenData/FeatureServer/7`;
`https://permits.fargond.gov/Dashboard.aspx?report=permitReviewsPrmtTableDiv`;
`https://permits.fargond.gov/Help.aspx`;
`https://bismarcknd.gov/2384/Open-Development-Projects`;
`https://www.arcgis.com/home/item.html?id=90744ac909e04dfab1ba94c718d32ef0`.

## South Dakota Focus Counties

**Decision: Sioux Falls / Minnehaha parcel narrow admit; Pennington, Brown,
Brookings, and statewide sources hold.**

- Production source candidate: `sioux_falls_sd_parcels_nearby_narrow`. The
  official City of Sioux Falls ArcGIS item `d57efdf717064169a21c70b8b380e387`
  describes authoritative parcel polygons for Sioux Falls, South Dakota; the
  City is responsible for parcel geometry and shares parcel attribute
  responsibility with Minnehaha County and Lincoln County. The item is public,
  authoritative, and licensed under CC BY 4.0. A previously reviewed
  `services.arcgis.com/iPiPjILCMYxPZWTc/.../Tax_Parcels/FeatureServer/5`
  endpoint returned non-South-Dakota sample coordinates and is not admitted.
- Use `TAG` as canonical parcel identity. `OBJECTID` is only a transport cursor.
  Query with `outSR=4326`, derive centroids for radius search, and retain
  geometry for future exact-boundary distance.
- Admitted fields are parcel geometry, `TAG`, situs address/ZIP, county,
  acreage, parcel square feet, activity/land-use class, parcel type, owner name
  and mailing fields, legal-start/form dates, unit counts, and stable source
  evidence. No complete sale-history source was identified, and legal
  descriptions are unnecessary for Phase 2 nearby-parcel scoring, so sale and
  legal-description evidence remain out of scope.
- Query with guarded ArcGIS pages, for example
  `/MapServer/1/query?where=TAG%20IS%20NOT%20NULL%20AND%20TAG%20%3C%3E%20%27%27&outFields=OBJECTID,TAG,ADDRESS,ACREAGE,SQFT,ACTIVITY,OWNNAME1,OWNNAME2,OWNADDRESS,OWNCITY,OWNSTATE,OWNZIP,OWNZIP2,COUNTY,COUNTYID,LANDUSE,NUMUNITS,LegalStartDate,FORM_DATE,PARCELTYPE,ZIPCODE&returnGeometry=true&outSR=4326&resultRecordCount=200&f=json`.
  Block publication on null/duplicate `TAG`, empty geometry, schema drift,
  count collapse, or stale edit dates.
- Rights pass only for a narrowed nearby-parcel context under CC BY 4.0:
  internal storage and customer display/API output of derived parcel context
  with City of Sioux Falls/Minnehaha County attribution, license link, retrieval
  date, change notice, and public-record disclaimer. Do not imply title-quality
  ownership, do not export raw source parcels as a standalone resale dataset,
  and suppress fields if later county terms conflict with the catalog license.
- Pennington County/Rapid City is a technical hold. The official open
  TaxParcels FeatureServer exposes 54,804 polygons with `PIN`, `TaxID`,
  `PropAddress`, grantee/grantor instrument fields, land-use/type flags,
  land/structure/total values, acreage, and EPSG:6574 geometry, and RapidMap
  notes weekday morning data loads. However, reviewed rights evidence limits
  unrestricted distribution to printed maps and Pennington County website terms
  require permission for reproduction, modification, distribution, or commercial
  use beyond personal/educational/non-commercial use.
- Brown County/Aberdeen is a hold. The official assessor page routes property
  GIS/ownership/assessment/tax to Beacon, with richer sales/building/soil
  details behind paid subscription, and the county GIS ordinance establishes
  licensed data access, redistribution, and third-party licensing controls.
- Brookings County is a hold. The GIS division maintains parcel data and Beacon
  exposes tax-property map context, including recent sales, but official
  ordinance/request-form evidence requires written approval, treats the data as
  county property, bars copying, publishing, transfer, sale, sublicensing, or
  third-party release without permission, and prices parcel products and
  ownership/address attributes separately.
- No statewide South Dakota parcel/cadastral source cleared the gate for these
  markets. The Department of Revenue describes county directors of equalization
  as the assessors for real property and directs parcel-specific assessment
  questions to the counties; the state property-tax portal is not a countywide
  parcel geometry/owner/value bulk source.

Evidence URLs:
`https://catalog.data.gov/dataset/minnehaha-county-gis-open-data`;
`https://dataworks.siouxfalls.gov/documents/cityofsfgis::minnehaha-county-gis-open-data`;
`https://www.arcgis.com/home/item.html?id=d57efdf717064169a21c70b8b380e387`;
`https://gis.siouxfalls.gov/arcgis/rest/services/Data/Property/MapServer/1`;
`https://gis.rcgov.org/server/rest/services/OpenData/TaxParcels/FeatureServer/0`;
`https://www.arcgis.com/home/item.html?id=b840192c688f4ebe8c9b9aeb548952d0`;
`https://www.rcgov.org/departments/public-works/geographic-information-system/rapidmap-214.html`;
`https://www.pennco.org/terms_and_conditions/index.php`;
`https://www.brown.sd.us/department/assessor/beacon`;
`https://www.brown.sd.us/ordinance/title-19-gis-data-access-and-distribution`;
`https://www.brookingscountysd.gov/194/Geographic-Information-Systems`;
`https://www.brookingscountysd.gov/197/Interactive-Maps`;
`https://www.brookingscountysd.gov/DocumentCenter/View/67`;
`https://www.brookingscountysd.gov/DocumentCenter/View/65`;
`https://www.brookingscountysd.gov/DocumentCenter/View/64`;
`https://dor.sd.gov/individuals/taxes/property-tax/`;
`https://dor.sd.gov/government/director-of-equalization/contact-county-directors-of-equalization/`.

## Cook County, IL - Assessor Parcel Universe Current Year

**Decision: narrow derived nearby-parcel context admit.**

- Production source: `cook_county_il_assessor_parcels_current_year_nearby`.
- Endpoint:
  `https://datacatalog.cookcountyil.gov/resource/pabr-t5kh.json`.
  The official dataset is `Assessor - Parcel Universe (Current Year Only)`,
  published by the Cook County Assessor's Office Data Department. Live metadata
  reviewed on July 18, 2026 showed roughly 1.86M current-year parcel rows,
  `row_id` as the API row key, countywide geographic coverage, and bi-weekly
  publishing/data-change frequency.
- Admitted fields are parcel identity (`pin`, `pin10`, `row_id`, `year`),
  centroid coordinates, ZIP, property class, township, neighborhood/tax codes,
  municipality, ward, Chicago community area, industrial corridor, enterprise
  zone, opportunity-zone, central-business-district, flood/noise indicators,
  TIF, walkability score, and subdivision ID. These support Phase 2 radius
  discovery and parcel-context explanations around Chicago-area permit signals.
- Address, owner, assessed-value, sale, deed, and raw parcel-source replacement
  exports are intentionally out of scope for this source. Cook County first-party
  address and assessed-value datasets can be admitted later as separate,
  reviewed joins by `pin` + `year` if the enrichment path needs those fields.
- Query with Socrata keyset pagination on `row_id`, selecting only allowlisted
  fields and filtering to rows with `pin`, `row_id`, `lat`, and `lon`. Block
  publication on null/duplicate row identity, missing coordinates, schema drift,
  stale metadata, or abnormal row-count collapse.
- Rights pass is based on Cook County's open-data posture for free,
  machine-readable public data. Build Signals uses this as value-added
  nearby-parcel context with Cook County Assessor attribution, retrieval date,
  public-record/current-year caveats, and no raw bulk parcel resale.

Evidence URLs:
`https://datacatalog.cookcountyil.gov/Property-Taxation/Assessor-Parcel-Universe-Current-Year-Only-/pabr-t5kh`;
`https://datacatalog.cookcountyil.gov/api/views/pabr-t5kh`;
`https://datacatalog.cookcountyil.gov/stories/s/Open-Data-Policy/bq8i-b9qy/`;
`https://datacatalog.cookcountyil.gov/stories/s/gzdr-q7c4`;
`https://github.com/ccao-data/wiki/blob/master/SOPs/Open-Data.md`.
## Washington DC - Owner Polygons Common Ownership Layer

**Decision: narrow derived nearby-parcel admit.**

- Production source: `washington_dc_owner_parcels_nearby`.
- Endpoint:
  `https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/Property_and_Land_WebMercator/FeatureServer/40/query`.
  The official layer name is Owner Polygons (Common Ownership Layer), exposes
  ArcGIS FeatureServer pagination, and returned service centroids during live
  validation on July 18, 2026.
- Admitted fields are `SSL`, situs address, owner name, owner mailing address,
  land area, current land/improvement/total assessed values, last sale
  date/price, property/use code, vacancy land-use indicator, extract/edit dates,
  and service centroid. The source uses `SSL` as stable parcel identity and
  `OBJECTID` only as an ArcGIS cursor.
- Suppressed fields include deed book/page/instrument internals, mortgage
  company, annual tax and tax-balance fields, tax rates, binary annotation data,
  shape metrics, raw polygon export, and raw source-replacement exports.
- Rights pass is based on DC Open Data's public-domain / commercial-compatible
  reuse posture unless otherwise noted. Build Signals uses this as value-added
  parcel proximity, scoring, and graph evidence with District attribution and a
  public-record/currentness disclaimer, not as a title or tax-balance product.
