"""TOTP-based 2FA enrollment and management.

Flow:
  1. POST /auth/2fa/setup    — mint a base32 secret, return secret + otpauth URI
                               (frontend renders QR). totp_enabled stays False.
  2. POST /auth/2fa/verify   — user submits a code from their authenticator;
                               if it validates, flip totp_enabled=True.
  3. POST /auth/2fa/disable  — requires BOTH current password AND a valid TOTP
                               code, so a stolen access token alone can't turn
                               off the second factor.

Login enforcement lives in app/routes/auth.py — once `totp_enabled` is True,
/auth/login refuses to issue a token unless a valid `totp_code` accompanies
the credentials.
"""
from __future__ import annotations

import pyotp
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.user import User
from app.services.audit_service import log_change
from app.services.mfa_secrets import enrollment_ready, read_secret, store_secret
from app.services.rate_limiter import limiter
from app.services.security import verify_password
from app.utils.auth_deps import get_current_user

router = APIRouter(prefix="/auth/2fa", tags=["auth"])

CODE_ATTEMPT_LIMIT = 10
CODE_ATTEMPT_WINDOW = 15 * 60


def _limited_principal(principal: dict = Depends(get_current_user)) -> dict:
    # Shared across verify/disable, organizations, tokens, and source IPs.
    decision = limiter.check(
        key=f"mfa:code:{principal['user_id']}",
        limit=CODE_ATTEMPT_LIMIT,
        window_seconds=CODE_ATTEMPT_WINDOW,
        required=True,
    )
    if not decision.allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many authenticator attempts. Try again later.",
            headers={"Retry-After": str(decision.retry_after), "Cache-Control": "no-store"},
        )
    return principal


def _locked_user(db: Session, principal: dict) -> User:
    # Authentication may have loaded this row before a competing change committed.
    with db.no_autoflush:
        if db.get_bind().dialect.name == "sqlite":
            db.execute(
                update(User).where(User.id == principal["user_id"])
                .values(updated_at=User.updated_at)
                .execution_options(synchronize_session=False)
            )
        user = (
            db.query(User).filter(User.id == principal["user_id"])
            .populate_existing().with_for_update().first()
        )
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


def _commit_change(db: Session, user: User, principal: dict, action: str) -> None:
    try:
        db.add(user)
        log_change(
            db, "user", user.id, action,
            actor_id=user.id, organization_id=principal["org_id"],
        )
        db.commit()
    except Exception:
        db.rollback()
        raise


# ── Schemas ────────────────────────────────────────────────────────────────

class SetupResponse(BaseModel):
    secret: str
    otpauth_uri: str


class StatusResponse(BaseModel):
    enabled: bool
    enrollment_ready: bool


class VerifyRequest(BaseModel):
    code: str


class DisableRequest(BaseModel):
    password: str
    code: str


# ── Routes ─────────────────────────────────────────────────────────────────

@router.get("/status", response_model=StatusResponse)
def authenticator_status(
    response: Response,
    principal: dict = Depends(get_current_user),
):
    """Report account state independently from enrollment key availability."""
    response.headers["Cache-Control"] = "no-store"
    return StatusResponse(
        enabled=principal["user"].totp_enabled,
        enrollment_ready=enrollment_ready(),
    )


@router.post("/setup", response_model=SetupResponse)
def setup(
    response: Response,
    db: Session = Depends(get_db),
    principal: dict = Depends(get_current_user),
):
    """Begin 2FA enrollment.

    Mints a new base32 secret and persists it on the user row. The user is
    NOT considered 2FA-enabled until they prove possession of the secret by
    submitting a code to /verify — until then, login flow is unchanged.

    Calling /setup again on an unconfirmed enrollment rotates the secret,
    which is the right behavior if the QR was never scanned or the user
    wants to restart. Calling it on an *already-enabled* user 400s, so the
    user must /disable first.
    """
    user = _locked_user(db, principal)
    if user.totp_enabled:
        raise HTTPException(
            status_code=400,
            detail="2FA already enabled. Disable it first to re-enroll.",
        )
    secret = pyotp.random_base32()
    store_secret(user, secret)
    db.add(user)
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    otpauth_uri = pyotp.TOTP(secret).provisioning_uri(
        name=user.email, issuer_name="BuildSignals",
    )
    result = SetupResponse(secret=secret, otpauth_uri=otpauth_uri)
    _commit_change(db, user, principal, "2fa_setup")
    response.headers["Cache-Control"] = "no-store"
    return result


@router.post("/verify", status_code=204)
def verify(
    payload: VerifyRequest,
    db: Session = Depends(get_db),
    principal: dict = Depends(_limited_principal),
):
    """Confirm the user can generate codes from the secret minted at /setup.

    Uses `valid_window=1` to tolerate ~30s of clock skew between the device
    and the server — a single window on either side of the current step.
    """
    user: User = principal["user"]
    secret = read_secret(user)
    if not secret:
        raise HTTPException(
            status_code=409,
            detail="2FA setup not initiated. Call /auth/2fa/setup first.",
        )
    if not pyotp.TOTP(secret).verify(payload.code, valid_window=1):
        raise HTTPException(status_code=400, detail="Invalid TOTP code")
    user.totp_enabled = True
    _commit_change(db, user, principal, "2fa_enabled")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/disable", status_code=204)
def disable(
    payload: DisableRequest,
    db: Session = Depends(get_db),
    principal: dict = Depends(_limited_principal),
):
    """Turn off 2FA. Requires the current password AND a valid TOTP code.

    Defense in depth: a stolen access token alone is not enough to weaken
    the account — the attacker would also need to know the password and
    have a working second factor. On success we drop both `totp_enabled`
    and the secret, so re-enabling means a fresh /setup + /verify pair.
    """
    user = _locked_user(db, principal)
    if not user.totp_enabled:
        raise HTTPException(status_code=409, detail="2FA is not enabled")
    # We return a generic 401 for either failure so we don't tell an
    # attacker *which* of password / code was wrong.
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    secret = read_secret(user)
    if not secret or not pyotp.TOTP(secret).verify(
        payload.code, valid_window=1,
    ):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    user.totp_enabled = False
    user.totp_secret = None
    user.totp_secret_ciphertext = None
    db.add(user)
    db.commit()
    log_change(
        db, "user", user.id, "2fa_disabled",
        actor_id=user.id, organization_id=principal["org_id"],
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
