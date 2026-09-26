# Infrastructure

Committed config for ops automation. These values are **not secrets** — they
point at public health endpoints and Render service URLs.

| File | Purpose |
|------|---------|
| [`uptime.env`](uptime.env) | API base URL for scheduled health probes |
| [`staging.env.example`](staging.env.example) | Copy-paste values for Render staging dashboard |

## Uptime monitoring

1. After first deploy, set `UPTIME_BASE_URL` in `uptime.env` to your live API.
2. Optionally mirror it as a GitHub secret (Settings → Secrets → Actions):
   `UPTIME_BASE_URL`
3. The workflow prefers the secret; falls back to this file.

Or run:

```bash
./scripts/setup-infra.sh
```

## Staging

Apply [`render-staging.yaml`](../render-staging.yaml) as a **separate** Render
project. Walkthrough: [`docs/runbooks/staging-deploy.md`](../docs/runbooks/staging-deploy.md).
