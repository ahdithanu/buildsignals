# End-to-end tests (Playwright)

Browser-level tests covering the critical user journeys: register → land on
the dashboard, log out / log back in, bad-password rejection, and creating a
deal through the modal.

## ⚠️ Status: written but never executed

These specs were authored against the source (real element ids, button text,
and select option values read from `src/pages/` and `src/components/`) but
**have not been run against the app** — the machine they were written on had
Node 10, and Playwright needs Node 18+. They couldn't even be type-checked
locally.

**On the first real run, budget time to fix a selector or two.** The auth
spec is the most stable (fixed `#email` / `#password` / `#fullName` ids). The
deal spec is the most fragile — its Asset Type / Market fields are radix
`<Select>` components driven via `role="combobox"` + `role="option"`, which
are the likeliest to need adjustment.

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

The backend boots against a throwaway `e2e-test.db` (gitignored via `*.db`)
and raises the auth rate limits so repeated register/login from one IP isn't
429'd — the same gotcha documented in `loadtest/README.md`.

## CI

Not wired into a workflow yet — do that once the specs are confirmed green
locally. A `.github/workflows/e2e.yml` would:

1. `actions/setup-node@v4` (Node 20) + `actions/setup-python@v5` (3.11)
2. `pip install -r requirements.txt` and `npm ci`
3. `npm run e2e:install`
4. `npm run e2e` (the config's `webServer` handles booting both servers)
5. Upload `playwright-report/` as an artifact on failure

Keep it a separate workflow from `ci.yml` — E2E is slower and browser-based,
and you may not want it blocking every push.

## Layout

```
e2e/
  playwright.config.ts   # boots both servers, chromium project
  tests/
    helpers.ts           # registerAndLogin(), uniqueEmail(), PASSWORD
    auth.spec.ts         # register / login / logout / bad-password
    deal.spec.ts         # create a deal via the AddDealModal
```
