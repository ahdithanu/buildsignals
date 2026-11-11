# California Refresh Qualification

November 10, 2026 PST; direct checks completed November 11 at 07:09-07:13 UTC.
Branch `codex/reviewed-city-expansion`, based on `e51e445`. This is local source
qualification and implementation, not a deployment or inventory receipt.

## Actual Source Checks

Official San Francisco dataset links now resolve to `data.sf.gov`. The legacy
`data.sfgov.org` metadata URLs redirected to that hostname. Retain strict host
validation: change the two exact catalog URLs, landing/evidence defaults and
generated host manifest instead of allowing arbitrary redirects. Dataset IDs and
native record identifiers are unchanged.

Three canonical metadata requests returned HTTP 200, with every configured
canary field present:

| Dataset | Publisher metadata license ID | Metadata SHA-256 |
|---|---|---|
| SF building, `i98e-djp9` | `PDDL` | `d9dac422cb28fd8907fb3aae1ad49996182166ca867feb766a9306963c33f888` |
| SF planning non-projects, `y673-d69b` | `USGOV_WORKS` | `36d55fe92b91f7a5ae10aa706188362b9e018639134106168e64045eecb32d10` |
| LA submitted permits, `gwh9-jnip` | Not supplied | `42776cd784706e7dd420c6ec878c26c2dbdac3886d56ca69f1172b335d1bfa39` |

These are publisher declarations, not independent legal opinions. Do not infer
that municipal records are federal works from Socrata's license label. LA's
existing rights review is separate; no new license was invented.

Six aggregate-only GETs returned HTTP 200. Each used `$limit=1` and
`$select=count(*) AS count,max(<date>) AS latest_<date>` (one max per date).
No records, contacts or property owners were returned by these aggregate checks.
The recent window used calendar bounds `[2026-10-12, 2026-11-12)`, derived from
the UTC run date. Publisher floating dates have no timezone offset; this does
not prove they represent UTC instants.

| Source | Catalog-filtered publisher rows | Recent-window rows | Max publisher date |
|---|---:|---:|---|
| SF building | 1,152,022 | 6,544 | `data_loaded_at=2026-11-10T05:35:13.052` |
| SF planning | 15,724 | 387 | `open_date=2026-11-09`, `close_date=2026-11-12` |
| LA submitted | 10,695 | 1,041 | `submitted_date=2026-11-06`, `status_date=2026-11-09`, `refresh_time=2026-11-07` |

Each query retained the catalog predicate. Recent SF building used
`data_loaded_at >= '2026-10-12T00:00:00' AND data_loaded_at < '2026-11-12T00:00:00'`.
Planning used the union of equivalent open/close-date windows; LA used submitted/
status-date windows. These are diagnostic counts, not activated profiles, unique
projects, production inventory, complete city coverage or new filing counts.
The future planning close-date maximum is retained as a warning, not freshness
evidence. An OR-window can contain that row because its open date is in range.

## Implemented SF Building Profile

The worker now supports only the SF building source from this California pass:

- 31-day publisher-row-load window, primary-address scope retained. Publisher
  documentation states that only new/changed rows are updated since December
  2024. Older changed filings can enter the window; this is not a historic census.
- Explicit mapped-field projection plus native cursor and publisher date fields;
  no wildcard or contact fields. Existing normalization/provenance is reused.
- Ascending `data_loaded_at,record_id` keyset; 250-row pages, 100,000-row ceiling,
  401-page exhaustion budget and at-most-100-page execution chunks retained.
- Existing 36-hour freshness assertion retained, labeled publisher record update,
  not a new filing or an independent dataset heartbeat. Quiet periods can still
  fail that conservative admission gate; do not remove it to make a run pass.
- Manual profile and incremental reconciliation; no source or schedule enabled.
  This does not reconcile deletions, identity merges or all historical revisions.

Actual read-only worker verification (count plus 10-row sample and three-row
freshness probe) returned `provider_count=6544`, `sample_valid=13`,
`sample_failed=0`, `status=verified`. No sample IDs/raw rows were printed or
persisted by this verification. It did not open an application database session.
After adding the metadata-verified `data_as_of` field, the final projection
passed the same live check again: 6,544 publisher rows, 13 valid samples,
zero failed samples. These are two separate read-only checks, not two runs
that inserted data. Final guards also reject an unreviewed hostname or license.

```sh
OPENROUTER_API_KEY= DATABASE_URL=sqlite:// INGESTION_ALLOWED_HOSTS=data.sf.gov \
  .venv/bin/python -m scripts.recurring_regions \
  --source-key san_francisco_ca_building_permits_primary_address --verify
```

The full-catalog manifest was regenerated with the existing offline command:

```sh
DATABASE_URL=sqlite:// .venv/bin/python -m app.services.ingestion.cli \
  catalog rollout-manifest --output app/services/ingestion/production_rollout.json
```

## Held Sources and Release Gates

LA's latest `refresh_time` is already beyond the existing 96-hour SLA under the
current parser's timestamp interpretation. Its freshness hold is not lifted;
LA is not added to the recurring worker. One recent metadata publication date
does not establish row freshness or a stable refresh cadence.

SF planning has open/close dates but no qualified row-update watermark. An
open/close union misses intermediate changes and excluded terminal statuses;
planning remains outside this recurring profile. Parcel coverage, geocoding,
native-ID uniqueness over the corpus and map/actionability remain separate tests.

Read-only AWS Scheduler inventory found 22 enabled schedules in the
`buildsignals-ingestion` group and no SF/LA schedule. This is not a census of
other AWS groups or providers. No schedules, task definitions, host environments,
images, database rows, production source configuration or paid services changed.

Before activation: move only reviewed changes onto a current release base;
include the canonical catalog in the worker image; review the exact host policy;
explicitly migrate any existing tenant source still bound to the old URL (the
worker deliberately rejects silent URL rebinding); rerun a fresh canary; obtain
release/activation approval; then verify actual scheduled reconciliation,
idempotency, tenant inventory and product evidence/map behavior. The root
research checkout must not be deployed.

## Final Offline Verification

After freezing all source/profile/test changes, the root suite completed:

```sh
OPENROUTER_API_KEY= DATABASE_URL=sqlite:// .venv/bin/python -m pytest tests -q
```

**2,440 passed, 70 skipped in 266.68s.** Skips are not passes; this is not new
PostgreSQL/RLS, scheduled-worker or browser E2E acceptance. Scoped Ruff, generated
manifest `--check` and whitespace checks passed. Independent review found no
remaining critical issues in the bounded profiles/qualifier.

An earlier full run had three test-state failures (2,400 passed/70 skipped);
all three passed together in a fresh process. Config module reloads and shared
registration throttles were isolated in test-only checkpoint `8ec18e1`, with
111 focused checks including real throttling assertions. No production guard
was disabled. An overlapping iteration had four failures while catalog tests
and manifest pins changed during execution (2,418 passed/70 skipped); it is not
an acceptance receipt. The frozen-code run above supersedes both.

No frontend logic was changed in this slice. Existing unrelated root research
and frontend edits were preserved. No push, merge, release or source activation.

Primary evidence: [SF building](https://data.sf.gov/Housing-and-Buildings/Building-Permits/i98e-djp9),
[SF planning](https://data.sf.gov/Economy-and-Community/Planning-Department-Records-Non-Projects/y673-d69b),
[LA metadata](https://data.lacity.org/api/views/gwh9-jnip.json),
[Socrata query documentation](https://dev.socrata.com/docs/queries/).
