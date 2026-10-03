"""FastAPI dependencies for organization API key authentication."""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, Header, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.api_key import OrganizationApiKey
from app.services.api_key_service import authenticate_api_key, has_scope
from app.services.rate_limiter import PUBLIC_API_KEY_LIMIT, PUBLIC_API_KEY_WINDOW, limiter


def _extract_api_key(authorization: Optional[str], x_api_key: Optional[str]) -> str | None:
    if x_api_key:
        return x_api_key.strip()
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    if not token.startswith("bs_live_"):
        return None
    return token


def require_api_key_scope(required_scope: str):
    """Require a non-revoked organization API key with the requested scope."""

    def _checker(
        response: Response,
        authorization: Optional[str] = Header(None),
        x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
        db: Session = Depends(get_db),
    ) -> OrganizationApiKey:
        secret = _extract_api_key(authorization, x_api_key)
        if not secret:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or malformed API key",
                headers={"WWW-Authenticate": "Bearer"},
            )

        api_key = authenticate_api_key(db, secret=secret)
        if api_key is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or revoked API key",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not has_scope(api_key, required_scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"API key requires {required_scope!r} scope",
            )
        decision = limiter.check(
            key=f"public-api-key:{api_key.id}",
            limit=PUBLIC_API_KEY_LIMIT,
            window_seconds=PUBLIC_API_KEY_WINDOW,
        )
        response.headers["X-API-Key-RateLimit-Limit"] = str(PUBLIC_API_KEY_LIMIT)
        response.headers["X-API-Key-RateLimit-Remaining"] = str(decision.remaining)
        if not decision.allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="API key rate limit exceeded",
                headers={
                    "Retry-After": str(decision.retry_after),
                    "X-API-Key-RateLimit-Limit": str(PUBLIC_API_KEY_LIMIT),
                    "X-API-Key-RateLimit-Remaining": "0",
                },
            )
        return api_key

    return _checker
