# Verified Regional Ingestion

The regional expansion uses independently scheduled, bounded jobs for reviewed
Florida, Texas, Arizona and Georgia sources. Mississippi's D'Iberville and Biloxi
entries remain candidate `legal_hold` sources, not production coverage.

## Admission and Scope

`scripts/recurring_regions.py` permits only named, active production catalog
entries with a recorded rights basis. Each run performs a bounded live count
where supported and an existing normalization canary before writing. It reuses
the application's ingestion, graph, brand matching and provenance pipeline in
the explicitly pinned non-demo organization. It does not call an LLM.

| Region | Reviewed Feeds | Event Meaning |
| --- | --- | --- |
| Florida | DEP ERP, Miami-Dade WASD, Orlando | Environmental application, permit process, application processing |
| Texas | Fort Worth, Arlington applications and issued permits | Filing and issuance are separate feeds |
| Texas | Austin Site Plan Cases | Application-start-date slice, not every Austin permit |
| Texas | Dallas Legistar, San Marcos notices, Taylor RSS | Bounded public meeting/notice records, not universal permit coverage |
| Texas | Comptroller sales-tax locations | Retail activity context, not construction or verified store openings |
| Arizona | Mesa, Tempe | Submittal/resubmittal and status-change context |
| Georgia | Savannah | Issued-date slice only; does not establish pre-approval coverage |

Date-filtered sources use an overlapping 31-day UTC window; the higher-volume
Texas sales-tax feed uses seven days. Savannah's official layer stores dates as
MM/DD/YYYY strings, so it uses explicit dates rather than a timestamp predicate.
Archive/feed sources use their existing connector date scope and stricter record
caps. Dallas is limited to five events, 150 items per event and 250 records.
RSS/NewsFlash sources are capped at 100 records. Archives expose no independent
provider count endpoint; receipts explicitly report null rather than invented
control totals. None of these counts establish complete city/state inventory.

Each refresh is capped at four 250-record pages, bounded timeouts/retries and a
tenant/source-specific PostgreSQL advisory lock. Failed reconciliation marks the
run partial-with-errors and quarantines the source. Records aging out of the
date window are not retired as deleted. Updates outside that overlap require
separate reconciliation. Customer rows are never copied into the public demo;
the Columbus demo continues to refresh independently.

## Provisioning

Run bounded verification for each source, collecting its JSON receipt:

```sh
PYTHONPATH=. python scripts/recurring_regions.py --source-key SOURCE_KEY --verify
```

Create a JSON array of those real receipts, then provision within one hour:

```sh
PYTHONPATH=. python scripts/configure_regional_ingestion.py \
  --organization-id CONFIRMED_WORKSPACE_ID \
  --image EXISTING_API_ECR_IMAGE_AT_SHA256_DIGEST \
  --verified-report /path/to/receipts.json --confirm-production
```

Only receipts marked verified and supported by the worker are scheduled. Workers
reverify live on every run, so a forged/stale technical receipt cannot bypass
the runtime source checks. The provisioner validates AWS account and image
repository/digest, preserves daily cadence (advancing past start dates to their
next daily occurrence so AWS accepts schedule updates), and uses separate
versioned task definitions with per-source outbound hosts. As with the Columbus
worker, the tested script is embedded in the task command against a pinned
worker image; no production schema or API deployment is required. The regional
worker image derives from the existing API image with the tested ingestion
normalization/service fixes only. It does not replace the API image or `latest`.
The separate regional Scheduler role may launch only those task revisions on
the existing cluster and pass only the existing ECS execution role. Secrets use
managed references. Columbus schedules and their role are not modified.

## Operations and Gates

Inspect the `buildsignals-ingestion` Scheduler group, actual scheduler-started ECS
tasks, exit codes, `/ecs/buildsignals-ingestion` logs, persisted ingestion runs and
tenant-scoped measured coverage. Schedule configuration alone is not evidence
of successful ingestion. Failed launch delivery retries do not monitor container
exit failures. Automatic runtime-failure paging remains unconfigured.

Candidate legal/technical holds are not overridden by domain access or a working
endpoint. D'Iberville/Biloxi need a documented reuse basis for the declared
commercial storage and derived-display scope. Atlanta and Phoenix retain their
existing holds. Austin Site Plan Cases was separately admitted using current
official PUBLIC_DOMAIN dataset metadata and its existing field/suppression
scope; other Austin entries are not silently included. Parcel catalogs require a separately bounded geographic
admission; no county/state parcel bulk imports or for-sale claims are enabled
by these permit/planning jobs.

## Oversized Source Evidence

Dallas agenda titles can exceed the database's 1,000-character display field;
the bounded title retains its original in `unmapped.original_title` and raw
evidence. Orlando's compound parcel strings can exceed 255 characters. Those
remain unresolved (`parcel_id=null`) with the full value preserved under
`unmapped.unresolved_canonical_fields`, rather than becoming truncated identities.
Long graph display labels receive a stable hash suffix within 255 characters;
the original project name stays in graph attributes and source evidence.

A completed Socrata run can retain a terminal keyset cursor. Completion is
checked using terminal status, zero failures and independent provider counts,
not by requiring the checkpoint to be empty.
