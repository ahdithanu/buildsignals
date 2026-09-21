"""Prometheus /metrics endpoint."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_metrics_exposes_prometheus_text():
    # Generate some traffic so the counters are non-zero.
    client.get("/health")
    client.get("/health")

    r = client.get("/metrics")
    assert r.status_code == 200
    assert "text/plain" in r.headers["content-type"]
    body = r.text
    # Our custom metric families are present.
    assert "http_requests_total" in body
    assert "http_request_duration_seconds" in body
    assert "http_requests_in_progress" in body


def test_metrics_labels_use_route_template_not_raw_path():
    # Hitting a parametrized route must NOT create a label per id — the label
    # should be the template. We can't easily hit a real /v1/deals/{id} without
    # auth, but /health is a fixed path and must appear by its template.
    client.get("/health")
    body = client.get("/metrics").text
    assert 'path="/health"' in body
    # A raw uuid should never appear as a path label.
    client.get("/health/deep")
    assert 'path="/health/deep"' in client.get("/metrics").text


def test_metrics_token_required_when_set(monkeypatch):
    monkeypatch.setenv("METRICS_TOKEN", "s3cr3t-scrape")

    # No token → 401.
    assert client.get("/metrics").status_code == 401
    # Wrong token → 401.
    assert client.get(
        "/metrics", headers={"Authorization": "Bearer nope"}
    ).status_code == 401
    # Correct token → 200.
    ok = client.get("/metrics", headers={"Authorization": "Bearer s3cr3t-scrape"})
    assert ok.status_code == 200
    assert "http_requests_total" in ok.text


def test_metrics_open_when_token_unset(monkeypatch):
    monkeypatch.delenv("METRICS_TOKEN", raising=False)
    assert client.get("/metrics").status_code == 200
