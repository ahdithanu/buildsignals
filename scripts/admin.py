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
import getpass
import json
import os
import sys
from pathlib import Path
from typing import Optional
from uuid import uuid4

# Make `app.*` importable when the script runs from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models.contact import Contact, ContactStatus  # noqa: E402
from app.models.deal import Deal, DealStatus, RiskLevel  # noqa: E402
from app.models.deal_assumptions import DealAssumptions  # noqa: E402
from app.models.deal_outputs import DealOutputs  # noqa: E402
from app.models.organization import Organization  # noqa: E402
from app.models.organization_membership import (  # noqa: E402
    MemberRole,
    OrganizationMembership,
)
from app.models.signal import Signal  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.audit_service import log_change  # noqa: E402
from app.services.password_policy import PasswordPolicyError, validate_password  # noqa: E402
from app.services.security import hash_password, verify_password  # noqa: E402

DEMO_ORG_SLUG = "build-signals-demo-workspace"
DEMO_DATA_SOURCE = "BuildSignals synthetic demo"


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


def _demo_password_from_env_or_prompt(args: argparse.Namespace) -> str:
    password = os.environ.get("BUILD_SIGNALS_DEMO_PASSWORD") or ""
    if password or not args.prompt_password:
        return password
    return getpass.getpass("Demo password: ")


def _seed_demo_data(db: Session, *, org_id: str) -> bool:
    existing = (
        db.query(Deal)
        .filter(Deal.organization_id == org_id, Deal.source == DEMO_DATA_SOURCE)
        .first()
    )
    if existing:
        return False

    samples = [
        {
            "deal": {
                "name": "Demo: North Loop Retail Redevelopment",
                "address": "410 Demo Market St",
                "city": "Austin",
                "state": "TX",
                "zip_code": "78701",
                "property_type": "retail",
                "sq_ft": 42000,
                "year_built": 1998,
                "asking_price": 18_400_000,
                "status": DealStatus.underwriting,
                "risk_level": RiskLevel.medium,
                "score": 78.0,
                "notes": "Synthetic walkthrough opportunity with pre-approval retail signals and parcel context.",
            },
            "assumptions": {
                "purchase_price": 17_900_000,
                "closing_costs_pct": 0.018,
                "renovation_cost": 1_100_000,
                "loan_amount": 11_600_000,
                "interest_rate": 0.061,
                "loan_term_years": 25,
                "gross_rental_income": 1_960_000,
                "vacancy_pct": 0.07,
                "opex_pct": 0.31,
                "cap_rate_market": 0.058,
                "exit_cap_rate": 0.062,
                "hold_period_years": 5,
                "rent_growth_pct": 0.028,
            },
            "outputs": {
                "noi": 1_352_400,
                "dscr": 1.42,
                "cash_on_cash": 0.083,
                "cap_rate": 0.076,
                "irr": 0.174,
                "equity_multiple": 2.1,
                "total_project_cost": 19_322_000,
                "equity_required": 7_722_000,
                "annual_debt_service": 953_000,
                "net_cash_flow": 399_400,
                "exit_value": 23_900_000,
                "profit": 8_100_000,
            },
            "contacts": [
                {
                    "name": "Demo Broker",
                    "role": "Listing broker",
                    "email": "broker@example.invalid",
                    "phone": "555-0100",
                    "company": "Synthetic CRE Advisors",
                }
            ],
            "signals": [
                {
                    "signal_type": "permit",
                    "source": DEMO_DATA_SOURCE,
                    "description": "Synthetic permit application for national coffee tenant build-out before approval.",
                    "severity": 7.0,
                },
                {
                    "signal_type": "planning",
                    "source": DEMO_DATA_SOURCE,
                    "description": "Synthetic planning agenda item indicates drive-through variance review next month.",
                    "severity": 6.5,
                },
            ],
        },
        {
            "deal": {
                "name": "Demo: Inland Logistics Infill",
                "address": "825 Demo Industrial Pkwy",
                "city": "Phoenix",
                "state": "AZ",
                "zip_code": "85009",
                "property_type": "industrial",
                "sq_ft": 126000,
                "year_built": 2014,
                "asking_price": 32_750_000,
                "status": DealStatus.qualified,
                "risk_level": RiskLevel.low,
                "score": 86.0,
                "notes": "Synthetic infill warehouse example for dashboard, signals, assumptions, and memo views.",
            },
            "assumptions": {
                "purchase_price": 31_900_000,
                "closing_costs_pct": 0.015,
                "renovation_cost": 650_000,
                "loan_amount": 20_735_000,
                "interest_rate": 0.057,
                "loan_term_years": 30,
                "gross_rental_income": 2_780_000,
                "vacancy_pct": 0.04,
                "opex_pct": 0.24,
                "cap_rate_market": 0.054,
                "exit_cap_rate": 0.057,
                "hold_period_years": 7,
                "rent_growth_pct": 0.032,
            },
            "outputs": {
                "noi": 2_028_000,
                "dscr": 1.67,
                "cash_on_cash": 0.096,
                "cap_rate": 0.064,
                "irr": 0.191,
                "equity_multiple": 2.4,
                "total_project_cost": 33_028_500,
                "equity_required": 12_293_500,
                "annual_debt_service": 1_214_000,
                "net_cash_flow": 814_000,
                "exit_value": 42_600_000,
                "profit": 13_900_000,
            },
            "contacts": [],
            "signals": [
                {
                    "signal_type": "tenant_risk",
                    "source": DEMO_DATA_SOURCE,
                    "description": "Synthetic renewal watch: major tenant has 18 months remaining with expansion option.",
                    "severity": 4.0,
                }
            ],
        },
    ]

    for sample in samples:
        deal = Deal(**sample["deal"], organization_id=org_id, source=DEMO_DATA_SOURCE)
        db.add(deal)
        db.flush()
        db.add(DealAssumptions(deal_id=deal.id, organization_id=org_id, **sample["assumptions"]))
        db.add(DealOutputs(deal_id=deal.id, organization_id=org_id, **sample["outputs"]))
        for contact in sample["contacts"]:
            db.add(
                Contact(
                    deal_id=deal.id,
                    organization_id=org_id,
                    status=ContactStatus.not_contacted,
                    **contact,
                )
            )
        for signal in sample["signals"]:
            db.add(Signal(deal_id=deal.id, organization_id=org_id, **signal))
    return True


def cmd_ensure_demo_workspace(args: argparse.Namespace) -> int:
    """Create or repair the isolated synthetic demo user + organization."""
    _confirm(args, "create or update the demo workspace")
    email = (args.email or os.environ.get("BUILD_SIGNALS_DEMO_EMAIL") or "").strip().lower()
    password = _demo_password_from_env_or_prompt(args)
    if not email:
        _fatal("demo email is required via --email or BUILD_SIGNALS_DEMO_EMAIL")
    if not password:
        _fatal("demo password is required via BUILD_SIGNALS_DEMO_PASSWORD or --prompt-password")
    try:
        validate_password(password, email=email)
    except PasswordPolicyError as exc:
        _fatal(f"demo password does not meet policy: {exc}")

    with SessionLocal() as db:
        org = db.query(Organization).filter(Organization.slug == DEMO_ORG_SLUG).first()
        created_org = False
        if not org:
            org = Organization(
                id=str(uuid4()),
                name=args.org_name,
                slug=DEMO_ORG_SLUG,
                is_active=True,
            )
            db.add(org)
            db.flush()
            created_org = True
        else:
            org.name = args.org_name
            org.is_active = True

        user = db.query(User).filter(User.email == email).first()
        created_user = False
        if user:
            memberships = (
                db.query(OrganizationMembership)
                .filter(OrganizationMembership.user_id == user.id)
                .all()
            )
            other_org_ids = {m.organization_id for m in memberships if m.organization_id != org.id}
            if other_org_ids:
                _fatal(
                    f"refusing to reuse {email!r}; it already belongs to non-demo org(s): "
                    f"{', '.join(sorted(other_org_ids))}"
                )
            if not verify_password(password, user.password_hash):
                _fatal(
                    f"refusing to reset credentials for existing demo user {email!r}. "
                    "Use the current BUILD_SIGNALS_DEMO_PASSWORD or choose a new demo email."
                )
            if not user.is_active:
                _fatal(f"existing demo user {email!r} is inactive; choose a new demo email or reactivate separately")
            if user.is_superuser:
                _fatal(f"existing demo user {email!r} is a superuser; choose a non-privileged demo email")
            if user.totp_enabled:
                _fatal(
                    f"existing demo user {email!r} has 2FA enabled; choose a new demo email "
                    "or explicitly disable 2FA through the existing support flow"
                )
        else:
            user = User(
                id=str(uuid4()),
                email=email,
                full_name=args.full_name,
                password_hash=hash_password(password),
                is_active=True,
                is_superuser=False,
            )
            db.add(user)
            db.flush()
            created_user = True

        membership = (
            db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.user_id == user.id,
                OrganizationMembership.organization_id == org.id,
            )
            .first()
        )
        if not membership:
            membership = OrganizationMembership(
                id=str(uuid4()),
                organization_id=org.id,
                user_id=user.id,
                role=MemberRole.viewer,
                is_default=True,
            )
            db.add(membership)
        else:
            membership.role = MemberRole.viewer
            membership.is_default = True

        seeded_data = _seed_demo_data(db, org_id=org.id)

        db.commit()
        _audit(
            db,
            "organization",
            org.id,
            "ensure_demo_workspace",
            reason=args.reason,
            org_id=org.id,
            extra={
                "demo": True,
                "demo_email": email,
                "created_org": created_org,
                "created_user": created_user,
                "seeded_data": seeded_data,
            },
        )
        print(json.dumps({
            "organization_id": org.id,
            "organization_slug": org.slug,
            "demo_email": email,
            "created_org": created_org,
            "created_user": created_user,
            "role": MemberRole.viewer.value,
            "seeded_data": seeded_data,
            "activation": [
                "Set BUILD_SIGNALS_EXPOSE_DEMO_CREDENTIALS=true",
                "Set BUILD_SIGNALS_DEMO_EMAIL to this demo email",
                "Set BUILD_SIGNALS_DEMO_PASSWORD to the same password used for this command",
                "Redeploy/restart the API service",
            ],
        }, indent=2))
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

    p = sub.add_parser(
        "ensure-demo-workspace",
        help="Create or repair the isolated synthetic public demo workspace.",
    )
    p.add_argument("--email", help="Demo user email. Defaults to BUILD_SIGNALS_DEMO_EMAIL.")
    p.add_argument(
        "--prompt-password",
        action="store_true",
        help="Prompt for the demo password if BUILD_SIGNALS_DEMO_PASSWORD is not set.",
    )
    p.add_argument("--full-name", default="Build Signals Demo")
    p.add_argument("--org-name", default="Build Signals Demo Workspace")
    p.set_defaults(func=cmd_ensure_demo_workspace)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
