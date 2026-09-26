# Detroit BSEED Building Permit Plan Reviews Promotion Review

## Status

Approved by the Build Signals owner on August 15, 2026 for the narrow
production rights and data-minimization scope below.

## Source

- Candidate: `detroit_mi_bseed_building_plan_reviews`
- Official item: `https://www.arcgis.com/home/item.html?id=b47bda202cac49dcbef8d477e9ecb09b`
- Publisher: City of Detroit Buildings, Safety Engineering, and Environmental
  Department (BSEED)
- Published purpose: public building-permit plan-review activity
- Rights basis: the official item is public-authoritative and City guidance
  identifies open-portal permitting information as free, public-domain data

## Technical Review

The layer contained 39,489 rows and 39,489 distinct `record_id` values on
August 15, 2026. Submitted and task-status activity was current through August
14. A bounded no-write canary fetched and validated 40 of 40 records with zero
failures, including separate pre-approval and approved probes.

`record_id` is the canonical source identity and the join key to Detroit's
issued building-permit confirmation source. `Accepted - Document Review
Required` and `Routed for Electronic Review` are pre-approval evidence;
`Plans Approved` is approved evidence. The current layer behaves as one row per
permit rather than task history, so updates use stable upserts and periodic full
reconciliation.

## Proposed Production Scope

Allow only:

- ArcGIS `ObjectId` for deterministic keyset collection
- permit/application `record_id`
- site `address` and `parcel_id`
- `submitted_date`
- review `task`, `task_status`, and `task_status_date`
- project `work_description`
- published `longitude` and `latitude`

Retain City of Detroit and BSEED attribution, the official item link, source
evidence, and retrieval timestamps. The proposed connector uses 1,000-row
keyset pages ordered by `ObjectId`, daily collection, and periodic full
reconciliation so status changes are not mistaken for new permits.

Suppress and do not fetch:

- applicant, owner, contractor, architect, engineer, or reviewer contact data
- phone numbers, email addresses, and mailing addresses
- plan files, attachments, documents, and document bodies
- internal `pmr_id`, `address_id`, and redundant district/street components
- raw geometry when published coordinates are sufficient
- raw source-replacement downloads or customer-facing raw exports

The proposed export policy is
`derived_plan_review_intelligence_only_no_raw_source_replacement`.

## Approved Scope

1. Build Signals may store and process the allowlisted fields for commercial,
   customer-facing derived development intelligence with City/BSEED
   attribution and no raw-source replacement export.
2. The field allowlist, contact and document suppression, coordinate-only
   geospatial policy, and reconciliation policy above are sufficient for a
   narrow production promotion.

The machine-readable approval record is
`detroit_mi_bseed_building_plan_reviews_approval.json`.
