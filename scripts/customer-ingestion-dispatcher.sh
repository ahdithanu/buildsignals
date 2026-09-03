#!/usr/bin/env bash
# Bounded multi-tenant dispatcher for catalog-backed customer ingestion.

set -euo pipefail

ROLLOUT_WAVE="${INGESTION_ROLLOUT_WAVE:-}"
SHARD_COUNT="${INGESTION_SHARD_COUNT:-1}"
SHARD_INDEX="${INGESTION_SHARD_INDEX:-0}"
MAX_ORGANIZATIONS="${INGESTION_MAX_ORGANIZATIONS:-100}"
MAX_SOURCES="${INGESTION_MAX_SOURCES:-100}"
MAX_SOURCES_PER_ORG="${INGESTION_MAX_SOURCES_PER_ORGANIZATION:-25}"
WALL_CLOCK_SECONDS="${INGESTION_WALL_CLOCK_SECONDS:-3000}"
LEASE_SECONDS="${INGESTION_ENROLLMENT_LEASE_SECONDS:-3600}"
PLAN_ONLY="${INGESTION_PLAN_ONLY:-false}"

ARGS=(
  dispatch-enrollments
  --shard-count "$SHARD_COUNT"
  --shard-index "$SHARD_INDEX"
  --max-organizations "$MAX_ORGANIZATIONS"
  --max-sources "$MAX_SOURCES"
  --max-sources-per-organization "$MAX_SOURCES_PER_ORG"
  --wall-clock-seconds "$WALL_CLOCK_SECONDS"
  --lease-seconds "$LEASE_SECONDS"
)

if [[ -n "$ROLLOUT_WAVE" ]]; then
  ARGS+=(--rollout-wave "$ROLLOUT_WAVE")
fi
if [[ "$PLAN_ONLY" == "true" ]]; then
  ARGS+=(--plan-only)
fi
if [[ -n "${INGESTION_ORGANIZATIONS:-}" ]]; then
  IFS=',' read -r -a ORGANIZATIONS <<< "$INGESTION_ORGANIZATIONS"
  for organization in "${ORGANIZATIONS[@]}"; do
    ARGS+=(--organization "$organization")
  done
fi

python -m app.services.ingestion.cli "${ARGS[@]}"
