# Validation checklist — frontend changes pending a Node 18+ run

A large batch of frontend fixes (the security audit remediation + earlier UI
work) was authored in an environment with **Node 10**, so it could not be
built, type-checked, or run in a browser. Everything is structurally verified
(imports resolve, no dangling symbols, logic traced against the real backend
contracts) but **not runtime-validated**.

This doc is the handoff: run it on any **Node 18+** machine, confirm each
check, then flip the two follow-up switches at the bottom. The backend
(295 pytest, ruff, real-Postgres migrations) and infra are already validated
and are **not** part of this checklist.

---

## 0. Prerequisites

- Node **18+** (`node --version`), npm 9+.
- Python 3.11 + the backend running locally if you want to click through the
  app (`uvicorn app.main:app --port 8000`, SQLite by default).

---

## 1. Automated gates — must all pass

Run from the repo root.

```bash
npm install            # regenerates package-lock.json (currently stale — see §4)
npm run lint           # eslint — must be clean
npm run typecheck      # tsc --noEmit — catches type errors vite's swc build skips
npm run test           # vitest — the 6 unit suites
npm run build          # vite build — must compile with no errors
```

**Passing looks like:** all four exit 0. The most likely failures are TypeScript
errors in the files touched by the audit fixes — if any appear, paste them and
they're quick to fix (the changes are additive props / hooks / attributes).

Then the browser E2E (boots both servers itself):

```bash
npm run e2e:install    # one-time: chromium binary
npm run e2e            # playwright — login → dashboard → deal flows
```

**Passing looks like:** the specs go green. These were also authored blind
(see `e2e/README.md`) — expect to fix a selector or two on the first run.

---

## 2. Per-fix manual verification (browser)

Log in, then confirm each audit fix behaves. Grouped by severity.

### CRITICAL — keyboard access (CR-1)
- On **Deal Inbox** and **Dashboard → Top Opportunities**, `Tab` to a table
  row: it should show a **visible focus ring**, and **Enter/Space** should
  open/preview the deal. Before the fix, rows were unreachable by keyboard.
- Quick automated cross-check: run **axe DevTools** (or Lighthouse a11y) on
  Deal Inbox — the "interactive controls must be focusable" / "name-role-value"
  violations on the table rows should be gone.

### HIGH — data integrity
- **H-1 enrichment (Deal Inbox → "Run AI Enrichment"):** with the backend up,
  the Network tab should show `POST /v1/deals/:id/enrich` **with an
  `Authorization: Bearer` header** (not the old unauthenticated `/deals/...`).
  The toast must reflect reality — "complete", "partially complete", or
  "failed" — never "complete" when requests errored.
- **H-3 recalculate (Underwriting):** move a slider, click **Recalculate** —
  the outputs (DSCR/IRR/cash-on-cash) must reflect the **on-screen** value, not
  the last saved one. Then switch to another tab and back (window refocus): your
  unsaved slider edits must **not** be wiped.
- **H-2 pipeline (Pipeline):** drag a card to another column — it moves
  instantly. Force the move endpoint to fail (e.g. stop the backend) and drag:
  the card must **snap back** (rollback), not stay in the wrong column. Open the
  board in two tabs; a move in one should appear in the other after refetch.

### HIGH — accessibility labels (H-5, H-7)
- With a screen reader (VoiceOver: ⌘F5) or axe: the **Add Deal** modal's Asset
  Type / Market dropdowns announce their field names; the header search,
  notification bell, mobile search, and the Deal Inbox filters/close button all
  have accessible names.

### MEDIUM — reliability
- **L-1 double-submit (Add Deal modal):** the submit button disables and shows
  "Adding…" while in flight; a failed create keeps the modal **open with your
  input intact** (previously it closed and cleared).
- **M-2 memo regenerate (Memo Generator):** click "Regenerate section" — the
  button disables + spins; on failure the section restores its **prior text**
  (not a stuck "Regenerating…"). Rapid clicks don't interleave.
- **M-7 persistent 401 (hard to force):** if a refresh succeeds but the retried
  request still 401s, you should be bounced to login rather than left stuck.

### Visual
- **M-12:** a deal with status **"closed"** shows a green badge, not grey.
- Product name reads **"DealSignal"** everywhere (sidebar, Settings, memo
  footer); the sidebar footer shows the **real logged-in user**, not a
  hardcoded name.

---

## 3. Post-deploy checks (after it's on Render)

- **H-4 security headers:**
  ```bash
  curl -sI https://<frontend-url>/ | grep -iE 'strict-transport|x-frame|x-content-type|referrer-policy|permissions-policy'
  ```
  All five should be present.
- **M-3 Sentry token scrub** (needs a prod `VITE_SENTRY_DSN`): trigger a
  navigation to `/reset-password?token=abc123`, then check the Sentry event/
  transaction — the URL should show `token=[redacted]`, never the real token.

---

## 4. Flip these two switches once §1 is green

Both were worked around because they couldn't be validated blind:

1. **Restore `npm ci`.** `npm install` in §1 regenerates `package-lock.json`.
   Commit the refreshed lock, then change `npm install` back to `npm ci` in
   **`.github/workflows/frontend.yml`** and **`.github/workflows/e2e.yml`**
   (both have a comment marking the spot).
2. **Enable the CSP.** `render.yaml` ships the Content-Security-Policy as a
   commented block. After `npm run build && npm run preview`, load the app and
   confirm **zero CSP violations** in the console (adjust `connect-src` to your
   real API + Sentry origins), then uncomment it.

Also consider enabling the `frontend.yml` `pull_request` trigger (currently
`workflow_dispatch`-only) once it's confirmed green, so future frontend PRs are
gated.

---

## What to report back

If anything in §1 fails, paste the exact error — the fixes are small and I can
turn them around immediately. Once §1 + §2 pass, the audit's release blockers
are validated and the app is shippable to end-users (see the release
recommendation in the audit report).
