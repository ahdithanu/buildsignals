# End-to-end tests (Playwright)

Browser-level critical journeys cover registration, login/logout, deal creation,
dashboard activity, organization-scoped ingestion inventory, acquisition
screening, and AI evaluations.

## Verification status

On 2026-09-20 the acquisition screening spec passed at desktop (1440x1000)
and mobile (390x844) sizes with real local API responses in disposable SQLite.
It exercises registration, fixture deal creation, profile switching, market
validation, unknown diligence, and overflow checks. A subsequent full run on the
same date passed all nine configured workflows, including auth, activity display,
deal creation, and measured empty inventory. This is local SQLite qualification,
not a claim that production data or PostgreSQL isolation is ready.

```bash
PYTHON=.venv/bin/python npx playwright test -c e2e/playwright.config.ts acquisition-screen.spec.ts
```

## Requirements

- Node 22 and npm dependencies installed (`npm ci`).
- Python backend dependencies installed from `requirements.txt`.
- Playwright Chromium installed (`npm run e2e:install`).
- Selected ports available (8000 and 8080 by default). Do not stop unrelated services to free them.

The runner accepts `E2E_API_PORT` and `E2E_WEB_PORT` (defaults 8000 and 8080).
These settings keep the disposable backend, CORS, frontend API URL, browser
base URL and registration helper aligned. The investment-area spec also uses
these ports; older specs with explicit URLs still require the default ports.
For example, use `E2E_API_PORT=8001 E2E_WEB_PORT=8081` when the default ports
are occupied. Both selected ports must be free; existing servers are never reused.

When another agent is updating dependencies in a shared checkout, wait for its
explicit ready signal before starting the app or running tests.

## Running

```bash
# All specs; the config starts and stops BOTH servers.
npm run e2e

# Acquisition screening only.
npm run e2e -- acquisition-screen.spec.ts

# Evaluation dashboard only.
npm run e2e -- evaluations.spec.ts

# Select an installed Python interpreter if python3 is not suitable.
PYTHON=/path/to/python npm run e2e -- evaluations.spec.ts

# Interactive sessions, still using the isolated backend.
npx playwright test -c e2e/playwright.config.ts --headed
npx playwright test -c e2e/playwright.config.ts --debug
npx playwright test -c e2e/playwright.config.ts evaluations.spec.ts --headed
npx playwright test -c e2e/playwright.config.ts evaluations.spec.ts --debug
```

The repository config starts FastAPI on `127.0.0.1:8000` through `e2e/backend.py`
and Vite on port 8080 by default. The backend creates a fresh SQLite database in a
`TemporaryDirectory`, runs Alembic migrations, and overrides inherited database
and service credentials. It raises auth rate limits for repeated local
registration and disables configured email, Redis, and Sentry integrations.
Both servers set `reuseExistingServer: false`; a localhost URL alone is not
proof that a pre-existing server uses disposable data.

Do not replace this setup with staging/production URLs, a persistent database,
or manually started servers. No deployment is part of these tests. Staging
deployment is documented separately in `docs/staging.md` and
`docs/runbooks/staging-deploy.md`, using `render-staging.yaml`.

## Evaluation Journey

`tests/evaluations.spec.ts` uses `registerAndLogin()` and `uniqueEmail()` to
create a new organization and admin through the real registration UI. It uses
the desktop Admin menu, verifies the empty state, seeds four synthetic datasets,
and checks repeat seeding does not duplicate them. It runs the Copilot example
replay, checks the passing gate, evidence/rubric/citations, heuristic confidence,
and explicitly unknown tokens, cost, and latency. No API mocking or live LLM
generation is used.

A second replay is loaded again after a page reload and compared with the
baseline. Both runs must be compatible, with zero metric deltas and no gate or
case regression. At 390px, the test navigates through the Account menu and
exercises comparison controls again, including same-run rejection. Both document
and main-container horizontal overflow are checked. Desktop/mobile screenshots
are written via `testInfo.outputPath()` into the test results directory.

Passing synthetic replays verify the dashboard integration, not production AI
quality. This spec does not cover live evaluation runners or non-admin access;
those contracts have separate API/component tests.

Verified locally on 2026-09-23 with Node 22, Anaconda Python, and Chromium:
the focused evaluation journey passed, and the full suite passed all eight
tests after the Router 7 upgrade. Desktop (1440px) and mobile (390px) screenshots
were visually inspected, including mobile output, unknown telemetry, and
comparison detail. Each invocation used a newly migrated temporary database.

## Live Investment Areas (Opt-In)

`tests/investment-areas.spec.ts` exercises `InvestmentAreaPanel` mounted on
`/signals` at 1440x1000 and 390x844. It registers a fresh organization using the
real UI and leaves its local evidence inventory empty. No private inventory is
seeded, no API responses are mocked, and no production database is used.

The test is skipped unless `RUN_LIVE_INVESTMENT_AREAS=1`. One test and backend
snapshot cache serve both metros and viewports: the first request downloads six
bounded public FHFA/Census files (one HPI, one population/crosswalk, four annual
county permit files), with no download retries. Subsequent requests must retain
the same snapshot and provenance. Automatic test retries are disabled, even in
CI. Public service failures fail the opted-in run; ordinary CI stays independent
of their availability. Re-running starts a new backend and consumes another
six-download budget, so do not retry without authorization.

```bash
RUN_LIVE_INVESTMENT_AREAS=1 \
E2E_API_PORT=8001 E2E_WEB_PORT=8081 \
PYTHON=/Users/ahdithebomb/Desktop/DealSignal/.venv/bin/python \
OPENROUTER_API_KEY= \
npx playwright test -c e2e/playwright.config.ts investment-areas.spec.ts
```

Assertions cover all six source URLs, periods, SHA-256 hashes and capture
timestamps; research/investment-quality limitations; Ocala's numeric research
score; Tampa's unavailable aligned rank but observed population/migration
context; honest zero local evidence; document/main/panel horizontal overflow;
and uncaught browser page errors. Four full-page screenshots are written through
`testInfo.outputPath()` under `test-results/`:
`investment-areas-{ocala,tampa}-{1440,390}.png`.

This qualifies the local browser/API/public-input integration, not investment
performance, complete metro evidence, production activation, or PostgreSQL RLS.

Verification on 2026-11-10: the final authorized live Chromium run passed
(`1 passed`, 7.1s test / 16.1s total) on ports 8001/8081 after the parent added
the no-store header and v2 population-crosswalk completeness guards. The first
attempt had exposed the missing header; the final run verifies that correction.
The fresh disposable backend fetched six official public files; both metros and
both viewports shared snapshot
`523fea1590d2bd056ec511f0e679e5c1e738a7303f26335aeadbfc88fc0bdd98`
with **360 eligible metros**. Neither hash nor cohort count is hardcoded in the
test assertions. Ocala displayed a rounded research score of **0.251 / 1**;
Tampa had no aligned rank but displayed population growth **0.398%** and net
migration **4.936 per 1,000**. Both showed zero local records/geocoded records.

All source/provenance, disclaimer, research-state, demand-context, horizontal
overflow and uncaught page-error checks passed. All four full-page screenshots
were visually inspected; they are in
`test-results/investment-areas-live-inve-1161e-y-local-evidence-on-signals-chromium/`.
Focused TypeScript, ESLint and backend-runner Ruff checks passed. Config inspection
confirmed unchanged default 8000/8080 URLs. A separate opt-out execution on the
alternate ports reported `1 skipped` with no public downloads. Both runs' servers exited; the
unrelated existing PID 76819 on port 8000 was not stopped or reused.

## CI And Artifacts

The browser workflow is `.github/workflows/e2e.yml`; consult that file for its
current triggers and runtime versions. It installs backend/frontend dependencies
and Chromium, then runs the repository E2E command. The config enables the
GitHub and HTML reporters in CI, with a trace on first retry and a screenshot on
failure. HTML reports are written to `playwright-report/` and per-test outputs
to `test-results/` by default.

## Layout

```text
e2e/
  backend.py                  # migrated temporary SQLite backend
  playwright.config.ts        # owns both servers; Chromium project
  tests/
    helpers.ts                # isolated registration and sign-out helpers
    auth.spec.ts               # registration/login/logout/bad password
    deal.spec.ts               # create a deal through the modal
    dashboard-activity.spec.ts # browser-only activity fixture, desktop/mobile
    measured-inventory.spec.ts # real organization-scoped inventory
    evaluations.spec.ts        # real synthetic replay and comparison journey
```
