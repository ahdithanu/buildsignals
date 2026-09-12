# Browser workflow checks

These tests exercise the actual frontend and API using synthetic accounts and
disposable local data. They are engineering checks, not production certification.

## Requirements

- Node 20+
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

Set `PYTHON` when the Python runtime is not `python3`. Playwright refuses to
reuse existing servers on either test port; their database cannot be inferred
from a loopback URL. Do not point these tests at production or customer data.

`backend.py` creates a temporary SQLite database, applies the complete Alembic
chain, uses ephemeral signing/encryption keys, disables email and telemetry,
and removes its database after shutdown. It never accepts an inherited database
target or uses the application's sample-deal seed. Rate limits are raised only
inside that disposable process.

## Coverage

- Registration, logout/login and confirmed bad-password rejection.
- Creating a deal through the actual form.
- Empty tenant inventory, permit/parcel/planning filters and logout protection.
- Two-entity assessment authoring, source-version checks, event timestamp,
  independent review, publication, withdrawal, reload and revision pagination at
  390px, 768px and 1440px. Viewport and full-page captures are saved as artifacts.
- Authenticator enrollment, MFA-enforced sign-in and disable at the same widths.
  This spec disables traces/screenshots to avoid retaining even synthetic keys.
  It uses the backend's existing `pyotp` library as its test authenticator.

The assessment spec wraps `scripts/verify_assessment_workflow.cjs`. Its standalone
URL overrides accept only loopback addresses, but cannot prove an already-running
backend's database is disposable. Prefer the managed Playwright fixture above.

## Additional Gates

```sh
node e2e/auth-cookie-races/reproduce.mjs --require-safe
VITE_API_BASE_URL=https://buildsignals-api.onrender.com npm run build
node scripts/verify_browser_policy.cjs
```

The cookie harness owns its own temporary database and ephemeral loopback ports.
See its README for the exact protocol and browser limitations. The browser-policy
check serves the built app locally and intercepts the API with synthetic
responses. It verifies the strict trial CSP, the 180 KiB gzip login-script budget,
no overflow, and reload recovery after a failed page download. Non-local network
requests are blocked except for intercepted test responses. Passing it does not
turn the production report-only script policy into an enforced policy.

## CI

`.github/workflows/e2e.yml` runs on relevant pull requests and manual dispatch.
It installs Chromium, runs workflows and cookie checks, builds the frontend and
runs the browser-policy gate. HTML reports and policy captures are retained for
14 days. Local passing results do not prove that a hosted CI run executed; check
the actual pull-request run separately.

## Layout

```
e2e/
  playwright.config.ts   # boots both servers, chromium project
  backend.py             # disposable migrated database and ephemeral keys
  tests/
    helpers.ts           # registerAndLogin(), uniqueEmail(), PASSWORD
    auth.spec.ts         # register / login / logout / bad-password
    deal.spec.ts         # create a deal via the AddDealModal
    measured-inventory.spec.ts
    assessment-workflow.spec.ts
    authenticator.spec.ts
```
