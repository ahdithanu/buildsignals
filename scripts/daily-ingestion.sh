#!/usr/bin/env bash
# Daily permit + parcel ingestion — sync catalog, then run all active sources.
#
# Used by Render cron, GitHub Actions, and manual ops runs.
#
# Environment:
#   INGESTION_ORGANIZATION          org slug or id (default: default-org)
#   INGESTION_MAX_PAGES_PER_SOURCE  pages per source (default: 10, max 100)
#   INGESTION_STAGE                 all | pre_approval_and_approved | approved_only
#
# Exit 0 when all sources succeed; 1 when any source fails.

set -euo pipefail

ORG="${INGESTION_ORGANIZATION:-default-org}"
MAX_PAGES="${INGESTION_MAX_PAGES_PER_SOURCE:-10}"
STAGE="${INGESTION_STAGE:-all}"

echo "Ingestion run: organization=${ORG} max_pages=${MAX_PAGES} stage=${STAGE}"

python -m app.services.ingestion.cli catalog sync --organization "$ORG"

python -m app.services.ingestion.cli run-all \
  --organization "$ORG" \
  --max-pages-per-source "$MAX_PAGES" \
  --stage "$STAGE"

echo "Daily ingestion completed successfully."
