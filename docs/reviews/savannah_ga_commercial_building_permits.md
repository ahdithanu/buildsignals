# Savannah Commercial Building Permit Tracker Review

## Decision

Status: `operational_retry`

The official City of Savannah Permit Tracker and SAGIS feature service passed a
bounded no-write lifecycle canary. Production use is not yet approved.

## Source Contract

- Official page: https://www.savannahga.gov/4290/Permit-Tracker
- Public service: https://pub.sagis.org/arcgis/rest/services/Savannah/BuildingPermit_FC/FeatureServer/0
- Scope: commercial building permits in `In Review`, `Approved`, or `Issued`
- Publisher cadence: weekly
- Pagination: ascending `OBJECTID` keyset, 2,000 rows per production page
- Row identity: `PermitNumber|Address|OBJECTID`
- Business identity: `PermitNumber`
- Lifecycle: `In Review` is pre-approval; `Approved` and `Issued` are approved

Permit number alone is not a safe row key because the public layer can repeat a
permit across multiple site addresses, and a permit/address pair can repeat
across tracker observations. The composite identity preserves each source row
while retaining the permit number for graph resolution.

## Data Minimization

The candidate fetches only object ID, parcel PIN, permit number, permit type,
work class, status, district, issued/finalized dates, site address, work
description, and valuation. It does not request applicant names, contacts,
attachments, documents, or raw geometry.

## Rights And Freshness

The City identifies the tracker as Development Services-managed and updated
weekly. SAGIS describes its open-data catalog as publicly available for no-cost
download and public use. Before production promotion, the Build Signals owner
must explicitly approve the narrow commercial derived-intelligence scope,
attribution, evidence retention, and raw-source replacement prohibition.

## Initial Evidence

On August 20, 2026, the formal connector canary fetched and validated 70 of 70
observations with zero failures: 18 pre-approval and 52 approved. Separate stage
probes confirmed both `In Review` and `Approved`/`Issued` behavior. Current 2026
examples included a grocery store, hotels, new commercial construction, and
tenant buildouts.
