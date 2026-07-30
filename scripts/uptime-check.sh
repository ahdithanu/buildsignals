#!/usr/bin/env bash
# External uptime probe — use from cron, GitHub Actions, or Better Uptime webhook.
#
# Usage:
#   BASE=https://dealsignal-api.onrender.com ./scripts/uptime-check.sh
#   BASE=... ./scripts/uptime-check.sh --deep    # also checks /health/deep (DB)
#
# Exit 0 when healthy; 1 on failure (suitable for paging hooks).

set -euo pipefail

BASE="${BASE:?Set BASE to the API origin}"
DEEP=false

for arg in "$@"; do
  case "$arg" in
    --deep) DEEP=true ;;
    -h|--help)
      echo "Usage: BASE=https://api.example.com $0 [--deep]"
      exit 0
      ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

check() {
  local path="$1"
  local label="$2"
  local code
  code=$(curl -sf -o /dev/null -w '%{http_code}' "${BASE}${path}") || {
    echo "FAIL: ${label} unreachable (${BASE}${path})" >&2
    return 1
  }
  if [[ "$code" != "200" ]]; then
    echo "FAIL: ${label} returned HTTP ${code}" >&2
    return 1
  fi
  echo "OK: ${label} (${code})"
}

check "/health" "liveness"
if $DEEP; then
  check "/health/deep" "deep health (DB)"
fi

echo "Uptime check passed."
