# Secrets management

How DealSignal handles credentials. Read this before adding a new
integration or when a secret needs rotating.

## Inventory

Every real secret the app currently uses. Config knobs (limits,
sample rates, cookie names) are not listed here — those live in
`.env.example`.

| Secret | Purpose | Where it lives (prod) | Rotates when |
|---|---|---|---|
| `SECRET_KEY` | JWT signing (access + refresh tokens). | Render dashboard env var on `dealsignal-api`. | On suspected compromise, or every 90 days. Rotation logs everyone out — see "Rotation" below. |
| `DATABASE_URL` | Postgres connection incl. password. | Render dashboard, auto-injected from the linked Postgres instance. | On suspected compromise. Not on a schedule — the credential is machine-only and not human-known. |
| `SENTRY_DSN` | Sentry ingest token. Low-sensitivity — DSNs are per-project and can only send events, not read them. | Render dashboard env var. | If leaked externally (spam events); otherwise long-lived. |
| `RESEND_API_KEY` | Outbound email (password-reset). | Render dashboard env var. | On suspected compromise, or if a Resend account admin leaves. |

## Storage

- **Production / staging:** Render dashboard env vars on the affected
  service. Never in `render.yaml` — that file is version-controlled.
- **Local dev:** `.env` at the repo root. Gitignored (`.gitignore`
  covers `.env`). Use `.env.example` as the template.
- **CI:** GitHub Actions repo secrets. The CI job that runs pytest
  uses throwaway values (`ci-test-secret-key-not-for-production`) —
  no real prod credentials touch CI.
- **Nowhere else.** Not in Slack, not in tickets, not in docs, not in
  Notion. If you paste a credential somewhere ephemeral to unblock
  someone, rotate it right after.

## Guardrails already in place

- `app/config.py` refuses to boot the API in production (`ENVIRONMENT=production`)
  if:
  - `SECRET_KEY` equals the dev default.
  - `DATABASE_URL` is unset or SQLite.
  - `CORS_ALLOWED_ORIGINS` is empty or contains `*`.
  - `ALLOW_ANONYMOUS=true`.
  - `REFRESH_COOKIE_SAMESITE=none` without `REFRESH_COOKIE_SECURE=true`.
  These fail-fast checks turn "someone deployed with the dev key" from
  a silent security incident into a boot crashloop that the deploy
  process catches.
- `.env` is gitignored. `.env.example` uses obviously-fake placeholder
  values.

## Rotation

### `SECRET_KEY`
JWTs signed with the old key immediately become invalid — every active
session gets logged out and must re-authenticate. Expect a support
spike for a few minutes.

1. Generate a new value: `python -c 'import secrets; print(secrets.token_urlsafe(64))'`
2. Update the Render env var on `dealsignal-api`.
3. Trigger a redeploy of the API service so the new value takes effect
   on all workers.
4. Refresh cookies signed with the old key start returning 401 → the
   frontend's silent-refresh path fires → users are bounced to `/login`.
   No manual invalidation needed.

Rotation is only strictly required on a suspected compromise; a
90-day cadence is a good default posture.

### `DATABASE_URL`
Rotate at the Postgres layer, not the env var:

1. Render dashboard → the Postgres instance → *Reset Password*.
2. Render auto-updates the injected `DATABASE_URL` on linked services.
3. Redeploy `dealsignal-api` to pick up the new URL.

### `SENTRY_DSN`
Regenerate the client key in Sentry (`Settings → Client Keys (DSN)`)
and swap the env var on Render. Old key stops accepting events
immediately.

### `RESEND_API_KEY`
Sign into Resend → *API Keys* → create a new key → update Render env
→ redeploy → delete the old key in Resend. Two-step so no window
where password-reset emails fail.

## Access control

- **Render dashboard env vars** — anyone with owner/admin access on
  the DealSignal Render workspace can view them in plaintext. Keep
  that list to the current on-call engineers. When someone leaves the
  team, remove them from the Render workspace and rotate `SECRET_KEY`
  and `RESEND_API_KEY` (they had visibility, even if unused).
- **GitHub Actions secrets** — visible to anyone with `admin` on the
  repo. Only `GITHUB_TOKEN` is used at run time; there are no
  long-lived prod credentials in the repo's secrets.
- **Local `.env` files** — live on individual laptops. Assume
  compromised on laptop loss and rotate accordingly.

## Local dev onboarding

New engineer, first day:

1. Clone the repo, `cp .env.example .env`.
2. Generate a dev `SECRET_KEY`: `python -c 'import secrets; print(secrets.token_urlsafe(32))'`
3. Leave `DATABASE_URL` unset → the app defaults to SQLite at
   `./dealsignal.db` (see `app/config.py`).
4. `SENTRY_DSN` and `RESEND_API_KEY` — leave unset for local. Sentry
   is skipped (SDK never imported). Password-reset emails print to
   stdout in dev — see `app/services/email_service.py`.
5. Do NOT ask for prod credentials on your first day. If you find
   yourself needing them, stop and check with the tech lead — the
   answer is almost always "spin up a staging DB / Sentry project
   instead."

## Leaked-secret playbook

If a credential is exposed — in a screenshot, a public commit, a
support ticket — assume it's compromised. Move fast:

1. **Rotate immediately** using the rotation steps above. Don't wait
   to confirm the leak was seen.
2. **Investigate the blast radius.** Grep git history:
   ```
   git log --all -S '<leaked-value>' -- .
   ```
   If it's in git history, the fix is not `git rm` — it's rotation
   plus optionally a history rewrite. Assume anything ever pushed to
   GitHub was read by scanners within minutes.
3. **Sentry:** check for events from unexpected environments in the
   ~2h window before the leak was noticed.
4. **DB:** check `pg_stat_activity` for unexpected clients. If
   `DATABASE_URL` leaked, review recent audit-log rows for anything
   the intruder might have modified.
5. **File an incident note** in `#dealsignal-incidents` even if the
   blast radius is empty. The paper trail is the point.

## What's not here (yet)

Explicit gaps to close as the org grows:

- **Secrets vault** (1Password Teams, Doppler, HashiCorp Vault). Right
  now Render dashboard is the source of truth; a vault becomes worth
  the setup cost once we have more than one prod env or more than
  ~5 secrets.
- **Pre-commit secret scanning** (`gitleaks`, `trufflehog`). Cheap to
  add — a GitHub Action on every PR that fails on high-entropy strings
  or known patterns (Stripe keys, AWS access keys, etc.).
- **Automatic rotation** for `SECRET_KEY`. Right now this is manual.
  Not urgent; the rotation is disruptive by design.
