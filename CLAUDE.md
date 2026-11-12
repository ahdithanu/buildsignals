# BuildSignals / Claude Code

@AGENTS.md

November12current local task: `codex/recovery-preflight-hardening`, based on
main8cd7d96, integrating main a82b3cc after UI PR275 merged. Require source
DATABASE_URL and separate RESTORE_DATABASE_URL
identities before engine creation; tests use mocks/disposable localhost only.
Nonempty PGHOSTADDR/PGPORT/PGSERVICE are refused before connection to prevent
ambient libpq routing from invalidating the URL comparison.
Recovery PR276 publication/main integration are approved; this sidecar must not
merge/release. No production restore, source activation, API/worker or migration.
PR274 retail repair was released and its one-shot replay is consumed; older
pending repair notes below are historical, not authority to repeat it. The next
actual scheduled cycle is watched separately in the active chat. Standing
30-minute checklist continuation was recreated; avoid overlapping writers.
Merged UI context: `codex/acquisition-keyboard-acceptance` at a80d4df/PR275, synthetic
desktop/mobile keyboard acceptance for existing Inbox/Add Deal/Top Opportunities
flows. One writer owns the new E2E spec, parent owns docs. No source/model/
production calls in its tests. Actual scheduled-cycle
watch are separate; avoid overlapping writers. Standing30mcontinuation ACTIVE.
PR274 was released; earlier pending repair notes below do not authorize replay.
The new tests reproduced a null-NOI preview crash and nested Radix focus/Escape
conflicts. Metric guards, dialog-contained portals and controlled menu dismissal
are locally verified on clean locked dependencies/Node22.23.5:436unit and26browser
passed, no retries. No dependency change. Parent owns the approved staged
green-only merges and frontend-only release; this integration preserves UI code.

Current local work: `codex/retail-catalog-repair`, isolated from root research.
Read `docs/company-catalog-replay.md` and the latest handoff. Direct workers now
initialize company definitions before ingestion; a separate bounded stored replay
is needed for unchanged records. Do not weaken matching to produce cards. Keep
source evidence, reviewed decisions, tenant isolation and demo read-only behavior.
User approved staged release after checks and one bounded production repair;
local tests do not establish production acceptance. No new sources, provider/model
calls, migrations or paid upgrades. Operational receipts stay internal, not public.
PR #273 is merged and its final acceptance is recorded internally; older pending
SF status below is historical. Do not repeat the exhausted geocoding batch or
restore administrative credentials to runtime services.

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
