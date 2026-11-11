# New Port Richey Supported Automation Follow-Up

## November 10 Public Catalog Follow-Up

The parent subsequently used the documented, public ArcGIS search endpoint
for City-linked organization `5fOG6RMXXiEvqNzn`: 62 public items returned,
nextStart -1. Public item `c05de30e23354a62bbc8ceab4646fd73`,
`NPR 2026 Community Development Map_WFL1`, advertises Query capability, but
its service has only MPOD (1), NPR_Zoning_2026 (10), and NPR_FLU_2026 (11)
polygon layers. Item description, licenseInfo and accessInformation were blank.
Service URL: https://services7.arcgis.com/5fOG6RMXXiEvqNzn/arcgis/rest/services/NPR_2026_Community_Development_Map_WFL1/FeatureServer

This bounded catalog search plus item/service metadata reads supersede the
six-request-only stopping point below. No feature rows, contact records or
private Tyler endpoints were requested. This is a zoning/land-use lead, not
a permit or development-application export; no source was activated. The
remaining dependency is a supported recurring permit delivery contract and
retrieved artifact. City inquiries remain drafts; the November 10 Investment
Areas API/panel release approval explicitly excludes new-source activation.

The original investigation ledger is retained below as a dated receipt, not
an assertion that no later public catalog investigation occurred.

November 9, 2026. Read-only primary-source investigation. This writer changed
only this note; no browser, accounts, emails, requests submitted to the City,
fees, model calls, private APIs, database/cloud writes or source activation.

## Result And Exact Blocker

**No supported automatic permit ingestion path was verified within six research
requests.** The City publishes a public lookup portal and a GIS hub, but no
documented permit API, verified permit-row export artifact, recurring delivery
contract or public GIS permit layer was found in the reviewed sources. This is
a bounded negative result, not a claim those mechanisms do not exist.

The blocker is a supported, reproducible delivery contract for City permit
records: a published permit dataset/query endpoint, stable static report index,
or City-confirmed electronic export with an actually retrieved, scoped artifact.
Public lookup capability and vendor SPA implementation details do not supply
that contract. No worker-network canary or scheduled-ingestion acceptance was
performed. Keep NPR unactivated.

The [prior qualification](2026-11-09-new-port-richey-source-qualification.md)
remains the baseline for anonymous UI behavior. This investigation did not
repeat that search or claim a successful CSV download from it.

## Six-Request Ledger

Requests below count individual searches and opens, not just batched tool calls.
Search results are indexed official-page evidence, not fresh HTTP acceptance of
every referenced URL. No downloaded documents, feature rows or contact records
were retained.

| Request | Scope | Actual outcome |
| --- | --- | --- |
| 1 | City-domain search for permit reports, open data, GIS export/API | Official Building Division describes permit/plan lookup. No documented bulk interface in returned material. |
| 2 | ArcGIS-domain search for New Port Richey GIS permits/open data | City GIS hub surfaced; other results were County boundaries, zoning and an overlay district, not a City permit feed. |
| 3 | City-domain search for permit reports/export data | Building information and annual utilization/budget/environmental reports surfaced; no verified row-level building-permit series. |
| 4 | Read-only open of City GIS hub root | HTML returned with zero readable lines in the web tool. No dataset inventory or permit export schema verified. |
| 5 | City-domain search for public records/existing electronic data | Official Clerk guidance documents the request channel and recommends JustFOIA for tracking. |
| 6 | City/hub-domain search for GIS Maps and Data / permits / building | Official sitemap confirms GIS navigation under Technology Solutions and Business Development. No permit layer endpoint identified. |

No additional live requests, hidden catalog enumeration or guessed service
paths were made after request6.

## Verified Primary-Source Leads

### Building Division

[Official Building Division](https://www.cityofnewportrichey.org/Business/Development/Building-Division)
describes construction permitting/inspection responsibility within City limits
and Citizen Access permit/plan lookup. It warns that an NPR postal address does
not establish City jurisdiction. Its FY20-21 permit/inspection utilization-report
link is not evidence of a current record-level feed. This investigation did not
download that report or assert a schema. The department's published fallback
email for submitting applications is not an authorized ingestion mailbox.

No City-supported API, unattended export procedure or recurring permit-report
subscription was documented in the returned Building Division material.

### GIS Hub And Catalog Export Distinction

[City of New Port Richey GIS Data Hub](https://new-port-richey-gis-data-npr.hub.arcgis.com/)
was directly opened; no readable dataset listing was returned. An indexed
[hub search page](https://new-port-richey-gis-data-npr.hub.arcgis.com/search?tags=administrative%2520boundaries%2Ccity%2520limits%2Cboundaries%2Ccity%2520boundaries%2Coverlay%2520district)
exposes an "Export public catalog (CSV)" label. That label concerns the public
catalog, not verified permit records; no export was clicked/downloaded and no
permit dataset was identified. The
[official City sitemap](https://www.cityofnewportrichey.org/Sitemap)
confirms public GIS navigation, but provides no verified permit service contract
in this research result. Do not infer one from the generic ArcGIS platform.

County zoning/city-boundary search results and the joint Manatee Point overlay
are not City permit submissions. No Pasco County source was substituted for NPR
permit coverage, and no internal Tyler API was inferred or called.

### Supported Inquiry Route

The [official City Clerk page](https://www.cityofnewportrichey.org/Government/City-Clerk)
directs general-department records requests to the Clerk and recommends its
JustFOIA portal for tracking; it also describes in-person, telephone and email
requests. This is a documented inquiry route, not an automated feed agreement.
No form was opened/submitted, no account created, and no fee terms accepted.
Use the portal linked by that page rather than inventing its vendor hostname.

## Draft Inquiry, Not Sent

Ask the City Clerk/Development Department for an **existing** City-only
electronic permit export for a bounded date range, plus the documented public
mechanism, if any, for retrieving subsequent records and revisions. Prefer
permit ID, type/subtype, native status, application/issuance/update dates, site
address and parcel reference, with valuation only if already present. Exclude
owner/applicant/contact names, mailing addresses, telephone/email fields,
attachments, and unreviewed descriptions.

Ask whether an existing CSV/JSON download, public GIS permit layer, static report
index, documented integration or recurring attachment is supported. Request the
actual URL/schema, included permit classes, City-boundary scope, revision and
deletion semantics, update cadence, request limits, source-use/reuse conditions
and any fee estimate. Do not promise that the City maintains such a record or
must create a custom feed. Do not authorize paid work or submit this draft.

## Next Implementation Gate

No new connector implementation is justified by this follow-up alone. The next
unblocked action within the existing no-contact/no-account authorization is a
separately bounded ordinary-browser inspection of the **published GIS catalog**
to identify a City-owned permit item and its documented export/service link.
Coordinate browser ownership with the parent before doing so. Do not inspect SPA
traffic to turn an internal Tyler endpoint into an assumed public integration.

If a published permit layer is found, qualify its metadata/schema and count,
then at most a small explicit contact-free sample using the existing ArcGIS
connector. If a City-supported file export is obtained instead, preserve its
hash/receipt and test a narrow offline importer against that actual schema before
designing recurring retrieval. Either path still needs source-use/privacy review,
jurisdiction/date/revision validation, real-worker access and explicit activation.

Before calling NPR live: bounded canary; actual scheduled completion with exit0,
zero rejects and provider/seen/stored identity reconciliation; idempotent repeat;
then tenant-scoped API visibility and map checks only for validated coordinates.
Neither enabling a schedule nor finding a generic Export control meets this gate.
