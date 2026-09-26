#!/usr/bin/env bash
# One-shot infra setup: detect live API, configure uptime monitoring, print staging steps.
#
# Usage: ./scripts/setup-infra.sh [--url https://your-api.onrender.com]

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UPTIME_FILE="$REPO_ROOT/infra/uptime.env"
STAGING_DOC="$REPO_ROOT/docs/runbooks/staging-deploy.md"

DEFAULT_CANDIDATES=(
  "https://dealsignal-api.onrender.com"
  "https://api.dealsignal.com"
)

resolve_url() {
  if [[ "${1:-}" == "--url" && -n "${2:-}" ]]; then
    echo "$2"
    return
  fi
  local url
  for url in "${DEFAULT_CANDIDATES[@]}"; do
    if curl -sf -m 10 "${url}/health/deep" >/dev/null 2>&1; then
      echo "$url"
      return
    fi
    if curl -sf -m 10 "${url}/health" >/dev/null 2>&1; then
      echo "$url"
      return
    fi
  done
  echo "${DEFAULT_CANDIDATES[0]}"
}

URL="$(resolve_url "$@")"
mkdir -p "$REPO_ROOT/infra"

cat > "$UPTIME_FILE" <<EOF
# Infrastructure config (committed — health URLs are public endpoints)
# Updated by scripts/setup-infra.sh on $(date -u +%Y-%m-%dT%H:%M:%SZ)

UPTIME_BASE_URL=${URL}
EOF

echo "Wrote $UPTIME_FILE → UPTIME_BASE_URL=${URL}"

# Probe now
chmod +x "$REPO_ROOT/scripts/uptime-check.sh"
if BASE="$URL" "$REPO_ROOT/scripts/uptime-check.sh" --deep; then
  echo "✓ Live API healthy at ${URL}"
else
  echo "⚠ API not reachable yet at ${URL} — expected before first Render deploy."
  echo "  Re-run this script after deploy, or pass: $0 --url https://YOUR-API.onrender.com"
fi

# GitHub secret (optional — needs admin token)
if command -v gh >/dev/null 2>&1; then
  if gh secret set UPTIME_BASE_URL --body "$URL" --repo "$(git -C "$REPO_ROOT" remote get-url origin | sed -n 's|.*github.com[:/]\([^/]*/[^/.]*\).*|\1|p')" 2>/dev/null; then
    echo "✓ GitHub secret UPTIME_BASE_URL set"
  else
    echo "→ Set GitHub secret manually (repo admin required):"
    echo "  gh secret set UPTIME_BASE_URL --body '${URL}'"
    echo "  Or rely on committed infra/uptime.env (workflow fallback)."
  fi
fi

echo ""
echo "── Staging (manual — Render dashboard) ──"
echo "1. Render → New → Blueprint → select this repo"
echo "2. Choose render-staging.yaml (not render.yaml)"
echo "3. Follow: $STAGING_DOC"
echo ""
echo "Done."
