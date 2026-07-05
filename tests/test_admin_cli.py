"""Backoffice CLI (scripts/admin.py)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import admin as admin_cli  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.models.audit_log import AuditLog  # noqa: E402
from app.models.organization import Organization  # noqa: E402
from app.models.organization_membership import (  # noqa: E402
    MemberRole,
    OrganizationMembership,
)
from app.models.user import User  # noqa: E402
from app.services.security import hash_password  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _create_tables():
    # Admin CLI opens SessionLocal directly (script use), so it hits the DB
    # named by DATABASE_URL rather than a per-test fixture. Ensure tables
    # exist on that DB. Uses create_all rather than alembic — the CLI's
    # behavior is what's under test, not migration order.
    Base.metadata.create_all(bind=engine)
    yield
    # Leave the file — other tests in the run may use it. CI cleans up.


@pytest.fixture()
def org_with_two_admins():
    with SessionLocal() as db:
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
    with SessionLocal() as db:
        before = db.query(User).filter(User.email == email).first().token_version

    _run("--yes", "--reason", "test", "revoke-sessions", email)

    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email).first()
        assert user.token_version == before + 1
        # And an audit-log row landed with actor_id=None.
        rows = db.query(AuditLog).filter(
            AuditLog.entity_id == user.id,
            AuditLog.action == "admin_revoke_sessions",
        ).all()
        assert len(rows) == 1
        assert rows[0].actor_id is None
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
    with SessionLocal() as db:
        before = db.query(User).filter(User.email == email).first().token_version

    _run("--yes", "--reason", "test", "deactivate", email)

    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email).first()
        assert user.is_active is False
        assert user.token_version == before + 1
