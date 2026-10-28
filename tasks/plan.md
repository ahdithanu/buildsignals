# Columbus corpus and Development Velocity: first executable increment

## October 22 continuation: unified evidence and replay binding

The user authorized the next offline implementation: consolidate verified monthly
shards into a new, inactive local evidence snapshot; preserve original capture
times/payloads/IDs with explicit source/tenant namespace lineage; bind actual
qualification to the exact replay snapshot, source/method, cutoffs, protocol
content and floors; run a real archive diagnostic and synthetic adversarial tests.

Ownership: one agent builds the unifier/tests; one owns binding, manifest, driver
and evaluator/tests; a read-only agent challenges scope and tampering; the main
agent owns CLI integration, real-data runs and shared context. All original
monthly/partial artifacts remain read-only. No production, source activation,
network collection, paid calls or external evidence request is needed here.

Acceptance: one source and local organization, 36 original capture runs, 2,543
raw/permit records, 10,110 observations; immutable evidence timestamps retained;
repeatable content digest; modified/incomplete/mixed inputs refused. Unbound,
mismatched or stale evaluation receipts fail closed. A synthetic audited corpus
must clear the binding gate, while the real retrospective archive stays HOLD.
Full actual-reader scope and implementation hashes must be pinned, including
DV's source-wide reads rather than only a caller-selected subset of series.

Started: 2026-10-20; resumed 2026-10-22. Starting branch `codex/p0-8-corpus-qualification`,
HEAD `7885280`. User requested the fastest credible data/validation path and to
start authorized work now. Tasks are tracked in `tasks/todo.md`.

## Decision

Separate retrospective research history from prospective known-then validation.
A new download cannot manufacture historical availability. Preserve the frozen
v0 protocol and its HOLD. Do not backdate system receipt/recording timestamps.

First scope: City of Columbus, one source and one event attribute per cohort.
Preflight 2023-01-01 inclusive to 2026-01-01 exclusive (36 complete months).
Site filings are the early-stage candidate; commercial issuances are an
independent comparison series, never summed or substituted for filings.
Counts will decide feasibility, not signal performance. Provider reconciliation,
rights, lifecycle, missingness and coverage acceptance still precede admission.

## Ordered slices

1. Reproduce and fix qualification false readiness: current event-date span can
   pass despite recent batch capture; source method pins must be respected and
   distinct sources cannot fill each other's gaps. Regression tests must fail on
   the old behavior. No new automatic coverage-acceptance switch.
2. Add a plan-only monthly preflight CLI. Explicit `--probe` makes at most 36
   bounded public count requests, with no raw rows or database writes. Unknown
   and failed months remain unknown; oversized months need smaller intake slices.
3. Execute bounded preflight if endpoints are reachable. Preserve exact queries,
   source/method scope hashes, capture time and results in a durable receipt.
4. Record a concrete admission/validation runbook and unsent City records-request
   specification, then update shared context with results and remaining gates.

## Verification and boundaries

Run new tests first, then existing corpus, historical-intake, temporal baseline,
DV and replay regressions plus Ruff/diff/context checks. No catalog edits,
new source activation, paid calls, outreach or frozen-protocol changes in this
increment. After the 36-month public preflight and fresh CC0 metadata verification,
bounded local-only historical capture proceeded under the user's request. Seven
months completed before interruption; the partial August DB is preserved and the
remaining 29 months captured in a new attempt folder on October 22. Production
checklist work now includes read-only operational checks and correction of a
verified proxy-cache defect; deployment must preserve unrelated frontend work.
Public read-only probes are within
the user's requested investigation. If unavailable, record the failure honestly.

## Next dependency

Audited historical vintages could support a separately versioned publisher-known
study, but cannot be relabeled BuildSignals-known-then under v0. Without such
evidence, seed a descriptive baseline and freeze prospective outputs/comparator
before outcomes. First outcomes mature after the protocol's full outcome interval;
12 evaluable monthly cutoffs and five evaluable fires remain required, not a
promise of a pass. Resolve window/holdout implementation gaps before that study.
