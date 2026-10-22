# Columbus Site Engineering Historical Intake

**Status: gated, offline preparation only.** This document describes a pinned
cohort for future qualification. No Columbus source was accessed for this
change, no canary was run, no source was activated, and no legal or technical
hold was cleared. The checked-in fixture is synthetic and non-qualified.

## Pinned Cohort

- Source key: `columbus_oh_site_engineering_applications`
- Pinned source ID: `columbus-site-engineering`
- Dataset path: `BuildingZoning/MapServer/22/query`
- Geography: `{city: "Columbus", state: "OH"}`
- Filed attribute: `permit.filed_at`
- Parallel approval attribute: `permit.approval_stage`, restricted to
  `Approved`, `Complete`, `Completed`, or `Closed` and normalized to
  `approved`
- Filing date field: `B1_FILE_DD`
- Methodology version: `columbus-site-engineering-filed-at-v1`
- Candidate window: `2023-01-01` forward, subject to measured coverage
- Commercial building permits are issued-only and remain out of scope

The historical query is date-windowed on `B1_FILE_DD` and constrained to the
approved status set. It is bounded to a maximum scan of 10,000 records so the
qualification harness cannot silently become an unbounded export.

Every observation uses the fixed dedup key:

```text
fingerprint([entity_id, source_id, external_record_id, attribute, methodology_version])
```

`entity_id` is the permit `GraphEntity` deduplication unit. `value` and
`effective_at` are timezone-aware ISO timestamps for `permit.filed_at`. The
parallel approval-stage observation uses the normalized value `approved` and
the source status-update date when available.

## Access Path and Paging

The intended access path is a paged ArcGIS map-service query through the
existing ArcGIS connector. There is no approved bulk or archive endpoint in the
current source record. The connector uses ascending `OBJECTID` keyset
pagination, a page size of 500, and an intake bound of 10,000 records. The
historical helper returns a manual, gated copy of the catalog entry; it does
not alter the automatic prospective source schedule.

The source field mapping is:

| Source field | Normalized use |
| --- | --- |
| `B1_ALT_ID` | external application identifier |
| `B1_FILE_DD` | `permit.filed_at` and its event `effective_at` |
| `LAST_STATUS_DT` | source update timestamp and approval-stage `effective_at` |
| `B1_APPL_STATUS` | approval-stage eligibility and normalized stage |
| `SITE_ADDRESS` | site address evidence |
| `B1_PARCEL_NBR` | parcel reference |
| `B1_SITUS_ZIP` | site postal context |
| `B1_SHORT_NOTES`, `B1_WORK_DESC` | description evidence |
| `APPLICANT_BUS_NAME` | legal-entity evidence only |
| `ACA_URL` | official source evidence link |
| `FILED_YEAR` | validation/context only; never a timestamp source |

## Timestamp Policy

The four timestamps remain separate:

1. `source_filed_at` is the source event date from `B1_FILE_DD`.
2. `source_updated_at` is the source lifecycle update from `LAST_STATUS_DT`.
3. `first_observed_at` is the trusted raw receipt time supplied by the intake
   path.
4. `recorded_at` is the honest capture time supplied by the caller and must be
   timezone-aware and no earlier than `first_observed_at`.

`recorded_at` is never derived from `B1_FILE_DD` or `FILED_YEAR`, and a
retrospective import must not backdate it to the filing date. A historical row
therefore cannot by itself prove that Build Signals knew the fact at the time
of filing. Prospective ingestion may use the actual raw receipt timestamp; a
retrospective intake uses the archive retrieval/receipt time and remains
subject to qualification review.

## Rights and PII Gates

The source metadata is published under CC0, but that does not by itself grant
operational authorization for this historical intake. The rights gate remains
open pending written intake authorization and a separate activation decision.
This work does not clear either gate.

Existing catalog suppression remains in force. Suppress personal applicant
names, applicant email and phone, mailing address, attachments, document body,
raw geometry, and raw source replacement exports. Retain `APPLICANT_BUS_NAME`
only as legal-entity evidence, not as a personal applicant identity.

## Qualification and Fixtures

`tests/fixtures/columbus/site_engineering_intake_synthetic.jsonl` contains two
synthetic permits and four contract observations. It is labeled
`synthetic_non_qualified`, uses a 2026-10-20 receipt/capture time, and is
intentionally too small to satisfy historical depth requirements. It exists to
exercise normalization, dedup-key construction, timestamp separation, and the
replay loader without accessing ArcGIS.

No `candidate_catalog.json` entry is needed because the source is already in
the catalog. The pinned historical settings are `status: gated` and
`can_run_canary: false`.
