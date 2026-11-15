# Saved Criteria Retirement

## Scope

On November15 the owner chose retirement with preserved history, not permanent
deletion. Implementation is isolated on `codex/criteria-retirement`; this is not
part of the approved PR280/282/281 merge or an authorized production migration.

The owner subsequently approved review-only push/PR publication after checks.
This is not approval to merge, deploy or apply the migration in production.

The schema adds nullable `buy_boxes.retired_at`. No rows, JSON criteria, owners,
legacy fields, or saved screening bytes are deleted or rewritten. Existing
organization/RLS scope remains in force. No restoration or permanent deletion
endpoint is introduced.

## Contract

- Admin/editor `POST /buy-box/{id}/retire` takes only a complete validated
  `expected_criteria` baseline; it cannot choose an organization or actor.
- Refresh and lock the actual scoped row. Missing/foreign rows return404;
  unstructured or invalid stored criteria return422; changed baselines return409.
- Set the timestamp and actor audit atomically. Identical repeated retirement
  keeps the first timestamp and does not append another audit entry.
- Default lists exclude retired rows before pagination. `include_retired=true`
  allows scoped historical inspection. Existing history downloads retain their
  original bytes.
- Retired criteria cannot be edited or used for a new screen/export (409).
  Retirement is not an entitlement, listing-availability, or investment signal.
- The UI requires confirmation and hides writes for viewers/demo. It removes the
  active option but retains the selected retired ID, suppressing fresh screening
  and export until the user explicitly chooses other criteria. It reconciles
  only the current account's caches. Failed/stale requests do not report success
  or clear the selection; saved history remains available.
- The retirement button is offered only when the scoped list response contains
  the lifecycle field. An older API response without `retired_at` keeps existing
  create/edit/read behavior and does not expose the new unsupported write.

Value-based preconditions do not detect ABA and do not implement revision history.
The migration must be tested on a fresh disposable target; no production schema
or rollout is approved by choosing retirement.

A downgrade removes the retirement marker and can make archived profiles active
again under an older application. Audit and screening content remain, but a
production rollback needs a separately reviewed state-preservation plan; do not
treat the reversible schema operation as lossless retirement-state recovery.

## Verification

Final local results:3,245backend passed,zero skipped,91.46%appcoverage,
3existing geography-reflection warnings,476.92s.512frontend/78files passed;
typecheck/build/scopedESLint/Ruff/harness/diffchecks and independent reviews pass.
Existing Rollup annotation/large-chunk warnings remain.

Fresh normalChrome desktop1440/mobile390 lifecycle passed2/18.6s with external
traffic blocked. This covers create/edit/stale-conflict, retirement confirmation,
mobile Close while response is pending, focus restoration, retained retired
selection after reload, new-screen/export denial, and byte-identical past
downloads. Dialog screenshots were visually inspected; no overflow/overlap.

Real restricted PostgreSQL tests cover export/retirement/edit ordering and an
actual demo READ ONLY transaction. Migration upgrade, transactionally rolled-back
downgrade/reupgrade and final complete-model drift check pass. The owned fresh
PG17.11/PostGIS runtime was stopped and independently confirmed stopped; browser/
API/frontend fixture servers also stopped. This is local acceptance, not hosted
PG16 qualification or deployed behavior.

The first full run exposed11historical migration-test incompatibilities;
tests/test_schema_reconciliation.py now pins the new head and excludes only the
known later retired_at column from historical-revision data snapshots. All
original columns and current-head model/RLS/schema/rollback assertions remain.
Focused SQLite/PG reconciliation17passed before the final full green run.

Run `npm test`, `npm run typecheck`, and `npm run build` for frontend acceptance;
`python -m pytest -q --cov=app --cov-fail-under=85` for backend acceptance after
independently provisioning the disposable PostgreSQL fixtures documented in the
test helpers/CI. Use `e2e/criteria.playwright.config.ts` for the guarded browser
journey. Never substitute production credentials or allow paid/source requests.
