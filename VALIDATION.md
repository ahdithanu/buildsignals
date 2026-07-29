# Validation checklist — frontend release gate

Automated gates (§1) are **green** on Node 20 as of the enterprise-readiness
PR. Manual browser QA (§2) remains the release sign-off for accessibility
and UX audit fixes.

Backend (580 pytest, ruff, real-Postgres migrations) and infra CI are validated
separately — not repeated here.

---

## 0. Prerequisites

- Node **18+** (`node --version`), npm 9+.
- Python 3.11 + the backend running locally for manual QA (`uvicorn app.main:app --port 8000`).

---

## 1. Automated gates — must all pass

Run from the repo root.

```bash
npm ci                 # lock file is current — do not skip
npm run lint           # eslint — 0 errors required
npm run typecheck      # tsc --noEmit
npm run test           # vitest — 59 tests across 27 files
npm run build          # vite build
```

Then browser E2E (boots both servers):

```bash
npm run e2e:install    # one-time: chromium binary
npm run e2e            # playwright — auth + deal flows (4 specs)
```

CI runs the same gates via `.github/workflows/frontend.yml` and `e2e.yml`.

---

## 2. Per-fix manual verification (browser)

Log in, then confirm each audit fix behaves. Grouped by severity.

### CRITICAL — keyboard access (CR-1)
- On **Deal Inbox** and **Dashboard → Top Opportunities**, `Tab` to a table
  row: it should show a **visible focus ring**, and **Enter/Space** should
  open/preview the deal.
- Quick automated cross-check: run **axe DevTools** on Deal Inbox.

### HIGH — data integrity
- **H-1 enrichment:** Network tab shows `POST /v1/deals/:id/enrich` with
  `Authorization: Bearer`. Toast reflects actual outcome.
- **H-3 recalculate (Underwriting):** slider → Recalculate uses on-screen values;
  tab switch must not wipe unsaved edits.
- **H-2 pipeline:** drag rollback on failure; cross-tab sync after refetch.

### HIGH — accessibility labels (H-5, H-7)
- Screen reader / axe: Add Deal modal dropdowns, header search, notification
  bell, mobile search, Deal Inbox filters all have accessible names.

### MEDIUM — reliability
- **L-1 double-submit:** Add Deal button disables during submit; failed create
  keeps modal open.
- **M-2 memo regenerate:** button disables; failure restores prior text.
- **M-7 persistent 401:** refresh success + retried 401 → redirect to login.

### Visual
- **M-12:** "closed" status shows green badge.
- Product name reads **"DealSignal"** everywhere; sidebar shows real user.

---

## 3. Post-deploy checks (after Render deploy)

```bash
BASE=https://YOUR-API.onrender.com \
  FRONTEND=https://YOUR-FRONTEND.onrender.com \
  ./scripts/smoke-test.sh
```

- **H-4 security headers:** smoke script checks frontend headers when `FRONTEND` is set.
- **CSP:** open browser console — zero Content-Security-Policy violations.
- **M-3 Sentry token scrub:** `/reset-password?token=abc` → Sentry shows `token=[redacted]`.

---

## 4. Completed infrastructure switches

These were pending when this doc was authored; they are now done:

1. **`npm ci`** in `.github/workflows/frontend.yml` and `e2e.yml`.
2. **CSP enabled** in `render.yaml` (verify after first deploy).
3. **Frontend + E2E CI** gated on PRs and `main` push.

Track overall readiness in [docs/enterprise_readiness.md](docs/enterprise_readiness.md).

---

## What to report back

If §1 fails in CI, paste the exact error. For §2, note which checklist item
failed and the browser/steps to reproduce.
