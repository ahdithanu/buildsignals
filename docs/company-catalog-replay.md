# Company Catalog and Stored Evidence Replay

Direct regional and Columbus recurring workers initialize the current tenant's
shipped company profiles/aliases before ingestion. The prerequisite uses the
existing catalog normalizer and a bounded-wait, tenant-specific PostgreSQL
transaction lock. Initialization is idempotent. Effective forced tenant RLS is
required on the affected catalog tables; read-only demo sessions cannot run it.
The dedicated demo refresh remains an operator job, not a visitor capability.

Catalog synchronization alone does not redetect unchanged imported filings.
Use the explicit stored replay after first initialization or intentional catalog
changes. It does not fetch records, call models, geocode addresses, activate
sources or change raw evidence/native locations/source observation dates.

## Bounded Operator Command

First verify the database destination and obtain authorization for production
writes. The command defaults to **plan**: scoped bounded reads only, no catalog
mutation or replay. Keep actual tenant IDs, cursors and receipts internal.

```sh
python -m scripts.backfill_company_intelligence --organization-id TENANT_ID \
  --permit-limit 1000 --planning-limit 100 --batch-size 500
```

Add `--execute` only for an authorized target. Hard ceilings are 25,000 eligible
permits, 100 planning records and 500 records per transaction. Zero disables a
stream. `--after-permit-id` and `--after-planning-id` resume explicit cursors.
Limits/cursors are validated before opening the database. A partial result does
not establish whole-inventory acceptance or authorization to continue.

Execution requires an active non-demo organization and effective PostgreSQL RLS
on mapped `OrgMixin` tenant tables. Global authentication membership tables are
not tenant-data tables. Each committed batch can survive a later failure; a
retry is safe but may refresh existing derived match timestamps. Original source
observations remain unchanged. Errors print only the exception class, not SQL,
credentials or source payloads. The operator must inspect internal logs if a
batch fails; rerunning from the start does not duplicate matches.

## Matching and Review Semantics

Existing company detection, confidence, cohort, source semantics, activity dates,
location requirements and opening safeguards are unchanged. Matches are research
candidates, not verified new openings. Human confirmed/dismissed statuses remain;
automatic retraction/revival follows the existing detector. Replay locks current
records/matches against concurrent ingestion and review, without overriding those
decisions. Planning enrichment only updates derived classifications/priority.
Planning replay retires prior current named-company edges for that record/source
before reprojecting eligible edges. Evidence and inactive history remain; unrelated
property/permit relationships are not retired. This avoids showing a dismissed
match or an old positional-key duplicate as a current company relationship.

The browser's `status=all` review deep link now stays All rather than silently
defaulting to Needs Review. Viewer/demo API write restrictions are unchanged.
Passing synthetic browser tests is not production inventory acceptance.

## Verification

```sh
OPENROUTER_API_KEY= python -m pytest tests/test_company_catalog.py \
  tests/test_company_backfill.py tests/test_company_replay_worker.py \
  tests/test_brand_backfill.py tests/test_recurring_columbus.py \
  tests/test_recurring_regions.py -q
```

`tests/test_company_catalog_postgres.py` and `tests/test_company_replay_postgres.py`
additionally need a migrated, disposable
`TEST_POSTGRES_URL` with a non-superuser role. Browser fixture data is explicitly
synthetic: a local CSV is normalized with no catalog, then catalog initialization
and stored replay must produce an evidence-linked summary. Chromium checks the
retail card, All review, evidence sheet and server-side viewer write denial at
desktop/mobile widths. No real project count follows from that fixture.
