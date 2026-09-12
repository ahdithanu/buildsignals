from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.organization import Organization
from app.models.organization_membership import MemberRole, OrganizationMembership
from app.models.user import User
from app.schemas.auth import TokenResponse
from app.schemas.organization import (
    InviteMemberRequest,
    MemberResponse,
    MyOrganizationItem,
    OrganizationResponse,
    SwitchOrgRequest,
    UpdateMemberRequest,
)
from app.services.audit_service import log_change
from app.services.browser_sessions import issue_browser_session
from app.utils.auth_deps import get_current_user, require_role_of

router = APIRouter(prefix="/organizations", tags=["organizations"])


# ── helpers ────────────────────────────────────────────────────────────────

def _ensure_membership(db: Session, *, org_id: str, user_id: str) -> OrganizationMembership:
    m = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.organization_id == org_id,
            OrganizationMembership.user_id == user_id,
        )
        .populate_existing()
        .first()
    )
    if not m:
        raise HTTPException(status_code=404, detail="Membership not found")
    return m


def _lock_admin_membership(db: Session, *, org_id: str, user_id: str) -> None:
    # Serialize member mutations on their parent, including concurrent demotions.
    # SQLite ignores FOR UPDATE; a no-op write provides its equivalent write lock.
    if db.get_bind().dialect.name == "sqlite":
        db.execute(
            update(Organization)
            .where(Organization.id == org_id)
            .values(updated_at=Organization.updated_at)
        )
    org = (
        db.query(Organization)
        .filter(Organization.id == org_id)
        .with_for_update()
        .populate_existing()
        .first()
    )
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    if not org.is_active:
        raise HTTPException(status_code=403, detail="Organization is unavailable")
    # Dependencies may have run before another admin's revocation committed.
    user = db.query(User).filter(User.id == user_id).populate_existing().first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    membership = _ensure_membership(db, org_id=org_id, user_id=user_id)
    if membership.role != MemberRole.admin:
        raise HTTPException(status_code=403, detail="Requires admin role")


def _ensure_other_active_admin(db: Session, *, org_id: str, user_id: str, action: str) -> None:
    other_admin = (
        db.query(OrganizationMembership.id)
        .join(User, User.id == OrganizationMembership.user_id)
        .filter(
            OrganizationMembership.organization_id == org_id,
            OrganizationMembership.user_id != user_id,
            OrganizationMembership.role == MemberRole.admin,
            User.is_active.is_(True),
        )
        .first()
    )
    if other_admin is None:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot {action} the last admin of the organization (last active admin)",
        )


# ── list my organizations ──────────────────────────────────────────────────

@router.get("/me", response_model=list[MyOrganizationItem])
def list_my_organizations(
    response: Response,
    principal: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    memberships = (
        db.query(OrganizationMembership)
        .join(Organization, Organization.id == OrganizationMembership.organization_id)
        .filter(OrganizationMembership.user_id == principal["user_id"], Organization.is_active.is_(True))
        .order_by(OrganizationMembership.is_default.desc(), OrganizationMembership.joined_at.asc())
        .all()
    )
    return [
        MyOrganizationItem(
            organization=OrganizationResponse.model_validate(m.organization),
            role=m.role.value,
            is_default=m.is_default,
            joined_at=m.joined_at,
        )
        for m in memberships
    ]


# ── list members of an org ─────────────────────────────────────────────────

@router.get("/{org_id}/members", response_model=list[MemberResponse])
def list_members(
    org_id: str,
    response: Response,
    principal: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Any member can list (read-only operation)
    _ensure_membership(db, org_id=org_id, user_id=principal["user_id"])
    org = db.get(Organization, org_id)
    if org is None or not org.is_active:
        raise HTTPException(status_code=403, detail="Organization is unavailable")
    response.headers["Cache-Control"] = "no-store"

    rows = (
        db.query(OrganizationMembership, User)
        .join(User, User.id == OrganizationMembership.user_id)
        .filter(OrganizationMembership.organization_id == org_id)
        .order_by(OrganizationMembership.joined_at.asc())
        .all()
    )
    return [
        MemberResponse(
            id=m.id,
            user_id=u.id,
            email=u.email,
            full_name=u.full_name,
            role=m.role.value,
            is_default=m.is_default,
            joined_at=m.joined_at,
        )
        for m, u in rows
    ]


# ── invite an existing user ────────────────────────────────────────────────

@router.post("/{org_id}/members", response_model=MemberResponse, status_code=201)
def invite_member(
    org_id: str,
    payload: InviteMemberRequest,
    response: Response,
    principal: dict = Depends(require_role_of(MemberRole.admin)),
    db: Session = Depends(get_db),
):
    _lock_admin_membership(db, org_id=org_id, user_id=principal["user_id"])

    user = db.query(User).filter(User.email == payload.email).first()
    if not user:
        raise HTTPException(
            status_code=404,
            detail="No user with that email exists. Have them register first.",
        )
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Cannot invite an inactive user")

    existing = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.organization_id == org_id,
            OrganizationMembership.user_id == user.id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="User is already a member")

    membership = OrganizationMembership(
        id=str(uuid4()),
        organization_id=org_id,
        user_id=user.id,
        role=payload.role,
        is_default=False,
    )
    db.add(membership)
    db.flush()

    log_change(
        db, "membership", membership.id, "invite",
        actor_id=principal["user_id"], organization_id=org_id,
        new_values={"user_id": user.id, "email": user.email, "role": payload.role.value},
    )
    db.commit()
    response.headers["Cache-Control"] = "no-store"

    return MemberResponse(
        id=membership.id,
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=membership.role.value,
        is_default=membership.is_default,
        joined_at=membership.joined_at,
    )


# ── change a member's role ─────────────────────────────────────────────────

@router.patch("/{org_id}/members/{user_id}", response_model=MemberResponse)
def update_member_role(
    org_id: str,
    user_id: str,
    payload: UpdateMemberRequest,
    response: Response,
    principal: dict = Depends(require_role_of(MemberRole.admin)),
    db: Session = Depends(get_db),
):
    _lock_admin_membership(db, org_id=org_id, user_id=principal["user_id"])
    membership = _ensure_membership(db, org_id=org_id, user_id=user_id)
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Member user not found")
    if payload.role == MemberRole.admin and not user.is_active:
        raise HTTPException(status_code=400, detail="Cannot promote an inactive user to admin")

    # Prevent demoting the last admin
    if membership.role == MemberRole.admin and payload.role != MemberRole.admin:
        _ensure_other_active_admin(db, org_id=org_id, user_id=user_id, action="demote")

    old_role = membership.role.value
    membership.role = payload.role

    log_change(
        db, "membership", membership.id, "role_change",
        actor_id=principal["user_id"], organization_id=org_id,
        old_values={"role": old_role}, new_values={"role": payload.role.value},
    )
    db.commit()
    response.headers["Cache-Control"] = "no-store"

    return MemberResponse(
        id=membership.id,
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=membership.role.value,
        is_default=membership.is_default,
        joined_at=membership.joined_at,
    )


# ── remove a member ────────────────────────────────────────────────────────

@router.delete("/{org_id}/members/{user_id}", status_code=204)
def remove_member(
    org_id: str,
    user_id: str,
    principal: dict = Depends(require_role_of(MemberRole.admin)),
    db: Session = Depends(get_db),
):
    _lock_admin_membership(db, org_id=org_id, user_id=principal["user_id"])
    membership = _ensure_membership(db, org_id=org_id, user_id=user_id)

    # Prevent removing the last admin
    if membership.role == MemberRole.admin:
        _ensure_other_active_admin(db, org_id=org_id, user_id=user_id, action="remove")

    db.delete(membership)

    log_change(
        db, "membership", membership.id, "remove",
        actor_id=principal["user_id"], organization_id=org_id,
        old_values={"user_id": user_id},
    )
    db.commit()
    return None


# ── switch active org ──────────────────────────────────────────────────────

# Mounted on a separate path to avoid colliding with /organizations/me
switch_router = APIRouter(prefix="/auth", tags=["auth"])


@switch_router.post("/switch-org", response_model=TokenResponse)
def switch_org(
    payload: SwitchOrgRequest,
    request: Request,
    response: Response,
    principal: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Rotate this browser family into another active member workspace."""
    membership = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == principal["user_id"],
            OrganizationMembership.organization_id == payload.organization_id,
        )
        .first()
    )
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of that organization",
        )

    org = db.get(Organization, payload.organization_id)
    if org is None or not org.is_active:
        raise HTTPException(status_code=403, detail="Organization is unavailable")

    result = issue_browser_session(
        db, request, response,
        user=principal["user"],
        org_id=payload.organization_id,
        role=membership.role.value,
        principal_claims=principal["claims"],
    )
    db.commit()
    return result
