# BuildSignals ForgeOS Delivery Loop

This is the BuildSignals application of the pinned ForgeOS engineering workflow
and multi-agent protocol. Read `forgeos-project-profile.md` and the newest
`agent-handoff.md` first. The current user request and actual code take precedence
over historical receipts. This document creates no deployment or source authority.

## Run One Bounded Slice

1. Inspect status, branch/worktrees, current code, tests, evidence and checklist.
2. Select the highest-value unblocked gap in retail signal -> nearby parcels ->
   evidence/zoning gaps -> saved acquisition candidate. Skip permission-blocked
   production actions while safe local work remains; do not invent polish.
3. Write a task packet with expected behavior, evidence needed and stop conditions.
   Review architecture and record an ADR when changing an interface, schema, auth,
   infrastructure, module boundary or domain model. Escalate material architectural
   tradeoffs; record accepted technical debt, its mitigation and revisit trigger.
4. Assign independent lanes with disjoint write sets. Parent keeps the critical
   integration path; do not delegate it and then idle. Read-only audits may run
   concurrently, but share neither writers nor production collectors.
5. Reproduce a bug with a failing test, implement the smallest correction, then
   run focused tests. Use the existing ingestion, queries and client contracts.
6. Integrate through one owner. Review diffs, tenant boundaries, provenance,
   unknowns, resource bounds and retries independently. Fix findings and retest.
7. Run applicable regression, lint/type/build, real PostgreSQL and browser gates.
   Explicitly evaluate accessibility, observability/logging and error handling,
   bounded performance/resource behavior, statistical correctness and migration/
   rollback compatibility. Record why a dimension is not applicable; omission is
   not acceptance. Failed required gates block completion. Explain skips/failures
   honestly; never weaken assertions to get green output.
8. Update the current handoff/checklist and make a local checkpoint. Reassess
   immediately and continue the next unblocked slice. A commit or PR is not done.

## Task Packet

Record these fields in the slice's checklist or handoff, not another task system:

| Field | Required content |
| --- | --- |
| Outcome | Observable customer behavior, not a component count. |
| Baseline | Branch/head, real evidence receipt and known missing behavior. |
| Ownership | One writer per file set; reviewer and integration owner. |
| Acceptance | Exact assertions, including negative/isolation and retry cases. |
| Commands | Focused, regression, database and browser commands actually run. |
| Evidence | Real versus synthetic; source date/currentness; local versus production. |
| Gates | Credentials, rights, release, spend, source/task approvals, if required. |
| Next | Next bounded unblocked action, or the exact external dependency. |

For the current reviewed-anchor interface, `reviewed-parcel-search-anchor.md`
contains the decision record and acceptance gates. It does not waive a separate
production release, real-database concurrency proof or real-record browser proof.

## Stop And Escalate

Stop only when the objective is genuinely complete, the user pauses/redirects,
execution/usage limits are reached, or all remaining work requires a specific
external action with no credible safe local continuation. Report the dependency,
not an invented completion. Do not create schedules or user-owned chats to keep
this loop alive unless the user separately requests those actions.

Consolidate material decisions: paid calls/services, unavailable credentials,
data-use rights, security/data-integrity changes, irreversible operations and
publication/merge/release approvals. Preserve prior explicit restrictions.
No approval is inferred from a historical handoff, generic continuation or
completed one-shot. Never retry an ambiguous production mutation automatically.

## Release And Current State

Keep `AGENTS.md`, `CLAUDE.md`, onboarding, project profile and handoff aligned.
Put a short current summary first; keep old receipts explicitly historical.
Do not publish private operational receipts or dirty root research. Prefer the
existing tested release tooling over constructing another one-off framework;
any change to release tooling needs independent review and offline tests.

Release approval and its exact scope must precede cloud writes. In particular,
the standard API workflow runs migrations: an image-only/no-migration approval
does not authorize it. Browser tasks use a fresh normal Chrome window and new
tab, preserve user tabs/auth and never extract credentials. A disconnected
browser leaves visual acceptance unverified, not green.
