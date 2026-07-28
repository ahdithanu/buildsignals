# Deploy runbook — AWS

Deploying DealSignal on AWS. The app is three parts:

- **API** — the FastAPI container (this repo's `Dockerfile`) on **App Runner**
- **Frontend** — the static Vite build on **S3 + CloudFront**
- **Data** — **RDS** Postgres + **Redis** (ElastiCache, or Upstash)

App Runner is the closest AWS analog to Render — "point it at a container image,
it builds/scales/TLS-terminates." Use **ECS Fargate** instead if you outgrow it
(finer networking/scheduling control); the same image and steps apply.

> ⚠️ Before real users: the frontend still needs the Node 18+ validation pass
> in [../../VALIDATION.md](../../VALIDATION.md). This runbook gets the
> infrastructure live; that gate is separate.

---

## Architecture & two tiers

```
 users ──► CloudFront ──► S3 (static React)         VITE_API_BASE_URL baked at build
       └─► App Runner ──► RDS Postgres              (FastAPI container)
                     └──► Redis (ElastiCache/Upstash)
```

Two ways to wire the data layer — pick based on how much VPC plumbing you want:

| | **Pilot (simplest)** | **Hardened** |
|---|---|---|
| Postgres | RDS **publicly accessible**, security group locked to App Runner + your IP | RDS **private** in a VPC |
| Redis | **Upstash** (public, TLS, token — no VPC) | **ElastiCache** private in VPC |
| App Runner → data | over public TLS endpoints | via an **App Runner VPC connector** |
| Migrations | `docker run … migrate` from your machine/CI | one-off **ECS Fargate task** in-VPC |

The pilot tier avoids VPC connectors entirely and is genuinely fine to start.
The rest of this doc notes where the two diverge.

---

## 0. Prerequisites

- AWS account + `aws` CLI configured; Docker installed locally.
- A domain (optional) for CloudFront + App Runner custom domains.
- Decide a region (examples use `us-east-1`).

---

## 1. Postgres (RDS)

Create a PostgreSQL 16 instance (`db.t4g.micro` is fine to start).

**Critical — the app must connect as a NON-superuser role.** Postgres
superusers *silently bypass* row-level security even under FORCE RLS (this is
how migration 003 enforces tenant isolation). RDS's master user is **not** a
superuser, which is correct — but do **not** hand the app the RDS master
credentials with elevated grants. Create a dedicated app role:

```sql
-- as the RDS master user, once:
CREATE ROLE dealsignal LOGIN PASSWORD '<strong-password>';
GRANT ALL ON SCHEMA public TO dealsignal;   -- it owns/creates the tables
-- (the app role runs migrations, so it owns the tables → FORCE RLS applies to it)
```

Verify after connecting as the app role:
```sql
SELECT rolsuper FROM pg_roles WHERE rolname = current_user;   -- must be false
```
If that's `true`, RLS provides **zero** cross-tenant protection with no error.

`DATABASE_URL` = `postgresql://dealsignal:<pw>@<rds-endpoint>:5432/dealsignal`
(the app auto-rewrites a `postgres://` prefix).

---

## 2. Redis

- **Upstash (recommended to start):** create a Redis DB, copy the `rediss://`
  URL → `REDIS_URL`. Public + TLS + token; no VPC needed.
- **ElastiCache:** create a Redis (Valkey) cluster in your VPC; App Runner
  reaches it only via a VPC connector (§5).

Without `REDIS_URL` the rate limiter falls back to per-instance counting, so
the configured limits become N× under multiple App Runner instances. Set it.

---

## 3. Build & push the image (ECR)

```bash
AWS_ACCOUNT=<id>; REGION=us-east-1; REPO=dealsignal-api
aws ecr create-repository --repository-name $REPO --region $REGION
aws ecr get-login-password --region $REGION \
  | docker login --username AWS --password-stdin $AWS_ACCOUNT.dkr.ecr.$REGION.amazonaws.com

docker build -t $REPO .
docker tag  $REPO:latest $AWS_ACCOUNT.dkr.ecr.$REGION.amazonaws.com/$REPO:latest
docker push $AWS_ACCOUNT.dkr.ecr.$REGION.amazonaws.com/$REPO:latest
```

The image (`Dockerfile`) runs as non-root, bundles `alembic/`, and its
entrypoint takes `serve` (default) or `migrate`.

---

## 4. Run migrations (one-off, before serving traffic)

Migrations must run **once per deploy**, not on every instance (that races).
The image supports it via the `migrate` command:

- **Pilot tier** (RDS reachable): run it anywhere with DB access —
  ```bash
  docker run --rm -e DATABASE_URL=... -e SECRET_KEY=... -e ENVIRONMENT=production \
    $AWS_ACCOUNT.dkr.ecr.$REGION.amazonaws.com/$REPO:latest migrate
  ```
- **Hardened tier** (RDS private): run the same image as a **one-off ECS
  Fargate task** in the RDS VPC with command override `migrate`.

Wire this as a step in your deploy pipeline *before* App Runner picks up the
new image. (App Runner has no pre-deploy hook — this replaces Render's
`preDeployCommand`.)

---

## 5. API service (App Runner)

Create an App Runner service from the ECR image:

- **Port:** `8000` (the container honors `$PORT`; App Runner injects it).
- **Health check:** HTTP, path **`/health`**.
- **Auto-deploy:** on new ECR push (optional).
- **Environment variables** — set these (use **Secrets Manager**/SSM for the
  secret ones; App Runner can reference them):

  | Var | Value |
  |---|---|
  | `ENVIRONMENT` | `production` (turns on fail-fast config guards) |
  | `SECRET_KEY` | strong random ≥32 chars (Secrets Manager) |
  | `DATABASE_URL` | from §1 (Secrets Manager) |
  | `REDIS_URL` | from §2 (Secrets Manager) |
  | `CORS_ALLOWED_ORIGINS` | the CloudFront URL — no `*` |
  | `APP_BASE_URL` | the CloudFront URL (password-reset links) |
  | `REFRESH_COOKIE_SECURE` | `true` |
  | `METRICS_TOKEN` | random (protects `/metrics`) |
  | `RESEND_API_KEY` / `SENTRY_DSN` | optional |

  Do **not** set `ALLOW_ANONYMOUS` — production forces it false and refuses to
  boot if `true`.

- **VPC connector (hardened tier only):** if RDS/ElastiCache are private,
  attach an App Runner VPC connector in their subnets, and open the DB/Redis
  security groups to the connector's SG. (Skip entirely on the pilot tier.)

App Runner builds → waits for `/health` → cuts traffic over.

---

## 6. Frontend (S3 + CloudFront)

Build with the API URL baked in (Vite embeds `VITE_*` at build time):

```bash
VITE_API_BASE_URL=https://<app-runner-url> \
VITE_SENTRY_DSN=<optional> \
npm ci && npm run build            # emits dist/

aws s3 sync dist/ s3://<your-bucket>/ --delete
aws cloudfront create-invalidation --distribution-id <id> --paths '/*'
```

- **SPA routing:** set the CloudFront custom error response `403/404 → /index.html`
  (200), so client-side routes resolve (equivalent to Render's SPA rewrite).
- **Security headers (audit H-4):** `render.yaml`'s headers do NOT apply here.
  Attach a CloudFront **response-headers policy** with:
  - `Strict-Transport-Security: max-age=31536000; includeSubDomains`
  - `X-Frame-Options: DENY` · `X-Content-Type-Options: nosniff`
  - `Referrer-Policy: no-referrer` (also stops the reset `?token=` Referer leak)
  - `Permissions-Policy: camera=(), microphone=(), geolocation=()`
  - Content-Security-Policy — only after a build test (see VALIDATION.md §4);
    a wrong CSP white-screens the app.

---

## 7. Smoke test

```bash
API=https://<app-runner-url>
curl -sf $API/health | jq .
curl -sf $API/health/deep | jq .          # {"status":"ok","db":"ok"} — proves RDS wiring
curl -s -o /dev/null -w '%{http_code}\n' $API/metrics    # 401 (token required)
# first admin:
curl -sf -X POST $API/v1/auth/register -H 'Content-Type: application/json' \
  -d '{"email":"you@co.com","password":"<real>","full_name":"You","organization_name":"Your Co"}' | jq .role
```
Then load the CloudFront URL, log in, confirm the dashboard loads. If requests
go to `localhost`, `VITE_API_BASE_URL` wasn't set at build time — rebuild.

---

## 8. Post-deploy checklist

- [ ] App role's `rolsuper` is **false** (§1) — RLS is real.
- [ ] `/health/deep` green (DB reachable); `/metrics` 401 without the token.
- [ ] CloudFront response-headers policy attached (§6); verify with
      `curl -sI https://<cloudfront-url>/`.
- [ ] `CORS_ALLOWED_ORIGINS` / `APP_BASE_URL` / `VITE_API_BASE_URL` point at the
      real (custom-domain) URLs.
- [ ] Migrations run as a one-off in the deploy pipeline, never on the web
      service (§4).
- [ ] On-call / status-page TODOs filled in
      ([incident-response.md](incident-response.md)).

---

## Rough cost (pilot, us-east-1)

App Runner (0.25 vCPU/0.5 GB, scales to a floor) ~\$5–25/mo · RDS
`db.t4g.micro` ~\$13/mo · Upstash free tier · S3+CloudFront cents–low
dollars. Ballpark **~\$25–50/mo** to start; scales with traffic.

## CI/CD

The routine loop mirrors [deploy.md](deploy.md): build+push image to ECR →
run `migrate` (one-off) → App Runner picks up the new image. A GitHub Actions
workflow can do all three; the migration step needs network access to RDS
(public-with-SG on the pilot tier, or a VPC-attached runner/ECS task on the
hardened tier).
