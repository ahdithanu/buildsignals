# End-to-end tests (Playwright)

Browser-level critical journeys cover registration, login/logout, deal creation,
dashboard activity, organization-scoped ingestion inventory, acquisition
screening, and AI evaluations.

## Verification status

### Keyboard Acquisition Journeys (November 12, 2026)

`tests/keyboard-accessibility.spec.ts` exercises Inbox preview and Dashboard Top
Opportunities at 1440x1000 and 390x844 against a newly migrated disposable API.
All deals are explicitly synthetic. Setup/scoring requests are localhost-only,
disable redirects and require deterministic scoring. Browser external HTTP and
WebSocket requests are blocked, service workers disabled, and traces/videos off.
The existing SF opt-in also activates the backend external-socket guard.

The four journeys verify bounded real Tab navigation; Enter/Space activation;
visible nontransparent, positive-size focus rings; modal focus containment;
named form/search/filter controls; contained, unobscured option menus; Escape
returning focus to each trigger; menu/dialog reopening and form reset; and exact
saved-deal navigation. Two real defects were reproduced before the fixes: null
financials crashed preview, and independently scoped Radix portals interfered
with focus/Escape. Shared default body-portal behavior remains unchanged for
callers that do not opt into the dialog container. No dependency upgrade.

After confirming both default ports are free:

```sh
env -u DEMO_TEST_SNAPSHOT_DIR OPENROUTER_API_KEY= SCORING_MODE=deterministic \
  RUN_SF_MAP_E2E=1 RUN_LIVE_INVESTMENT_AREAS=1 \
  E2E_API_PORT=8000 E2E_WEB_PORT=8080 PYTHON=/path/to/project/.venv/bin/python \
  npm run e2e -- --workers=1 --retries=0 --trace=off
```

Frozen local result on Node22.23.5: **26 passed**, zero skipped/retries, including
all four new cases. `npm test`: **436 passed**; typecheck/build/lint also passed.
Existing lint/build warnings remain. Screenshots were inspected; per-run outputs
are ignored local artifacts, not committed data. This uses the default synthetic
demo fixture, not an acquisition/coverage claim for the 2,049-row historical demo.
No full axe/WCAG audit, screen-reader or production acceptance is claimed. The
current header has no notification bell; that historical checklist item is not
presented as a tested control.

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

## Reference Investment Areas (Opt-In)

`tests/investment-areas.spec.ts` exercises `InvestmentAreaPanel` mounted on
`/signals` at 1440x1000 and 390x844. It registers a fresh organization using the
real UI and leaves its local evidence inventory empty. It exercises the real
local API with the bundled, verified annual reference artifact. No private
inventory is seeded, no API responses are mocked, and no production database is
used. Use ports 8001/8081 for this acceptance run as shown below.

The legacy flag `RUN_LIVE_INVESTMENT_AREAS=1` remains an explicit opt-in to
browser/API acceptance, **not** permission to download live source data. The
backend loads its fixed release reference from `app/data`; no source acquisition
or external downloads occur during this test. Artifact generation and validation
belong to the parent release process and must finish before running the test.
Do not fetch replacement inputs or fall back to live government services when
an artifact is absent or invalid. The endpoint must return 200 in reference
mode; a 503 fails acceptance honestly rather than skipping it.

All browser HTTP requests outside the selected local web/API origins are blocked.
Known optional Google Fonts CSS and Vercel Analytics debug-script requests are
recorded and aborted without downloading them; source fetches, other unexpected
external attempts and browser downloads fail the test. This is browser-network
enforcement, not inspection of backend outbound sockets; the
fixed-artifact loader and its offline tests establish the server-side no-fetch
contract. Automatic test retries remain disabled. Without the legacy opt-in flag,
ordinary CI skips this acceptance journey.

```bash
RUN_LIVE_INVESTMENT_AREAS=1 \
E2E_API_PORT=8001 E2E_WEB_PORT=8081 \
PYTHON=/Users/ahdithebomb/Desktop/DealSignal/.venv/bin/python \
OPENROUTER_API_KEY= \
npx playwright test -c e2e/playwright.config.ts investment-areas.spec.ts
```

Assertions cover `input_mode: release_reference`; six customer-safe provenance
entries containing only `label: Public records`, period and capture timestamp;
Annual reference/captured-date presentation; newer-release caveats; absence of
raw source URLs, per-source hashes and ingestion keys in the customer API/DOM;
research/investment-quality limitations; Ocala's numeric research score; Tampa's
unavailable aligned rank but observed population/migration context; honest zero
local evidence; document/main/panel horizontal overflow; and uncaught browser
page errors. The opaque snapshot ID remains in the API for identity comparison,
but is not displayed as a source hash. Nonempty local-source entries must use
UUID `id` and the generic name `Public local records`; this empty-workspace test
does not create records to exercise that nonempty branch.

Four full-page screenshots and four customer-safe response receipts are written
through `testInfo.outputPath()` under `test-results/`:
`investment-areas-{ocala,tampa}-{1440,390}.{png,json}`. Neither snapshot ID nor
cohort count is hardcoded. Both metros and viewports must share the same reference
identity and provenance. `investment-areas-browser-checks.json` records the new
organization's `is_internal_operator: false`, page errors, download/source-fetch
attempts and blocked optional assets, without storing auth tokens or user data.

This qualifies the local browser/API/reference integration, not investment
performance, newer-release freshness, complete metro evidence, production
activation, or PostgreSQL RLS.

Verification on 2026-11-10: the final reference-mode Chromium run passed
(`1 passed`, 2.6s test / 8.1s total), using fresh disposable SQLite and ports
8001/8081. All four desktop/mobile metro states passed API and UI assertions;
all four full-page screenshots were visually inspected. Receipts and screenshots
are in `test-results/investment-areas-release-r-1c8d8-y-local-evidence-on-signals-chromium/`.

Observed reference: **360 eligible metros**, capture
`2026-11-10T19:43:58.986728+00:00`, snapshot
`523fea1590d2bd056ec511f0e679e5c1e738a7303f26335aeadbfc88fc0bdd98`.
Read-only local artifact SHA-256 matched
`27d693e85f5af00a94936b6cd2e7620a7957177578c3134360c824f86425afb3`.
Ocala displayed **0.251 / 1**; Tampa displayed an unavailable aligned score with
population growth **0.398%** and migration **4.936 per 1,000**. Both metros
showed zero local records/geocoded records. `/auth/me` confirmed the new
user was not a superuser and `is_internal_operator` was **false**.

There were zero uncaught page errors, source/unexpected external request attempts,
or browser downloads, with no raw source URLs/hashes in the customer contract.
Three optional font CSS attempts and three optional analytics-script attempts
were all blocked before external download, as recorded in the browser-checks
receipt. Initial attempts exposed a test-only SVG namespace false positive and
started before the concurrent auth flag landed; those are resolved, not skipped.
Focused TypeScript, ESLint and whitespace checks passed. Both test servers exited;
no production writes or unrelated-server shutdowns occurred. The earlier
network-fetch receipt is superseded by this local reference-mode acceptance;
neither receipt alone establishes deployed App Runner/frontend acceptance.

## Internal Operations (Synthetic)

`tests/internal-operations.spec.ts` is a separate browser journey for the internal
operations boundary. The disposable backend replaces (never appends to) any
inherited `INTERNAL_OPERATIONS_USER_IDS` with this one synthetic operator user
ID before importing the application:

- User: `11111111-1111-4111-8111-111111111111`
- Organization: `22222222-2222-4222-8222-222222222222`
- Email/password: `synthetic-operator@example.com` / `E2eOperatorOnly42!`
- Source: `33333333-3333-4333-8333-333333333333`, named
  `SYNTHETIC E2E source fixture - no ingestion`

These are deliberately public **test-only credentials**, not production
credentials. The user is an active admin in its isolated synthetic organization,
not a superuser. The single source descriptor is disabled and unscheduled, has
no inventory records or ingestion runs, and points at a reserved `.invalid`
address. Seeding inserts only local fixture metadata; the test never runs a
canary, ingestion job, activation, or source download. It checks the operator's
run list stays empty. All external browser HTTP requests are aborted, including
fonts, analytics and map tiles.

```bash
RUN_LIVE_INVESTMENT_AREAS=1 \
E2E_API_PORT=8001 E2E_WEB_PORT=8081 \
PYTHON=/Users/ahdithebomb/Desktop/DealSignal/.venv/bin/python \
OPENROUTER_API_KEY= \
npx playwright test -c e2e/playwright.config.ts \
  internal-operations.spec.ts investment-areas.spec.ts
```

The three operations tests cover an ordinary newly registered customer admin
(`is_internal_operator: false`), the synthetic allowlisted admin (`true`), and a
read-only demo (`false`). Customer and demo tokens receive 403 from direct
operations read APIs; the operator receives 200 and sees its one fixture source.
The ordinary customer still reads narrow source options, zero inventory counts,
national parcel coverage, map signals and map-readiness diagnostics. Direct
customer `/source-health` navigation redirects safely to `/`, while the demo's
full document reload returns to sign-in because demo credentials intentionally
have no refresh cookie. Re-entering demo uses the real login-screen demo action.

At 1024, 1440 and 390px, the tests check document/main/header overflow and header
control bounds/overlaps, and capture screenshots plus numeric layout receipts.
Desktop operators use the Operations navigation link; mobile operators use the
Account menu's Operations entry. Customer/demo navigation must not expose those
controls. Customer map diagnostics link back to dashboard coverage rather than
the internal console. Running the investment-reference spec alongside these
tests verifies that the new allowlist fixture does not grant ordinary fresh
workspaces operator access. Each invocation still uses a newly migrated
temporary SQLite database; default ports remain 8000/8080 unless overridden.

This is synthetic local authorization/layout evidence, **not production access,
production tenant-isolation acceptance or measured live source coverage**.
Initial combined run: customer, synthetic operator and investment-reference
tests passed; the demo test incorrectly expected a session to survive a full
reload. Its expectation now matches the intentional no-refresh-cookie demo
contract, but has not yet been rerun. Final combined acceptance is pending the
mobile Operations entry, silent-refresh flag/cache revocation and customer
national-coverage sanitization freeze. No test servers remain running.

## SF Derived Map (Opt-In, Synthetic)

`tests/sf-derived-map.spec.ts` uses the real login UI, local API and migrated
temporary SQLite database. It is skipped unless `RUN_SF_MAP_E2E=1`. The backend
forces `SF_DERIVED_LOCATIONS_ENABLED=false` otherwise, regardless of an inherited
flag, and creates no SF fixture. With the opt-in, it enables the flag only in
the disposable backend and adds a separate, non-operator viewer and workspace:

- User: `44444444-4444-4444-8444-444444444444`
- Organization: `55555555-5555-4555-8555-555555555555`
- Email/password: `synthetic-sf-viewer@example.com` / `E2eSfViewerOnly42!`
- Permit: `88888888-8888-4888-8888-888888888888`

These are deliberately public **test-only credentials**. Existing operator
allowlisting, its one disabled source/empty inventory and the historical demo
fixture are unchanged. The SF source uses the reviewed canonical key/URL so the
real eligibility predicate is exercised, but is manual and unscheduled. Its
single completed manual run, raw record and permit are synthetic fixture rows,
not evidence of acquisition or an actual ingestion execution. `save_match`
validates a constructed synthetic Census-shaped response locally and writes one
`PermitGeocode`; no provider request is made. The address and coordinates are
test inputs, not a verified filing or geocoding observation.

The backend explicitly clears `OPENROUTER_API_KEY` along with existing service
credentials. In this opt-in mode, a process-local Python audit hook denies
external DNS/socket connections. The browser aborts every HTTP request outside
the selected local web/API origins. Optional fonts, analytics and map tiles are
counted and blocked; unexpected external hosts and downloads fail acceptance.
No API responses or tiles are mocked. With tiles blocked, acceptance checks the
rendered amber Leaflet SVG marker and its bounds, not a downloaded basemap.

The actual application route is `/map?state=CA`; `/acquisition-map/signals` and
`/acquisition-map/readiness` are its API paths. At 1440x1000 and 390x844, the spec
checks the estimated-location label, marker selection, internal evidence link,
readiness's zero native/one derived count, honest absent parcels/searches,
horizontal overflow and unchanged native permit coordinates. Public-record
evidence URLs/attribution remain permitted; geocoder URLs, raw match data,
address/response hashes and benchmark metadata must not reach the map API/DOM.
A second test checks anonymous denial, cross-tenant 404/empty map results,
unchanged operator fixture counts and the existing demo map gate.

Choose **two free ports** before running; do not stop unrelated services or reuse
an existing backend. For example, after confirming 8103/8183 are free:

```bash
RUN_SF_MAP_E2E=1 E2E_API_PORT=8103 E2E_WEB_PORT=8183 \
PYTHON=/Users/ahdithebomb/Desktop/DealSignal/.venv/bin/python \
OPENROUTER_API_KEY= \
npx playwright test -c e2e/playwright.config.ts sf-derived-map.spec.ts
```

The spec disables retries. `testInfo.outputPath()` writes desktop/mobile map and
marker screenshots, aggregate layout/readiness receipts and browser/boundary
check receipts under `test-results/`. It never saves auth responses, tokens,
raw permit/provider responses or provider URL query strings. This is local
synthetic acceptance, not live SF coverage, provider access/accuracy, PostgreSQL
RLS or production activation. Browser execution and screenshot inspection are
pending the parent's free-port run; static checks are not browser acceptance.

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
    investment-areas.spec.ts   # release-reference research, desktop/mobile
    internal-operations.spec.ts # synthetic operator/customer/demo boundaries
    sf-derived-map.spec.ts     # opt-in synthetic SF estimates, desktop/mobile
```
