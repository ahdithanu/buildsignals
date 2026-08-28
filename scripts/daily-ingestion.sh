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
#   INGESTION_ROTATE_SHARDS         derive the shard from the UTC 24-hour window
#   INGESTION_STAGE                 all, pre_approval_and_approved, or approved_only
#   INGESTION_ROLLOUT_WAVE          optional reviewed nationwide wave (1-4)
#   INGESTION_PLAN_ONLY             true to inspect due work without fetching
#
# Exit 0 when all sources succeed; 1 when any source fails.

set -euo pipefail

ORG="${INGESTION_ORGANIZATION:-default-org}"
MAX_PAGES="${INGESTION_MAX_PAGES_PER_SOURCE:-}"
SHARD_COUNT="${INGESTION_SHARD_COUNT:-1}"
SHARD_INDEX="${INGESTION_SHARD_INDEX:-}"
ROTATE_SHARDS="${INGESTION_ROTATE_SHARDS:-false}"
PLAN_ONLY="${INGESTION_PLAN_ONLY:-false}"
STAGE="${INGESTION_STAGE:-all}"
ROLLOUT_WAVE="${INGESTION_ROLLOUT_WAVE:-}"

if ! [[ "$SHARD_COUNT" =~ ^[1-9][0-9]*$ ]] || (( SHARD_COUNT > 128 )); then
  echo "INGESTION_SHARD_COUNT must be between 1 and 128." >&2
  exit 2
fi

if [[ -z "$SHARD_INDEX" && "$ROTATE_SHARDS" == "true" ]]; then
  if (( SHARD_COUNT > 24 )); then
    echo "Rotating cron shards require INGESTION_SHARD_COUNT <= 24." >&2
    exit 2
  fi
  UTC_HOUR=$((10#$(date -u +%H)))
  SHARD_INDEX=$((UTC_HOUR * SHARD_COUNT / 24))
fi
SHARD_INDEX="${SHARD_INDEX:-0}"

if ! [[ "$SHARD_INDEX" =~ ^[0-9]+$ ]] || (( SHARD_INDEX >= SHARD_COUNT )); then
  echo "INGESTION_SHARD_INDEX must be between 0 and $((SHARD_COUNT - 1))." >&2
  exit 2
fi

echo "Ingestion run: organization=${ORG} max_pages=${MAX_PAGES:-catalog} shard=${SHARD_INDEX}/${SHARD_COUNT} stage=${STAGE} wave=${ROLLOUT_WAVE:-all} plan_only=${PLAN_ONLY}"

if [[ "${ENVIRONMENT:-development}" == "production" || "${ENVIRONMENT:-development}" == "staging" ]]; then
  HOST_AUDIT_ARGS=(
    catalog host-audit
    --allow-unused-hosts
    --stage "$STAGE"
    --shard-count "$SHARD_COUNT"
    --shard-index "$SHARD_INDEX"
  )
  if [[ -n "$ROLLOUT_WAVE" ]]; then
    python -m app.services.ingestion.cli catalog rollout-manifest --check
    HOST_AUDIT_ARGS+=(--rollout-wave "$ROLLOUT_WAVE")
  fi
  python -m app.services.ingestion.cli "${HOST_AUDIT_ARGS[@]}"
fi

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
