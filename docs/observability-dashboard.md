# Workspace observability dashboard

The admin-only `/admin/observability` page reads `GET /v1/observability/overview?days=1|7|30`.
It summarizes persisted evaluation runs/results and ingestion runs for the authenticated
organization. It does not consume process-local Prometheus counters, which cannot be
reliably scoped to a customer workspace or aggregated across instances.

## Semantics

- Windows are rolling UTC windows, with start inclusive and end exclusive.
- Evaluation counts include both live and replay runs and show them separately. They are
  **evaluation activity**, not a complete inventory of production AI calls.
- Cost, tokens, and latency are reported only when an eval result supplied the respective
  value. `null` means no measurement was reported. A measured zero remains zero.
- Daily buckets use UTC dates. The first and last buckets can be partial days.
- Stalled ingestion means a run in `running` status has no heartbeat for 15 minutes.
  A run that started outside the selected window is not included.
- Partial ingestion is separate from failed ingestion; partial runs with record errors
  receive a separate attention count. Token input and output coverage are shown
  independently when only one side was reported. Attention cards are counts only;
  source errors, model output, retrieved context, and customer data are not returned.

Strict workspace-admin authorization applies even when anonymous demo mode is enabled.
All aggregate queries constrain organization IDs, including joined evaluation results
and datasets. The endpoint is read-only and creates no new tables or migrations.

## Operations and scaling

This is an operational summary, not a replacement for Prometheus/Sentry. Existing
`/metrics` and tracing remain the source for fleet-wide HTTP latency and errors.
The API uses SQL aggregates over time-bounded run tables rather than loading records.
The evaluation run table has an `(organization_id, started_at)` index. If ingestion
history grows, add `(organization_id, started_at)` and consider hourly rollups or
materialized summaries. At a million opportunities, this query still scales with run
history, not opportunity count. Do not add raw log or evidence payloads to the response;
link to appropriately authorized detail pages instead.
