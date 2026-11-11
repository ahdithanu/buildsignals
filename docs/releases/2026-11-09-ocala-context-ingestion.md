# Ocala GIS Context Ingestion

## Authorization And Meaning

On November 9 the owner authorized proceeding with public-data ingestion for a
broader investment-area model, not permit-only recommendations. City inquiries
remain drafts. This narrow scope does not authorize hosted-model transmission,
account creation, fees or bypassing source access controls. Publisher commercial
reuse terms remain unverified; owner approval is not a publisher license claim.

Source: City of Ocala public GrowthManagement FeatureServer layer 19, New Building
Projects. This is a curated project/permit context inventory, not the weekly PDF
report or complete/current application feed. Application and issuance counts for
October 10-November 9 were both zero; publisher currentness remains unknown.
All native statuses, including EXPIRED, are retained without approval inference.
Project-polygon centroids are not verified parcel boundaries or for-sale lots.

## Scope And Delivery

The worker embeds one explicit source definition in `scripts/recurring_regions.py`
so the versioned task command carries its mappings without relying on new catalog
content in the existing API image. This is a worker-only release, not an API or
frontend deployment. Other source profiles and freshness contracts are unchanged.

Only OBJECTID, PermitNo, Applied, Subtype, Status, APN, Issued, Expired and WGS84
centroids are requested. No descriptions, owners, applicants, addresses, phone or
email fields. Existing normalization/raw evidence/graph projection and tenant
scope are used. Source URL and original event dates remain distinct from capture
time. Incremental replay does not infer deletion/withdrawal from disappearance.

Context guard: provider count must be 1..1000, standard canary must pass, execution
is bounded to five 250-row pages including an exhaustion probe; the connector
guard refuses any page taking the total beyond1000 before persistence. It also
rejects duplicate/blank IDs, extra fields, incomplete/non-finite/out-of-area
centroids and non-WGS84 references before returning a page. Factory wrapping is
limited to this isolated source worker and restored on every exit.
Before/seen/after must reconcile. Failure
quarantines the source rather than silently reactivating it on a later run.

## Preflight

- Ordinary HTTP full source: 61 before / 61 fetched / 61 after, 61 unique permit
  IDs, 61 centroids, terminal page. No raw feature rows logged or retained locally.
- Status aggregate: ISSUED52, EXPIRED2, ISSUED WITH PRIVATE PROVIDER1,
  ISSUED PENDING NOC6. This is not an investment recommendation or opening proof.
- Standard canary: 10 valid, zero failed.
- Same production database secret reference and non-demo destination as existing
  Texas worker checked without printing credentials or tenant identifiers.
- Provisioned only `region-ocala_fl_gis_new_building_projects-fb049ed6`, daily.
  Revision1 was paused before its initial invocation after review caught missing
  coordinate validation. Revision2 adds the guard and was enabled with first
  invocation November10 05:50:34 UTC (November9 21:50:34 Pacific).
  That actual Scheduler task `746ef511d1794259b0325775c1b986cb` stopped/exit1
  with IntegrityError. The profile had duplicate source_field mapping names,
  incompatible with the mapping uniqueness constraint. Corrected with synthetic
  mapping aliases and explicit raw centroid canary requirements. Added a real
  disposable-DB source-registration test and required-field regression. A retry
  is not accepted until the new revision's task/DB receipts pass.
- Existing immutable image retained:
  `sha256:de6dcaad61014d4702b62c532a638a1fba060fa949ea561cdb7f00c961ba8854`.

## Acceptance

Guarded revision3 carries the corrected mappings. Exact tested code SHA256:
`56171a7d2d9fdff950561d591efac1137d5ef64939409040e6887387cf16105b`.
First start November10 05:56:13UTC (November9 21:56:13Pacific).

Actual Scheduler task `99bb2164d2f64951b8049f316fbbffad`, startedBy
`chronos-schedule/region-ocala_fl_gis`, STOPPED/exit0. Ingestion run
`663896fb-eefd-469d-a774-8023d9cf71ff`: completed, provider61/seen61/after61,
inserted61, updated0, failed0, stored61.

Explicit idempotency task `628828af0f814539a34e978c6b7b5d0d` is a manual replay
of the same worker, not a second Scheduler invocation. Its run
`384aa2f9-436a-45ba-bf9d-6647ce6e2ff9`: completed, provider61/seen61/after61,
inserted0, updated0, failed0, stored61. The worker labels its ingestion runs
scheduled, so use the ECS startedBy receipt to distinguish this manual replay.

Manual idempotency task STOPPED/exit0. Post-run read-only audit task
`a7b58aa4d9ab467882c107994c951a85` returned active/context_only true, publisher
currentness unknown, stored61, unique61, valid coordinates61, evidence61, raw61,
raw allowlist valid, graph entities61, map-service rows61. It queried only the
explicit production tenant/source and did not print raw records or credentials.
The audit task also reached STOPPED/exit0.
This verifies production ingestion and map-service eligibility, not a browser
rendering acceptance or a deployed investment-area scoring model.
NPR and Ocala PDF ingestion are not activated by this release.

Local scoped health/connector/regional/provisioning tests before guard:152passed.
Final health/connector/source/guard/regional/provisioning tests:193passed; scoped Ruff passed.
Full suite not rerun for this worker-only change.
