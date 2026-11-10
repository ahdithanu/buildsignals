"""Explicit operator credentials for tests that exercise source operations."""
from uuid import uuid4

import pytest

from app import config
from app.models.organization import Organization
from app.models.organization_membership import MemberRole, OrganizationMembership
from app.models.user import User
from app.services.security import create_access_token
from app.utils.org_scope import DEFAULT_ORG_ID


@pytest.fixture
def internal_operator(client, db, monkeypatch):
    user_id = str(uuid4())
    if not db.get(Organization, DEFAULT_ORG_ID):
        db.add(Organization(id=DEFAULT_ORG_ID, name="Test workspace", slug=DEFAULT_ORG_ID))
    db.add(User(id=user_id, email=f"operator-{user_id}@example.com", full_name="Test operator",
                password_hash="!nologin", is_active=True))
    db.add(OrganizationMembership(organization_id=DEFAULT_ORG_ID, user_id=user_id,
                                  role=MemberRole.admin, is_default=True))
    db.commit()
    monkeypatch.setattr(config, "INTERNAL_OPERATIONS_USER_IDS", frozenset({user_id}))
    client.headers["Authorization"] = "Bearer " + create_access_token(user_id=user_id, org_id=DEFAULT_ORG_ID)
    return user_id
