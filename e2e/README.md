# End-to-end tests (Playwright)

Browser-level critical journeys cover registration, login/logout, deal creation,
dashboard activity, organization-scoped ingestion inventory, and AI evaluations.

## Requirements

- Node 22 and npm dependencies installed (`npm ci`).
- Python backend dependencies installed from `requirements.txt`.
- Playwright Chromium installed (`npm run e2e:install`).
- Ports 8000 and 8080 available. Do not stop unrelated services to free them.

When another agent is updating dependencies in a shared checkout, wait for its
explicit ready signal before starting the app or running tests.

## Running

```bash
# All specs; the config starts and stops BOTH servers.
npm run e2e

# Evaluation dashboard only.
npm run e2e -- evaluations.spec.ts

# Select an installed Python interpreter if python3 is not suitable.
PYTHON=/path/to/python npm run e2e -- evaluations.spec.ts

# Interactive sessions, still using the isolated backend.
npx playwright test -c e2e/playwright.config.ts evaluations.spec.ts --headed
npx playwright test -c e2e/playwright.config.ts evaluations.spec.ts --debug
```

The repository config starts FastAPI on `127.0.0.1:8000` through `e2e/backend.py`
and Vite on port 8080. The backend creates a fresh SQLite database in a
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
