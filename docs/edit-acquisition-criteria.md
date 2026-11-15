# Editing Saved Structured Acquisition Criteria

Local integration on mainc34cef4, not published, merged or deployed. Only the
criteria-specific change from06f7b3d is ported; earlier ingestion history is not.
This closes the existing
saved-criteria editing gap; deletion/retirement remains separate. No migration,
source activation, production task, paid model call or new data admission.

## API Contract

`PUT /buy-box/{buy_box_id}/acquisition-criteria` accepts only:

```json
{
  "expected_criteria": {
    "version": 1, "profile": "small_multifamily",
    "market_city": "Columbus", "market_state": "OH",
    "min_price": 1000000, "max_price": 3000000,
    "min_size": 16, "max_size": 32, "min_year_built": 1980
  },
  "acquisition_criteria": {
    "version": 1, "profile": "small_multifamily",
    "market_city": "Columbus", "market_state": "OH",
    "min_price": 1000000, "max_price": 3000000,
    "min_size": 20, "max_size": 32, "min_year_built": 1980
  }
}
```

Both complete objects use the existing AcquisitionCriteria validation. Extra
top-level and criterion fields are forbidden, including client org/user IDs.
The response is the existing BuyBoxResponse. Admin/editor membership is required;
viewer/demo writes remain denied by existing server authorization/middleware.
Tenant-scoped lookup and existing PostgreSQL RLS apply. Foreign/missing boxes
return404; legacy/unstructured or invalid input returns422; a changed baseline
returns409 without mutation or another audit.

The route refreshes the actual box under `FOR UPDATE` before comparing its
validated current criteria with expected_criteria. Successful replacement and
tenant/actor-attributed old/new audit commit together. ID, organization, owner,
creation time and legacy flat buy-box fields remain unchanged. Flat-field legacy
matching behavior is not silently rewritten by this structured-only endpoint.

This is a value-based precondition, not a monotonic revision/ETag. It detects
competing differing edits from the same baseline; an intervening A-to-B-to-A sequence
is not detectable. Repeating a successful changing PUT with its old baseline
returns409 and does not repeat the edit/audit. This is not an exactly-once API or
a general immutable buy-box revision history. Previously exported screen content,
hashes and downloads remain unchanged; live screening/new exports use the update.

## Client Behavior

The existing creation form is reused by the editor. The selected box has a named
pencil control for admin/editor, absent in demo/viewer UI. Explicit opening copies
current values plus a frozen baseline; background list refresh never overwrites
an open draft. Pending requests disable fields and duplicate submission. Server
errors preserve inputs. Conflicts preserve the draft, block resubmission, and
invalidate both list and screening queries rather than show mismatched targets
and old results.

Success cancels older list and screening requests, merges the authoritative returned criteria
into the org/user-scoped cache, then invalidates list and screen queries. Editing
does not reselect an old ID after the user changes selection. Reopening waits for
list readiness; cancel/reopen obtains refreshed values rather than accidentally
submitting the old precondition. Existing selected IDs and historical downloads
remain stable. UI controls are convenience, not the write-security boundary.

## Verification Scope

New HTTP tests cover full validation, unknown-field rejection, role/tenant/demo
denial, fresh cached rows, preserved fields/audits and historical-export bytes.
Two opt-in real local PostgreSQL tests independently prove actual blocker PID+
SQL and a cached losing editor waiting on the row lock: one differing edit wins,
the loser receives409, and exactly one old/new/actor audit remains. Foreign,
default and fresh unset-tenant SQL reads are denied. Those direct route-function
calls prove DB concurrency/isolation, not HTTP role checks; HTTP tests cover that
separately. Dedicated target defaults blank; skipped tests are not PG acceptance.

Desktop1440px/mobile390px browser journeys use fresh normal Chrome windows with
synthetic local API data, isolated migrated SQLite and external HTTP requests blocked.
They create/select/edit, refresh screening, compare historical download bytes,
reload persisted selection/criteria, simulate a real API competing edit, preserve
the409draft, and reopen fresh criteria. Screenshots wait for actual ancestor
opacity1; the save action is center-point checked against fixed navigation, with
horizontal overflow and page-error assertions. No live inventory is involved.

Read the latest handoff for exact command/results, local runtime proof/cleanup
and remaining source/release gates. No production, hosted PG16, arbitrary
multi-editor interleaving or full WCAG/screen-reader acceptance is implied.

Destination backend on mainc34cef4:3,186passed/zero skips/91.44%coverage,
3existing geography-reflection warnings464.36s. Criteria/research/physical-backend
PG subset7passed0.42s, using the default activity-monitor size. Typecheck/build/
Ruff/scoped lint/drift pass; existing build annotation/large-chunk warnings remain.
Dedicated Chrome criteria2passed14.0s without a caller-supplied guard flag;
research journeys2passed11.9s. The test config enables loopback-only backend
sockets; ordinary runs skip this opt-in spec and CI has a dedicated step.
Four deferred initial-screen regressions failed before the cancellation fix and
now pass for success/409 and both response orders. Final frontend485passed/76files
12.42s; focused63passed. Final Chrome2passed11.7s. Typecheck/build/scopedlint and
independent final review pass. Final CI-style headless criteria2passed11.5s.
Use destination receipts, not source-branch totals.
Owned PG/browser servers stopped. Separate PR publication/checks are approved;
merge/deployment remain unapproved. Generated-schema main9f09d87 is integrated
without changing runtime/tests. Read PR metadata for actual hosted outcomes.
