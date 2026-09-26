#!/bin/sh
# Entrypoint that cleanly separates migrating from serving, so migrations
# never run on every web instance (that races on a multi-instance deploy).
#
#   serve    (default) — start the API
#   migrate            — run `alembic upgrade head` and exit; run this as a
#                        ONE-OFF task before cutting traffic to a new image
#   ingest             — plan and run due catalog sources; for scheduled tasks / cron
set -e

case "${1:-serve}" in
  migrate)
    echo "[entrypoint] running alembic upgrade head"
    exec alembic upgrade head
    ;;
  ingest)
    echo "[entrypoint] running cadence-aware ingestion"
    exec ./scripts/daily-ingestion.sh
    ;;
  serve)
    # Honor $PORT (App Runner/ECS inject it); default 8000.
    # Scale within an instance via WEB_CONCURRENCY (needs REDIS_URL so the
    # rate limiter is shared across workers — see app/services/rate_limiter.py).
    exec uvicorn app.main:app \
      --host 0.0.0.0 \
      --port "${PORT:-8000}" \
      --workers "${WEB_CONCURRENCY:-1}"
    ;;
  *)
    # Anything else: run it verbatim (e.g. `python scripts/admin.py ...`).
    exec "$@"
    ;;
esac
