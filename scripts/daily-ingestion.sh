#!/usr/bin/env bash
# Cadence-aware permit + parcel ingestion.
#
# Used by Render cron, GitHub Actions, and manual ops runs.
#
# Environment:
#   INGESTION_ORGANIZATION          org slug or id (default: default-org)
#   INGESTION_MAX_PAGES_PER_SOURCE  optional override for catalog page limits
#   INGESTION_SHARD_COUNT           deterministic worker shard count (default: 1)
#   INGESTION_SHARD_INDEX           zero-based worker shard index (default: 0)
#   INGESTION_STAGE                 all, pre_approval_and_approved, or approved_only
#   INGESTION_ROLLOUT_WAVE          optional reviewed nationwide wave (1-4)
#   INGESTION_PLAN_ONLY             true to inspect due work without fetching
#
# Exit 0 when all sources succeed; 1 when any source fails.

set -euo pipefail

ORG="${INGESTION_ORGANIZATION:-default-org}"
MAX_PAGES="${INGESTION_MAX_PAGES_PER_SOURCE:-}"
SHARD_COUNT="${INGESTION_SHARD_COUNT:-1}"
SHARD_INDEX="${INGESTION_SHARD_INDEX:-0}"
PLAN_ONLY="${INGESTION_PLAN_ONLY:-false}"
STAGE="${INGESTION_STAGE:-all}"
ROLLOUT_WAVE="${INGESTION_ROLLOUT_WAVE:-}"

echo "Ingestion run: organization=${ORG} max_pages=${MAX_PAGES:-catalog} shard=${SHARD_INDEX}/${SHARD_COUNT} stage=${STAGE} wave=${ROLLOUT_WAVE:-all} plan_only=${PLAN_ONLY}"

ARGS=(
  scheduled-due
  --organization "$ORG"
  --shard-count "$SHARD_COUNT"
  --shard-index "$SHARD_INDEX"
  --stage "$STAGE"
)
if [[ -n "$MAX_PAGES" ]]; then
  ARGS+=(--max-pages-per-source "$MAX_PAGES")
fi
if [[ -n "$ROLLOUT_WAVE" ]]; then
  ARGS+=(--rollout-wave "$ROLLOUT_WAVE")
fi
if [[ "$PLAN_ONLY" == "true" ]]; then
  ARGS+=(--plan-only)
fi

python -m app.services.ingestion.cli "${ARGS[@]}"

echo "Cadence-aware ingestion completed successfully."
