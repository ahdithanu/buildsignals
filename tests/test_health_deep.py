"""/health and /health/deep endpoints."""
from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.main import app

client = TestClient(app)


def test_shallow_health_is_ok():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_deep_health_returns_ok_when_db_is_up():
    r = client.get("/health/deep")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"


def test_deep_health_returns_503_when_db_is_down():
    # Simulate a DB outage by making `Session.execute` raise.
    with patch(
        "app.routes.health.Session.execute",
        side_effect=OperationalError("SELECT 1", {}, Exception("connection refused")),
    ):
        r = client.get("/health/deep")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "degraded"
    # Exception class name only — no leaked message.
    assert body["db"] == "OperationalError"
