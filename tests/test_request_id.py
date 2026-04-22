"""Tests for RequestContextMiddleware.

Covers the four properties we rely on:
  1. A missing X-Request-ID gets auto-generated and echoed.
  2. A client-supplied X-Request-ID is trusted and echoed back verbatim.
  3. Obviously malformed client IDs are discarded in favor of a fresh uuid.
  4. The ID is visible to application code via get_request_id() during the
     request, and unset after the response.
"""
from __future__ import annotations

import re

from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.logging_config import get_request_id
from app.main import app

UUID_HEX = re.compile(r"^[0-9a-f]{32}$")

# Register a probe endpoint at import time so the middleware chain is hot.
_probe = APIRouter()


@_probe.get("/__probe/request-id")
def _probe_endpoint():
    return {"request_id": get_request_id()}


app.include_router(_probe)


client = TestClient(app)


def test_missing_header_gets_generated():
    r = client.get("/__probe/request-id")
    assert r.status_code == 200
    rid = r.headers.get("X-Request-ID")
    assert rid and UUID_HEX.match(rid), f"expected uuid hex, got {rid!r}"
    # Handler observed the same id the response advertises.
    assert r.json()["request_id"] == rid


def test_client_supplied_id_is_echoed():
    r = client.get(
        "/__probe/request-id",
        headers={"X-Request-ID": "trace-abc-123"},
    )
    assert r.status_code == 200
    assert r.headers["X-Request-ID"] == "trace-abc-123"
    assert r.json()["request_id"] == "trace-abc-123"


def test_malformed_client_id_is_discarded():
    # Spaces + weird chars fail the sanitizer → fresh uuid minted.
    r = client.get(
        "/__probe/request-id",
        headers={"X-Request-ID": "nope!! <script>"},
    )
    assert r.status_code == 200
    rid = r.headers["X-Request-ID"]
    assert UUID_HEX.match(rid)
    assert rid != "nope!! <script>"


def test_overly_long_client_id_is_discarded():
    long_id = "a" * 500
    r = client.get(
        "/__probe/request-id",
        headers={"X-Request-ID": long_id},
    )
    assert r.status_code == 200
    assert UUID_HEX.match(r.headers["X-Request-ID"])


def test_context_unset_after_request():
    client.get("/__probe/request-id")
    # Outside of any request, the ContextVar should be cleared.
    assert get_request_id() is None
