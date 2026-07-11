# Service level objectives

Proposed SLOs for DealSignal and how to measure them. These are **targets to
adopt**, not contractual commitments — an SLA is a separate, customer-facing
document with legal teeth (see the gap note at the end). Framed so you can
turn them on as soon as the monitoring in ["How we measure"](#how-we-measure)
is wired up.

## Objectives

| SLO | Target | Window | Rationale |
|---|---|---|---|
| **Availability** | 99.5% | 30-day rolling | ~3.6h/month of allowed downtime. Reasonable for a single-region pilot; raise to 99.9% once you have multi-region + PITR. |
| **Latency (reads)** | p95 < 500ms | 30-day rolling | Dashboard/list endpoints. Excludes AI-backed routes below. |
| **Latency (AI routes)** | p95 < 10s | 30-day rolling | generate-memo / enrich / score call an LLM; seconds, not milliseconds, is the honest bar. |
| **Error rate** | < 1% 5xx | 30-day rolling | Of all non-4xx requests. 4xx are client errors and don't count against us. |

These are starting points. Tighten them as the platform hardens; don't
inherit someone else's numbers.

## How we measure

Everything here is already emitted — the SLOs are computable today once a
scraper and a dashboard are pointed at the data.

- **Availability & error rate** — the `/metrics` endpoint
  (`docs/` → observability) exposes `http_requests_total{status=...}`. Error
  rate = `sum(5xx) / sum(non-4xx)`. Availability can be proxied from the same
  counter or, better, from an external uptime monitor hitting `/health`.
- **Latency** — `http_request_duration_seconds` is a histogram with
  per-route-template labels. p95 is a `histogram_quantile(0.95, ...)` query in
  Prometheus/Grafana. Split the AI routes out by their path labels.
- **Deep health** — `/health/deep` distinguishes "process up" from "DB
  reachable"; wire the uptime monitor to it, not just `/health`, so a DB
  outage counts against availability.
- **Errors** — Sentry captures the actual exceptions behind the 5xx rate, so
  a budget burn has a root cause attached.

## Error budget

At 99.5% availability the monthly error budget is ~3.6 hours. Policy when it's
burning:

- **Budget healthy (< 50% consumed):** ship normally.
- **Budget half gone:** slow down risky changes; prioritize reliability work
  over features until it recovers.
- **Budget exhausted:** feature freeze — only reliability fixes and rollbacks
  ship until the next window resets. This is the whole point of a budget: it
  turns "are we reliable enough?" into a number, not an argument.

Tie budget burn to the incident process in
[runbooks/incident-response.md](runbooks/incident-response.md) — a sustained
5xx spike is both a budget event and, if bad enough, an incident.

## Gaps

- **No SLA.** These SLOs are internal targets. A customer-facing SLA (with
  credits/remedies) is a business + legal decision, not just a metrics one.
- **Measurement not yet automated.** The data is emitted; the Grafana/Datadog
  dashboards, the Prometheus recording rules, and the alert thresholds that
  page when a budget is burning still need standing up (infrastructure, not
  code — see the readiness assessment).
- **Availability target assumes single region.** 99.5% is honest for the
  current setup. Don't advertise 99.9%+ without multi-region and PITR.
