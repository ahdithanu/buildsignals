"""FastAPI dependencies for organization API key authentication."""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.api_key import OrganizationApiKey
from app.services.api_key_service import authenticate_api_key, has_scope


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
        return api_key

    return _checker
