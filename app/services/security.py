"""Password hashing and JWT token utilities."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

import bcrypt
import jwt

from app.config import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    ALGORITHM,
    REFRESH_TOKEN_EXPIRE_DAYS,
    SECRET_KEY,
)

REFRESH_TOKEN_TYPE = "refresh"
ACCESS_TOKEN_TYPE = "access"


# ── Password hashing ────────────────────────────────────────────────────────
#
# We call bcrypt directly rather than through passlib. passlib 1.7.4 is the
# last release (unmaintained since 2020) and its backend self-test crashes
# under bcrypt >= 5, which pins the whole app to bcrypt 4.x. Talking to bcrypt
# directly removes that ceiling and drops an abandoned dependency.
#
# bcrypt only considers the first 72 BYTES of a password; bytes past that are
# ignored. passlib silently truncated to 72 bytes, and bcrypt 5 now *raises*
# on longer input instead of truncating. To (a) keep verifying hashes that
# passlib wrote and (b) not crash on a >72-byte password, we truncate to 72
# bytes ourselves before every hash and check — exactly reproducing the old
# behavior, so existing stored hashes still validate unchanged.
_BCRYPT_MAX_BYTES = 72


def _prepare(password: str) -> bytes:
    """Encode + truncate to bcrypt's 72-byte input limit (matches passlib)."""
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prepare(password), bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prepare(plain), hashed.encode("ascii"))
    except (ValueError, TypeError):
        # Malformed/empty stored hash, or non-ascii hash string. Treat any
        # such case as a failed verification rather than a 500.
        return False


# A real bcrypt hash (cost 12) used only to burn the same ~CPU as a genuine
# verify when a login targets a non-existent email. Without this, the missing
# user short-circuits before bcrypt runs and the fast response reveals which
# emails are registered (timing-based user enumeration). The plaintext behind
# it is irrelevant — we discard the result.
_DUMMY_HASH = "$2b$12$C6UzMDM.H6dfI/f/IKcEeO3Q0m3F.p3nJ0aYtQ8kFqf3zJ0mZ0aZ2"


def dummy_verify() -> None:
    """Run a throwaway bcrypt verify to keep login timing constant when the
    user lookup missed. Call it in the no-such-user branch."""
    try:
        bcrypt.checkpw(b"timing-equalizer", _DUMMY_HASH.encode("ascii"))
    except (ValueError, TypeError):
        pass


# ── JWT ─────────────────────────────────────────────────────────────────────

def create_access_token(
    *, user_id: str, org_id: str, token_version: int = 0,
    expires_minutes: Optional[int] = None,
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
        # `tv` (token version) is bumped by /auth/logout-all to invalidate
        # every outstanding refresh cookie for this user. Embedded here too
        # so a future check could reject access tokens after logout-all;
        # today we accept the 15-min window as a documented tradeoff.
        "tv": token_version,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(*, user_id: str, org_id: str, token_version: int = 0) -> str:
    """Create a long-lived refresh JWT, carried as an httpOnly cookie."""
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": user_id,
        "org_id": org_id,
        "typ": REFRESH_TOKEN_TYPE,
        "exp": expire,
        "jti": uuid4().hex,
        "tv": token_version,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """Decode an access JWT. Rejects tokens missing typ=='access' so a stolen
    refresh cookie can never be used as a bearer token, and vice versa."""
    try:
        claims = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
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
    except jwt.PyJWTError:
        return None
    if claims.get("typ") != REFRESH_TOKEN_TYPE:
        return None
    return claims
