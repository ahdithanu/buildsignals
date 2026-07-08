"""Prometheus metrics.

Exposes request-level metrics scrapable at GET /metrics. Recording happens
in RequestContextMiddleware (which already measures status + duration), so
there's no second timing pass.

Cardinality discipline
----------------------
The `path` label is the ROUTE TEMPLATE (e.g. "/v1/deals/{deal_id}"), never
the raw URL. Labelling with the raw path would mint a new time series per
deal id and blow up Prometheus memory. Unmatched requests (404s) collapse to
"__unmatched__" for the same reason.

Access
------
/metrics is gated by METRICS_TOKEN when set: scrapers must send
`Authorization: Bearer <token>`. When unset (local dev) it's open. Either
way, restrict it at the network layer in production — it leaks route names
and traffic shape.
"""
from __future__ import annotations

import os

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.requests import Request

# Buckets tuned for a web API: sub-10ms static-ish reads up to multi-second
# LLM/enrichment calls. Default prometheus buckets top out at 10s, which is
# fine here.
_LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests.",
    ["method", "path", "status"],
)

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds.",
    ["method", "path"],
    buckets=_LATENCY_BUCKETS,
)

REQUESTS_IN_PROGRESS = Gauge(
    "http_requests_in_progress",
    "HTTP requests currently being served.",
    ["method"],
)


def route_template(request: Request) -> str:
    """Return the matched route template for low-cardinality labels.

    After routing, Starlette puts the matched Route on request.scope["route"].
    Its `.path` is the template with `{param}` placeholders. Falls back to a
    single bucket for unmatched paths so 404 scans can't explode cardinality.
    """
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path or "__unmatched__"


def record(method: str, path: str, status: int, duration_seconds: float) -> None:
    """Record one completed request. Called from RequestContextMiddleware."""
    REQUEST_COUNT.labels(method=method, path=path, status=str(status)).inc()
    REQUEST_LATENCY.labels(method=method, path=path).observe(duration_seconds)


def render_latest() -> tuple[bytes, str]:
    """Return (payload, content_type) for the /metrics response."""
    return generate_latest(), CONTENT_TYPE_LATEST


def metrics_token() -> str | None:
    """Bearer token required to scrape /metrics, or None to leave it open."""
    return os.environ.get("METRICS_TOKEN", "").strip() or None
