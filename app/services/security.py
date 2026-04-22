"""Password hashing and JWT token utilities."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    ALGORITHM,
    REFRESH_TOKEN_EXPIRE_DAYS,
    SECRET_KEY,
)

REFRESH_TOKEN_TYPE = "refresh"
ACCESS_TOKEN_TYPE = "access"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── Password hashing ────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False


# ── JWT ─────────────────────────────────────────────────────────────────────

def create_access_token(
    *, user_id: str, org_id: str, expires_minutes: Optional[int] = None,
) -> str:
    """Create a short-lived access JWT, carried in the Authorization header."""
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": user_id,
        "org_id": org_id,
        "typ": ACCESS_TOKEN_TYPE,
        "exp": expire,
        # `jti` guarantees each minted token is unique even when minted in
        # the same second (JWT `exp` is second-granular). Also a hook for a
        # future server-side blocklist without reshaping the token format.
        "jti": uuid4().hex,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(*, user_id: str, org_id: str) -> str:
    """Create a long-lived refresh JWT, carried as an httpOnly cookie."""
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": user_id,
        "org_id": org_id,
        "typ": REFRESH_TOKEN_TYPE,
        "exp": expire,
        "jti": uuid4().hex,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """Decode an access JWT. Rejects tokens missing typ=='access' so a stolen
    refresh cookie can never be used as a bearer token, and vice versa."""
    try:
        claims = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
    # Legacy tokens minted before the typ claim existed are still accepted
    # as access tokens — they can only be access tokens since refresh tokens
    # are new. Drop this branch once all legacy tokens have expired.
    typ = claims.get("typ", ACCESS_TOKEN_TYPE)
    if typ != ACCESS_TOKEN_TYPE:
        return None
    return claims


def decode_refresh_token(token: str) -> Optional[dict]:
    """Decode a refresh JWT. Rejects anything missing typ=='refresh'."""
    try:
        claims = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
    if claims.get("typ") != REFRESH_TOKEN_TYPE:
        return None
    return claims
