# Staging deploy — Render blueprint

One-time setup for a **non-production** stack. Uses [`render-staging.yaml`](../../render-staging.yaml)
— separate Postgres/Redis/API/frontend from production.

---

## 1. Create the staging project

1. [Render dashboard](https://dashboard.render.com) → **New** → **Blueprint**
2. Connect the `cre-deal-intelligence` GitHub repo
3. When prompted for the blueprint file, specify **`render-staging.yaml`**
   (not `render.yaml`)
4. Review resources:

   | Resource | Name |
   |----------|------|
   | Postgres | `dealsignal-db-staging` |
   | Redis | `dealsignal-redis-staging` |
   | API | `dealsignal-api-staging` |
   | Frontend | `dealsignal-frontend-staging` |

5. Click **Apply**

---

## 2. Set environment variables

Render assigns default URLs: `https://<service-name>.onrender.com`.

**API service (`dealsignal-api-staging`):**

| Variable | Value |
|----------|-------|
| `CORS_ALLOWED_ORIGINS` | `https://dealsignal-frontend-staging.onrender.com` |
| `APP_BASE_URL` | `https://dealsignal-frontend-staging.onrender.com` |
| `RESEND_API_KEY` | *(optional — leave blank to log emails)* |
| `SENTRY_DSN` | *(optional)* |

**Frontend service (`dealsignal-frontend-staging`):**

| Variable | Value |
|----------|-------|
| `VITE_API_BASE_URL` | `https://dealsignal-api-staging.onrender.com` |
| `VITE_SENTRY_DSN` | *(optional)* |

> `VITE_*` vars require a **rebuild** after changes, not just a restart.

Copy-paste reference: [`infra/staging.env.example`](../../infra/staging.env.example)

---

## 3. Wait for deploy

API pre-deploy runs `alembic upgrade head`. Both services must show **Live**.

---

## 4. Seed sample data

```bash
# Render dashboard → dealsignal-api-staging → Shell
python seed.py
```

Use synthetic data only — no production PII ([`docs/staging.md`](../staging.md)).

---

## 5. Verify

```bash
BASE=https://dealsignal-api-staging.onrender.com \
  FRONTEND=https://dealsignal-frontend-staging.onrender.com \
  ./scripts/smoke-test.sh
```

Open the staging frontend URL, log in with a seeded user, load `/deals`.

---

## 6. Wire CI (optional)

Point a separate uptime check at staging with a relaxed alert path (dev Slack
channel, not on-call). Do **not** reuse production `UPTIME_BASE_URL`.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Frontend calls localhost | Rebuild frontend after setting `VITE_API_BASE_URL` |
| CORS errors | Match `CORS_ALLOWED_ORIGINS` to exact frontend URL (no trailing slash) |
| API boot loop | Check Render logs for missing `CORS_ALLOWED_ORIGINS` in staging |
