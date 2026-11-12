# BuildSignals / Claude Code

@AGENTS.md

SF geocode/map qualification is local on `codex/sf-map-qualification`; read
`docs/sf-derived-locations.md`. Separate derived evidence, strict stale-address
and tenant checks, plan-first bounded worker and default-off map fallback.
User approved20publicaddresses/1,000filings and bounded qualification/backfill plus
merge/map release after checks. Local2,625backend/428frontend/21browserpassed;
no migration needed. Do not replace live zero-coordinate receipts without audit.

November11 staged release: PR271/272 merged, SF exact-image preflight passed,
SF daily schedule added. Actual scheduled/replay collection passed6,711rows;
replay zero inserts/updates, read-only audit6,711evidence/graphlinks,0coordinates
and map points. Geocoding/parcel joining remains separate; see
`docs/releases/2026-11-11-sf-recurring-ingestion.md`. Other22 jobs unchanged;
API image unchanged, no migrations, paid upgrades or NJ activation.
Older local/publication status below is historical; the release receipt takes
precedence for current deployment and acceptance.

November 11 requested-market integration: this worktree starts at privacy release
5ff111f and preserves its owner-only operations, auth/session behavior and packaged
reference. Read `docs/releases/2026-11-11-requested-market-release.md`. SF is a
manual changed-row profile, not new coverage. NJ keeps PROP_LOC-only situs, unknown
postal, strict opt-in field guards and inactive 0.25..3-mile/2,000-row scopes.
Keep deployed Ocala context and 100k/wave-2 worker safeguards. No frontier, PDF
candidate, source activation or production operation is authorized. Parent
confirmed root3d8c7fd. User-approved PR-only publication is complete:
[PR #272](https://github.com/ahdithanu/buildsignals/pull/272), stacked on #271,
with tested runtime checkpoint86c8ee1. Merge/deploy/source activation still need
separate approval; use the PR for live CI status, not historical local counts.

November 10 Investment Areas: read the release receipt in
`docs/releases/2026-11-10-investment-areas.md` before making live/model claims.
The first production web-fetch attempt failed (VPC egress); its frontend was
rolled back. The corrected annual reference and owner-only operations gate are
now production-verified, with61Ocala context rows and denied demo operations.
Use the receipt for exact image, frontend, tests and remaining gates; never
commit the real owner allowlist or infer that other API internet egress is fixed.
Current-vintage metro ranking is research, not investment-quality or parcel
returns. Keep public caching separate from tenant evidence. NPR is not live.

Read `docs/agent-handoff.md` before taking the next task. Use
`docs/agent-onboarding.md` for setup. Update the shared handoff when stopping;
keep durable project instructions in AGENTS.md rather than duplicating them here.

October 24 local operational increment: source/run acceptance tooling and restore
target guards are described in `docs/runbooks/production-acceptance.md`. Do not
equate offline tests, completed source jobs, or provider backup metadata with
delivered alerts, tested restoration or customer-workflow acceptance. Read the
latest shared handoff before acting; production has not been reverified by these
local changes.

Current context (2026-10-22): PRs #251–#254 are MERGED and `main` was deployed to
the API (see `docs/releases/2026-10-19-api-rollout.md`). The ERCOT
(`ercot_mis_xlsx`), Census BPS and Loudoun LOLA connectors are committed as
`technical_hold` candidates with canaries/ingestion DISABLED and NOT activated;
Development Velocity v0 + the cutoff-safe replay harness are merged (score
UNVALIDATED). Keep every source gate: a merged or deployed PR and offline fixture
checks are not live qualification, commercial-reuse clearance, or source-activation
authorization. The #249 worker reliability fixes reached 13/14 regional workers
on October 19; Texas still needs its in-budget canary/re-provision. The Columbus
2023–2025 local archive is retrospective, not known-then validation. Preserve
partial DBs and receipt timestamps. Read the latest October 22 corpus/production
audit and shared handoff for completed capture, verification and remaining gates.
Unified local snapshot and snapshot-bound evaluation are implemented offline;
see `docs/signals/2026-10-22-unified-columbus-snapshot.md`. Real archive evaluation
remains HOLD. Data/code integrity does not certify independent coverage, mature
outcomes or a fully specified validation method. Do not activate its local source.
Read the handoff and
`docs/source-qualification/` before continuing.
