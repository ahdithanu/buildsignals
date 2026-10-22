"""Regression for proxy auth responses overriding origin no-store headers.

Evaluate every matching header rule, rather than inspecting a single rule:
Vercel header matching continues before the API rewrite / SPA fallback.
"""
import json
import re
from pathlib import Path

import pytest

CONFIG = json.loads((Path(__file__).resolve().parents[1] / "vercel.json").read_text())


def _matches(source, path):
    # The only named wildcard currently used by these header rules. Other
    # sources are wrapped regex patterns supported by Vercel source matching.
    source = source.replace("/:path*", "(?:/.*)?")
    return re.fullmatch(source, path) is not None


def _headers(path, rules):
    headers = {}
    for rule in rules:
        if _matches(rule["source"], path):
            headers.update((item["key"].lower(), item["value"]) for item in rule["headers"])
    return headers


@pytest.mark.parametrize("path", ["/v1", "/v1/", "/v1/auth/demo", "/v1/auth/refresh", "/v1/permits/123"])
def test_api_headers_prevent_storage_in_any_matcher_order(path):
    # Nonoverlapping cache rules prevent a later public catch-all from undoing
    # no-store; security headers still apply to the proxied response.
    for rules in (CONFIG["headers"], list(reversed(CONFIG["headers"]))):
        headers = _headers(path, rules)
        assert headers["cache-control"] == "no-store"
        assert headers["x-content-type-options"] == "nosniff"
        cache_values = [item["value"] for rule in rules if _matches(rule["source"], path)
                        for item in rule["headers"] if item["key"].lower() == "cache-control"]
        assert cache_values == ["no-store"]


@pytest.mark.parametrize("path", ["/", "/signals", "/assets/index-abc.js", "/favicon.ico", "/v10/about", "/v1-guide"])
def test_frontend_retains_revalidation_cache_policy(path):
    headers = _headers(path, CONFIG["headers"])
    assert headers["cache-control"] == "public, max-age=0, must-revalidate"
    assert headers["x-frame-options"] == "DENY"


def test_api_rewrite_precedes_spa_fallback():
    first = next(rule for rule in CONFIG["rewrites"] if _matches(rule["source"], "/v1/auth/demo"))
    assert first["destination"].endswith("/v1/:path*")
    assert first["destination"].startswith("https://")
