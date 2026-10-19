# Current Agent Handoff

Last updated: 2026-10-19 (America/Los_Angeles). This is a dated snapshot;
inspect Git and reverify production before acting. No credentials belong here.

## Deploy 2026-10-19: main shipped to App Runner

PRs #251–#254 are all MERGED to `main`, and `main` was deployed to the running
API (App Runner `dealsignal-api`, RUNNING) via the OIDC `deploy-aws.yml` workflow
(run 39211873165, success; migrate was a no-op — no new migrations). Verified:
direct `/health` 200, demo `enabled=true`, `/v1/temporal/development-velocity`
live in the deployed OpenAPI. Full receipt: `docs/releases/2026-10-19-api-rollout.md`.

Shipped (API): source-update-date completeness in health; Biloxi decoding + MDEQ
qualification record; the Development Velocity v0 route (score UNVALIDATED);
ERCOT/BPS/Loudoun connectors as INERT `technical_hold` candidates (NOT activated).
NOT shipped: the #249 **worker** fixes (quarantine guard + IAM-policy accumulation
in the regional provisioning scripts) — the live EventBridge schedules run an
embedded snapshot, so those need a gated regional RE-PROVISION (fresh canaries +
`--confirm-production`). No source activation; replay harness is offline tooling.

Next options: (a) regional re-provision to ship the worker fixes; (b) P2.2 signal
evaluation (predeclare outcomes/holdouts, run the backtest); (c) pursue Loudoun
(OMAGI) / MDEQ / ERCOT live qualification + commercial-reuse sign-off before any
activation. Keep every legal/technical source gate.

## Current Task: PR #252 ERCOT review corrections (historical; now merged)

Work on the existing `codex/ercot-connector` branch, based on `a6d4155` and
`e8f43b7`. PR #252 is stacked on open PR #251; the shared context updates from
`b547447` and `a6d4155` are retained here. Do not separately edit PR #251's
branch or claim this work resolves its methodology findings.

Authorized scope: fix decision classification, canonical normalization/stage
contracts, reporting-month derivation, persistence regression coverage and this
context harness. No live ingestion, source activation, merge or deployment is
authorized. `ercot_tx_interconnection_queue` stays `technical_hold`,
`can_run_canary=false`, with no production settings or enrollment.

Implemented: exact positive operational statuses or validated operator dates
classify decisions; completed studies, generic approval, signed IA and invalid
milestone placeholders remain applications. Separate canonical approval stages
and supported mappings now normalize successfully. Explicit interconnection
types and raw/unmapped evidence preserve domain meaning. The report label
supplies the snapshot month, with publication retained separately. The probe
uses publication `post_date` as `dataset_refreshed_at` freshness, rather
than the unsupported `report_period_month` label; raw source-update timestamps
do not become filing dates. The checked-in rollout manifest and three Render
digest pins are synchronized; runnable
candidate count remains zero and production/host policies are unchanged.

Verification in project `.venv` (Python 3.12, `OPENROUTER_API_KEY=` empty):
- Connector, ingestion persistence, XLSX reader, rollout, promotion and host
  policy subset: **113 passed** (`python -m pytest tests/test_ercot_mis.py
  tests/test_ercot_ingestion.py tests/test_xlsx_reader.py
  tests/test_ingestion_rollout.py tests/test_ingestion_promotion.py
  tests/test_ingestion_host_policy.py -q`).
- Existing permit ingestion, catalog, connector and XLSX subset: **259 passed**.
- After correcting freshness metadata, ERCOT ingestion, rollout, catalog and
  health subset: **245 passed**. Persistence asserts the publication timestamp
  is October 1 while report-period evidence remains September.
- `ruff check app/ scripts/ tests/`, `git diff --check` and
  `python3 scripts/agent_status.py --check`: passed.
- `catalog rollout-manifest --check`: current. Catalog validation passed for
  134 production and 37 candidate definitions; ERCOT remains held and excluded.
- `render.yaml` validates against the retrieved current Render JSON schema;
  no Blueprint sync or deployment was performed.
- Full backend suite (`OPENROUTER_API_KEY= python -m pytest -q`): **1,830 passed,
  69 skipped, one environment/setup failure** in 1,286.82 seconds. The sole
  failure was the public TypeScript example check: this fresh checkout lacked
  the locked TypeScript compiler, so `npx` selected the unrelated `tsc` package.
  After `npm ci --no-audit --no-fund`, rerunning
  `python -m pytest tests/test_public_api_examples.py -q` passed **both tests**.
  No product code or lockfile change was needed. The entire suite was not
  repeated after dependency installation. PostgreSQL/PostGIS integration and
  other skipped checks remain unverified locally; browser E2E was not run.

Persistence uses the real connector factory, XLSX reader, normalizer, run route
and ingestion service with synthetic HTTP and disposable SQLite. Four records
persist without failures; the second run adds no duplicates or events. This
does not verify production/PostgreSQL ingestion. The old 1,783-test receipt
below belongs to the original implementation, before these corrections.

Publication scope: this follow-up belongs on PR #252's existing branch only;
PR #251's branch and both PRs' merge/deploy state are unchanged. Next action is
review of this correction and its CI receipts, retaining all source holds.
Any live qualification/canary, promotion, merge or deployment remains separate.

Remaining qualification gates: written commercial-reuse confirmation; live
verification of the current public host/TLS and workbook contract through the
supported connector; and a bounded canary with a receipt, each under separate
authorization before promotion. Earlier manually captured index/workbook
observations are historical evidence, not a successful connector canary.

The roadmap's P0.8 corpus qualification remains partial; retrospective
observations alone cannot establish cutoff-safe, prospectively available
signals. P0.8 additionally needs rights-cleared historical permit/planning,
land, construction and infrastructure evidence and accepted minimum history;
the current Columbus corpus does not unlock scoring. Outcomes, horizons,
cohorts, samples, holdouts and false positive tolerance must be declared before
tuning. PR #251's remaining review findings stay outstanding. The offline
ERCOT increment does not validate Development Velocity, a Columbus historical
corpus, a power-constraint signal, or nationwide coverage.

## Session 2026-10-17/18: pilot demo map + 30-day build kickoff (multi-agent)

Operating mode now in effect (see AGENTS.md "Operating Mode"): build with
multiple agents; keep this harness current at all times.

Merged to `main` since the last entry:
- PR #249 (Biloxi/MDEQ + reliability: quarantine guard, IAM policy accumulation,
  source-update-date completeness) and PR #250 (demo geocoding backfill + pilot
  script). `main` tip ~`b18b080`.
- PR #251 MERGED: AGENTS.md operating-mode section + `docs/30-day-ingestion-bridge-plan.md`
  + Week-1 qualification reports.
- PR #252 MERGED (incl. the user's `0e24772` ERCOT review corrections +
  `tests/test_ercot_ingestion.py`): `ercot_mis_xlsx` connector + stdlib XLSX
  reader + NON-activated `technical_hold` `ercot_tx_interconnection_queue`.
  Held pending authorized live connector verification/canary + written
  commercial-reuse confirmation; not activation-ready.
- PR #253 MERGED: Census BPS + Loudoun LOLA as NON-activated `technical_hold`
  candidates + a backward-compatible `CSVConnector` `skip_leading_lines`/
  `fieldnames` option. Rollout manifest regenerated; Loudoun held on OMAGI rights
  (live canary passed); BPS is an aggregate baseline input (needs a composed id).
- PR #254 OPEN: **Development Velocity v0 + cutoff-safe replay/backtest scaffold**
  (the bridge, Columbus only). `app/services/development_velocity.py` is a pure
  offline signal on `activity_baseline()` (method `development-velocity-v0`;
  unvalidated 0-100 score, confidence separate, abstains below sample floor, no
  fabrication; `POST /temporal/development-velocity`). `eval/replay/` is a
  deterministic as-of replay harness (SignalFn registry + reference signal,
  manifest freeze, lead-time/frequency/reproducibility metrics, time-proof
  fixture). DV is now WIRED into the replay registry (`eval/replay/dv_signal.py`):
  the harness replays the real signal cutoff-safe with a firing threshold (score
  >= 70) PREDECLARED in the hashed thresholds file and pinned into
  `run_fingerprint` via `series.params` (not hardcoded, not tunable post-hoc —
  P2.2). Verified implement-then-independently (verifier PASS). 12 DV + 23 replay
  tests; full suite 1870 passed. The 0-100 score stays UNVALIDATED — this enables
  backtesting it, not validation. Benign caveat: activity_baseline's future-as_of
  guard reads datetime.now, uncovered by the driver clock guard (harmless for
  historical replays). NEXT (P2.2): predeclare outcomes/holdouts and evaluate.
  Designs: docs/signals/2026-10-18-*.

Verified-live state (2026-10-17/18):
- API live (App Runner RUNNING); public demo enabled at www.buildsignals.ai.
- 16 ENABLED daily ingestion schedules in AWS (`buildsignals-ingestion` group):
  14 regional FL/TX/AZ/GA + Columbus production + demo. Real public permit/
  planning events; not reverified per-run here.
- **Demo map lit up**: a one-off Fargate task on `buildsignals-columbus-demo:2`
  (deployed image, demo-tenant DB, command override — no new image/IAM) ran the
  bounded geocoding backfill: 420 addresses matched → 938 filings located. Live
  demo summary now `mapped_permits`/`derived_geocoded_permits` = 938,
  `mapped_filing_locations` = 420 (were 0). `/v1/demo/map` renders 100 pts/layer.
  Repeatable runner: `scripts/backfill_demo_geocode.py` (demo-tenant-only,
  bounded, idempotent).

Week-1 groundwork (three parallel agents, reports written, no catalog edits yet):
- `docs/releases/2026-10-17-columbus-coverage-attestation.md`: demo cohort 2,104
  permits (2,053 approved + 51 pre_approval, ~5-mo window), 938 geocoded (~45%),
  1,088 parcel references but 0 qualified parcel records. Production/customer
  coverage explicitly NOT attested (needs an authenticated measurement).
- `docs/source-qualification/2026-10-17-wedge-market-sources.md`: READY =
  Census Building Permits Survey (public domain; needs a single-header flatten
  before `CSVConnector`) and Loudoun County LOLA (ArcGIS; candidate-grade, confirm
  reuse with Loudoun OMAGI). BLOCKED = Prince William (rights conflict), Dallas
  Socrata (stale since 2020), Denton (no license). No new rights-clean DFW endpoint.
- `docs/source-qualification/2026-10-17-utility-interconnection-queues.md`:
  ERCOT Monthly GIS Report = recurring-interface candidate with durable INR
  identity and monthly XLSX; `ercot_mis_xlsx` is now implemented in PR #252.
  Written commercial-reuse confirmation and live connector qualification are
  outstanding; the earlier rights-clean interpretation is not clearance.
  PJM = blocker
  (no public queue feed; derived-data redistribution restricted; undocumented
  key-gated endpoint).

Deploy posture: the #249 reliability fixes are merged but NOT deployed to the
regional workers (App Runner auto-deploy off); per user, hold and BATCH with the
next deploy once Week-1 build increments are ready. No new source is activated;
all legal_hold sources untouched; parcels remain unqualified/unplotted.

Next build increments (serial catalog writes, one writer): the `ercot_mis_xlsx`
connector is built (PR #252, not activated). Remaining: add Census BPS (after a
single-header flatten) and Loudoun LOLA as candidate entries + canaries; pursue
written rights for Prince William. ERCOT remains held; obtain separate
live-verification/canary authorization and written commercial-reuse confirmation
before any promotion. Then build Development Velocity v0 + the replay/
backtest scaffold over Columbus. Deploy posture unchanged: batch the #249
reliability deploy with the next deploy.

## Session 2026-10-16: Mississippi production-readiness + reliability

Branch `codex/recent-columbus-filings`. Four local commits on top of `181fea1`
(not pushed, not merged):

- `4cf27c1` Biloxi production-readiness. New `app/services/ingestion/text_decoding.py`
  provides an opt-in tolerant decoder that reinterprets only bytes that are not
  valid UTF-8 through Windows-1252 (Latin-1 fallback for cp1252's undefined slots);
  clean UTF-8/cp1252 are unchanged, so strict decoding is NOT weakened elsewhere.
  `text_encoding` and bounded `max_index_page_bytes` are threaded through the HTML
  index + `planning_documents` connectors and the connector factory; the default
  path keeps strict `get_text`. The reviewed Biloxi connector config now lives in
  the candidate catalog as inert `probe_settings`/`probe_field_mappings`
  (adapter `planning_documents`, record_type `planning`), still `legal_hold` with
  `can_run_canary` false. `scripts/qualify_biloxi.py` loads that single source of
  truth (no duplicated rules). Tests: `tests/test_text_decoding.py`,
  `tests/test_biloxi_production_connector.py` (mixed-encoding index, stable
  identity, idempotent reruns, changed-document hash, compound-vs-single parcel,
  index/document byte limits, host isolation, factory wiring).
- `5e7231b` MDEQ contract qualified by bounded read-only inspection (one public
  GET, no query submission/pagination/bypass, not activated). enSearch is ASP.NET
  WebForms: `report_epd` POSTs `uxActionType/uxStartDate/uxEndDate` with rotating
  `__VIEWSTATE`/`__EVENTVALIDATION`; no pagination (0 `__doPostBack`, no pager),
  no control total, no API/export; only id is `ai_info.aspx?ai=N` (entity id reused
  across rows/dates, duplicates). Application-vs-decision IS derivable from
  `uxActionType`; no update/withdrawal semantics. Concrete blocker: no reliable
  recurring interface + unestablished commercial reuse. Recorded in the catalog
  (stays `legal_hold`) and `docs/releases/2026-10-16-mdeq-contract-qualification.md`.
  Tests lock all three MS gates (D'Iberville express written-permission restriction;
  Biloxi legal_hold with the mixed-encoding opt-in recorded, not activated).
- `0435734` Reliability: `evaluate_source_health` measures source-update-date
  completeness (`source_update_date_total/present/completeness`,
  `source_update_dates_incomplete`) across RawSourceRecords. When a source claims a
  publisher/filing timestamp (watermark enforced) but the date is present on <90%
  of records, it is surfaced as degraded so collection recency is not presented as
  filing recency; collection-only sources report completeness without penalty.
- `5b5ba97` Fixed 10 pre-existing full-suite failures (verified failing at base
  `181fea1` before any of this session's work). Root cause for 9 of them: the
  checked-in `production_rollout.json` had drifted from the candidate catalog since
  `de553e7`, so `require_current_rollout_manifest` rejected enrollment (422) and the
  rollout determinism/render-worker tests failed. Regenerated the manifest via
  `python -m app.services.ingestion.cli catalog rollout-manifest --output ...` and
  synced `render.yaml`'s three pinned `INGESTION_ROLLOUT_MANIFEST_DIGEST` values
  (`c073515e`→`e5a6f6e7`); only `candidate_catalog_fingerprint` + derived
  `manifest_digest` changed, `candidate_count` stays 0 (no activation). The 10th was
  a time-bombed provisioning test asserting an un-advanced `StartDate` against the
  ambient clock; pinned `now` in the test (production code unchanged).

Commands/results (local, Python 3.12 `.venv`, `OPENROUTER_API_KEY=` empty, no DB
or paid calls): focused ingestion/connector/catalog/health suites green throughout;
`ruff check` and `git diff --check` clean on changed files; full suite
`python -m pytest -q` => **1764 passed, 69 skipped, 0 failed** in ~347s. The
PostgreSQL/PostGIS RLS and browser E2E suites that CI runs were NOT run locally.
MDEQ live inspection is evidence, not a golden label; Biloxi/connector tests use
synthetic documents.

Remaining work / blockers:
- No Mississippi feed is activated. Biloxi still needs a documented commercial-reuse
  basis plus broader layout/privacy validation and revision/control-total scope
  before activation. MDEQ needs a written data-use agreement and a supported export/
  API with durable activity identity, totals and correction semantics. D'Iberville
  stays blocked by its express written-permission restriction. Atlanta/Phoenix and
  other catalog holds are untouched.
- Branch is local only: not pushed/merged, no deploy. `render.yaml`/manifest edits
  are in-repo source consistency, not a deployment or cloud change.

Implemented locally vs tested vs production-ready vs live:
- Implemented locally AND tested: the tolerant decoder + connector wiring, Biloxi
  catalog integration, MDEQ qualification record, source-update-date completeness,
  and the rollout-manifest/test fixes (full suite 0 failures).
- Production-ready: the decoder/connector/reliability code is behind the existing
  gates and could ship with the next API image, but activating any Mississippi
  source is NOT production-ready (legal + contract blockers above remain).
- Actually live: nothing from this session. No push, merge, image build, migration,
  schedule, or source activation was performed.

## Historical Task: Mississippi follow-up

Mississippi follow-up (2026-10-16): owner authorized proceeding with review,
not an agency license grant. See `docs/releases/2026-10-16-mississippi-review.md`.
D'Iberville's live Terms of Service actually prohibit commercial use/copying
without written permission; this is now recorded as an express restriction,
not an inference from a copyright footer. No similar express ban was identified
in the reviewed Biloxi privacy/public-meeting pages or MDEQ disclaimer; absence
of one is not affirmative legal clearance.

Biloxi local technical qualification is implemented in `scripts/qualify_biloxi.py`:
three PDFs/four HTML pages max, no DB writes or activation, existing document
parser, source-specific mixed-encoding handling, multiline contact suppression,
source hashes/pages/case IDs. Live result: ten items, seven single-format parcel
references, two compound unresolved references, one unknown. Fifteen targeted
tests passed; expanded catalog/regional checks: 219 passed in 3.63s; Ruff/diff
checks passed. Production integration, wider layout/privacy qualification and
revision/control-total semantics remain engineering work, not a request for the
owner to approve the same review again. D'Iberville needs written permission or
a reviewed authorized alternate channel. MDEQ search contract remains unqualified.
No Mississippi feed has been enabled; existing fourteen regional jobs unchanged.

Regional recurring ingestion expanded on 2026-10-16 under explicit user approval
for Florida, Texas, Georgia, Arizona and Mississippi, with only reviewed sources
passing verification enabled. This supersedes the Columbus-only scope below.

- Fourteen regional daily schedules are ENABLED in `buildsignals-ingestion`,
  alongside the unchanged production/demo Columbus schedules. Actual scheduled
  runs completed successfully for all fourteen; see
  `docs/releases/2026-10-16-regional-production-runs.json` for task/run receipts.
- Stored source-record totals from completed runs: FL 622 across three feeds,
  TX 1,001 across eight feeds, AZ 290 across two feeds, GA 25 from Savannah.
  These 1,938 regional records are not unique projects, complete statewide
  coverage, or exclusively permit submissions. Tax, environmental, status,
  issuance and planning events remain explicitly distinguished.
- Independent read-only audit task `9be345ecfb0e4f61938c6d6c070373fc`
  exited 0 and confirmed all fourteen regional sources active/latest runs
  completed/zero failures. Including Columbus, the customer workspace has
  1,904 permit-table records plus 82 planning records, 980 with coordinates.
  1,420 permit records lack normalized source-update dates; recent collection
  must not be represented as proof of recent filing or correction dates.
- First runs exposed real data bounds: Dallas agenda titles >1,000 characters,
  Orlando compound parcel references >255, and a San Marcos graph label >255.
  Originals remain in immutable raw evidence/unmapped fields; oversized parcel
  references become unresolved rather than truncated identities. Stable hash
  suffixes bound graph labels. Full-cohort local replay and scheduled rechecks
  passed. Austin's completed keyset cursor is no longer treated as incomplete.
- Dedicated worker-only image:
  `159667575905.dkr.ecr.us-east-1.amazonaws.com/dealsignal-api@sha256:de6dcaad61014d4702b62c532a638a1fba060fa949ea561cdb7f00c961ba8854`.
  It derives from the existing API image with only normalization/service fixes.
  API image, ECR `latest`, frontend and production schema were not changed.
  Regional task revisions: original thirteen `:3`, Austin Site Plan Cases `:2`.
- Regional IAM is separate from Columbus, exact task revisions/cluster and
  execution-role scoped; outbound hosts are per source. Existing managed secret
  references are reused. Tenant/source advisory locks and bounded windows/caps
  apply. No customer records are copied into the public demo.
- Schedule updates advance expired start dates to the next daily occurrence,
  preserving cadence; AWS rejected old start dates during verification.
- Final targeted suite: 287 passed in 16.23s; Ruff and diff checks passed.
  Offline Python 3.11 worker-image smoke passed. No paid LLM calls. Full suite
  and customer-authenticated browser workflows were not rerun in this task.
- Public anonymous demo API smoke passed: read routes 200, restricted reads and
  all four write methods 403. Demo remains Columbus-only (2,097 records); mapped
  locations and qualified parcel geometry remain zero in that demo.
- Mississippi MDEQ, D'Iberville and Biloxi remain legal/technical holds: a
  supported reusable export/API or written source-use permission is required.
  Other catalog holds, including Atlanta and Phoenix, were not bypassed.
  Austin Site Plan Cases alone was separately admitted using verified official
  PUBLIC_DOMAIN metadata and its existing field/suppression scope.
- Runtime failure paging remains unconfigured. Measured source-update-date
  completeness is weaker than collection freshness; do not advertise all
  collected records as newly filed. Parcel feeds need bounded geographic
  qualification and were not bulk-imported. No for-sale claim is established.
- Runbook: `docs/runbooks/regional-ingestion.md`. Code and receipts are local
  commits on `codex/recent-columbus-filings`; not pushed or merged.

Recurring production and independent demo ingestion are now ENABLED and verified
on 2026-10-16, superseding the manual-only status below. User explicitly approved
recurring collection, separate demo refresh, and verification of a scheduled run.

- AWS EventBridge Scheduler group `buildsignals-ingestion`: production daily
  starts 21:49:18 UTC; demo daily starts 21:51:19 UTC, both `rate(1 day)` ENABLED.
  These are current 14:49/14:51 Pacific; rate schedules repeat every 24 hours.
- Task definitions `buildsignals-columbus-production:2` and
  `buildsignals-columbus-demo:2` pin the existing API image digest and embed the
  tested worker command. Worker SHA256:
  `15a1a999ea751e917f6a3aab88fa691b34197641ab4eca5d840b32a4b5300212`.
  Existing managed DB/SECRET_KEY references are reused; no plaintext keys copied.
  Scheduler IAM trust is account/group scoped, RunTask restricted to these two
  task revisions/cluster, PassRole only to the existing ECS execution role.
- Actual scheduler-started production task `a14d06edc643479c90629e9505b23935`
  exited 0: run `8ae765ce-098c-4613-8e06-f4e3592c0b49`, completed, 48 seen,
  27 inserted, 21 updated, zero failed, no checkpoint, provider before/after 48.
  Independent read-only DB audit confirmed 48 stored production records and
  the completed scheduled receipt. This was not a manually launched worker.
- Actual scheduler-started demo task `b556b41b4db046449931175434aba590`
  exited 0: run `ede7f860-7327-4654-bfb8-6dc90348e13c`, completed, 48 seen,
  27 inserted, zero failed, provider before/after 48. Existing source identity
  adopted in each tenant, avoiding duplication of the previous 21-row snapshot.
- Worker `scripts/recurring_columbus.py` uses a rolling 31-day filing window,
  existing normalization/evidence/graph code, max four 250-record pages, bounded
  retries/timeouts, and PostgreSQL advisory locks. It never retires records merely
  aging out of the window. Demo fetches independently from the reviewed public
  feed, never from customer tables; only maps2.columbus.gov is allowed outbound.
- `scripts/configure_recurring_columbus.py` reproduces the versioned tasks and
  schedules. It requires explicit production confirmation, tenant and reviewed
  ECR image digest, and checks the AWS account before changing resources.
- Focused worker/provisioning/demo/historical tests: 82 passed; Ruff and
  diff checks passed. No API image deployment, migrations or paid model calls.
- Final independent read-only audit task `42d1bae867a64c9c98882c1d8d488db9`
  confirmed 48 source records in each tenant, completed scheduled runs, and
  demo source inactive. Public API smoke confirmed 2,097 total demo records,
  5,008 graph entities, 8,321 relationships and 1,082 parcel references. All
  read routes passed; restricted reads and POST/PUT/PATCH/DELETE still return
  403. Qualified parcel records and mapped coordinates remain zero.
- Runbook: `docs/runbooks/recurring-columbus-ingestion.md`. Logs:
  `/ecs/buildsignals-ingestion` (30-day retention); ingestion run receipts in DB.
  Automatic runtime-failure paging is not configured. Updates to filings older
  than 31 days require separate reconciliation. Only this reviewed Columbus
  site-application feed is enabled; this is not national or parcel coverage.

Recent-filings activation completed after user approved the existing signed-in
workspace plus a separate sanitized public-demo subset. Branch:
`codex/recent-columbus-filings` (local commits; not pushed/merged).
- Production task `3bb48eaae16549e29a7e18d2f101a149`: exit 0, 21 Columbus site
  applications inserted, zero failed, no checkpoint, provider counts 21/21.
  Destination was the sole active non-demo organization; query `.one()` fails
  closed if ambiguous. No customer rows were copied to demo.
- Public demo task `05fd7a4a8eb2493fb622e11ae08cc2e2`: exit 0, 21 reviewed public
  site applications replayed with the new explicit recent-snapshot seed path.
  Q1-only default guard remains. Source snapshots remain inactive in demo.
- Independent read-only task `41351cc7edc84394b176aa3598c76103` confirmed 21
  production recent filings; newest filed date October 13, 2026. Collection
  interval was October 1 inclusive through October 16 exclusive. Production
  source is active but manual and date-bounded, NOT automatically refreshed.
- Demo API summary: 2,070 permits, 4,919 graph entities, 8,197 relationships,
  1,057 parcel references, zero qualified parcel records/map coordinates.
  Anonymous login and read routes passed; restricted reads and all write-method
  probes returned 403. Temporary private S3 import archive was removed.
- Vercel deployment `dpl_HXpc64UPv3nNi925LnKTYaZR9pub` READY and aliased to
  www.buildsignals.ai. Demo subtitle no longer claims only Q1; filing/issuance/
  capture dates are shown separately in the list. API service image unchanged;
  the reviewed seed helper ran as a one-off task, not an API code deployment.
- Verification: 68 targeted backend tests, 3 demo frontend tests, typecheck,
  local production build and focused Ruff passed. npm audit --omit=dev: zero
  vulnerabilities. Vercel full install reported 4 moderate/6 high advisories;
  development dependency audit remains pending. Bundle-size warning remains.
- First large CLI upload was interrupted. Added explicit frontend-only Vercel
  upload rules. First allowlist attempt excluded directories and failed remote
  typecheck/lint before promotion; corrected rules included 302 frontend files
  and subsequent deployment succeeded. No checks were bypassed.
- Follow-up `f730d4f` fixes browser-local date shifts by displaying UTC calendar
  dates explicitly. Four frontend tests and typecheck pass. Final deployment
  `dpl_AM68dHrfzDgPVQaAb7Qb2d3ToK86` is READY and aliased to www.buildsignals.ai.
  Recent snapshot local replay twice retained 21 permits, 81 entities, 82 edges
  with no count growth. Browser verified recent under-review applications on
  the first filing page; signed-in customer browser workflow remains unverified.

Next: configure scheduled, bounded current-source refresh using managed secret
references (existing GitHub ingestion environment is unconfigured); add durable
job receipts and recent-demo refresh policy. Do not represent this fixed-window
import as continuous ingestion or nationwide coverage. New seed CLI code is
local until its branch is published or a new API image includes it.

Recent-filings follow-up (2026-10-16): production read-only audit task
`0de200bceac54ff4ac12338d4086456a` exited 0. The sole non-demo workspace
has no registered sources. Demo has only the six inactive historical sources.
Last five GitHub ingestion-cron runs were skipped; repository variables and
production-environment secret name lists were empty. No ECS services or EventBridge
Scheduler schedules were found in us-east-1; this is not an exhaustive account audit.
Bounded local Columbus site application intake for October 1 inclusive through
October 16 exclusive returned 21 records, zero failures, no checkpoint, and
provider counts 21 before/after. Existing historical intake tests: 9 passed.
Qualification DB/report are under `/private/tmp/buildsignals-columbus-site-20261001.*`;
temporary files are not durable project inventory. This does not qualify geometry.
Production task `4f6a3c7e06164f43bce87b236d4bee8a` stopped with NoResultFound
while resolving `default-org`, before source creation or record writes. Confirm
the intended destination workspace rather than guessing another tenant. No recent
records were loaded into production; no schedule was activated. Public demo still
uses a Q1-only replay guard and historical labels; add an explicit recent cohort
path with matching UI labels/tests rather than bypassing that guard.

Public read-only demo activation was approved and completed on 2026-10-16.
App Runner operation `9a909ca644b34ba59b8303a7822d496a` SUCCEEDED with
`DEMO_ENABLED=true`; no OpenRouter configuration or source activation changed.
The existing seed pipeline loaded six reviewed Q1 Columbus snapshots into the
reserved demo tenant: 2,049 permits, 4,852 graph entities, 8,115 relationships,
and 1,038 distinct reported parcel references. Seed ECS task
`a2d789c959e14bc7b1cb592f9b9cac2a` exited 0. These are historical records, not
unique projects or live nationwide inventory. There are zero qualified parcel
records and zero mapped coordinates in this cohort; do not claim otherwise.
The temporary private S3 seed archive was removed after successful import.

Production verification: anonymous POST `/v1/auth/demo` issues a viewer token
with demo/read_only claims and 60-minute expiry. Summary, permits, graph hubs,
parcel references and map routes returned 200. Settings, users, export and
POST/PUT/PATCH/DELETE mutation probes returned 403. Browser verification clicked
`Enter demo mode` on `/login`, reached `/demo` without credentials, and displayed
the read-only banner and populated counts. Local `tests/test_demo.py`: 51 passed.
This smoke test is not a new exhaustive tenant-isolation audit.

The approved main API release to AWS is complete, with OpenRouter unconfigured
and scoring deterministic. User approved this production deployment and required
migrations on 2026-10-16. No paid model calls were approved.
Portable-agent instructions/tooling are checkpointed locally as `d4a9c83` on
`codex/portable-agent-handoff`; publishing that branch remains separate.

## Completed API Release (2026-10-16)

- Release source: main `edcbc52`; workflow run `38953119809`.
- Repaired deployment IAM trust to the exact current immutable GitHub subject,
  retaining main-only scope. GitHub reports `use_immutable_subject=true`.
- First authentication attempt stopped before application/database changes.
- First migration task then failed before connecting to the DB because its
  production CORS allowlist was missing. Registered `dealsignal-migrate:2`
  with the existing API origins; preserved role/secret references.
- Confirmed API and migration task reference the same DATABASE_URL/SECRET_KEY
  secrets without reading values. RDS has seven-day retention and a recent
  point-in-time recovery timestamp (restore procedure not tested in this task).
- Retried migrations succeeded (task `b35a3853aa694e558285c2450c346e87`, exit 0),
  upgrading `20260915_0001` through `20260928_0008`.
- New image digest: `sha256:648ec2c7fe8a4eca1cac32dd74b83872eaa0ba762abbe31f8915fd82a71d791e`.
- App Runner operation `f26e7fff97fa478ebafba78f080d7e4a` SUCCEEDED at
  2026-10-16 12:21:35 America/Los_Angeles; service is RUNNING. Workflow succeeded.
- Earlier image digest retained for rollback reference:
  `sha256:bd3ccc8bb085957656b0013a5d533ecdf99c77cbc4aafcca58480e5951632556`.
- Production sign-in page renders. Authenticated user/data workflows remain
  unverified. Demo configuration has not been enabled or seeded by this release.
- Direct readiness and database health returned 200; live ScoreResponse now has
  scoring_method/fallback_reason and OpenAPI exposes `/v1/auth/demo`.
- Through Vercel, GET `/v1/auth/demo` returns 200 with enabled=false, and
  unauthenticated GET `/v1/deals` returns 401. Model key remains absent from
  runtime variables and secret references; unset SCORING_MODE defaults deterministic.
- Full receipt: `docs/releases/2026-10-16-api-rollout.md`.

## Completed Product Work

- PR #247 merged as `4d47f4c`: OpenRouter client, optional enrichment/memos/model
  scoring, deterministic scoring default, validation/fallback, benchmark tooling.
- Review follow-up fixed exhausted timeout/connection handling, malformed JSON
  benchmark classification, production validator use, and omitted memo evidence.
- Final PR backend CI: **1,767 passed**, including PostgreSQL-backed tests,
  in 705.75 seconds. Run: GitHub Actions `38865887692`.
- Final offline OpenRouter/review subset: **38 passed**. Frontend/E2E/security/
  pre-commit/Vercel checks passed on final PR head `a59d32b`.
- Production frontend subsequently built from `edcbc52` (main), which includes
  PR #247 and only adds generated OpenAPI updates. Do not restore the obsolete
  `cleanup-and-hardening` product tree over main.

PR: https://github.com/ahdithanu/buildsignals/pull/247
Audit: `docs/openrouter-cleanup-integration.md`. Older local receipts there are
historical; the final CI receipt above supersedes their counts.

## Earlier Production Verification (2026-10-16, Superseded for API State)

Read-only observations; these are not authorization to modify cloud resources.

- `https://www.buildsignals.ai` is Vercel production, ready, deployment
  `dpl_WmgWdc8qDNWHyagTriQoc3d8wKoF`, source commit `edcbc52`.
- `vercel.json` proxies `/v1` to
  `https://xg4xjxc2p2.us-east-1.awsapprunner.com`.
- AWS App Runner `dealsignal-api` is RUNNING. Its last successful deployment
  was 2026-09-19; ECR `latest` was pushed 2026-09-18. Auto-deploy is false.
- Direct API `/health`, `/health/deep` and `/health/ready` returned healthy.
  Readiness reflects the running version; it does not prove compatibility
  with all migrations in current main.
- Live OpenAPI's ScoreResponse lacks `scoring_method`/`fallback_reason` and
  lists no `/auth/demo` routes. Live `GET /v1/auth/demo` returned 401.
  Serving `/demo` HTML with 200 is not proof of a working demo data session.
- App Runner has no `OPENROUTER_API_KEY` runtime variable or secret reference;
  no SCORING_MODE/primary/fallback model settings were configured.
- `.github/workflows/deploy-aws.yml` is manual and includes a migration task.
  No image tagged with PR #247's merge SHA was found in ECR.

Vercel connector lacked team scope; Vercel CLI access worked. AWS CLI and gh
read-only access worked in the previous agent environment. Other agents must
authenticate independently. Render MCP had no workspace selected.

## Next Actions and Dependencies

1. Portable-agent setup is implemented and verified locally. See Git history for
   its checkpoint. Publishing this new branch has not been requested; another
   machine/clone will need the branch published before it can read these files.
2. API rollout and public demo activation are complete. Ordinary authenticated
   customer workflows remain unverified. Qualified parcel geometry/geocoding is
   still required before this demo can display mapped acquisition candidates.
3. Provision an OpenRouter production key/config through a managed secret path
   only with applicable approval. Never copy or print a local key in chat.
4. Run live model smoke tests and the corrected benchmark only with paid-call
   authorization. No current post-fix model ranking/cost result is published.
   Keys/credits/model availability and key rotation remain unverified.
5. Resume acquisition pilot/source qualification work from the linked checklists
   after the immediate release blockers. Do not activate unreviewed sources.

## Evidence and Product Limits

- The 2,049 Columbus records are historical source qualification/demo data,
  not 2,049 unique projects or measured nationwide production inventory.
- No current live jurisdiction/record/freshness count was measured in this task.
- Nearby parcels are candidates unless separate source-backed availability
  evidence verifies a listing/for-sale claim.
- No paid model calls were performed. The initial production verification and
  portability tasks were read-only; the later approved deployment has the
  infrastructure/migration changes recorded above.

## Session Verification

Portability verification (2026-10-16):

- `python3 scripts/agent_status.py --check`: passed; all shared files/adapters found.
- `make agent-status`: passed; branch, commit and working-tree status reported.
- The same script with `--check` invoked by absolute path from `/private/tmp`:
  passed, correctly locating the repository rather than using the caller's folder.
- `ruff check scripts/agent_status.py`: passed.
- `git diff --check`: passed.
- Product test suites were not rerun for these docs and read-only tooling changes.
  Prior product test receipts are recorded above, not represented as new runs.
- Instruction discovery and cloud authentication inside external agent apps:
  unverified; Claude Code is installed locally, Antigravity CLI was not found.

Use `python3 scripts/agent_status.py` to inspect the actual working tree. Before
switching agents again, replace this snapshot with the latest state and next task.
