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

# JWT settings (will be used by auth layer)
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
ALGORITHM = "HS256"

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

# Routes that never require authentication. Matched as exact strings or path
# prefixes. Keep this list minimal — everything else is authenticated.
PUBLIC_PATH_PREFIXES: tuple[str, ...] = (
    "/health",
    "/healthz",
    "/auth/login",
    "/auth/register",
    "/auth/refresh",
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
