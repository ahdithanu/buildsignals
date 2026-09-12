"""Health check endpoints.

Two flavours, both public:

- `/health` is a shallow liveness probe. Returns 200 without touching
  the DB. Used by Render's built-in health checks and by uptime
  monitors — anything that pages on repeated failure. Kept cheap so
  a DB blip doesn't restart the whole service.

- `/health/deep` actually queries the DB (`SELECT 1`). Returns 503 if
  the DB is unreachable. Use this from CI post-deploy verification or
  a dashboard where "is the app really working" matters more than
  "is the process running." Do NOT wire this to Render's restart
  policy — a transient DB error would then restart every worker.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import metrics
from app.db import get_db
from app.services.account_lockout import lockout
from app.services.rate_limiter import InMemoryRateLimiter, RateLimitUnavailable, limiter

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check():
    return {"status": "ok"}


@router.get("/health/deep")
def health_check_deep(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        # 503 rather than 500 — the process is fine, the dependency isn't.
        # Include exception class only (not the message) so we don't leak
        # connection strings or hostnames into a public endpoint.
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "db": type(exc).__name__},
        )
    return {"status": "ok", "db": "ok"}


@router.get("/health/auth-protection")
def authentication_protection_health():
    """Dependency readiness, not a restart probe or an authentication bypass."""
    headers = {"Cache-Control": "no-store"}
    try:
        # Fixed synthetic keys test the same writes, reads and deletes used by
        # login without consuming a customer's budget. Probe races are harmless.
        limiter.check(key="readiness", limit=1, window_seconds=60, required=True)
        lockout.record_failure("__buildsignals_readiness__")
        lockout.is_locked("__buildsignals_readiness__")
        lockout.reset("__buildsignals_readiness__")
        limiter.reset("readiness", required=True)
    except RateLimitUnavailable:
        return JSONResponse(status_code=503, content={"status": "degraded", "auth_protection": "unavailable"}, headers=headers)
    return JSONResponse(content={
        "status": "ok", "auth_protection": "local" if isinstance(limiter, InMemoryRateLimiter) else "shared",
    }, headers=headers)


@router.get("/metrics")
def prometheus_metrics(authorization: str | None = Header(default=None)):
    """Prometheus scrape endpoint.

    When METRICS_TOKEN is set, requires `Authorization: Bearer <token>`;
    when unset (dev), it's open. Restrict at the network layer in prod
    regardless — it exposes route names and traffic volume.
    """
    token = metrics.metrics_token()
    if token is not None:
        expected = f"Bearer {token}"
        if authorization != expected:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or invalid metrics token",
                headers={"WWW-Authenticate": "Bearer"},
            )
    payload, content_type = metrics.render_latest()
    return Response(content=payload, media_type=content_type)
