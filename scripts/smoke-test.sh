#!/usr/bin/env bash
# Post-deploy smoke test for DealSignal API + optional frontend URL.
#
# Usage:
#   BASE=https://dealsignal-api.onrender.com ./scripts/smoke-test.sh
#   BASE=... FRONTEND=https://app.example.com SMOKE_EMAIL=... SMOKE_PASSWORD=... ./scripts/smoke-test.sh
#
# Exit 0 when all checks pass; non-zero on first failure.

set -euo pipefail

BASE="${BASE:?Set BASE to the API origin, e.g. https://dealsignal-api.onrender.com}"
FRONTEND="${FRONTEND:-}"
SMOKE_EMAIL="${SMOKE_EMAIL:-}"
SMOKE_PASSWORD="${SMOKE_PASSWORD:-}"
COOKIE_JAR="${COOKIE_JAR:-$(mktemp /tmp/ds-smoke-cookies.XXXXXX)}"

cleanup() {
  rm -f "$COOKIE_JAR"
}
trap cleanup EXIT

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

pass() {
  echo "OK: $*"
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "$1 is required"
}

require_cmd curl
require_cmd jq

echo "Smoke testing API at $BASE"

# Shallow liveness
health=$(curl -sf "$BASE/health") || fail "/health unreachable"
echo "$health" | jq -e '.status == "ok"' >/dev/null || fail "/health status not ok"

# Deep health (DB)
deep=$(curl -sf "$BASE/health/deep") || fail "/health/deep unreachable (503 = DB down)"
echo "$deep" | jq -e '.database == "ok"' >/dev/null 2>&1 || \
  echo "$deep" | jq -e '.status == "ok"' >/dev/null || fail "/health/deep DB check failed"

# OpenAPI version stamp
version=$(curl -sf "$BASE/openapi.json" | jq -r '.info.version // empty')
[[ -n "$version" ]] || fail "openapi.json missing info.version"
pass "openapi version $version"

# Auth round-trip (optional — requires seeded smoke user)
if [[ -n "$SMOKE_EMAIL" && -n "$SMOKE_PASSWORD" ]]; then
  login=$(curl -sf -X POST "$BASE/v1/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"$SMOKE_EMAIL\",\"password\":\"$SMOKE_PASSWORD\"}" \
    -c "$COOKIE_JAR") || fail "login failed"
  token_len=$(echo "$login" | jq -r '.access_token // empty | length')
  [[ "$token_len" -gt 20 ]] || fail "login returned no access_token"
  grep -q ds_refresh "$COOKIE_JAR" || fail "refresh cookie (ds_refresh) not set"
  refresh=$(curl -sf -X POST "$BASE/v1/auth/refresh" -b "$COOKIE_JAR" -c "$COOKIE_JAR") || fail "refresh failed"
  refresh_len=$(echo "$refresh" | jq -r '.access_token // empty | length')
  [[ "$refresh_len" -gt 20 ]] || fail "refresh returned no access_token"
  pass "auth login + refresh"
else
  echo "SKIP: auth round-trip (set SMOKE_EMAIL + SMOKE_PASSWORD to enable)"
fi

# Frontend headers (optional)
if [[ -n "$FRONTEND" ]]; then
  headers=$(curl -sI "$FRONTEND/" | tr -d '\r')
  for h in Strict-Transport-Security X-Frame-Options X-Content-Type-Options Referrer-Policy Permissions-Policy; do
    echo "$headers" | grep -qi "^$h:" || fail "frontend missing header $h"
  done
  pass "frontend security headers present"
fi

echo "All smoke checks passed."
