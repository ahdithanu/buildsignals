from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.organization import Organization
from app.models.organization_membership import MemberRole, OrganizationMembership
from app.models.user import User
from app.routes.auth import _set_refresh_cookie
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
from app.services.security import create_access_token
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
        .first()
    )
    if not m:
        raise HTTPException(status_code=404, detail="Membership not found")
    return m


# ── list my organizations ──────────────────────────────────────────────────

@router.get("/me", response_model=list[MyOrganizationItem])
def list_my_organizations(
    principal: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    memberships = (
        db.query(OrganizationMembership)
        .filter(OrganizationMembership.user_id == principal["user_id"])
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
    principal: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Any member can list (read-only operation)
    _ensure_membership(db, org_id=org_id, user_id=principal["user_id"])

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
    principal: dict = Depends(require_role_of(MemberRole.admin)),
    db: Session = Depends(get_db),
):
    org = db.get(Organization, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    user = db.query(User).filter(User.email == payload.email).first()
    if not user:
        raise HTTPException(
            status_code=404,
            detail="No user with that email exists. Have them register first.",
        )

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
    db.commit()

    log_change(
        db, "membership", membership.id, "invite",
        actor_id=principal["user_id"], organization_id=org_id,
        new_values={"user_id": user.id, "email": user.email, "role": payload.role.value},
    )
    db.commit()

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
    principal: dict = Depends(require_role_of(MemberRole.admin)),
    db: Session = Depends(get_db),
):
    membership = _ensure_membership(db, org_id=org_id, user_id=user_id)

    # Prevent demoting the last admin
    if membership.role == MemberRole.admin and payload.role != MemberRole.admin:
        admin_count = (
            db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.organization_id == org_id,
                OrganizationMembership.role == MemberRole.admin,
            )
            .count()
        )
        if admin_count <= 1:
            raise HTTPException(
                status_code=400,
                detail="Cannot demote the last admin of the organization",
            )

    old_role = membership.role.value
    membership.role = payload.role
    db.commit()

    log_change(
        db, "membership", membership.id, "role_change",
        actor_id=principal["user_id"], organization_id=org_id,
        old_values={"role": old_role}, new_values={"role": payload.role.value},
    )
    db.commit()

    user = db.get(User, user_id)
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
    membership = _ensure_membership(db, org_id=org_id, user_id=user_id)

    # Prevent removing the last admin
    if membership.role == MemberRole.admin:
        admin_count = (
            db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.organization_id == org_id,
                OrganizationMembership.role == MemberRole.admin,
            )
            .count()
        )
        if admin_count <= 1:
            raise HTTPException(
                status_code=400,
                detail="Cannot remove the last admin of the organization",
            )

    db.delete(membership)
    db.commit()

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
    response: Response,
    principal: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Issue a new JWT scoped to a different org the user belongs to."""
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

    token = create_access_token(
        user_id=principal["user_id"],
        org_id=payload.organization_id,
    )
    # Rotate the refresh cookie so a silent refresh can't throw the user
    # back to the previous org.
    _set_refresh_cookie(
        response,
        user_id=principal["user_id"],
        org_id=payload.organization_id,
    )
    return TokenResponse(
        access_token=token,
        user_id=principal["user_id"],
        organization_id=payload.organization_id,
        role=membership.role.value,
    )
