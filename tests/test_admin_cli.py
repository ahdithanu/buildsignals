"""Backoffice CLI (scripts/admin.py)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import Base  # noqa: E402
from app.models.audit_log import AuditLog  # noqa: E402
from app.models.contact import Contact  # noqa: E402
from app.models.deal import Deal  # noqa: E402
from app.models.deal_assumptions import DealAssumptions  # noqa: E402
from app.models.deal_outputs import DealOutputs  # noqa: E402
from app.models.organization import Organization  # noqa: E402
from app.models.organization_membership import (  # noqa: E402
    MemberRole,
    OrganizationMembership,
)
from app.models.signal import Signal  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.security import create_access_token, hash_password  # noqa: E402
from scripts import admin as admin_cli  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_cli_database(tmp_path, monkeypatch):
    # The CLI bypasses get_db; never let tests touch the configured app database.
    engine = create_engine(f"sqlite:///{tmp_path / 'admin-cli.db'}")
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(admin_cli, "SessionLocal", sessionmaker(bind=engine))
    try:
        yield
    finally:
        engine.dispose()


@pytest.fixture()
def org_with_two_admins():
    with admin_cli.SessionLocal() as db:
        org = Organization(id=str(uuid4()), name="Admin CLI Org", slug=f"acli-{uuid4().hex[:8]}")
        db.add(org)
        db.flush()

        alice = User(
            id=str(uuid4()), email=f"alice-{uuid4().hex[:6]}@example.com",
            password_hash=hash_password("CorrectHorseBattery42"),
            full_name="Alice",
        )
        bob = User(
            id=str(uuid4()), email=f"bob-{uuid4().hex[:6]}@example.com",
            password_hash=hash_password("CorrectHorseBattery42"),
            full_name="Bob",
        )
        db.add_all([alice, bob])
        db.flush()

        db.add(OrganizationMembership(id=str(uuid4()), organization_id=org.id, user_id=alice.id, role=MemberRole.admin, is_default=True))
        db.add(OrganizationMembership(id=str(uuid4()), organization_id=org.id, user_id=bob.id, role=MemberRole.admin, is_default=True))
        db.commit()

        yield {"org_id": org.id, "alice": alice.email, "bob": bob.email, "alice_id": alice.id}


def _run(*argv):
    return admin_cli.main(list(argv))


def _delete_demo_org_if_present(db):
    existing = db.query(Organization).filter(Organization.slug == admin_cli.DEMO_ORG_SLUG).first()
    if not existing:
        return
    deal_ids = [
        row[0]
        for row in db.query(Deal.id).filter(Deal.organization_id == existing.id).all()
    ]
    if deal_ids:
        db.query(Contact).filter(Contact.deal_id.in_(deal_ids)).delete(synchronize_session=False)
        db.query(Signal).filter(Signal.deal_id.in_(deal_ids)).delete(synchronize_session=False)
        db.query(DealAssumptions).filter(DealAssumptions.deal_id.in_(deal_ids)).delete(synchronize_session=False)
        db.query(DealOutputs).filter(DealOutputs.deal_id.in_(deal_ids)).delete(synchronize_session=False)
        db.query(Deal).filter(Deal.id.in_(deal_ids)).delete(synchronize_session=False)
    db.query(AuditLog).filter(AuditLog.organization_id == existing.id).delete(synchronize_session=False)
    db.query(OrganizationMembership).filter(
        OrganizationMembership.organization_id == existing.id
    ).delete(synchronize_session=False)
    db.delete(existing)
    db.commit()


def test_find_user_prints_json(org_with_two_admins, capsys):
    rc = _run("find-user", org_with_two_admins["alice"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["email"] == org_with_two_admins["alice"]
    assert any(m["role"] == "admin" for m in payload["memberships"])


def test_mutation_refuses_without_yes(org_with_two_admins, capsys):
    with pytest.raises(SystemExit):
        _run("revoke-sessions", org_with_two_admins["alice"])
    err = capsys.readouterr().err
    assert "--yes" in err


def test_revoke_sessions_bumps_token_version(org_with_two_admins):
    email = org_with_two_admins["alice"]
    with admin_cli.SessionLocal() as db:
        before = db.query(User).filter(User.email == email).first().token_version

    _run("--yes", "--reason", "test", "revoke-sessions", email)

    with admin_cli.SessionLocal() as db:
        user = db.query(User).filter(User.email == email).first()
        assert user.token_version == before + 1
        # And an audit-log row landed with actor_id=None.
        rows = db.query(AuditLog).filter(
            AuditLog.entity_id == user.id,
            AuditLog.action == "admin_revoke_sessions",
        ).all()
        assert len(rows) == 1
        assert rows[0].actor_id is None
        assert rows[0].organization_id == org_with_two_admins["org_id"]
        assert "reason" in (rows[0].new_values or "")


def test_set_role_prevents_last_admin_demotion(org_with_two_admins, capsys):
    # Bob is one of two admins. Demoting one is fine — demoting the second is not.
    _run("--yes", "--reason", "test", "set-role",
         org_with_two_admins["bob"],
         "--org-id", org_with_two_admins["org_id"],
         "--role", "editor")

    # Alice is now the LAST admin.
    with pytest.raises(SystemExit):
        _run("--yes", "--reason", "test", "set-role",
             org_with_two_admins["alice"],
             "--org-id", org_with_two_admins["org_id"],
             "--role", "editor")
    err = capsys.readouterr().err
    assert "last admin" in err


def test_deactivate_revokes_sessions_and_deactivates(org_with_two_admins):
    email = org_with_two_admins["alice"]
    with admin_cli.SessionLocal() as db:
        before = db.query(User).filter(User.email == email).first().token_version

    _run("--yes", "--reason", "test", "deactivate", email)

    with admin_cli.SessionLocal() as db:
        user = db.query(User).filter(User.email == email).first()
        assert user.is_active is False
        assert user.token_version == before + 1
        audit = db.query(AuditLog).filter(
            AuditLog.entity_id == user.id,
            AuditLog.action == "admin_deactivate",
        ).one()
        assert audit.organization_id == org_with_two_admins["org_id"]


def test_ensure_demo_workspace_creates_isolated_synthetic_tenant(capsys):
    email = f"demo-{uuid4().hex[:8]}@buildsignals.test"
    password = "SyntheticDemoPass123"
    with admin_cli.SessionLocal() as db:
        _delete_demo_org_if_present(db)

    previous_password = os.environ.get("BUILD_SIGNALS_DEMO_PASSWORD")
    os.environ["BUILD_SIGNALS_DEMO_PASSWORD"] = password
    try:
        rc = _run(
            "--yes",
            "--reason",
            "public demo activation",
            "ensure-demo-workspace",
            "--email",
            email,
        )
    finally:
        if previous_password is None:
            os.environ.pop("BUILD_SIGNALS_DEMO_PASSWORD", None)
        else:
            os.environ["BUILD_SIGNALS_DEMO_PASSWORD"] = previous_password

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["demo_email"] == email
    assert payload["organization_slug"] == admin_cli.DEMO_ORG_SLUG
    assert payload["created_org"] is True
    assert payload["created_user"] is True
    assert payload["role"] == "viewer"
    assert payload["seeded_data"] is True

    with admin_cli.SessionLocal() as db:
        org = db.query(Organization).filter(Organization.slug == admin_cli.DEMO_ORG_SLUG).one()
        user = db.query(User).filter(User.email == email).one()
        memberships = (
            db.query(OrganizationMembership)
            .filter(OrganizationMembership.user_id == user.id)
            .all()
        )
        assert len(memberships) == 1
        assert memberships[0].organization_id == org.id
        assert memberships[0].role == MemberRole.viewer
        assert memberships[0].is_default is True
        assert user.is_active is True
        assert user.is_superuser is False
        assert user.totp_enabled is False
        assert user.password_hash != password
        assert db.query(Deal).filter(
            Deal.organization_id == org.id,
            Deal.source == admin_cli.DEMO_DATA_SOURCE,
        ).count() == 2
        assert db.query(Signal).filter(
            Signal.organization_id == org.id,
            Signal.source == admin_cli.DEMO_DATA_SOURCE,
        ).count() == 3
        audit = db.query(AuditLog).filter(
            AuditLog.entity_id == org.id,
            AuditLog.action == "admin_ensure_demo_workspace",
        ).one()
        assert audit.organization_id == org.id

    previous_password = os.environ.get("BUILD_SIGNALS_DEMO_PASSWORD")
    os.environ["BUILD_SIGNALS_DEMO_PASSWORD"] = password
    try:
        rc = _run(
            "--yes",
            "--reason",
            "demo idempotency",
            "ensure-demo-workspace",
            "--email",
            email,
        )
    finally:
        if previous_password is None:
            os.environ.pop("BUILD_SIGNALS_DEMO_PASSWORD", None)
        else:
            os.environ["BUILD_SIGNALS_DEMO_PASSWORD"] = previous_password

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["created_org"] is False
    assert payload["created_user"] is False
    assert payload["seeded_data"] is False


def test_ensure_demo_workspace_refuses_auth_reset_for_existing_demo_user(capsys):
    email = f"demo-existing-{uuid4().hex[:8]}@buildsignals.test"
    original_hash = hash_password("ExistingDemoPass123")
    with admin_cli.SessionLocal() as db:
        _delete_demo_org_if_present(db)
        org = Organization(id=str(uuid4()), name="Build Signals Demo Workspace", slug=admin_cli.DEMO_ORG_SLUG)
        user = User(
            id=str(uuid4()),
            email=email,
            full_name="Existing Demo",
            password_hash=original_hash,
            is_active=True,
            is_superuser=False,
        )
        db.add_all([org, user])
        db.flush()
        db.add(OrganizationMembership(
            id=str(uuid4()),
            organization_id=org.id,
            user_id=user.id,
            role=MemberRole.viewer,
            is_default=True,
        ))
        db.commit()

    previous_password = os.environ.get("BUILD_SIGNALS_DEMO_PASSWORD")
    os.environ["BUILD_SIGNALS_DEMO_PASSWORD"] = "DifferentDemoPass123"
    try:
        with pytest.raises(SystemExit):
            _run(
                "--yes",
                "--reason",
                "must not reset",
                "ensure-demo-workspace",
                "--email",
                email,
            )
    finally:
        if previous_password is None:
            os.environ.pop("BUILD_SIGNALS_DEMO_PASSWORD", None)
        else:
            os.environ["BUILD_SIGNALS_DEMO_PASSWORD"] = previous_password

    assert "refusing to reset credentials" in capsys.readouterr().err
    with admin_cli.SessionLocal() as db:
        user = db.query(User).filter(User.email == email).one()
        assert user.password_hash == original_hash
        assert user.totp_enabled is False


def test_demo_viewer_cannot_mutate_or_manage_external_actions(client, db):
    email = f"demo-viewer-{uuid4().hex[:8]}@buildsignals.test"
    org = Organization(id=str(uuid4()), name="Build Signals Demo Workspace", slug=f"{admin_cli.DEMO_ORG_SLUG}-{uuid4().hex[:6]}")
    user = User(
        id=str(uuid4()),
        email=email,
        full_name="Demo Viewer",
        password_hash=hash_password("SyntheticDemoPass123"),
        is_active=True,
        is_superuser=False,
    )
    db.add_all([org, user])
    db.flush()
    db.add(OrganizationMembership(
        id=str(uuid4()),
        organization_id=org.id,
        user_id=user.id,
        role=MemberRole.viewer,
        is_default=True,
    ))
    db.commit()
    token = create_access_token(user_id=user.id, org_id=org.id)
    headers = {"Authorization": f"Bearer {token}"}

    deal_response = client.post(
        "/v1/deals",
        json={"name": "Should not write", "property_type": "retail"},
        headers=headers,
    )
    invite_response = client.post(
        f"/v1/organizations/{org.id}/members",
        json={"email": email, "role": "viewer"},
        headers=headers,
    )
    api_key_response = client.post(
        f"/v1/organizations/{org.id}/api-keys",
        json={"name": "demo key", "scopes": ["deals:read"]},
        headers=headers,
    )
    webhook_response = client.post(
        f"/v1/organizations/{org.id}/webhook-subscriptions",
        json={"name": "demo hook", "target_url": "https://example.invalid/hook", "event_types": ["deal.created"]},
        headers=headers,
    )

    assert deal_response.status_code == 403
    assert invite_response.status_code == 403
    assert api_key_response.status_code == 403
    assert webhook_response.status_code == 403


def test_ensure_demo_workspace_refuses_existing_non_demo_user(org_with_two_admins, capsys):
    previous_password = os.environ.get("BUILD_SIGNALS_DEMO_PASSWORD")
    os.environ["BUILD_SIGNALS_DEMO_PASSWORD"] = "SyntheticDemoPass123"
    try:
        with pytest.raises(SystemExit):
            _run(
                "--yes",
                "--reason",
                "should not cross tenant boundary",
                "ensure-demo-workspace",
                "--email",
                org_with_two_admins["alice"],
            )
    finally:
        if previous_password is None:
            os.environ.pop("BUILD_SIGNALS_DEMO_PASSWORD", None)
        else:
            os.environ["BUILD_SIGNALS_DEMO_PASSWORD"] = previous_password

    err = capsys.readouterr().err
    assert "non-demo org" in err
