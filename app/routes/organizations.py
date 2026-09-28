from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.api_key import OrganizationApiKey
from app.models.organization import Organization
from app.models.organization_membership import MemberRole, OrganizationMembership
from app.models.user import User
from app.models.webhook import WebhookDelivery, WebhookSubscription
from app.routes.auth import _set_refresh_cookie
from app.schemas.auth import TokenResponse
from app.schemas.organization import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyResponse,
    ApiKeyUsageRollupRebuildResponse,
    ApiKeyUsageSummary,
    InviteMemberRequest,
    MemberResponse,
    MyOrganizationItem,
    OrganizationResponse,
    SwitchOrgRequest,
    UpdateMemberRequest,
)
from app.schemas.webhook import (
    WebhookDeliveryResponse,
    WebhookDeliverySummaryResponse,
    WebhookSubscriptionCreate,
    WebhookSubscriptionResponse,
    WebhookSubscriptionUpdate,
    WebhookTestEventRequest,
)
from app.services.api_key_service import create_api_key, revoke_api_key, to_response
from app.services.api_usage_service import (
    get_api_key_usage_totals,
    rebuild_api_key_usage_rollups,
    summarize_api_key_usage,
)
from app.services.audit_service import log_change
from app.services.security import create_access_token
from app.services.webhook_service import (
    attempt_webhook_delivery,
    create_subscription,
    enqueue_webhook_event,
    replay_webhook_delivery,
    summarize_webhook_deliveries,
    update_subscription,
)
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


# ── organization API keys ──────────────────────────────────────────────────

@router.get("/{org_id}/api-keys", response_model=list[ApiKeyResponse])
def list_api_keys(
    org_id: str,
    principal: dict = Depends(require_role_of(MemberRole.admin)),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(OrganizationApiKey)
        .filter(OrganizationApiKey.organization_id == org_id)
        .order_by(OrganizationApiKey.created_at.desc())
        .all()
    )
    usage = get_api_key_usage_totals(db, api_key_ids=[row.id for row in rows])
    return [
        to_response(
            row,
            usage_total_calls=usage.get(row.id, (0, None))[0],
            usage_last_called_at=usage.get(row.id, (0, None))[1],
        )
        for row in rows
    ]


@router.post("/{org_id}/api-keys", response_model=ApiKeyCreateResponse, status_code=201)
def create_organization_api_key(
    org_id: str,
    payload: ApiKeyCreateRequest,
    principal: dict = Depends(require_role_of(MemberRole.admin)),
    db: Session = Depends(get_db),
):
    if not db.get(Organization, org_id):
        raise HTTPException(status_code=404, detail="Organization not found")
    api_key, secret = create_api_key(
        db,
        organization_id=org_id,
        name=payload.name,
        scopes=payload.scopes,
        actor_id=principal["user_id"],
        expires_at=payload.expires_at,
    )
    db.flush()
    log_change(
        db, "organization_api_key", api_key.id, "create",
        actor_id=principal["user_id"], organization_id=org_id,
        new_values={
            "name": api_key.name,
            "key_prefix": api_key.key_prefix,
            "scopes": payload.scopes,
            "expires_at": api_key.expires_at.isoformat() if api_key.expires_at else None,
        },
    )
    db.commit()
    db.refresh(api_key)
    response = to_response(api_key).model_dump()
    return ApiKeyCreateResponse(**response, secret=secret)


@router.delete("/{org_id}/api-keys/{key_id}", response_model=ApiKeyResponse)
def revoke_organization_api_key(
    org_id: str,
    key_id: str,
    principal: dict = Depends(require_role_of(MemberRole.admin)),
    db: Session = Depends(get_db),
):
    api_key = (
        db.query(OrganizationApiKey)
        .filter(OrganizationApiKey.organization_id == org_id, OrganizationApiKey.id == key_id)
        .first()
    )
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")
    was_revoked = api_key.revoked_at is not None
    revoke_api_key(db, api_key=api_key, actor_id=principal["user_id"])
    if not was_revoked:
        log_change(
            db, "organization_api_key", api_key.id, "revoke",
            actor_id=principal["user_id"], organization_id=org_id,
            old_values={"name": api_key.name, "key_prefix": api_key.key_prefix},
        )
    db.commit()
    db.refresh(api_key)
    return to_response(api_key)


@router.get("/{org_id}/api-keys/{key_id}/usage", response_model=ApiKeyUsageSummary)
def get_organization_api_key_usage(
    org_id: str,
    key_id: str,
    principal: dict = Depends(require_role_of(MemberRole.admin)),
    db: Session = Depends(get_db),
):
    api_key = (
        db.query(OrganizationApiKey)
        .filter(OrganizationApiKey.organization_id == org_id, OrganizationApiKey.id == key_id)
        .first()
    )
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")
    return summarize_api_key_usage(db, organization_id=org_id, api_key_id=key_id)


@router.post(
    "/{org_id}/api-keys/{key_id}/usage/rebuild-rollups",
    response_model=ApiKeyUsageRollupRebuildResponse,
)
def rebuild_organization_api_key_usage_rollups(
    org_id: str,
    key_id: str,
    principal: dict = Depends(require_role_of(MemberRole.admin)),
    db: Session = Depends(get_db),
):
    api_key = (
        db.query(OrganizationApiKey)
        .filter(OrganizationApiKey.organization_id == org_id, OrganizationApiKey.id == key_id)
        .first()
    )
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")
    rebuilt_events = rebuild_api_key_usage_rollups(db, organization_id=org_id, api_key_id=key_id)
    log_change(
        db, "organization_api_key", api_key.id, "rebuild_usage_rollups",
        actor_id=principal["user_id"], organization_id=org_id,
        new_values={"rebuilt_events": rebuilt_events},
    )
    db.commit()
    return ApiKeyUsageRollupRebuildResponse(api_key_id=key_id, rebuilt_events=rebuilt_events)


# ── webhook subscriptions ─────────────────────────────────────────────────

@router.get("/{org_id}/webhook-subscriptions", response_model=list[WebhookSubscriptionResponse])
def list_webhook_subscriptions(
    org_id: str,
    principal: dict = Depends(require_role_of(MemberRole.admin)),
    db: Session = Depends(get_db),
):
    if not db.get(Organization, org_id):
        raise HTTPException(status_code=404, detail="Organization not found")
    return (
        db.query(WebhookSubscription)
        .filter(WebhookSubscription.organization_id == org_id)
        .order_by(WebhookSubscription.created_at.desc(), WebhookSubscription.id.desc())
        .all()
    )


@router.post("/{org_id}/webhook-subscriptions", response_model=WebhookSubscriptionResponse, status_code=201)
def create_webhook_subscription(
    org_id: str,
    payload: WebhookSubscriptionCreate,
    principal: dict = Depends(require_role_of(MemberRole.admin)),
    db: Session = Depends(get_db),
):
    if not db.get(Organization, org_id):
        raise HTTPException(status_code=404, detail="Organization not found")
    return create_subscription(
        db,
        organization_id=org_id,
        payload=payload,
        actor_id=principal["user_id"],
    )


@router.patch("/{org_id}/webhook-subscriptions/{subscription_id}", response_model=WebhookSubscriptionResponse)
def update_webhook_subscription(
    org_id: str,
    subscription_id: str,
    payload: WebhookSubscriptionUpdate,
    principal: dict = Depends(require_role_of(MemberRole.admin)),
    db: Session = Depends(get_db),
):
    if not db.get(Organization, org_id):
        raise HTTPException(status_code=404, detail="Organization not found")
    return update_subscription(
        db,
        organization_id=org_id,
        subscription_id=subscription_id,
        payload=payload,
        actor_id=principal["user_id"],
    )


@router.get("/{org_id}/webhook-deliveries", response_model=list[WebhookDeliveryResponse])
def list_webhook_deliveries(
    org_id: str,
    subscription_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    skip: int = 0,
    principal: dict = Depends(require_role_of(MemberRole.admin)),
    db: Session = Depends(get_db),
):
    if not db.get(Organization, org_id):
        raise HTTPException(status_code=404, detail="Organization not found")
    query = db.query(WebhookDelivery).filter(WebhookDelivery.organization_id == org_id)
    if subscription_id:
        query = query.filter(WebhookDelivery.subscription_id == subscription_id)
    if status:
        query = query.filter(WebhookDelivery.status == status)
    return (
        query.order_by(WebhookDelivery.created_at.desc(), WebhookDelivery.id.desc())
        .offset(skip)
        .limit(min(max(limit, 1), 100))
        .all()
    )


@router.get("/{org_id}/webhook-delivery-summary", response_model=WebhookDeliverySummaryResponse)
def get_webhook_delivery_summary(
    org_id: str,
    principal: dict = Depends(require_role_of(MemberRole.admin)),
    db: Session = Depends(get_db),
):
    if not db.get(Organization, org_id):
        raise HTTPException(status_code=404, detail="Organization not found")
    return summarize_webhook_deliveries(db, organization_id=org_id)


@router.post("/{org_id}/webhook-test-events", response_model=list[WebhookDeliveryResponse], status_code=201)
def create_webhook_test_event(
    org_id: str,
    payload: WebhookTestEventRequest,
    principal: dict = Depends(require_role_of(MemberRole.admin)),
    db: Session = Depends(get_db),
):
    if not db.get(Organization, org_id):
        raise HTTPException(status_code=404, detail="Organization not found")
    deliveries = enqueue_webhook_event(
        db,
        organization_id=org_id,
        event_type=payload.event_type,
        event_id=payload.event_id,
        payload={
            **payload.payload,
            "event_type": payload.event_type,
            "event_id": payload.event_id,
            "organization_id": org_id,
            "triggered_by": principal["user_id"],
        },
    )
    log_change(
        db,
        "webhook_delivery",
        payload.event_id,
        "enqueue_test_event",
        actor_id=principal["user_id"],
        organization_id=org_id,
        new_values={"event_type": payload.event_type, "delivery_count": len(deliveries)},
    )
    db.commit()
    for delivery in deliveries:
        db.refresh(delivery)
    return deliveries


@router.post("/{org_id}/webhook-deliveries/{delivery_id}/attempt", response_model=WebhookDeliveryResponse)
def attempt_organization_webhook_delivery(
    org_id: str,
    delivery_id: str,
    principal: dict = Depends(require_role_of(MemberRole.admin)),
    db: Session = Depends(get_db),
):
    delivery = (
        db.query(WebhookDelivery)
        .filter(WebhookDelivery.organization_id == org_id, WebhookDelivery.id == delivery_id)
        .first()
    )
    if delivery is None:
        raise HTTPException(status_code=404, detail="Webhook delivery not found")
    attempted = attempt_webhook_delivery(db, delivery_id=delivery.id)
    log_change(
        db,
        "webhook_delivery",
        attempted.id,
        "attempt",
        actor_id=principal["user_id"],
        organization_id=org_id,
        new_values={
            "status": attempted.status,
            "attempt_count": attempted.attempt_count,
            "response_status_code": attempted.response_status_code,
        },
    )
    db.commit()
    db.refresh(attempted)
    return attempted


@router.post("/{org_id}/webhook-deliveries/{delivery_id}/replay", response_model=WebhookDeliveryResponse)
def replay_organization_webhook_delivery(
    org_id: str,
    delivery_id: str,
    principal: dict = Depends(require_role_of(MemberRole.admin)),
    db: Session = Depends(get_db),
):
    replayed = replay_webhook_delivery(db, organization_id=org_id, delivery_id=delivery_id)
    log_change(
        db,
        "webhook_delivery",
        replayed.id,
        "replay",
        actor_id=principal["user_id"],
        organization_id=org_id,
        new_values={
            "status": replayed.status,
            "attempt_count": replayed.attempt_count,
        },
    )
    db.commit()
    db.refresh(replayed)
    return replayed


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
