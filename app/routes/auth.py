import re
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

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
from app.services.audit_service import log_change
from app.services.security import create_access_token, hash_password, verify_password
from app.utils.auth_deps import get_current_user
from app.utils.org_scope import DEFAULT_ORG_ID

router = APIRouter(prefix="/auth", tags=["auth"])


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
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
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

    token = create_access_token(user_id=user.id, org_id=org.id)
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        organization_id=org.id,
        role=role.value,
    )


# ── login ───────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    if not user.is_active:
        raise HTTPException(status_code=401, detail="Account is inactive")

    # Pick the default membership, or the first one
    membership = (
        db.query(OrganizationMembership)
        .filter(OrganizationMembership.user_id == user.id)
        .order_by(OrganizationMembership.is_default.desc(), OrganizationMembership.joined_at.asc())
        .first()
    )
    if not membership:
        raise HTTPException(status_code=403, detail="User has no organization membership")

    token = create_access_token(user_id=user.id, org_id=membership.organization_id)
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        organization_id=membership.organization_id,
        role=membership.role.value,
    )


# ── me ──────────────────────────────────────────────────────────────────────

@router.get("/me", response_model=MeResponse)
def me(principal: dict = Depends(get_current_user)):
    return MeResponse(
        user=UserResponse.model_validate(principal["user"]),
        organization_id=principal["org_id"],
        role=principal["role"],
    )
