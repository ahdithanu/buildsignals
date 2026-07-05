from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Database configuration
# Set DATABASE_URL env var for PostgreSQL in production:
#   DATABASE_URL=postgresql://user:pass@host:5432/dealsignal
#
# Falls back to SQLite for local development / demo mode.
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    f"sqlite:///{BASE_DIR / 'dealsignal.db'}",
)

# Fix Render/Heroku postgres:// → postgresql:// prefix
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# JWT settings (used by auth layer).
#
# Access tokens are short-lived and held in memory on the frontend (never
# localStorage). Refresh tokens are long-lived and carried as an httpOnly
# Secure cookie scoped to /auth/refresh, so XSS cannot read them and the
# browser automatically attaches them only to the refresh endpoint.
_DEFAULT_SECRET_KEY = "dev-secret-change-in-production"
SECRET_KEY = os.environ.get("SECRET_KEY", _DEFAULT_SECRET_KEY)


def _require_int(name: str, default: str) -> int:
    raw = os.environ.get(name, default)
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer, got {raw!r}") from exc


ACCESS_TOKEN_EXPIRE_MINUTES = _require_int("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
REFRESH_TOKEN_EXPIRE_DAYS = _require_int("REFRESH_TOKEN_EXPIRE_DAYS", "14")
ALGORITHM = "HS256"

# Refresh-cookie attributes. In production we want Secure + SameSite=lax so
# the cookie only flows over TLS and is not sent on cross-site POSTs beyond
# top-level navigations. In dev (http://localhost) Secure must be off or the
# browser drops the cookie entirely.
REFRESH_COOKIE_NAME = os.environ.get("REFRESH_COOKIE_NAME", "ds_refresh")
REFRESH_COOKIE_PATH = "/auth"  # scoped: only /auth/refresh and /auth/logout see it
REFRESH_COOKIE_SAMESITE = os.environ.get("REFRESH_COOKIE_SAMESITE", "lax").lower()
if REFRESH_COOKIE_SAMESITE not in ("lax", "strict", "none"):
    raise RuntimeError(
        f"REFRESH_COOKIE_SAMESITE must be one of lax|strict|none, got {REFRESH_COOKIE_SAMESITE!r}"
    )

# Environment: "development" | "staging" | "production"
ENVIRONMENT = os.environ.get("ENVIRONMENT", "development").lower()
IS_PRODUCTION = ENVIRONMENT == "production"


def _parse_origins(raw: str | None) -> list[str]:
    """Split comma/whitespace-separated origins, strip blanks, drop trailing slashes."""
    if not raw:
        return []
    items: list[str] = []
    for part in raw.replace("\n", ",").split(","):
        origin = part.strip().rstrip("/")
        if origin:
            items.append(origin)
    return items


# CORS — comma-separated list of allowed origins, e.g.:
#   CORS_ALLOWED_ORIGINS=https://app.dealsignal.com,https://staging.dealsignal.com
# In development this defaults to the Vite dev server. In production "*" is
# rejected and the app will fail to start if the list is empty.
_DEFAULT_DEV_ORIGINS = "http://localhost:8080,http://localhost:5173,http://127.0.0.1:8080"
CORS_ALLOWED_ORIGINS: list[str] = _parse_origins(
    os.environ.get(
        "CORS_ALLOWED_ORIGINS",
        "" if IS_PRODUCTION else _DEFAULT_DEV_ORIGINS,
    )
)

if IS_PRODUCTION:
    if not CORS_ALLOWED_ORIGINS:
        raise RuntimeError(
            "CORS_ALLOWED_ORIGINS must be set (non-empty, no '*') when ENVIRONMENT=production"
        )
    if "*" in CORS_ALLOWED_ORIGINS:
        raise RuntimeError(
            "CORS_ALLOWED_ORIGINS cannot contain '*' when ENVIRONMENT=production"
        )


def _parse_bool(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


# Authentication posture.
#
# When True, requests without a valid Bearer token fall through to the
# default organization + system user (legacy demo behaviour, required by
# existing pytest suite). When False, any non-public route without a valid
# token returns 401.
#
# Default: True in development/staging, False in production. Override with
# ALLOW_ANONYMOUS=true|false. Production rejects ALLOW_ANONYMOUS=true outright.
ALLOW_ANONYMOUS: bool = _parse_bool(
    os.environ.get("ALLOW_ANONYMOUS"),
    default=not IS_PRODUCTION,
)

if IS_PRODUCTION and ALLOW_ANONYMOUS:
    raise RuntimeError(
        "ALLOW_ANONYMOUS=true is not permitted when ENVIRONMENT=production"
    )
if IS_PRODUCTION:
    if SECRET_KEY == _DEFAULT_SECRET_KEY or not SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY must be set to a strong random value when ENVIRONMENT=production "
            "(the dev default is rejected)"
        )
    if len(SECRET_KEY) < 32:
        raise RuntimeError(
            "SECRET_KEY must be at least 32 characters when ENVIRONMENT=production"
        )
    if DATABASE_URL.startswith("sqlite"):
        raise RuntimeError(
            "DATABASE_URL must point to PostgreSQL when ENVIRONMENT=production "
            "(SQLite is not safe for production)"
        )
    if REFRESH_COOKIE_SAMESITE == "none" and not REFRESH_COOKIE_SECURE:
        raise RuntimeError(
            "REFRESH_COOKIE_SAMESITE=none requires REFRESH_COOKIE_SECURE=true"
        )

# Secure flag on the refresh cookie — resolved here after IS_PRODUCTION is
# known. Allows tests / local dev to disable Secure (needed because browsers
# refuse Secure cookies over http://localhost).
REFRESH_COOKIE_SECURE: bool = _parse_bool(
    os.environ.get("REFRESH_COOKIE_SECURE"),
    default=IS_PRODUCTION,
)

# Routes that never require authentication. Matched as exact strings or path
# prefixes. Keep this list minimal — everything else is authenticated.
PUBLIC_PATH_PREFIXES: tuple[str, ...] = (
    "/health",
    "/healthz",
    # AuthContextMiddleware runs INSIDE ApiVersioningMiddleware, so by the
    # time it evaluates this list the path has already been rewritten from
    # /auth/* to /v1/auth/*. Unversioned forms are kept for defense-in-depth
    # in case the middleware chain is ever reordered.
    "/auth/login",
    "/auth/register",
    "/auth/refresh",
    "/auth/logout",
    "/auth/password/forgot",
    "/auth/password/reset",
    "/v1/auth/login",
    "/v1/auth/register",
    "/v1/auth/refresh",
    "/v1/auth/logout",
    "/v1/auth/password/forgot",
    "/v1/auth/password/reset",
    "/docs",
    "/redoc",
    "/openapi.json",
)


def is_public_path(path: str) -> bool:
    """Return True when `path` is an unauthenticated public endpoint."""
    # Root "/" is public (landing ping for health indicators, etc.).
    if path == "/":
        return True
    return any(path == p or path.startswith(p + "/") or path == p for p in PUBLIC_PATH_PREFIXES)


# ── Observability (Sentry) ──────────────────────────────────────────────────
# Optional. When unset, Sentry is disabled (init is a no-op). In production
# we strongly recommend setting it — without it, errors are invisible.
SENTRY_DSN = os.environ.get("SENTRY_DSN", "").strip() or None
SENTRY_TRACES_SAMPLE_RATE = float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1"))
SENTRY_PROFILES_SAMPLE_RATE = float(os.environ.get("SENTRY_PROFILES_SAMPLE_RATE", "0.0"))
# Release tag for grouping deploys in Sentry — Render/Heroku set this automatically.
SENTRY_RELEASE = os.environ.get("RENDER_GIT_COMMIT") or os.environ.get("GIT_COMMIT") or None
