#!/usr/bin/env bash
# Run bounded, no-write canaries for every shard in one reviewed rollout wave.

set -uo pipefail

ORG="${INGESTION_ORGANIZATION:-default-org}"
WAVE="${INGESTION_ROLLOUT_WAVE:-1}"
SHARD_COUNT="${INGESTION_SHARD_COUNT:-4}"
SAMPLE_SIZE="${INGESTION_CANARY_SAMPLE_SIZE:-10}"

if ! [[ "$WAVE" =~ ^[1-4]$ ]]; then
  echo "INGESTION_ROLLOUT_WAVE must be between 1 and 4." >&2
  exit 2
fi
if ! [[ "$SHARD_COUNT" =~ ^[1-9][0-9]*$ ]] || (( SHARD_COUNT > 128 )); then
  echo "INGESTION_SHARD_COUNT must be between 1 and 128." >&2
  exit 2
fi
if ! [[ "$SAMPLE_SIZE" =~ ^[1-9][0-9]*$ ]] || (( SAMPLE_SIZE > 100 )); then
  echo "INGESTION_CANARY_SAMPLE_SIZE must be between 1 and 100." >&2
  exit 2
fi

failed=0
for (( shard=0; shard<SHARD_COUNT; shard++ )); do
  python -m app.services.ingestion.cli canary \
    --organization "$ORG" \
    --all \
    --rollout-wave "$WAVE" \
    --shard-count "$SHARD_COUNT" \
    --shard-index "$shard" \
    --sample-size "$SAMPLE_SIZE" \
    --json || failed=1
done

exit "$failed"
