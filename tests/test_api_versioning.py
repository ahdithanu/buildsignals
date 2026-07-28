"""ApiVersioningMiddleware — unversioned rewrite + deprecation headers."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_versioned_path_reaches_router():
    r = client.get("/v1/health")
    # /health lives at root, not /v1 — so /v1/health should 404.
    # This proves versioning does NOT double-prefix a real versioned URL.
    assert r.status_code == 404


def test_unversioned_infrastructure_paths_are_not_rewritten():
    r = client.get("/health")
    assert r.status_code == 200
    # No deprecation on /health — it's intentionally unversioned.
    assert "Deprecation" not in r.headers


def test_unversioned_api_paths_get_rewritten_and_deprecation_header():
    # /openapi.json exists at root — the app has it. Any real API call
    # exercises the rewrite; use a public one that doesn't need auth.
    # /docs is exempt (infra), but /v1/docs shouldn't exist. Use the
    # health probe as a rewrite target the router serves.
    #
    # Simpler proof: hit an unversioned auth endpoint that IS a real
    # API route. /auth/register on this backend accepts POST; a GET
    # returns 405. That 405 tells us we reached the /v1/auth/register
    # router — rewrite worked.
    r = client.get("/auth/register")
    assert r.status_code == 405
    # And the deprecation-header contract fired even on 405.
    assert r.headers.get("Deprecation") == "true"
    assert "Sunset" in r.headers
    assert 'rel="successor-version"' in r.headers.get("Link", "")
    # Successor URL is the versioned form.
    assert "/v1/auth/register" in r.headers["Link"]


def test_root_path_is_untouched():
    r = client.get("/")
    # 404 (nothing mounted at /) — but importantly, no rewrite attempted,
    # no deprecation header.
    assert "Deprecation" not in r.headers
