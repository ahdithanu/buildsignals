# End-to-end tests (Playwright)

Browser-level tests covering the critical user journeys: register → land on
the dashboard, log out / log back in, bad-password rejection, and creating a
deal through the modal.

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

- Node 18+
- Python backend deps installed (the config boots the API itself)

## Running

```bash
# One-time: install the browser binary.
npm run e2e:install

# Run everything. The config boots BOTH servers automatically:
#   backend  — FastAPI on :8000 (fresh migrated SQLite DB, rate limits raised)
#   frontend — Vite dev server on :8080
npm run e2e

# Headed / debug:
npx playwright test -c e2e/playwright.config.ts --headed
npx playwright test -c e2e/playwright.config.ts --debug
```

The backend boots against a throwaway database in a temporary directory
and raises the auth rate limits so repeated register/login from one IP isn't
429'd — the same gotcha documented in `loadtest/README.md`.

## CI

Workflow lives at `.github/workflows/e2e.yml`. It's **manual-trigger only**
(`workflow_dispatch`) right now — run it from the Actions tab. Once the specs
pass on a real run, uncomment the `pull_request` trigger in that file to gate
PRs on them.

It's kept separate from `ci.yml` on purpose: E2E is slow (two servers + a real
browser) and shouldn't block every push. The job does setup-node@20 +
setup-python@3.11, installs both dependency trees, `npm run e2e:install` for
the browser, then `npm run e2e` (the config's `webServer` boots both servers),
and uploads `playwright-report/` as an artifact.

First-run note: the artifact path assumes the HTML report lands at repo-root
`playwright-report/`. If Playwright writes it elsewhere (e.g. under `e2e/`),
fix the `path:` in the upload step — a one-line change the first run surfaces.

## Layout

```
e2e/
  playwright.config.ts   # boots both servers, chromium project
  tests/
    helpers.ts           # registerAndLogin(), uniqueEmail(), PASSWORD
    auth.spec.ts         # register / login / logout / bad-password
    deal.spec.ts         # create a deal via the AddDealModal
```
