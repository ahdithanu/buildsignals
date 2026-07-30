# Monitoring & alerting setup

Guide for standing up the observability pieces referenced in `docs/slo.md`.
The application already emits metrics and health endpoints; this doc covers
what to wire externally.

---

## 1. Uptime monitoring

**Target:** `/health/deep` on the production API (not shallow `/health`).

**In-repo automation:** `.github/workflows/uptime.yml` runs every 5 minutes when
the repository secret `UPTIME_BASE_URL` is set (e.g. `https://dealsignal-api.onrender.com`).
Uses `scripts/uptime-check.sh --deep`.

**Manual / cron:**

```bash
BASE=https://YOUR-API.onrender.com ./scripts/uptime-check.sh --deep
```

| Check | Interval | Timeout | Alert if |
|-------|----------|---------|----------|
| Deep health | 1 min | 10s | 2 consecutive failures |
| Shallow health | 5 min | 5s | 5 consecutive failures (process crash) |

Recommended providers: Better Uptime, Pingdom, UptimeRobot, or Grafana Cloud
synthetic checks.

Example curl (manual):

```bash
curl -sf https://YOUR-API.onrender.com/health/deep | jq .
```

---

## 2. Metrics scraping

The API exposes Prometheus text at `GET /metrics`. Access requires:

```
Authorization: Bearer $METRICS_TOKEN
```

**Setup:**

1. Copy `METRICS_TOKEN` from Render dashboard (auto-generated in blueprint).
2. Configure your scraper (Prometheus, Grafana Agent, Datadog OpenMetrics)
   with the bearer token.
3. Scrape interval: 15–30s.

**Key queries** (Prometheus):

```promql
# 5xx error rate (5 min window)
sum(rate(http_requests_total{status=~"5.."}[5m]))
  / sum(rate(http_requests_total{status!~"4.."}[5m]))

# p95 latency by route
histogram_quantile(0.95,
  sum by (le, handler) (rate(http_request_duration_seconds_bucket[5m]))
)
```

---

## 3. Sentry alerts

When `SENTRY_DSN` / `VITE_SENTRY_DSN` are set:

| Alert | Condition | Action |
|-------|-----------|--------|
| New issue spike | >10 events in 5 min | Slack `#dealsignal-incidents` |
| Regression | Issue reopens after resolve | Page on-call |
| Release health | Error rate 2× baseline post-deploy | Rollback consideration |

Tag releases via `RENDER_GIT_COMMIT` (automatic on Render).

---

## 4. Error budget alerts

From `docs/slo.md` — 99.5% availability ≈ 3.6h/month budget.

| Burn rate | Alert severity | Response |
|-----------|----------------|----------|
| >50% budget consumed mid-month | Warning | Slow feature shipping |
| >80% budget consumed | High | Reliability sprint |
| Budget exhausted | Critical | Feature freeze |

Wire the 5xx rate query above to your paging tool with thresholds aligned
to these tiers. Example rules: [`docs/prometheus/alerts.example.yml`](prometheus/alerts.example.yml).

---

## 5. Render-native alerts

In Render dashboard → service → Notifications:

- Deploy failed
- Service unhealthy (health check failing)
- Postgres disk >80%
- Postgres connections >80% of limit

---

## 6. Dashboard checklist

Create a single "DealSignal Production" dashboard with:

- [ ] Uptime (external probe)
- [ ] Request rate (2xx / 4xx / 5xx)
- [ ] p50 / p95 latency (split AI routes)
- [ ] Postgres connections + CPU (Render metrics)
- [ ] Sentry issue count (last 24h)
- [ ] Error budget remaining (%)

---

## 7. Staging parity

When staging exists (see `docs/enterprise_readiness.md` G5), duplicate
monitors against staging URLs with relaxed thresholds. Staging alerts should
notify a dev channel, not on-call.
