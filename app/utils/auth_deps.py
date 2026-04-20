"""FastAPI dependencies for extracting the authenticated user from requests."""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.organization_membership import OrganizationMembership, MemberRole
from app.models.user import User
from app.services.security import decode_access_token
from app.utils.org_scope import RequestContext


class AuthPrincipal(RequestContext):
    """Extends RequestContext with the role for RBAC checks.

    Drop-in replacement for RequestContext — still unpacks as (org_id, user_id).
    """
    role: str  # type: ignore[assignment]


def _parse_bearer(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def get_current_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> dict:
    """Resolve the JWT into a {user, org_id, role} dict.

    Raises 401 if the token is missing, invalid, expired, or the user
    is inactive. Raises 403 if the user is not a member of the claimed org.
    """
    token = _parse_bearer(authorization)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    claims = decode_access_token(token)
    if not claims:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = claims.get("sub")
    org_id = claims.get("org_id")
    if not user_id or not org_id:
        raise HTTPException(status_code=401, detail="Token missing required claims")

    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    membership = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.organization_id == org_id,
        )
        .first()
    )
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not a member of this organization",
        )

    return {
        "user": user,
        "org_id": org_id,
        "user_id": user_id,
        "role": membership.role.value,
    }


def require_role(*allowed: MemberRole):
    """Dependency factory for RBAC.

    Permissive: if NO Authorization header is present, the request runs in
    demo mode (default-org / system user) and is allowed through. This keeps
    backward compatibility with the unauth'd demo flow while still enforcing
    role checks for any request that DOES present a token.

    Usage:
        @router.delete(..., dependencies=[Depends(require_role(MemberRole.admin))])
    """
    allowed_values = {r.value for r in allowed}

    def _checker(
        authorization: Optional[str] = Header(None),
        db: Session = Depends(get_db),
    ) -> Optional[dict]:
        # Demo mode passthrough — no token, no enforcement
        if not authorization:
            return None
        # Token present → must be valid AND have a permitted role
        principal = get_current_user(authorization=authorization, db=db)
        if principal["role"] not in allowed_values:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {sorted(allowed_values)}",
            )
        return principal

    return _checker


def require_role_strict(*allowed: MemberRole):
    """Strict variant: ALWAYS requires authentication. Use for sensitive
    endpoints like member management where the demo flow shouldn't apply."""
    allowed_values = {r.value for r in allowed}

    def _checker(principal: dict = Depends(get_current_user)) -> dict:
        if principal["role"] not in allowed_values:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {sorted(allowed_values)}",
            )
        return principal

    return _checker
