"""Backoffice CLI.

For support-desk actions that don't yet have a UI. Runs against the
production DB via the same `DATABASE_URL` the app reads. On Render,
invoke via `render shell` on `dealsignal-api`:

    $ render shell -s dealsignal-api
    $ python scripts/admin.py <command> [args]

Every mutating command asks for `--yes` before touching data — so a
fat-finger during a support call doesn't unintentionally wipe a user's
2FA or promote the wrong person to admin.

Every mutation also writes an audit-log row with `actor_id=None` and
`action=admin_<what>`, so an ops action shows up in the same trail as
customer-driven changes. Use `--reason "<why>"` to add context; it goes
into the audit log's `new_values.reason` field for future forensics.

Commands intentionally cover only "things support asks for in the first
30 days." Add new ones when a specific need shows up; don't preemptively
build an admin console.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

# Make `app.*` importable when the script runs from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models.organization_membership import (  # noqa: E402
    MemberRole,
    OrganizationMembership,
)
from app.models.user import User  # noqa: E402
from app.services.audit_service import log_change  # noqa: E402


def _find_user(db: Session, email: str) -> User:
    user = db.query(User).filter(User.email == email).first()
    if not user:
        _fatal(f"no user with email {email!r}")
    return user


def _confirm(args: argparse.Namespace, action: str) -> None:
    if not args.yes:
        _fatal(
            f"refusing to {action} without --yes. "
            f"Pass --yes when you're sure (and --reason to leave a paper trail)."
        )


def _user_audit_org_id(db: Session, user_id: str) -> Optional[str]:
    membership = (
        db.query(OrganizationMembership)
        .filter(OrganizationMembership.user_id == user_id)
        .order_by(
            OrganizationMembership.is_default.desc(),
            OrganizationMembership.joined_at.asc(),
        )
        .first()
    )
    return membership.organization_id if membership else None


def _audit(
    db: Session,
    entity_type: str,
    entity_id: str,
    action: str,
    *,
    reason: Optional[str],
    org_id: Optional[str] = None,
    extra: Optional[dict] = None,
) -> None:
    payload: dict = {"admin": True}
    if reason:
        payload["reason"] = reason
    if extra:
        payload.update(extra)
    log_change(
        db,
        entity_type,
        entity_id,
        f"admin_{action}",
        actor_id=None,
        organization_id=org_id,
        new_values=payload,
    )
    db.commit()


# ── commands ────────────────────────────────────────────────────────────────


def cmd_find_user(args: argparse.Namespace) -> int:
    """Look up a user + their memberships. Read-only, no confirmation."""
    with SessionLocal() as db:
        user = _find_user(db, args.email)
        memberships = (
            db.query(OrganizationMembership)
            .filter(OrganizationMembership.user_id == user.id)
            .all()
        )
        print(json.dumps({
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "is_active": user.is_active,
            "token_version": user.token_version,
            "totp_enabled": user.totp_enabled,
            "memberships": [
                {"org_id": m.organization_id, "role": m.role.value, "default": m.is_default}
                for m in memberships
            ],
        }, indent=2, default=str))
    return 0


def cmd_revoke_sessions(args: argparse.Namespace) -> int:
    """Bump `token_version` so every existing JWT for this user is 401'd on next call."""
    _confirm(args, "revoke all sessions")
    with SessionLocal() as db:
        user = _find_user(db, args.email)
        old_version = user.token_version
        user.token_version = old_version + 1
        db.commit()
        _audit(
            db, "user", user.id, "revoke_sessions",
            reason=args.reason,
            org_id=_user_audit_org_id(db, user.id),
            extra={"old_token_version": old_version, "new_token_version": user.token_version},
        )
        print(f"revoked all sessions for {user.email} (token_version {old_version} → {user.token_version})")
    return 0


def cmd_reset_2fa(args: argparse.Namespace) -> int:
    """Clear TOTP for a user who lost their authenticator. Requires re-enrollment."""
    _confirm(args, "reset 2FA")
    with SessionLocal() as db:
        user = _find_user(db, args.email)
        if not user.totp_enabled:
            print(f"{user.email} does not have 2FA enabled; nothing to do")
            return 0
        user.totp_secret = None
        user.totp_secret_ciphertext = None
        user.totp_enabled = False
        # Also bump token_version — any session created after enrolling in 2FA
        # should not survive a 2FA reset.
        user.token_version = user.token_version + 1
        db.commit()
        _audit(
            db, "user", user.id, "reset_2fa",
            reason=args.reason,
            org_id=_user_audit_org_id(db, user.id),
        )
        print(f"cleared 2FA for {user.email}; they must re-enroll on next login")
    return 0


def cmd_set_role(args: argparse.Namespace) -> int:
    """Change a user's role within an org."""
    _confirm(args, f"set role to {args.role}")
    try:
        target_role = MemberRole(args.role)
    except ValueError:
        _fatal(f"unknown role {args.role!r}. Valid: {[r.value for r in MemberRole]}")

    with SessionLocal() as db:
        user = _find_user(db, args.email)
        membership = (
            db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.user_id == user.id,
                OrganizationMembership.organization_id == args.org_id,
            )
            .first()
        )
        if not membership:
            _fatal(f"{user.email} is not a member of org {args.org_id}")

        # Prevent demoting the last admin — matches the API-level guard in
        # organizations.py so support can't accidentally lock an org out.
        if membership.role == MemberRole.admin and target_role != MemberRole.admin:
            admin_count = (
                db.query(OrganizationMembership)
                .filter(
                    OrganizationMembership.organization_id == args.org_id,
                    OrganizationMembership.role == MemberRole.admin,
                )
                .count()
            )
            if admin_count <= 1:
                _fatal(
                    f"cannot demote {user.email} — they are the last admin of {args.org_id}. "
                    f"Promote someone else to admin first."
                )

        old_role = membership.role.value
        membership.role = target_role
        db.commit()
        _audit(
            db, "membership", membership.id, "set_role",
            reason=args.reason,
            org_id=args.org_id,
            extra={"user_id": user.id, "old_role": old_role, "new_role": target_role.value},
        )
        print(f"set {user.email} to {target_role.value} in org {args.org_id}")
    return 0


def cmd_deactivate(args: argparse.Namespace) -> int:
    """Deactivate a user (soft-disable — no delete). Also revokes sessions."""
    _confirm(args, "deactivate user")
    with SessionLocal() as db:
        user = _find_user(db, args.email)
        if not user.is_active:
            print(f"{user.email} is already inactive")
            return 0
        user.is_active = False
        user.token_version = user.token_version + 1  # kill live sessions
        db.commit()
        _audit(
            db, "user", user.id, "deactivate",
            reason=args.reason,
            org_id=_user_audit_org_id(db, user.id),
        )
        print(f"deactivated {user.email}; existing sessions revoked")
    return 0


# ── glue ────────────────────────────────────────────────────────────────────


def _fatal(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(2)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="admin",
        description="DealSignal backoffice — support-desk actions on the production DB.",
    )
    parser.add_argument(
        "--reason", default=None,
        help="Free-text explanation logged to the audit trail. Use it.",
    )
    parser.add_argument(
        "--yes", action="store_true",
        help="Confirm the action. Mutating commands refuse to run without this.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("find-user", help="Show a user's profile and memberships.")
    p.add_argument("email")
    p.set_defaults(func=cmd_find_user)

    p = sub.add_parser("revoke-sessions", help="Kill every session for a user (token_version++).")
    p.add_argument("email")
    p.set_defaults(func=cmd_revoke_sessions)

    p = sub.add_parser("reset-2fa", help="Clear a user's TOTP setup so they can re-enroll.")
    p.add_argument("email")
    p.set_defaults(func=cmd_reset_2fa)

    p = sub.add_parser("set-role", help="Change a user's role within an organization.")
    p.add_argument("email")
    p.add_argument("--org-id", required=True)
    p.add_argument("--role", required=True, choices=[r.value for r in MemberRole])
    p.set_defaults(func=cmd_set_role)

    p = sub.add_parser("deactivate", help="Soft-disable a user and revoke their sessions.")
    p.add_argument("email")
    p.set_defaults(func=cmd_deactivate)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
