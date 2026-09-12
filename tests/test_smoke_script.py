"""Post-deploy checks must distinguish connectivity from usable data routes."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "smoke-test.sh"
pytestmark = pytest.mark.skipif(
    not shutil.which("bash") or not shutil.which("jq"), reason="bash and jq required"
)


@pytest.fixture
def run_smoke(tmp_path):
    fake_curl = tmp_path / "curl"
    fake_curl.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "from urllib.parse import urlsplit\n"
        "args = sys.argv[1:]\n"
        "url = next(a for a in args if a.startswith('https://'))\n"
        "path = urlsplit(url).path\n"
        "with open(os.environ['CURL_CALLS'], 'a') as f: f.write(path + '\\n')\n"
        "if path == os.environ.get('FAIL_PATH'): sys.exit(22)\n"
        "if path == '/health/ready':\n"
        " print(json.dumps({'status': os.environ.get('READY_STATUS', 'ready')}))\n"
        "elif path in ('/health', '/health/deep'): print('{\"status\":\"ok\",\"db\":\"ok\"}')\n"
        "elif path == '/openapi.json': print('{\"info\":{\"version\":\"test\"}}')\n"
        "elif path in ('/v1/auth/login', '/v1/auth/refresh'):\n"
        " if path.endswith('/login'):\n"
        "  payload = json.load(sys.stdin)\n"
        "  assert payload['password'] == os.environ['SMOKE_PASSWORD']\n"
        " with open(args[args.index('-c') + 1], 'w') as f: f.write('ds_refresh')\n"
        " print(json.dumps({'access_token': 'test-token-' + 'x' * 30}))\n"
        "else:\n"
        " assert 'Authorization: Bearer test-token-' + 'x' * 30 in args\n"
        " print('{}' if path == os.environ.get('INVALID_BODY_PATH') else '[]')\n"
    )
    fake_curl.chmod(0o700)
    calls = tmp_path / "calls.log"

    def run(**overrides):
        env = {
            "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
            "BASE": "https://api.example.test",
            "CURL_CALLS": str(calls),
            "COOKIE_JAR": str(tmp_path / "cookies"),
            **overrides,
        }
        result = subprocess.run(
            ["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=10
        )
        requested = calls.read_text().splitlines() if calls.exists() else []
        return result, requested

    return run


def test_smoke_rejects_missing_schema_even_when_connectivity_works(run_smoke):
    result, calls = run_smoke(FAIL_PATH="/health/ready")
    assert result.returncode != 0
    assert calls == ["/health", "/health/deep", "/health/ready"]
    assert "database schema is not ready" in result.stderr


def test_smoke_rejects_degraded_readiness_body(run_smoke):
    result, _ = run_smoke(READY_STATUS="degraded")
    assert result.returncode != 0
    assert "/health/ready status not ready" in result.stderr


def test_pilot_smoke_requires_authenticated_checks(run_smoke):
    result, calls = run_smoke(REQUIRE_AUTH_SMOKE="true")
    assert result.returncode != 0
    assert not calls
    assert "requires SMOKE_EMAIL and SMOKE_PASSWORD" in result.stderr


def test_smoke_reads_authenticated_routes_and_handles_quoted_password(run_smoke):
    result, calls = run_smoke(
        REQUIRE_AUTH_SMOKE="true",
        SMOKE_EMAIL="pilot@example.test",
        SMOKE_PASSWORD='test-"quote\\and-space password',
    )
    assert result.returncode == 0, result.stderr
    assert calls[-3:] == [
        "/v1/planning/events", "/v1/brand-expansion", "/v1/permit-brand-matches"
    ]
    assert "verify real inventory" in result.stdout
    assert "test-token" not in result.stdout + result.stderr


@pytest.mark.parametrize("path", ["/v1/planning/events", "/v1/brand-expansion"])
def test_smoke_rejects_authenticated_server_failure(run_smoke, path):
    result, calls = run_smoke(
        SMOKE_EMAIL="pilot@example.test", SMOKE_PASSWORD="test-only", FAIL_PATH=path
    )
    assert result.returncode != 0
    assert path in calls
    assert f"authenticated GET {path}" in result.stderr


def test_smoke_rejects_wrong_success_response(run_smoke):
    result, _ = run_smoke(
        SMOKE_EMAIL="pilot@example.test",
        SMOKE_PASSWORD="test-only",
        INVALID_BODY_PATH="/v1/planning/events",
    )
    assert result.returncode != 0
    assert "unexpected response" in result.stderr
