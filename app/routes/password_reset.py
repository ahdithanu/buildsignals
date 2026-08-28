"""Password reset flow: /auth/password/forgot and /auth/password/reset.

Security properties this module is responsible for:

- **No account enumeration.** `/forgot` always returns 204, whether or
  not the email maps to a real user. An attacker watching the response
  cannot learn which emails are registered.
- **Tokens are single-use, short-lived, and stored hashed.** The plaintext
  exists only in the outgoing email URL; the DB holds a SHA-256 hex
  digest. A read-only DB leak cannot be replayed.
- **Per-IP and per-email rate limits** on /forgot prevent abuse of the
  send-email side-channel.
- **Successful reset invalidates every existing session** by bumping
  `user.token_version`, which the refresh-cookie path checks against.
"""
from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.password_reset_token import PasswordResetToken
from app.models.user import User
from app.services.account_lockout import lockout
from app.services.audit_service import log_change
from app.services.email_service import get_email_service
from app.services.password_policy import PasswordPolicyError, validate_password
from app.services.rate_limiter import limiter
from app.services.security import hash_password

router = APIRouter(prefix="/auth/password", tags=["auth"])


# ── Tunables ──────────────────────────────────────────────────────────────

# Per-IP throttle on /forgot — broad bucket to catch a single source
# blasting many emails through the reset side-channel.
FORGOT_IP_LIMIT = 10
FORGOT_IP_WINDOW = 60 * 60  # 1 hour

# Per-email throttle — even from many IPs, we don't want to spam a single
# real user with reset emails (or burn through their inbox quota).
FORGOT_EMAIL_LIMIT = 3
FORGOT_EMAIL_WINDOW = 60 * 60

# Per-IP throttle on /reset — blunts token-brute-forcing attempts. 20/hr
# is generous since real users follow a link from email exactly once.
RESET_IP_LIMIT = 20
RESET_IP_WINDOW = 60 * 60

TOKEN_TTL = timedelta(hours=1)


# ── Schemas ───────────────────────────────────────────────────────────────


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


# ── Helpers ───────────────────────────────────────────────────────────────


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def _too_many(detail: str, retry_after: int) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": detail},
        headers={"Retry-After": str(retry_after)},
    )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def _app_base_url() -> str:
    return os.environ.get("APP_BASE_URL", "http://localhost:5173")


def _render_email(reset_url: str) -> tuple[str, str]:
    """Return (text, html) bodies for the reset email."""
    text = (
        "You (or someone using your email) asked to reset your BuildSignals "
        "password.\n\n"
        f"Open this link to choose a new password — it expires in 1 hour:\n\n"
        f"{reset_url}\n\n"
        "If you didn't request this, you can ignore this email; your "
        "password won't change.\n"
    )
    html = f"""\
<p>You (or someone using your email) asked to reset your BuildSignals password.</p>
<p>
  <a href="{reset_url}">Choose a new password</a> &mdash; the link expires in 1 hour.
</p>
<p>If you didn't request this, you can ignore this email; your password won't change.</p>
"""
    return text, html


# ── Endpoints ─────────────────────────────────────────────────────────────


@router.post("/forgot", status_code=204)
def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Kick off a password reset by emailing a one-time link.

    Always returns 204. The response is identical whether or not the
    email matches a known account — this is the whole point of the
    endpoint from a security standpoint.
    """
    ip = _client_ip(request)
    email_key = payload.email.lower()

    # Per-IP bucket: stop one source from harvesting the email side-channel.
    ip_decision = limiter.check(
        key=f"forgot:ip:{ip}",
        limit=FORGOT_IP_LIMIT,
        window_seconds=FORGOT_IP_WINDOW,
    )
    if not ip_decision.allowed:
        return _too_many(
            "Too many password reset requests. Try again later.",
            ip_decision.retry_after,
        )

    # Per-email bucket: protect real users from being spammed even when
    # the requests are spread across many source IPs.
    email_decision = limiter.check(
        key=f"forgot:email:{email_key}",
        limit=FORGOT_EMAIL_LIMIT,
        window_seconds=FORGOT_EMAIL_WINDOW,
    )
    if not email_decision.allowed:
        return _too_many(
            "Too many password reset requests for this account. Try again later.",
            email_decision.retry_after,
        )

    user = db.query(User).filter(User.email == payload.email).first()

    # Same response shape whether we send mail or not — *don't* short-circuit
    # before this point in a way an attacker can time.
    if user and user.is_active:
        plaintext = secrets.token_urlsafe(32)
        row = PasswordResetToken(
            user_id=user.id,
            token_hash=_hash_token(plaintext),
            expires_at=_utcnow() + TOKEN_TTL,
        )
        db.add(row)

        log_change(
            db,
            "user",
            user.id,
            "password_reset_requested",
            actor_id=user.id,
            new_values={"ip": ip},
        )
        db.commit()

        reset_url = f"{_app_base_url()}/reset-password?token={plaintext}"
        text, html = _render_email(reset_url)
        # Email send is fire-and-forget from the endpoint's perspective —
        # we already committed the token row, so a transient SMTP blip
        # doesn't strand us in a "row but no email" inconsistency that
        # the user could recover from by re-requesting.
        get_email_service().send(
            to=user.email,
            subject="Reset your BuildSignals password",
            html=html,
            text=text,
        )

    return Response(status_code=204)


@router.post("/reset", status_code=204)
def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Burn a reset token and set a new password."""
    ip = _client_ip(request)
    decision = limiter.check(
        key=f"reset:ip:{ip}",
        limit=RESET_IP_LIMIT,
        window_seconds=RESET_IP_WINDOW,
    )
    if not decision.allowed:
        return _too_many(
            "Too many password reset attempts. Try again later.",
            decision.retry_after,
        )

    token_hash = _hash_token(payload.token)
    row = (
        db.query(PasswordResetToken)
        .filter(PasswordResetToken.token_hash == token_hash)
        .first()
    )
    # One error message for "not found", "expired", and "already used" —
    # we don't want the response to differentiate, since each variant
    # leaks information about token state to a guesser.
    # SQLite strips tzinfo on round-trip; coerce to aware UTC for compare.
    expires_at = row.expires_at if row is not None else None
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if (
        row is None
        or row.used_at is not None
        or expires_at <= _utcnow()
    ):
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    try:
        validate_password(payload.new_password, email=user.email)
    except PasswordPolicyError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Atomically claim the token: flip used_at from NULL in a single UPDATE.
    # Only the first of N concurrent requests gets rowcount 1; losers get 0
    # and the same generic 400. Closes the check-then-set race (two requests
    # both seeing used_at IS NULL and both resetting / double-bumping
    # token_version).
    claimed = (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.used_at.is_(None),
        )
        .update({"used_at": _utcnow()}, synchronize_session=False)
    )
    if claimed == 0:
        db.rollback()
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    # Commit the new password + revoke every outstanding session.
    user.password_hash = hash_password(payload.new_password)
    user.token_version = (user.token_version or 0) + 1
    db.add(user)

    # Successful reset = legitimate access proven via email. Drop any
    # lingering failed-login counter so the user isn't immediately locked
    # out when they try to sign in with their new password.
    lockout.reset(user.email.lower())

    log_change(
        db,
        "user",
        user.id,
        "password_reset_completed",
        actor_id=user.id,
    )
    db.commit()

    return Response(status_code=204)
