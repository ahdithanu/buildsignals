# OpenRouter and cleanup integration

Integration base: `c7cf23a` (`origin/main` fetched October 15, 2026).
Source: `cleanup-and-hardening` at `234199b`. The original branch is preserved.
This is a selective port of its final changes, not a merge of the old product tree.

## Source commit disposition

| Source commits | Disposition |
|---|---|
| `990b0c5`, `8e9ff02`, `54eb799`, `f6cfd9d` | Do not replay older ingestion, planning, UI, catalog or worktree changes over current product code. |
| `e00618c` | Port OpenRouter client, three service integrations, benchmark, config, focused tests and Makefile. Preserve current dependencies, tenant checks and rate-limit headers. |
| `2dcef17`, `4d70260` | Keep benchmark usage guidance and diagnostic columns; omit obsolete results and intermediate model aliases. |
| `40a1b55`, `e3bfaae`, `47e5725` | Port shared rubric, deterministic default and score validation. Preserve current pure `evaluate_deal_score` API used by tenant-scoped evaluations. |
| `18ada69`, `73bd6ce` | Port per-task status, repeats, concurrency, error reruns, strict parsing, full outputs and numeric grounding diagnostics. |
| `3a9a16d`, `6e69581`, `58ce309` | Port provider failure handling and scoring-method transparency; retain current HTTP response headers. Return a sanitized provider status reason. |
| `d72affa` | Port error redaction and one-time artifact redaction script. No old result artifacts copied. |
| `678a912` | Port honest pending-results README guidance. Preserve newer dependency versions rather than downgrading them. |
| `183c6c3`, `2a2bedc`, `234199b` | Current main already has no tracked numbered duplicate files; no deletions necessary. Preserve current real Sentry implementation. |
| `ce67d21` | Add numbered-copy and worktree ignore rules. No tracked worktree marker exists on current main. Exclude nested worktrees from Vitest discovery. |
| `bc8693e` | Do not add old database deselection workaround: current main already isolates admin CLI tests with a temporary SQLite fixture. |
| `3a0cf3c` | Keep the five final enrich expected labels copied from each input. No new score or memo labels. |
| `56b2bbe` | No stale artifacts exist on main; ignore generated results pending a reviewed paid rerun. |

## Compatibility checks

- No ingestion, planning, tenant isolation, demo, UI, migration, Sentry, or production environment changes.
- Existing evaluation workflows continue using the pure offline scorer and memo formatter.
- Existing rate-limit response headers remain intact.
- Deterministic scorer compared against base implementation over 864 combinations: identical.
- Client construction checked offline with a placeholder key; no provider request made.
- Fixed primary-model ordering in fallback arrays, SDK response Retry-After access,
  malformed score parsing fallback, and memo context retention without signals.
- Simulated fallback script uses an explicitly invalid primary model slug.
- Model availability, paid benchmark results and production execution remain unverified.

## Verification

- Full backend: `OPENROUTER_API_KEY= .venv/bin/python -m pytest -q`:
  **1685 passed, 69 skipped**, 274.05 seconds. This run collected the initial
  25 OpenRouter tests; the subsequently expanded 30-test subset passed separately.
- Final focused OpenRouter subset: **30 passed**, 0.08 seconds.
- Evaluation API and AI-rate-limit regression run plus OpenRouter subset:
  **84 passed**, 21.07 seconds (before the final added Retry-After/parse cases).
- `npm test -- --reporter=dot`: **365 passed, 68 files** after excluding nested worktrees.
- `npm run typecheck`: passed after installing the existing lockfile with `npm ci`.
- `npm run build`: passed, with the existing large-chunk warning.
- `git diff --check`: passed.
- Current test collection: **1759 tests**; no original test files deleted or modified.
- Initial frontend runs included the unrelated nested worktree and failed with
  duplicate React runtime errors. Test discovery now excludes `.worktrees`.
- No live model calls, benchmark runs, migrations, push, merge, or deployment.
