# Cherry Hill Zoning: Metadata Qualification

## Scope And Result

Read-only public metadata discovery, November15. No feature inventory was
downloaded, stored in an application database or activated for ingestion. This
does not qualify parcel joins, current permitted uses or production coverage.
Existing NJGIN parcel radius caps and production hold are unchanged.

The prior historical anchor case22-P-0043/block133.01/lot7 is a research pointer,
not current entitlement or parcel continuity proof. The prior 161-row publisher
radius verification retained no reusable parcel polygons; do not repeat that
radius collection merely to generate another receipt. MOD-IV municipality/map
identifiers must not be interpreted as zoning. Owner-mail fields are not situs.

## Official References

- [Municipal ordinance landing page](https://chnj.gov/160/Zoning-Ordinance)
  explicitly separates its November2022 base document from later amendments.
  Effective-law completeness must be reconciled before any use classification.
- [Municipal zoning guidance](https://www.chnj.gov/203/Zoning) links the ordinance,
  interactive map and additional diligence references. Proposed uses need a
  specific definition rather than a generic retail/office label.
- [Municipally linked Chapter40](https://ecode360.com/44759761) and
  [ArticleIV district rules](https://ecode360.com/44761061) are rule references,
  not yet captured/reconciled into a reviewed, dated rules corpus.
- [Official interactive map](https://gis.chtownship.com/CH_PublicWorksWebMap2022/index.html)
  points through its public config to ArcGIS webmap
  `d988ae07e18f484f8a7dfe0ea1242ec5` in the municipal portal.

## Verified Service Metadata

Webmap operational metadata points to
`https://gis.chtownship.com/arcgis/rest/services/CherryHill_Zoning/MapServer`.
The service root returned polygon layers0Parcels,1OverlayZones,
2RedevelopmentAreas and3Zoning; Query/Data capabilities, maxRecordCount1000,
source spatial reference102711/latest3424 (feet). Layer3 metadata exposes
`ZONE_CURR` as the zoning renderer field, `Zoning2018` as a separate historical
field, `OBJECTID_1` as transport OID and `BLOCK` as a display field. Neither OID
nor block alone is a durable parcel identity. Its advertised pagination and
geometry formats are capabilities, not tested completeness or join acceptance.

Metadata copyright/description fields were blank. Blank metadata is not a reuse
license, certification of currency, or permission to redistribute a raw corpus.
Effective dates and complete amendment/overlay applicability remain unverified.
No code labels or sample map categories were used as golden permitted-use labels.

## Request Bounds And Tooling

Browser-text extraction could not parse the map app/config. A normal direct
HTTPS metadata GET succeeded without alternate proxies, cookies, spoofed
headers or transport-policy bypass. Requests to config, webmap item data,
MapServer root and layer3 were bounded at30seconds/8MiB per response, without
redirect following or transient retries. Root metadata output was initially
truncated by the tool; a subsequent small response was successfully inspected.
These are logical observed operations, not a measurement of wire attempts.
No count/feature/radius/geometry query, paid call, source registration, production
task or data mutation was performed by this qualification.

## Next Acceptance Gate

Qualify current parcel identity/full geometry and responsible authority; retain
a narrowly projected, bounded, rights-reviewed zoning/overlay capture with
effective-date evidence. Use a proven spatial engine and full geometries, not
the display boundary helper that can omit multipolygon parts. Report exact,
split/ambiguous, unmatched and conflicting assignments separately. Reconcile
applicable code plus amendments and choose one specific proposed use for human-
reviewed expected classifications. Keep possible entitlement paths, adopted
zoning and actual recorded decisions separate. No production activation or paid
AI evaluation follows merely from this metadata discovery.
