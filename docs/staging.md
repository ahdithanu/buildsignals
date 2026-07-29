# Staging environment

Guide for standing up a non-production Render stack (enterprise checklist G5–G6).

---

## Purpose

- Validate migrations and deploys before production.
- Run E2E and manual QA against a persistent URL.
- Test CSP, CORS, and cookie settings without pilot-user impact.

---

## Setup

1. **Duplicate the blueprint** in Render with a new name, e.g. `dealsignal-staging`.
2. Override env vars:

   | Variable | Staging value |
   |----------|---------------|
   | `ENVIRONMENT` | `staging` |
   | `CORS_ALLOWED_ORIGINS` | Staging frontend URL |
   | `APP_BASE_URL` | Staging frontend URL |
   | `VITE_API_BASE_URL` | Staging API URL (frontend build) |
   | `VITE_SENTRY_ENVIRONMENT` | `staging` |

3. Use **separate** Postgres and Redis instances — never point staging at prod data.
4. Seed with synthetic data only:

   ```bash
   render shell -s dealsignal-api-staging
   python seed.py
   ```

5. Run smoke test:

   ```bash
   BASE=https://dealsignal-api-staging.onrender.com ./scripts/smoke-test.sh
   ```

---

## Data policy (G6)

- No production PII, customer exports, or real email addresses.
- Use `@example.com` or a mail sink for password-reset testing.
- Refresh staging from seed script quarterly; do not restore prod backups into staging
  without anonymization.

---

## CI integration (optional)

Add a `workflow_dispatch` deploy job that targets staging after `main` merge,
or require manual promote from staging → production via Render dashboard.

---

## Cost

Mirror production plan tiers at minimum `starter` for API + Postgres so behavior
matches prod (no free-tier sleep, valid Postgres retention).
