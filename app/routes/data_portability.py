"""GDPR data portability — admin-only org-wide data export.

Buyers in regulated industries need to answer two questions before signing:
"can a user export all their data?" and "can we delete an org?". This module
ships the export half; deletion lives in a separate PR.

Posture
-------
- Admin-only inside the requested org. A non-admin gets 403; an admin of a
  *different* org also gets 403 (no cross-tenant peeking even with a valid
  token).
- The path's `{org_id}` MUST equal the caller's active org from the JWT.
  We don't allow admins of org A to export org B even if they happen to
  also be members of B — they have to switch orgs first. This keeps the
  audit trail clean (the export is logged against the active org).
- Includes soft-deleted rows. GDPR "complete copy" obligations override the
  default `active_query` filter. Each row carries its own `deleted_at` so
  the recipient can distinguish live vs tombstoned data.
- Strips `password_hash` everywhere. Never include it. Tests assert this.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.audit_log import AuditLog
from app.models.buy_box import BuyBox
from app.models.contact import Contact
from app.models.deal import Deal
from app.models.deal_assumptions import DealAssumptions
from app.models.deal_distribution import DealDistribution
from app.models.deal_outputs import DealOutputs
from app.models.document import Document
from app.models.memo import Memo
from app.models.organization import Organization
from app.models.organization_membership import MemberRole, OrganizationMembership
from app.models.outreach_activity import OutreachActivity
from app.models.pipeline_event import PipelineEvent
from app.models.signal import Signal
from app.models.user import User
from app.services.audit_service import log_change
from app.utils.auth_deps import require_role_of

router = APIRouter(prefix="/organizations", tags=["data-portability"])


# Tables to dump, in stable order. Key is the JSON field name in the export.
# Each model has an `organization_id` column we filter on. We do NOT use
# `active_query` here — GDPR exports must include soft-deleted rows.
_ORG_SCOPED_MODELS: list[tuple[str, type]] = [
    ("deals", Deal),
    ("deal_assumptions", DealAssumptions),
    ("deal_outputs", DealOutputs),
    ("contacts", Contact),
    ("outreach_activities", OutreachActivity),
    ("signals", Signal),
    ("documents", Document),
    ("memos", Memo),
    ("pipeline_events", PipelineEvent),
    ("buy_boxes", BuyBox),
    ("deal_distributions", DealDistribution),
    ("audit_logs", AuditLog),
]

# Fields stripped from any User payload that leaves this endpoint. Keep this
# list deny-by-default — if a future column lands on User (e.g. mfa_secret),
# add it here BEFORE deploying.
_USER_SECRET_FIELDS = {"password_hash"}


def _serialize(obj: Any, *, drop: Iterable[str] = ()) -> dict:
    """Convert a SQLAlchemy ORM instance into a JSON-safe dict.

    Walks the mapper's column list (not `__dict__`) so relationships and
    unloaded lazy attributes don't accidentally trigger queries or leak.
    """
    drop_set = set(drop)
    out: dict[str, Any] = {}
    mapper = sa_inspect(obj.__class__)
    for col in mapper.columns:
        name = col.key
        if name in drop_set:
            continue
        val = getattr(obj, name, None)
        if hasattr(val, "value") and hasattr(val, "name"):  # Enum
            val = val.value
        elif hasattr(val, "isoformat"):  # datetime / date
            val = val.isoformat()
        out[name] = val
    return out


def _serialize_user(user: User) -> dict:
    """Same as `_serialize` but always strips secret credential fields."""
    return _serialize(user, drop=_USER_SECRET_FIELDS)


@router.get("/{org_id}/export")
def export_organization_data(
    org_id: str,
    principal: dict = Depends(
        require_role_of(MemberRole.admin, must_match_active_org=True)
    ),
    db: Session = Depends(get_db),
):
    """Return every tenant-scoped row for `org_id` as a downloadable JSON blob.

    Admin-only. The `{org_id}` must match the caller's active org — admins
    cannot cross-export by guessing another org's id, even one they belong
    to under a different membership.
    """
    org = db.get(Organization, org_id)
    if not org:
        # Membership existed but org row is gone — exotic but possible during
        # an in-flight delete. Treat as 404 since there's literally nothing
        # to export.
        raise HTTPException(status_code=404, detail="Organization not found")

    export: dict[str, Any] = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "organization_id": org_id,
        "organization": _serialize(org),
    }

    # Members: include each user's profile (sans password_hash) plus their
    # membership row. Joining here avoids two N+1 round-trips on the client.
    member_rows = (
        db.query(OrganizationMembership, User)
        .join(User, User.id == OrganizationMembership.user_id)
        .filter(OrganizationMembership.organization_id == org_id)
        .all()
    )
    export["members"] = [
        {
            "user": _serialize_user(user),
            "role": membership.role.value,
            "is_default": membership.is_default,
            "joined_at": membership.joined_at.isoformat() if membership.joined_at else None,
            "membership_id": membership.id,
        }
        for membership, user in member_rows
    ]

    # Tenant-scoped tables. Include soft-deleted rows so the export is
    # genuinely complete — the recipient can filter on `deleted_at` if they
    # only want live data.
    for field_name, model in _ORG_SCOPED_MODELS:
        rows = (
            db.query(model)
            .filter(model.organization_id == org_id)
            .all()
        )
        export[field_name] = [_serialize(r) for r in rows]

    # Audit the export itself. Compliance officers care that exports happened
    # at all — it's an exfiltration vector worth surveilling.
    log_change(
        db,
        entity_type="organization",
        entity_id=org_id,
        action="data_export",
        actor_id=principal["user_id"],
        organization_id=org_id,
        new_values={"exported_at": export["exported_at"]},
    )
    db.commit()

    # Return as a downloadable JSON file so a browser hitting this directly
    # gets a save dialog instead of a wall of text. JSON-encodes via FastAPI's
    # default encoder, which already handles the primitive types we built.
    filename = f"dealsignal-export-{org.slug or org_id}-{export['exported_at'][:10]}.json"
    return JSONResponse(
        content=export,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
