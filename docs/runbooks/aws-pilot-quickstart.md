# AWS pilot deploy — quickstart

Locked-in decisions for the first production deploy. Follow in order.

| Decision | Value |
|----------|-------|
| Region | `us-east-1` |
| Tier | Pilot (public RDS + Upstash Redis) |
| Domain | AWS default URLs first (App Runner + CloudFront) |
| Secrets | AWS Secrets Manager |
| Email | Skip (`RESEND_API_KEY` unset — resets log only) |
| Sentry | Optional — set if you have projects |
| Ingestion org | `default-org` |
| Ingestion cron | GitHub Actions (`INGESTION_DATABASE_URL` after RDS) |

Full reference: [deploy-aws.md](deploy-aws.md).

---

## Step 1 — RDS Postgres

```bash
export AWS_REGION=us-east-1
export DB_ID=dealsignal-pilot
export DB_PASSWORD='<generate-strong-password>'
```

Create via AWS Console: **RDS → Create database → PostgreSQL 16 → db.t4g.micro → Public access: Yes**, or use CLI/your IaC.

After the instance is available, connect as master and create the app role:

```sql
CREATE DATABASE dealsignal;
CREATE ROLE dealsignal LOGIN PASSWORD '<same-or-different-strong-password>';
GRANT ALL ON SCHEMA public TO dealsignal;
-- After migrations (step 4), verify:
SELECT rolsuper FROM pg_roles WHERE rolname = current_user;  -- must be false as dealsignal
```

**Security group:** allow inbound **5432** from:
- Your IP (for migrate/ingest from laptop)
- App Runner (after created — add its egress or use 0.0.0.0/0 temporarily for pilot, tighten later)

Save:

```bash
export DATABASE_URL="postgresql://dealsignal:<password>@<rds-endpoint>:5432/dealsignal"
```

---

## Step 2 — Redis (Upstash)

1. [console.upstash.com](https://console.upstash.com) → Create database → region **us-east-1**
2. Copy the **`rediss://`** URL

```bash
export REDIS_URL="rediss://default:<token>@<host>:6379"
```

---

## Step 3 — Secrets

Generate keys:

```bash
export SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
export METRICS_TOKEN=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
echo "SECRET_KEY=$SECRET_KEY"
echo "METRICS_TOKEN=$METRICS_TOKEN"
```

Store in **Secrets Manager** (or save locally for App Runner env setup):
- `dealsignal/SECRET_KEY`
- `dealsignal/DATABASE_URL`
- `dealsignal/REDIS_URL`
- `dealsignal/METRICS_TOKEN`

---

## Step 4 — ECR + image

```bash
export AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
export AWS_REGION=us-east-1
export REPO=dealsignal-api

aws ecr create-repository --repository-name $REPO --region $AWS_REGION 2>/dev/null || true
aws ecr get-login-password --region $AWS_REGION \
  | docker login --username AWS --password-stdin $AWS_ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com

docker build -t $REPO .
docker tag $REPO:latest $AWS_ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com/$REPO:latest
docker push $AWS_ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com/$REPO:latest

export ECR_IMAGE=$AWS_ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com/$REPO:latest
```

---

## Step 5 — Migrations (one-off)

```bash
docker run --rm \
  -e DATABASE_URL="$DATABASE_URL" \
  -e SECRET_KEY="$SECRET_KEY" \
  -e ENVIRONMENT=production \
  -e CORS_ALLOWED_ORIGINS=https://placeholder.cloudfront.net \
  $ECR_IMAGE migrate
```

Use a placeholder CORS value for migrate-only; update after CloudFront URL is known.

---

## Step 6 — App Runner

Console: **App Runner → Create service → Container registry → ECR** → select `$REPO:latest`.

| Setting | Value |
|---------|-------|
| Port | `8000` |
| Health check | HTTP `/health` |
| `ENVIRONMENT` | `production` |
| `SECRET_KEY` | from Secrets Manager |
| `DATABASE_URL` | from Secrets Manager |
| `REDIS_URL` | from Secrets Manager |
| `REFRESH_COOKIE_SECURE` | `true` |
| `METRICS_TOKEN` | from Secrets Manager |
| `CORS_ALLOWED_ORIGINS` | set after step 7 (CloudFront URL) |
| `APP_BASE_URL` | same CloudFront URL |

Save the service URL:

```bash
export API_URL=https://<id>.us-east-1.awsapprunner.com
```

Update RDS SG if App Runner can't reach DB.

Smoke:

```bash
curl -sf $API_URL/health | jq .
curl -sf $API_URL/health/deep | jq .
```

Register first admin:

```bash
curl -sf -X POST $API_URL/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@company.com","password":"<strong>","full_name":"You","organization_name":"Your Co"}' | jq .
```

---

## Step 7 — Frontend (S3 + CloudFront)

```bash
export VITE_API_BASE_URL=$API_URL
npm ci && npm run build

aws s3 mb s3://dealsignal-pilot-frontend-$AWS_ACCOUNT --region $AWS_REGION
aws s3 sync dist/ s3://dealsignal-pilot-frontend-$AWS_ACCOUNT/ --delete
```

Create CloudFront distribution (S3 origin, default root `index.html`, SPA error pages 403/404 → `/index.html` 200).

Attach **response headers policy** (HSTS, X-Frame-Options, nosniff, Referrer-Policy, Permissions-Policy). CSP after build test — see [VALIDATION.md](../../VALIDATION.md).

```bash
export FRONTEND_URL=https://<cloudfront-id>.cloudfront.net
```

**Update App Runner env** (requires redeploy/restart):
- `CORS_ALLOWED_ORIGINS=$FRONTEND_URL`
- `APP_BASE_URL=$FRONTEND_URL`

Rebuild frontend if API URL changed.

---

## Step 8 — Smoke test

```bash
BASE=$API_URL FRONTEND=$FRONTEND_URL ./scripts/smoke-test.sh
```

Log in at `$FRONTEND_URL`, load `/deals`.

---

## Step 9 — Daily ingestion

**GitHub** → repo **Settings → Secrets → Actions**:

```
INGESTION_DATABASE_URL = <same DATABASE_URL as App Runner>
```

Ensure RDS SG allows GitHub-hosted runner IPs (pilot: often your IP + broad rule temporarily).

Manual first run:

```bash
docker run --rm \
  -e DATABASE_URL="$DATABASE_URL" \
  -e SECRET_KEY="$SECRET_KEY" \
  -e ENVIRONMENT=production \
  -e CORS_ALLOWED_ORIGINS="$FRONTEND_URL" \
  -e INGESTION_ORGANIZATION=default-org \
  $ECR_IMAGE ingest
```

Or: **Actions → ingestion-cron → Run workflow**.

Check **Ingestion Operations** in the app.

---

## Step 10 — Uptime (optional)

GitHub secret:

```
UPTIME_BASE_URL = <App Runner URL without trailing slash>
```

Workflow `.github/workflows/uptime.yml` probes `/health/deep` every 5 minutes.

---

## Pilot checklist

- [ ] RDS up, `dealsignal` role, `rolsuper = false`
- [ ] Upstash Redis URL set on App Runner
- [ ] ECR image pushed, migrate succeeded
- [ ] App Runner `/health/deep` green
- [ ] CloudFront loads app, login works
- [ ] CORS + `VITE_API_BASE_URL` aligned
- [ ] First `ingest` run completed
- [ ] `INGESTION_DATABASE_URL` secret set
- [ ] Manual QA ([VALIDATION.md](../../VALIDATION.md) §2) before external users

---

## When to upgrade off pilot tier

Move to **hardened** (private RDS, VPC connector, ECS ingest) when:
- External customers on multi-tenant data
- Compliance review requires no public database endpoint
- GitHub Actions can't reliably reach RDS for ingestion
