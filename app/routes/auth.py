import re
from uuid import uuid4

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import (
    REFRESH_COOKIE_NAME,
    REFRESH_COOKIE_PATH,
    REFRESH_COOKIE_SAMESITE,
    REFRESH_COOKIE_SECURE,
    REFRESH_TOKEN_EXPIRE_DAYS,
)
from app.db import get_db
from app.models.organization import Organization
from app.models.organization_membership import MemberRole, OrganizationMembership
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    MeResponse,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services.account_lockout import lockout
from app.services.audit_service import log_change
from app.services.password_policy import PasswordPolicyError, validate_password
from app.services.rate_limiter import (
    LOGIN_LIMIT,
    LOGIN_WINDOW,
    REFRESH_LIMIT,
    REFRESH_WINDOW,
    REGISTER_LIMIT,
    REGISTER_WINDOW,
    limiter,
)
from app.services.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from app.utils.auth_deps import get_current_user
from app.utils.org_scope import DEFAULT_ORG_ID


def _set_refresh_cookie(
    response: Response, *, user_id: str, org_id: str, token_version: int = 0,
) -> None:
    """Attach a rotated refresh JWT to the response as an httpOnly cookie."""
    refresh = create_refresh_token(
        user_id=user_id, org_id=org_id, token_version=token_version,
    )
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh,
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=REFRESH_COOKIE_SECURE,
        samesite=REFRESH_COOKIE_SAMESITE,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
    )


def _refresh_failure(detail: str, *, clear: bool = True) -> JSONResponse:
    """401 response that also tells the browser to drop the bad cookie.

    We return a JSONResponse instead of `raise HTTPException(...)` because
    FastAPI's exception handler builds its own response and drops cookies
    attached to the route's injected `Response` object.
    """
    resp = JSONResponse(status_code=401, content={"detail": detail})
    if clear:
        _clear_refresh_cookie(resp)
    return resp

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    """Best-effort client IP.

    `request.client.host` is the immediate peer (Render's load balancer).
    When running behind a trusted proxy, X-Forwarded-For holds the real
    client. We take the leftmost entry — note that in prod you want to
    configure uvicorn with --proxy-headers and --forwarded-allow-ips so
    `request.client.host` is already resolved correctly; this fallback
    is defensive.
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def _too_many(detail: str, retry_after: int) -> JSONResponse:
    """429 with a Retry-After header, which well-behaved clients honor."""
    return JSONResponse(
        status_code=429,
        content={"detail": detail},
        headers={"Retry-After": str(retry_after)},
    )


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "org"


def _unique_slug(db: Session, base: str) -> str:
    slug = base
    i = 1
    while db.query(Organization).filter(Organization.slug == slug).first():
        i += 1
        slug = f"{base}-{i}"
    return slug


# ── register ────────────────────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=201)
def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    # Per-IP registration throttle. Keyed on IP alone (not email) because
    # the attacker picks the emails — rate-limiting by their choice of key
    # would defeat the purpose.
    ip = _client_ip(request)
    decision = limiter.check(
        key=f"register:{ip}",
        limit=REGISTER_LIMIT,
        window_seconds=REGISTER_WINDOW,
    )
    if not decision.allowed:
        return _too_many(
            "Too many registrations from this address. Try again later.",
            decision.retry_after,
        )

    # Password policy (length ≥ 12, not digits-only, not obviously weak,
    # not containing the user's own email handle).
    try:
        validate_password(payload.password, email=payload.email)
    except PasswordPolicyError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Check email uniqueness
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    # Create user
    user = User(
        id=str(uuid4()),
        email=payload.email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        is_active=True,
        is_superuser=False,
    )
    db.add(user)
    db.flush()

    # Create org (new or join default)
    if payload.organization_name:
        slug = _unique_slug(db, _slugify(payload.organization_name))
        org = Organization(
            id=str(uuid4()),
            name=payload.organization_name,
            slug=slug,
            is_active=True,
        )
        db.add(org)
        db.flush()
        role = MemberRole.admin  # creator becomes admin of their org
    else:
        org = db.get(Organization, DEFAULT_ORG_ID)
        if not org:
            raise HTTPException(
                status_code=500,
                detail="Default organization not found — run seed.py",
            )
        role = MemberRole.editor

    # Membership
    membership = OrganizationMembership(
        id=str(uuid4()),
        organization_id=org.id,
        user_id=user.id,
        role=role,
        is_default=True,
    )
    db.add(membership)
    db.commit()

    log_change(
        db, "user", user.id, "register",
        actor_id=user.id, organization_id=org.id,
        new_values={"email": user.email, "role": role.value},
    )
    db.commit()

    token = create_access_token(
        user_id=user.id, org_id=org.id, token_version=user.token_version,
    )
    _set_refresh_cookie(
        response, user_id=user.id, org_id=org.id, token_version=user.token_version,
    )
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        organization_id=org.id,
        role=role.value,
    )


# ── login ───────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    # Two layered checks run in order:
    #   1. IP-based rate limiter (cheap, kills password-grinders fast).
    #   2. Per-account lockout (catches distributed spray across many IPs).
    # Precedence: the IP check runs first, so a single-IP grinder will see
    # a 429 well before the 423 lockout ever fires. The lockout only
    # surfaces when the attempts came from many sources.
    ip = _client_ip(request)
    email_key = payload.email.lower()
    rl_key = f"login:{email_key}:{ip}"
    decision = limiter.check(
        key=rl_key, limit=LOGIN_LIMIT, window_seconds=LOGIN_WINDOW,
    )
    if not decision.allowed:
        return _too_many(
            "Too many login attempts. Try again later.",
            decision.retry_after,
        )

    # Account-level lockout: distributed password-spray protection.
    locked, retry_after = lockout.is_locked(email_key)
    if locked:
        return JSONResponse(
            status_code=status.HTTP_423_LOCKED,
            content={"detail": "Account temporarily locked due to repeated failed logins."},
            headers={"Retry-After": str(retry_after)},
        )

    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        # Count this against the account, not just the IP.
        lockout.record_failure(email_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    if not user.is_active:
        raise HTTPException(status_code=401, detail="Account is inactive")

    # Successful login — clear both the IP bucket and the account
    # lockout counter so a user who mistyped twice doesn't carry the
    # failed attempts forward into their next session.
    limiter.reset(rl_key)
    lockout.reset(email_key)

    # Pick the default membership, or the first one
    membership = (
        db.query(OrganizationMembership)
        .filter(OrganizationMembership.user_id == user.id)
        .order_by(OrganizationMembership.is_default.desc(), OrganizationMembership.joined_at.asc())
        .first()
    )
    if not membership:
        raise HTTPException(status_code=403, detail="User has no organization membership")

    token = create_access_token(
        user_id=user.id, org_id=membership.organization_id,
        token_version=user.token_version,
    )
    _set_refresh_cookie(
        response, user_id=user.id, org_id=membership.organization_id,
        token_version=user.token_version,
    )
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        organization_id=membership.organization_id,
        role=membership.role.value,
    )


# ── refresh ─────────────────────────────────────────────────────────────────

@router.post("/refresh", response_model=TokenResponse)
def refresh(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    refresh_cookie: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
):
    """Exchange a valid refresh cookie for a new access token.

    Rotates the refresh cookie on every call: the old refresh token is
    replaced with a fresh one carrying a new `exp`, so a stolen cookie
    has a bounded useful lifetime even without a server-side blocklist.
    Public route (see PUBLIC_PATH_PREFIXES); authentication is via the
    cookie, not an Authorization header.
    """
    ip = _client_ip(request)
    decision = limiter.check(
        key=f"refresh:{ip}",
        limit=REFRESH_LIMIT,
        window_seconds=REFRESH_WINDOW,
    )
    if not decision.allowed:
        return _too_many(
            "Too many refresh attempts. Try again later.",
            decision.retry_after,
        )

    if not refresh_cookie:
        # No cookie to clear — just 401.
        return _refresh_failure("Missing refresh cookie", clear=False)
    claims = decode_refresh_token(refresh_cookie)
    if not claims:
        return _refresh_failure("Invalid or expired refresh token")

    user_id = claims.get("sub")
    org_id = claims.get("org_id")
    if not user_id or not org_id:
        return _refresh_failure("Malformed refresh token")

    user = db.get(User, user_id)
    if not user or not user.is_active:
        return _refresh_failure("User no longer active")

    # Token-version revocation check: /auth/logout-all bumps user.token_version,
    # which invalidates every refresh cookie minted before that bump. A claim
    # missing `tv` is treated as version 0 (legacy tokens minted pre-feature).
    cookie_tv = claims.get("tv", 0)
    if cookie_tv != user.token_version:
        return _refresh_failure("Refresh token revoked")

    membership = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.organization_id == org_id,
        )
        .first()
    )
    if not membership:
        return _refresh_failure("Membership revoked")

    access = create_access_token(
        user_id=user_id, org_id=org_id, token_version=user.token_version,
    )
    _set_refresh_cookie(
        response, user_id=user_id, org_id=org_id, token_version=user.token_version,
    )
    return TokenResponse(
        access_token=access,
        user_id=user_id,
        organization_id=org_id,
        role=membership.role.value,
    )


# ── logout ──────────────────────────────────────────────────────────────────

@router.post("/logout", status_code=204)
def logout(response: Response):
    """Clear the refresh cookie. Idempotent; safe to call without a session."""
    _clear_refresh_cookie(response)
    # Returning None lets FastAPI use the injected `response` (with the
    # Set-Cookie clearing header) rather than constructing a new 204.
    return None


# ── logout-all ─────────────────────────────────────────────────────────────

@router.post("/logout-all", status_code=204)
def logout_all(
    response: Response,
    db: Session = Depends(get_db),
    principal: dict = Depends(get_current_user),
):
    """Revoke every outstanding refresh token for the current user.

    Bumps `user.token_version`. The next /auth/refresh that arrives with a
    cookie carrying the old version compares `claims['tv'] != user.token_version`
    and is rejected with 401. The immediate access token the caller is holding
    stays valid for the remainder of its 15-minute TTL — that's an accepted
    tradeoff to avoid a per-request DB lookup on every authenticated call.
    """
    user: User = principal["user"]
    user.token_version = (user.token_version or 0) + 1
    db.add(user)
    db.commit()
    log_change(
        db, "user", user.id, "logout_all",
        actor_id=user.id, organization_id=principal["org_id"],
        new_values={"token_version": user.token_version},
    )
    db.commit()
    _clear_refresh_cookie(response)
    return None


# ── me ──────────────────────────────────────────────────────────────────────

@router.get("/me", response_model=MeResponse)
def me(principal: dict = Depends(get_current_user)):
    return MeResponse(
        user=UserResponse.model_validate(principal["user"]),
        organization_id=principal["org_id"],
        role=principal["role"],
    )
