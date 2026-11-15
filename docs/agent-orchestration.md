# Coding Coordination and Research Agents

Review-only integration of the local research workflow onto current main.
Not merged or deployed. Production settings and existing source jobs are unchanged.
No paid model calls are required for the offline checks.

## Two Separate Responsibilities

Coding agents change the repository under explicit ownership and review. Product
research agents examine a bounded, explicitly exported workspace snapshot. Neither
one grants source activation, cloud, publication, migration or release authority.

## Local Dashboard Workflow

The follow-up adds a Deal Research panel and authenticated endpoints:

- `GET /v1/deals/{id}/research/capabilities` reads availability and remaining attempts.
- `POST /v1/deals/{id}/research` accepts only a version-4 `request_id` UUID.

Current admin/editor membership is required; demo, viewer and anonymous sessions
cannot start research. The UI never starts a run on page load, asks for confirmation
before sending saved facts, and never automatically replays the paid POST after a
401/error. Results and requests are scoped to the current account/workspace/deal.
Late responses cannot populate a different context. Quota-refresh errors preserve
already received findings and disable new runs; the read-only quota retry cannot
spend a run. Unknowns/questions and quoted facts remain separate; text is not HTML.

The API is **local development/test only**. Staging/production are explicitly
denied in code, independently of environment flags. Defaults:

| Setting | Default | Purpose |
|---|---|---|
| `AGENT_RESEARCH_API_ENABLED` | `false` | Local API admission switch |
| `AGENT_RESEARCH_CONTEXT_ENABLED` | `false` | Scoped snapshot availability |
| `AGENT_RESEARCH_PYTHON` | empty | Server-owned absolute SDK interpreter path |
| `AGENT_RESEARCH_DAILY_RUN_LIMIT` | `0` | Per-workspace UTC-day attempt ceiling, 0..100 |

These settings do not authorize paid calls. Real execution additionally needs
the configured OpenRouter key and explicit UI confirmation. The separate CLI's
`AGENT_RESEARCH_ENABLED=1`/`--execute` gates remain unchanged; only the trusted
API bridge constructs that worker invocation, never client-supplied settings.

### Admission and Audit

Before dispatch, the service serializes on a fresh organization row lock in
PostgreSQL, or `BEGIN IMMEDIATE` in local SQLite. It computes the UTC day after
the lock wait, checks the request UUID across all that workspace's dates/deals,
checks the day's reservations and commits one `research_reserved` AuditLog entry.
The lock is released before calling the worker. Commit failure means zero dispatch.
Failures/timeouts/crashes consume the reservation; unknown outcomes are not refunded
or automatically retried. Duplicate UUID returns 409; exhausted quota returns 429
with Retry-After. The existing fail-open HTTP limiter is not used as this budget.

Separate completed/failed metadata records contain the actor, request/run ID,
context hash, safe status and successful usage receipts. No prompts, findings,
addresses, raw errors, API keys or stderr are written to these audit entries.
Unreported cost stays null. Failure can occur after a billable call, so failed
attempts may have unknown usage. Audit-commit failure never redispatches a worker.

This is an attempt admission limit, **not a dollar ceiling, complete billing
meter, tamper-proof ledger, or process-concurrency limit**. It relies on retained
audit rows and all writers following the locking protocol. Existing billing/eval
usage rollups do not include this research path. Completed findings are returned
to the active page, **not saved as a research-history record**; reload discards them.
A dedicated retained budget/result store and audit access/retention review remain
hosted-release prerequisites. Existing policies/schema were not altered.

### Worker Boundary

Only a trusted server configuration selects the absolute interpreter and model
settings. A constant Python bootstrap uses isolated mode (`-I`), no bytecode writes
(`-B`) and no shell. The six-entry environment contains only OpenRouter settings,
the worker execution gate, local environment name and tracing-disable flag; no
database, JWT, cloud, proxy or alternate-provider credentials are inherited.
Evidence travels on bounded stdin, not command-line arguments or temporary files.

Nonblocking stdin/stdout exchange avoids pipe deadlocks, caps stdout at 40,000
bytes while reading, discards stderr, and applies a 75-second I/O/wait deadline.
Owned process groups are terminated on success and failure; the direct child is
reaped. Descendants that escape the owned session are outside this boundary.
Kernel process creation/termination is not itself interruptible by the selector.
This is not an OS/network/memory/spend sandbox. A timeout cannot undo provider cost.

The parent independently checks strict JSON, exact stages, evidence IDs/quotes,
finite typed usage and required research-only labels before returning results.
Malformed worker output becomes a generic 503, never a provider traceback.

### Portable Coding Task Packets

`scripts/agent_task_packets.py` accepts JSON stdin and emits writer/reviewer
packets for Codex, Claude Code and Antigravity. Example input:

```json
{"version":1,"tasks":[{"id":"research-tests","agent":"codex","reviewer":"claude_code","objective":"Review the offline research validation tests.","files":["tests/test_research_agents.py"]}]}
```

```sh
python scripts/agent_task_packets.py < task-plan.json
```

This is a planner, not a dispatcher. It never executes a shell, model, coding
agent or generated prompt, and never writes files. It rejects duplicate IDs,
overlapping or ancestor file claims (case-insensitive), traversal, absolute paths,
globs and protected secret/data/private-receipt paths. Bounds: 64 KiB input,
16 tasks, 32 files per task, 128 total files. Every writer has a different-labelled
read-only reviewer. Shared docs/catalog/migrations must have one coordinator.

The coordinator must inspect actual paths, symlinks and worktree state before
separately authorized execution. Lexical validation is not a filesystem sandbox;
agent labels do not prove independent execution or independent review. No
external agent application was launched or compatibility-tested here.

### Tenant-Scoped Research Context

The authenticated `GET /v1/deals/{deal_id}/research-context` endpoint is disabled
unless the **API process** has `AGENT_RESEARCH_CONTEXT_ENABLED=true`. It requires
current admin/editor membership, rejects demo and anonymous callers even in
anonymous development mode, and returns 404 for foreign/deleted deals.

It reuses `eval_workflows.execute_live(..., 'score_explanation', ...)` to obtain
the existing scoped snapshot without persisting a score, audit or model output.
The returned versioned bundle has saved deal facts, derived financial outputs
when present, contact counts/statuses, activity types and saved signals; it does
not export contact names/emails. The existing serializer caps context at 10,000
characters and each related list at 1,000 records (it fetches 1,001 to detect
overflow). These limits are not DB-read, memory or HTTP payload guarantees.
Responses are `Cache-Control: no-store`. Existing tenant/RLS infrastructure is
unchanged; this change does not add or migrate any database policy.

Use your authenticated local API client to export a local deal's bundle. Store
private snapshots only in an ignored path such as `data/qualification/`, never
in source control or public logs. Do not use production credentials or enable
this setting in production as part of these instructions. Saved facts are not
independently verified public records or fresh parcel/listing coverage.

### Isolated Agents SDK Runner

`openai-agents==0.24.0` requires OpenAI SDK 3.x; the application pins OpenAI
1.55.3. **Do not install them in the same environment or upgrade app requirements.**
Create a separate environment outside the repository, then install only the
optional runtime requirements:

```sh
python3 -m venv /tmp/buildsignals-agents-venv
/tmp/buildsignals-agents-venv/bin/python -m pip install -r agent_runtime/requirements.txt
PYTHONPATH=. /tmp/buildsignals-agents-venv/bin/python scripts/check_research_sdk.py
```

The requirements pin the two direct SDK packages, not every transitive package.
The integration check uses the actual SDK Runner with a fake client and blocked
socket connections. It makes no provider requests and needs no key.

Dry-run validation needs only the application's Python, not the SDK or a key:

```sh
python -m agent_runtime.research < data/qualification/local-research-context.json
```

Execution is a **separate paid action**. After reviewing the snapshot and approving
its transmission, load `OPENROUTER_API_KEY` through your local secret manager.
The usual `OPENROUTER_PRIMARY_MODEL` / `OPENROUTER_FALLBACK_MODELS` settings apply.
Do not put a key or bearer token in a command, file committed to Git, or log.
Both `--execute` and `AGENT_RESEARCH_ENABLED=1` are required:

```sh
AGENT_RESEARCH_ENABLED=1 PYTHONPATH=. /tmp/buildsignals-agents-venv/bin/python -m agent_runtime.research --execute < data/qualification/local-research-context.json
```

Two sequential, tool-free stages run: evidence analyst and diligence reviewer.
Both use a custom SDK Model adapter calling the existing `OpenRouterClient`;
there is no SDK default-provider path, database session, shell, URL fetch, file
write or autonomous ingestion tool. Agent turns are capped at one per stage,
800 completion tokens each, with 30-second network timeouts and no client retries.
Server-side model fallbacks still apply; two successful stages mean two client
completion requests, not a guarantee about provider-internal attempts. This is
not a hard process-level wall-time, memory or spend sandbox.

Tracing is disabled before SDK use, globally and per run; sensitive-data tracing
is also off. CLI failures emit a generic JSON error, not provider exceptions.
Usage includes requested/resolved model, provider, tokens, latency and reported
cost; missing cost stays `null`, never a fabricated zero. Receipts omit raw output.
Final findings themselves include quotes and must be treated as private data.

Input is capped before JSON parsing at 20,000 bytes, with at most ten distinct
evidence IDs. Each stage's output must parse as plain JSON with only `facts`,
`unknowns`, and `questions`. Facts contain only a known source ID and an exact
nonempty quote from its supplied evidence. Unverified questions/unknowns are
separate. Exact matching checks presence, **not truth, relevance or investment
quality**. Caller-supplied JSON is not authenticated merely by matching the
export schema; the local runner explicitly marks its authenticity unverified.

## Verification and Remaining Work

The integration branch is based on current main and excludes unrelated local
ingestion and criteria changes. Its acceptance results are recorded in the current
handoff and PR; historical source-branch test totals are not destination results.
No paid model run or production acceptance is claimed.

| Destination check | Result |
|---|---|
| Backend including real PostgreSQL cases | 3,135 passed, zero skipped; 3 existing reflection warnings |
| App statement coverage | 91.44% (85% CI floor) |
| Frontend | 477 passed |
| Desktop/mobile Chrome | 2 passed |
| CI-style headless Chromium | 2 passed |
| Typecheck, build, scoped lint, Ruff, migration/drift | Passed |
| Optional SDK with fake client and no network | Passed |

Counts apply to this current-main integration, not an earlier local branch.
The 2,717 unchanged main test cases plus 418 added cases total 3,135. Existing
build/reflection warnings are not suppressed. These are local results; hosted CI
is checked separately when the PR is published.

Offline checks use the ordinary application test environment. Optional SDK checks
use the separately installed pinned runtime with a fake client and blocked sockets.
Browser acceptance uses synthetic saved deals and a synthetic worker in the E2E
launcher only, with external connections blocked. It tests UI/API/quota integration,
not live-model quality.

Research PostgreSQL tests require a separately provisioned disposable target:
`SNAPSHOT_TEST_POSTGRES_URL` and `SNAPSHOT_TEST_RUN_ID`. The URL must use
`postgresql+psycopg2`, a numeric loopback host, an explicit port, no query/routing
overrides, and a database named `bs_snapshot_test_<run_id>`. The run ID must be a
UUID4 hex string. The database's independently provisioned comment must be
`BuildSignals disposable snapshot test:<run_id>`; the connection role must be
neither superuser nor BYPASSRLS. Do not relabel an unknown database or use
production credentials. Nonempty ambient libpq `PG*` overrides are rejected.
Every physical connection is independently verified read-only before use.
Generic application/test URLs are never substituted for this dedicated target.

CI creates an additional run-specific database inside its ephemeral PostgreSQL
service, verifies the role/nonce before migration, and runs these tests there.
The ordinary local suite skips these cases when their dedicated target is absent;
skips are not database-isolation proof.

Browser cases use a dedicated opt-in configuration, run as an explicit CI step:

```sh
RUN_RESEARCH_E2E=1 E2E_API_PORT=8287 E2E_WEB_PORT=8087 PYTHON=/path/to/app-python node node_modules/@playwright/test/cli.js test -c e2e/research.playwright.config.ts
```

Locally this opens a fresh normal Chrome window; CI uses its installed headless
Chromium. Each run owns disposable API/web servers.
It does not reuse production data or existing browser windows. The existing lint
config excludes E2E files; real-browser execution is a separate check.

### Bounded Checklist

- [x] Portable offline coding packets and separate SDK environment.
- [x] Bounded tenant-scoped context and tool-free SDK stages.
- [x] Local isolated worker, authenticated API and independent output validation.
- [x] Committed attempt reservations and metadata outcomes before/after dispatch.
- [x] User-triggered dashboard panel, confirmation and safe failure handling.
- [x] Offline protocol, database-lock and desktop/mobile browser acceptance.
- [ ] Approved real-model evaluation on reviewed non-sensitive inputs.
- [ ] Monetary spend policy, retained results, complete usage/billing integration.
- [ ] Reviewed hosted worker image/lifecycle and audit/budget-store access/retention.
- [ ] Install the guarded `multi_agent_research` evaluation workflow if selected.
- [ ] Separately approved coding-agent dispatch; current packets do not execute agents.
- [ ] Current-main integration, PR/publication and production release approval.

Preserve source rights and evidence/privacy gates. Do not claim that two agents
have discovered or validated investment opportunities, or that this is deployed.

API shapes were checked against the installed SDK 0.24.0 source. Official context:
[Agents tracing controls](https://developers.openai.com/api/docs/guides/agents/integrations-observability)
and [Codex execution surfaces](https://developers.openai.com/blog/codex-as-a-platform).
