"""Structured logging for DealSignal.

In production we emit JSON lines so Render/Datadog/CloudWatch can index
fields (request_id, user_id, org_id, status, duration_ms) without regex.
In dev we keep a human-readable one-line format so tailing logs feels
like `uvicorn` did before this PR.

A ContextVar-backed filter injects per-request fields into every log
record without requiring each call site to pass them explicitly.
"""
from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from typing import Any, Optional

from app.config import IS_PRODUCTION

# ── per-request context ────────────────────────────────────────────────────

_request_id_var: ContextVar[Optional[str]] = ContextVar(
    "dealsignal_request_id", default=None,
)


def set_request_id(request_id: Optional[str]) -> object:
    return _request_id_var.set(request_id)


def reset_request_id(token: object) -> None:
    _request_id_var.reset(token)  # type: ignore[arg-type]


def get_request_id() -> Optional[str]:
    return _request_id_var.get()


# ── log record enrichment ──────────────────────────────────────────────────

class _ContextFilter(logging.Filter):
    """Attach request_id (+ org/user if auth context is set) to every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_var.get() or "-"
        # Pull org/user lazily to avoid a hard dep during cold-start logging.
        try:
            from app.utils.org_scope import _current_context  # type: ignore
            ctx = _current_context.get()
            record.org_id = ctx.org_id if ctx else "-"
            record.user_id = ctx.user_id if ctx else "-"
        except Exception:
            record.org_id = "-"
            record.user_id = "-"
        return True


# ── formatters ─────────────────────────────────────────────────────────────

_STANDARD_FIELDS = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "taskName",
}


class _JsonFormatter(logging.Formatter):
    """One JSON object per line. Unknown fields on the record become keys."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "org_id": getattr(record, "org_id", "-"),
            "user_id": getattr(record, "user_id", "-"),
        }
        # Surface any structured fields attached via `extra=` at the call site.
        for key, val in record.__dict__.items():
            if key in _STANDARD_FIELDS or key in payload or key.startswith("_"):
                continue
            try:
                json.dumps(val)  # skip non-serializable
                payload[key] = val
            except (TypeError, ValueError):
                payload[key] = repr(val)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


_DEV_FMT = (
    "%(asctime)s %(levelname)-5s [%(request_id)s] %(name)s: %(message)s"
)


# ── entry point ────────────────────────────────────────────────────────────

_configured = False


def configure_logging(level: str = "INFO") -> None:
    """Idempotently wire the root logger + uvicorn loggers into our format."""
    global _configured
    if _configured:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        _JsonFormatter() if IS_PRODUCTION else logging.Formatter(_DEV_FMT, "%H:%M:%S")
    )
    handler.addFilter(_ContextFilter())

    root = logging.getLogger()
    # Replace any preexisting handlers so uvicorn's default plain formatter
    # doesn't double-log alongside ours.
    root.handlers = [handler]
    root.setLevel(level)

    # Uvicorn's access logger emits one record per request; we replace our
    # middleware's log with that one in production, but keep both during dev.
    # Letting uvicorn's access log propagate to root picks up our formatter.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True

    _configured = True
