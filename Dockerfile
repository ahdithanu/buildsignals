# Production image for the DealSignal API (FastAPI/uvicorn).
# Used by any container host — AWS App Runner / ECS Fargate, Fly.io, Cloud Run.
# (Render uses its native Python runtime, not this image.)
#
# Build:  docker build -t dealsignal-api .
# Serve:  docker run -p 8000:8000 --env-file .env dealsignal-api
# Migrate: docker run --env-file .env dealsignal-api migrate   # one-off, see runbook
FROM python:3.11-slim AS base

# - PYTHONDONTWRITEBYTECODE/UNBUFFERED: standard container hygiene.
# - No build-time DB access (the old image ran seed.py at build — removed).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install deps first for layer caching. All wheels (psycopg2-binary, bcrypt,
# cryptography) — no compiler needed on slim.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code + migrations (the old image omitted alembic/, so it couldn't migrate).
COPY app/ app/
COPY alembic/ alembic/
COPY alembic.ini .
COPY seed.py .
COPY docker-entrypoint.sh .
RUN chmod +x docker-entrypoint.sh

# Run as non-root.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Liveness for hosts that honor Docker HEALTHCHECK (App Runner uses its own
# HTTP health check config — point it at /health; see runbook).
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,os,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/health').status==200 else 1)"

ENTRYPOINT ["./docker-entrypoint.sh"]
# Default: serve. Pass "migrate" to run alembic instead (one-off task).
CMD ["serve"]
