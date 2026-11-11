# Requested Market Qualification Queue

Owner intake, November 10, 2026. These are priority investigation markets,
not verified projects, live inventory, activated sources or statewide coverage.
Company examples are not a detection allowlist. This queue does not alter the
production catalog, rollout manifest, source rights, schedules or tenant data.

## Requested Markets

The original two lists contained ten entries and nine distinct labels. Cherry
Hill appeared in both lists and is represented once. The owner then explicitly
confirmed two replacements: Los Angeles, CA replaces La Prada; Maricopa County,
AZ replaces Apache Junction/TCO. The queue therefore contains nine markets, not
eleven. Preserve the former labels as intake history, not separate active targets.

| ID | Requested market | Intake status | Next qualification action |
|---|---|---|---|
| swedesboro_nj | Swedesboro, NJ | parcel_sample_passed | NJGIN code0817: 1,046 publisher rows, three valid samples. Full catalog/radius/run acceptance and a supported municipal permit export remain pending. |
| deptford_nj | Deptford, NJ | parcel_sample_passed | NJGIN code0802: 13,298 publisher rows, three valid samples. Keep distinct from West Deptford; permit export and production parcel acceptance remain pending. |
| cherry_hill_nj | Cherry Hill, NJ | parcel_sample_passed | NJGIN code0409: 27,047 publisher rows, three valid samples. Planning-document connector is a lead, not live permit coverage. |
| freehold_unresolved | Freehold | identity_pending | Confirm state and governing municipality; if New Jersey, distinguish Borough from Township. |
| vero_beach_fl | Vero Beach, FL | supported_export_unqualified | Official City and Indian River parcel-distribution leads documented; recurring record contract, jurisdiction and reuse remain unqualified. |
| east_lansing_mi | East Lansing, MI | parcel_contract_hold | Official City parcel metadata found; durable identity, currentness, query execution and reuse remain unverified. No qualified permit export. |
| san_francisco_ca | San Francisco, CA | building_canary_passed_release_pending | Canonical hostname corrected locally; bounded building refresh profile passed a real read-only canary. No SF schedule enabled; planning and parcels remain separate. |
| los_angeles_ca | Los Angeles, CA | publisher_freshness_hold | Owner-confirmed replacement for La Prada. Existing submitted-permit source responds, but latest refresh exceeds its 96-hour SLA; not added to worker. City is not County. |
| maricopa_county_az | Maricopa County, AZ | existing_candidate_hold | Owner-confirmed replacement for Apache Junction/TCO. Preserve existing planning and parcel use-rights gates; county scope does not establish municipal coverage. |

Vero Beach and East Lansing are normalized market labels, not a claim of verified
source scope. Unresolved labels stay visible and do not become invented projects.

## Existing Repository Evidence

Offline inspection of `codex/reviewed-city-expansion` at e9ef590 found:

- `san_francisco_ca_building_permits_primary_address` and
  `san_francisco_ca_planning_department_non_project_records` already in
  `app/services/ingestion/catalog.json` and `production_rollout.json`. Do not
  create duplicate connectors. SF parcel ownership/sale-evidence limits are in
  `docs/parcel_source_onboarding_decisions.md`.
- `los_angeles_ca_building_permits_submitted` is already cataloged and listed in
  the rollout manifest. This does not establish a current successful schedule,
  citywide completeness or an admitted Los Angeles County parcel feed. Its
  recorded publisher-freshness enforcement hold needs requalification; do not
  equate disabling a freshness assertion with a fresh source. County EPIC-LA
  and parcel owner/data-sales rights gates remain separate.
- `maricopa_county_az_planning_zoning_agendas` already exists in
  `candidate_catalog.json`. Its recorded commercial-purpose approval gate and
  separate Assessor/County parcel confirmation requirement remain in force.
  This request does not supply those missing confirmations.
- No exact catalog/candidate/rollout entry was found for the other requested
  labels. Existing metro research containing Vero Beach or East Lansing does
  not establish city filings, parcel coverage or current production ingestion.

No production/API/source request was made for the initial intake. A catalog match is not
a live-coverage measurement. Current counts and run/freshness receipts must be
verified separately in the authorized workspace.

## Acceptance Order

1. Resolve each governing authority and geographic scope from official evidence;
   keep city, county, township/borough and postal-place identities separate.
2. Qualify supported public access, reuse/attribution, minimal field scope,
   privacy, native identifiers and bounded recurring collection. Do not bypass
   portal restrictions, accept fees or send inquiries without authorization.
3. Admit planning/filing and parcel evidence separately. Retain source lineage,
   observed/collected dates, lifecycle stages, geometry quality and ambiguous
   matches. If TCO is an occupancy stage, preserve it as such, not a new filing.
4. Verify a bounded canary and actual scheduled run, tenant-scoped inventory,
   publisher-date freshness and map behavior before describing a market as live.
5. Prove retail/development signal -> evidence -> nearby parcel -> availability
   evidence -> saved opportunity. Nearby or assessor parcels are not for-sale
   inventory. Investment quality still needs rents, vacancy, leases, capex and
   parcel economics; counts alone are not an investment recommendation.

## November 10 Qualification Progress

November11 correction supersedes the initial NJ address projection. Read
`docs/source-qualification/2026-11-11-nj-retail-radius.md`: property situs uses
PROP_LOC only, owner mail/unverified postal fields are suppressed, and strict
projection is enforced before raw persistence and in canaries. A real historical
Cherry Hill retail reference resolved to one current parcel; a quarter-mile
public check reconciled161 distinct parcel rows with zero duplicates. It did
not activate a source or verify current expansion, parcel continuity or sale.
One-mile scope exceeded the2,000-row cap; maximum3miles and the row cap remain.

Read the dated receipts before continuing:

- `docs/source-qualification/2026-11-10-california-refresh.md`: three canonical
  metadata responses and six aggregate checks. SF building changed-row scope has
  6,544 publisher rows and passed two bounded read-only canaries (13 valid / zero
  failed each). These are not inserted inventory or unique projects. Local catalog,
  worker and manifest changes do not enable a production schedule. SF planning is
  held pending a qualified change-watermark strategy; LA remains stale.
- `docs/source-qualification/2026-11-10-south-jersey-markets.md`: official municipal
  identities and source leads, including existing NJGIN narrow parcel admission.
  Direct-client qualification passed seven bounded logical operations/nine samples, counting
  41,391 publisher rows across three municipalities, not deployed parcels. Direct
  metadata shows optional GUID present; an earlier web omission was corrected.
  Separate full-catalog canaries also passed 3/3 samples per municipality; an
  inactive nearby profile is implemented. Its live radius/retail-anchor/run
  acceptance is still pending, and actual wire attempts were not measured.
  Do not substitute a municipality code for zoning or a transport OID for a parcel ID.
- `docs/source-qualification/2026-11-10-vero-beach-east-lansing.md`: actual bounded
  observations and remaining supported-export, schema, identity/currentness and
  rights dependencies. No sample/ingestion success inferred from metadata alone.

Next: verify NJGIN's bounded radius/retail-anchor contract, prepare reviewed SF building
changes on an appropriate release base, then obtain activation/release approval
and verify actual scheduled reconciliation and tenant map behavior. Continue
other qualified work while Freehold identity and Maricopa permissions are pending.
Existing internal source diagnostics remain owner-only; preserve mandatory
attribution and honest customer-facing coverage labels.
