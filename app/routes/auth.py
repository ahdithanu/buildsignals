import re
from uuid import uuid4

import pyotp
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.config import REFRESH_COOKIE_NAME
from app.db import get_db
from app.models.organization import Organization
from app.models.organization_membership import MemberRole, OrganizationMembership
from app.models.user import User
from app.schemas.auth import (
    DeleteAccountRequest,
    LoginRequest,
    MeResponse,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services.account_lockout import lockout
from app.services.audit_service import log_change
from app.services.browser_sessions import (
    browser_request,
    issue_browser_session,
    refresh_binding,
    revoke_browser_session,
)
from app.services.password_policy import PasswordPolicyError, validate_password
from app.services.rate_limiter import (
    LOGIN_ACCOUNT_LIMIT,
    LOGIN_IP_LIMIT,
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
    decode_refresh_token,
    dummy_verify,
    hash_password,
    verify_password,
)
from app.utils.auth_deps import get_current_user
from app.utils.client_address import client_address as _client_ip


def _refresh_failure(detail: str) -> JSONResponse:
    """Fail closed without mutating any potentially newer browser cookie."""
    # Never clear a cookie from an error response: it may arrive after login.
    return JSONResponse(status_code=401, content={"detail": detail}, headers={"Cache-Control": "no-store"})

router = APIRouter(prefix="/auth", tags=["auth"])


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


# ── register ────────────────────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=201)
def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    browser_request(request)
    # Per-IP registration throttle. Keyed on IP alone (not email) because
    # the attacker picks the emails — rate-limiting by their choice of key
    # would defeat the purpose.
    ip = _client_ip(request)
    decision = limiter.check(
        key=f"register:{ip}",
        limit=REGISTER_LIMIT,
        window_seconds=REGISTER_WINDOW,
        required=True,
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

    # Public signup always creates a tenant; joining one requires an admin grant.
    org_name = (payload.organization_name or "").strip()
    if not org_name:
        owner_name = " ".join(payload.full_name.split())
        suffix = "'s workspace"
        org_name = (
            f"{owner_name[:255 - len(suffix)].rstrip()}{suffix}"
            if owner_name else "Personal workspace"
        )
    org_id = str(uuid4())
    # 63 characters + separator + UUID fit the 100-character slug column.
    # The UUID also keeps concurrent same-name signups from sharing a slug.
    slug_base = _slugify(org_name)[:63].rstrip("-")
    org = Organization(
        id=org_id,
        name=org_name,
        slug=f"{slug_base}-{org_id}",
        is_active=True,
    )
    db.add(org)
    db.flush()
    role = MemberRole.admin

    # Membership
    membership = OrganizationMembership(
        id=str(uuid4()),
        organization_id=org.id,
        user_id=user.id,
        role=role,
        is_default=True,
    )
    db.add(membership)
    log_change(
        db, "user", user.id, "register",
        actor_id=user.id, organization_id=org.id,
        new_values={"email": user.email, "role": role.value},
    )
    result = issue_browser_session(db, request, response, user=user, org_id=org.id, role=role.value)
    db.commit()
    return result


# ── login ───────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    browser_request(request)
    # Admission budgets run before password hashing. Broad IP/account budgets
    # cannot be cleared by a racing successful login; failure locks are separate.
    ip = _client_ip(request)
    email_key = payload.email.lower()
    rl_key = f"login:{email_key}:{ip}"
    for key, limit in (
        (f"login:ip:{ip}", LOGIN_IP_LIMIT),
        (rl_key, LOGIN_LIMIT),
        (f"login:account:{email_key}", LOGIN_ACCOUNT_LIMIT),
    ):
        decision = limiter.check(
            key=key, limit=limit, window_seconds=LOGIN_WINDOW, required=True,
        )
        if not decision.allowed:
            return _too_many("Too many login attempts. Try again later.", decision.retry_after)

    # Account-level lockout: distributed password-spray protection.
    locked, retry_after = lockout.is_locked(email_key)
    if locked:
        return JSONResponse(
            status_code=status.HTTP_423_LOCKED,
            content={"detail": "Account temporarily locked due to repeated failed logins."},
            headers={"Retry-After": str(retry_after)},
        )

    user = db.query(User).filter(User.email == payload.email).first()
    if user:
        password_ok = verify_password(payload.password, user.password_hash)
    else:
        # Burn the same bcrypt CPU as a real verify so a missing email can't be
        # distinguished from a wrong password by response timing.
        dummy_verify()
        password_ok = False
    if not user or not password_ok:
        # Count this against the account, not just the IP.
        lockout.record_failure(email_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    if not user.is_active:
        raise HTTPException(status_code=401, detail="Account is inactive")

    # 2FA enforcement: if the user has confirmed 2FA enrollment, a valid
    # TOTP code is required to mint a token. Missing vs invalid get distinct
    # X-Auth-Reason headers so the frontend can render the right UI ("show
    # the TOTP prompt" vs "tell the user the code was wrong") without
    # leaking which check failed in a generic 401 message body.
    # Failures here record against the account lockout the same way a wrong
    # password would, so an attacker who guessed the password can't grind
    # codes indefinitely.
    if user.totp_enabled:
        if not payload.totp_code:
            lockout.record_failure(email_key)
            return JSONResponse(
                status_code=401,
                content={"detail": "TOTP code required"},
                headers={"X-Auth-Reason": "totp_required"},
            )
        from app.services.mfa_secrets import read_secret

        secret = read_secret(user)
        if not secret or not pyotp.TOTP(secret).verify(
            payload.totp_code, valid_window=1,
        ):
            lockout.record_failure(email_key)
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid TOTP code"},
                headers={"X-Auth-Reason": "totp_invalid"},
            )

    # Clear consecutive-failure state, but retain the aggregate admission
    # budgets that bound parallel attempts and repeated successful logins.
    limiter.reset(rl_key, required=True)
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

    organization = db.get(Organization, membership.organization_id)
    if not organization or not organization.is_active:
        raise HTTPException(status_code=403, detail="Organization is unavailable")
    result = issue_browser_session(db, request, response, user=user,
                                   org_id=membership.organization_id, role=membership.role.value)
    db.commit()
    return result


# ── refresh ─────────────────────────────────────────────────────────────────

@router.post("/refresh", response_model=TokenResponse)
def refresh(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    refresh_cookie: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
):
    """Exchange a revocation-bound cookie without any Set-Cookie side effect."""
    browser_request(request)
    response.headers["Cache-Control"] = "no-store"
    ip = _client_ip(request)
    decision = limiter.check(
        key=f"refresh:{ip}",
        limit=REFRESH_LIMIT,
        window_seconds=REFRESH_WINDOW,
        required=True,
    )
    if not decision.allowed:
        return _too_many(
            "Too many refresh attempts. Try again later.",
            decision.retry_after,
        )

    if not refresh_cookie:
        # No cookie to clear — just 401.
        return _refresh_failure("Missing refresh cookie")
    claims = decode_refresh_token(refresh_cookie)
    if not claims:
        return _refresh_failure("Invalid or expired refresh token")
    binding = refresh_binding(db, request, claims)

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
    if type(cookie_tv) is not int or cookie_tv != user.token_version:
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
    organization = db.get(Organization, org_id)
    if not organization or not organization.is_active:
        return _refresh_failure("Organization is unavailable")

    access = create_access_token(
        user_id=user_id, org_id=org_id, token_version=user.token_version, browser_session=binding,
    )
    return TokenResponse(
        access_token=access,
        user_id=user_id,
        organization_id=org_id,
        role=membership.role.value,
    )


# ── logout ──────────────────────────────────────────────────────────────────

@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    """Revoke only this browser family. Never expire a newer login's cookie."""
    revoke_browser_session(db, request)
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return None


# ── logout-all ─────────────────────────────────────────────────────────────

@router.post("/logout-all", status_code=204)
def logout_all(
    response: Response,
    db: Session = Depends(get_db),
    principal: dict = Depends(get_current_user),
):
    """Revoke every outstanding refresh token for the current user.

    Bumps `user.token_version`. Both refresh and business-route identity checks
    reject earlier versions immediately on their next request. No clearing
    Set-Cookie is sent, so a late response cannot overwrite a newer login.
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
    response.headers["Cache-Control"] = "no-store"
    return None


# ── me ──────────────────────────────────────────────────────────────────────

@router.get("/me", response_model=MeResponse)
def me(principal: dict = Depends(get_current_user)):
    return MeResponse(
        user=UserResponse.model_validate(principal["user"]),
        organization_id=principal["org_id"],
        role=principal["role"],
    )


# ── delete account (GDPR self-service erasure) ──────────────────────────────

def _lock_account_organizations(db: Session, *, user_id: str) -> tuple[User, set[str]]:
    org_ids = {
        row[0] for row in db.query(OrganizationMembership.organization_id)
        .filter(OrganizationMembership.user_id == user_id).all()
    }
    # Same parent-row lock as organization member mutations. Lock ALL current
    # memberships (not only admins), so a concurrent promotion cannot escape the
    # check. Deterministic ordering also serializes multi-organization deletions.
    for org_id in sorted(org_ids):
        if db.get_bind().dialect.name == "sqlite":
            db.execute(
                update(Organization).where(Organization.id == org_id)
                .values(updated_at=Organization.updated_at)
            )
        db.query(Organization).filter(Organization.id == org_id).with_for_update().first()

    # Always take the user lock AFTER organization locks. PostgreSQL FK checks
    # then prevent a new membership from being inserted during the deletion.
    user = (
        db.query(User).filter(User.id == user_id)
        .with_for_update().populate_existing().first()
    )
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    current_ids = {
        row[0] for row in db.query(OrganizationMembership.organization_id)
        .filter(OrganizationMembership.user_id == user_id).all()
    }
    if not current_ids.issubset(org_ids):
        # Do not acquire additional parents out of order. Retry the whole action
        # if an invitation committed while the initial locks were being acquired.
        raise HTTPException(status_code=409, detail="Memberships changed; retry account deletion")
    return user, current_ids


@router.post("/delete-account", status_code=204)
def delete_account(
    payload: DeleteAccountRequest,
    response: Response,
    db: Session = Depends(get_db),
    principal: dict = Depends(get_current_user),
):
    """Permanently delete the caller's own account (GDPR right to erasure).

    Requires re-entering the current password. Irreversible.

    The user row holds the personal data (email, name, password hash, 2FA
    secret); deleting it is the erasure. FKs handle the rest: memberships and
    password-reset tokens cascade away, and authored records (deals, audit
    rows, buy boxes) have their `created_by`/`actor_id` set NULL — the org's
    data stays, the personal link is severed.

    Guard: a user who is the SOLE active admin of an org can't self-delete — that
    would orphan the org with no one able to manage it. They must promote
    another admin (or delete the org) first.
    """
    user: User = principal["user"]

    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=403, detail="Password is incorrect")

    verified_hash, verified_version = user.password_hash, user.token_version
    user, org_ids = _lock_account_organizations(db, user_id=user.id)
    if user.password_hash != verified_hash or user.token_version != verified_version:
        raise HTTPException(status_code=401, detail="Credentials changed; sign in again")
    if principal["org_id"] not in org_ids:
        raise HTTPException(status_code=403, detail="Organization membership revoked")

    # Re-read roles after acquiring locks; cached membership roles may be stale.
    admin_memberships = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.role == MemberRole.admin,
        )
        .populate_existing()
        .all()
    )
    sole_admin_orgs: list[str] = []
    for m in admin_memberships:
        other_admins = (
            db.query(OrganizationMembership)
            .join(User, User.id == OrganizationMembership.user_id)
            .filter(
                OrganizationMembership.organization_id == m.organization_id,
                OrganizationMembership.role == MemberRole.admin,
                OrganizationMembership.user_id != user.id,
                User.is_active.is_(True),
            )
            .count()
        )
        if other_admins == 0:
            org = db.get(Organization, m.organization_id)
            sole_admin_orgs.append(org.name if org else m.organization_id)
    if sole_admin_orgs:
        raise HTTPException(
            status_code=409,
            detail=(
                "You are the only admin of: "
                + ", ".join(sole_admin_orgs)
                + ". Promote another active admin or delete the organization first."
            ),
        )

    user_id = user.id
    # Audit before delete. The row's actor_id FK is SET NULL when the user
    # row goes, so the trail keeps entity_id + action, not a dangling pointer.
    log_change(
        db, "user", user_id, "account_deleted",
        actor_id=user_id, organization_id=principal["org_id"],
    )
    # Flush the audit before the user's FK is nulled, but retain every lock
    # until both audit and deletion commit atomically.
    db.flush()
    db.delete(user)
    db.commit()

    response.headers["Cache-Control"] = "no-store"
    return None
