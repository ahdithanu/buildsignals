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

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import get_db

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
