"""Admin-only bounded export of explicitly registered tenant tables/columns.

Includes deal workflows, graph metadata, saved assessments, and a manifest of
scopes/exclusions. This is not a complete account-data copy or an assertion of
GDPR compliance. Organization deletion uses its separate, unchanged inventory.

Posture
-------
- Admin-only inside the requested org. A non-admin gets 403; an admin of a
  *different* org also gets 403 (no cross-tenant peeking even with a valid
  token).
- The path's `{org_id}` MUST equal the caller's active org from the JWT.
  We don't allow admins of org A to export org B even if they happen to
  also be members of B — they have to switch orgs first. This keeps the
  audit trail clean (the export is logged against the active org).
- Includes soft-deleted rows from the listed tables, with `deleted_at` retained.
- Member profiles use an explicit allowlist that excludes credential columns.
- Synchronous exports are all-or-nothing across the existing table inventory:
  at most 10,000 database rows and 20 MiB of encoded JSON. Larger organizations
  need a separately implemented background export, not silent truncation.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, load_only

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
from app.services.organization_export import (
    EXPORT_SCHEMA_VERSION,
    EXPORT_TABLES,
    USER_FIELDS,
    build_manifest,
    prepare_row,
    serialize,
    validate_references,
)
from app.utils.auth_deps import require_role_of
from app.utils.org_scope import DEFAULT_ORG_ID

log = logging.getLogger("dealsignal.erasure")

# Global per-export budgets, not per-table limits or client-selectable page sizes.
# A member embeds two database rows (membership + allowlisted user profile).
EXPORT_ROW_CAP = 10_000
EXPORT_BYTE_CAP = 20 * 1024 * 1024
_EXPORT_HEADERS = {"Cache-Control": "no-store"}


class _NoStoreExportRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        if self.name != "export_organization_data":
            return handler

        async def export_handler(request: Request):
            try:
                response = await handler(request)
            except HTTPException as exc:
                exc.headers = {**(exc.headers or {}), **_EXPORT_HEADERS}
                raise
            except RequestValidationError:
                return JSONResponse(
                    status_code=422,
                    content={"detail": "Invalid organization export request."},
                    headers=_EXPORT_HEADERS,
                )
            except Exception:
                # Do not return partial data, DB error details, or a download
                # attachment when serialization, reading, or audit commit fails.
                log.error("organization.export_failed")
                return JSONResponse(
                    status_code=500,
                    content={"detail": "Organization export failed. No data was returned."},
                    headers=_EXPORT_HEADERS,
                )
            response.headers.update(_EXPORT_HEADERS)
            return response

        return export_handler


router = APIRouter(prefix="/organizations", tags=["data-portability"], route_class=_NoStoreExportRoute)


def _export_too_large(limit: str) -> None:
    raise HTTPException(
        status_code=413,
        detail=f"Organization export exceeds the synchronous {limit} limit. No data was returned.",
        headers=_EXPORT_HEADERS,
    )


class _ExportBudget:
    def __init__(self):
        self.rows = 0
        self.encoded_bytes = 0

    def add(self, item: dict, *, row_cost: int = 1) -> dict:
        self.rows += row_cost
        if self.rows > EXPORT_ROW_CAP:
            _export_too_large(f"{EXPORT_ROW_CAP:,}-row")
        encoder = json.JSONEncoder(ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        for chunk in encoder.iterencode(item):
            self.encoded_bytes += len(chunk.encode("utf-8"))
            if self.encoded_bytes > EXPORT_BYTE_CAP:
                _export_too_large(f"{EXPORT_BYTE_CAP:,}-byte")
        return item

    def collect(self, query, serialize, *, row_cost: int = 1) -> list[dict]:
        allowance = max(0, (EXPORT_ROW_CAP - self.rows) // row_cost)
        items = []
        # The extra row detects overflow without COUNT(*) or unbounded .all().
        for index, row in enumerate(query.limit(allowance + 1).yield_per(100)):
            if index == allowance:
                _export_too_large(f"{EXPORT_ROW_CAP:,}-row")
            items.append(self.add(serialize(row), row_cost=row_cost))
        return items


class OrgDeletionRequest(BaseModel):
    # GitHub-style "type the name to confirm" — makes an irreversible bulk
    # delete impossible to trigger by accident or a stray API call.
    confirm: str = Field(..., description="Must exactly equal the organization's name.")


# Legacy deletion inventory. Export additions must not change deletion behavior.
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

# Allowlist public profile fields so future credential columns cannot leak.
_USER_EXPORT_FIELDS = set(USER_FIELDS)


def _serialize(obj: Any) -> dict:
    """Serialize only registered columns, without traversing relationships."""
    return serialize(obj)


def _serialize_user(user: User) -> dict:
    """Only explicitly registered profile fields, never credential columns."""
    return _serialize(user)


def _serialize_member(row) -> dict:
    membership, user = row
    if user is None:
        # A corrupt membership must not disappear from a supposedly full copy.
        raise ValueError("Organization member profile is missing")
    return {
        "user": _serialize_user(user),
        "role": membership.role.value,
        "is_default": membership.is_default,
        "joined_at": membership.joined_at.isoformat() if membership.joined_at else None,
        "membership_id": membership.id,
    }


@router.get("/{org_id}/export")
def export_organization_data(
    org_id: str,
    principal: dict = Depends(
        require_role_of(MemberRole.admin, must_match_active_org=True)
    ),
    db: Session = Depends(get_db),
):
    """Return the registered tenant-scoped tables as one downloadable JSON blob.

    Admin-only. The `{org_id}` must match the caller's active org — admins
    cannot cross-export by guessing another org's id, even one they belong
    to under a different membership. The row cap covers the organization,
    membership/profile pairs (two rows each), and all exported table rows.
    Overflow returns 413, never a partial or paginated download.
    """
    org = db.get(Organization, org_id)
    if not org:
        # Membership existed but org row is gone — exotic but possible during
        # an in-flight delete. Treat as 404 since there's literally nothing
        # to export.
        raise HTTPException(status_code=404, detail="Organization not found")

    budget = _ExportBudget()
    export: dict[str, Any] = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "organization_id": org_id,
        "organization": budget.add(_serialize(org)),
    }

    # Members: include each user's profile (sans password_hash) plus their
    # membership row. Joining here avoids two N+1 round-trips on the client.
    member_query = (
        db.query(OrganizationMembership, User)
        .outerjoin(User, User.id == OrganizationMembership.user_id)
        .options(load_only(*(getattr(User, field) for field in USER_FIELDS), raiseload=True))
        .filter(OrganizationMembership.organization_id == org_id)
        .order_by(OrganizationMembership.id)
    )
    export["members"] = budget.collect(member_query, _serialize_member, row_cost=2)

    member_ids = {member["user"]["id"] for member in export["members"]}
    redactions = {"nonmember_user_references": 0, "unsupported_graph_link_targets": 0}
    for entry in EXPORT_TABLES:
        export[entry.name] = budget.collect(
            entry.query(db, org_id),
            lambda row: prepare_row(entry, _serialize(row), member_ids, redactions),
        )
    validate_references(db, org_id, export)
    export["manifest"] = build_manifest(
        export, row_count=budget.rows, row_cap=EXPORT_ROW_CAP,
        byte_cap=EXPORT_BYTE_CAP, redactions=redactions,
    )

    # Prepare and size-check the entire response BEFORE recording success. This
    # catches encoding failures and JSON envelope overhead as well as row data.
    filename = f"dealsignal-export-{org.slug or org_id}-{export['exported_at'][:10]}.json"
    response = JSONResponse(
        content=export,
        headers={
            **_EXPORT_HEADERS,
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
    if len(response.body) > EXPORT_BYTE_CAP:
        _export_too_large(f"{EXPORT_BYTE_CAP:,}-byte")

    # Audit the export itself. Compliance officers care that exports happened
    # at all — it's an exfiltration vector worth surveilling.
    log_change(
        db,
        entity_type="organization",
        entity_id=org_id,
        action="data_export",
        actor_id=principal["user_id"],
        organization_id=org_id,
        new_values={"exported_at": export["exported_at"], "row_count": budget.rows,
                    "byte_count": len(response.body), "schema_version": EXPORT_SCHEMA_VERSION,
                    "scopes": export["manifest"]["scopes"]},
    )
    db.commit()

    return response


@router.post("/{org_id}/delete")
def delete_organization_data(
    org_id: str,
    payload: OrgDeletionRequest,
    principal: dict = Depends(
        require_role_of(MemberRole.admin, must_match_active_org=True)
    ),
    db: Session = Depends(get_db),
):
    """GDPR right-to-erasure: permanently delete all data for an organization.

    Irreversible. Guard rails, in order:
      - admin of the org, and `{org_id}` must equal the caller's active org
        (require_role_of(..., must_match_active_org=True));
      - the request body must echo the org's exact name;
      - the default/demo org can never be deleted.

    Deletes every tenant-scoped row, memberships, and users whose ONLY
    membership was this org (users belonging to other orgs are left intact).
    Because the org's audit_logs are deleted too, the erasure itself is
    recorded to the application log (which lives in separate storage) as a
    PII-free receipt, not to audit_logs.
    """
    if org_id == DEFAULT_ORG_ID:
        raise HTTPException(status_code=403, detail="The default organization cannot be deleted")

    org = db.get(Organization, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    if payload.confirm != org.name:
        raise HTTPException(
            status_code=400,
            detail="Confirmation text does not match the organization name",
        )

    # Identify users to erase: members of this org with no membership elsewhere.
    member_ids = [
        m.user_id
        for m in db.query(OrganizationMembership)
        .filter(OrganizationMembership.organization_id == org_id)
        .all()
    ]
    orphan_user_ids: list[str] = []
    for uid in member_ids:
        other = (
            db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.user_id == uid,
                OrganizationMembership.organization_id != org_id,
            )
            .count()
        )
        if other == 0:
            orphan_user_ids.append(uid)

    deleted: dict[str, int] = {}

    # Tenant tables, deleted in REVERSE of the export order so child rows
    # (e.g. deal_outputs) go before their parent (deals) and no FK is violated.
    for field_name, model in reversed(_ORG_SCOPED_MODELS):
        n = (
            db.query(model)
            .filter(model.organization_id == org_id)
            .delete(synchronize_session=False)
        )
        deleted[field_name] = n

    deleted["memberships"] = (
        db.query(OrganizationMembership)
        .filter(OrganizationMembership.organization_id == org_id)
        .delete(synchronize_session=False)
    )

    if orphan_user_ids:
        deleted["users"] = (
            db.query(User)
            .filter(User.id.in_(orphan_user_ids))
            .delete(synchronize_session=False)
        )
    else:
        deleted["users"] = 0

    db.delete(org)
    db.commit()

    receipt = {
        "deleted_at": datetime.now(timezone.utc).isoformat(),
        "organization_id": org_id,
        "deleted_by": principal["user_id"],
        "rows_deleted": deleted,
    }
    # PII-free record in application logs — survives the audit_logs deletion.
    log.warning("organization.erased %s", receipt)
    return receipt
