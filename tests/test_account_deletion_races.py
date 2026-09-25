"""Account deletion must share the member-management active-admin invariant."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, get_ident
from uuid import uuid4

import pytest
from fastapi import HTTPException, Response
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.db import configure_sqlite_foreign_keys
from app.models.audit_log import AuditLog
from app.models.organization import Organization
from app.models.organization_membership import MemberRole, OrganizationMembership
from app.models.user import User
from app.routes.auth import delete_account
from app.routes.organizations import update_member_role
from app.schemas.auth import DeleteAccountRequest
from app.schemas.organization import UpdateMemberRequest
from app.services.security import create_access_token, hash_password
from app.utils.auth_deps import get_current_user

PASSWORD = "LocalAccountDeletionRegression42!"


def _fixture(db, *, second_active=True, second_role=MemberRole.admin, org_count=1):
    users = [User(id=str(uuid4()), email=f"delete-{uuid4().hex}@example.com",
                  full_name="Synthetic account", password_hash=hash_password(PASSWORD),
                  is_active=active) for active in (True, second_active)]
    orgs = [Organization(id=str(uuid4()), name="Synthetic organization", slug=uuid4().hex)
            for _ in range(org_count)]
    db.add_all([*users, *orgs])
    db.flush()
    for user, role in zip(users, [MemberRole.admin, second_role]):
        # Opposite membership insertion orders exercise multi-parent locking.
        for org in orgs if user is users[0] else reversed(orgs):
            db.add(OrganizationMembership(user_id=user.id, organization_id=org.id, role=role))
    db.commit()
    tokens = [create_access_token(user_id=user.id, org_id=orgs[0].id) for user in users]
    return users, orgs, tokens


def _delete(client, token):
    return client.post("/v1/auth/delete-account", json={"password": PASSWORD},
                       headers={"Authorization": f"Bearer {token}"})


def _active_admins(db, org_id):
    return db.query(OrganizationMembership).join(User).filter(
        OrganizationMembership.organization_id == org_id,
        OrganizationMembership.role == MemberRole.admin,
        User.is_active.is_(True),
    ).count()


@pytest.mark.parametrize("active,role", [
    (False, MemberRole.admin), (True, MemberRole.editor), (False, MemberRole.viewer),
])
def test_only_another_active_admin_permits_account_deletion(client, db, active, role):
    users, orgs, tokens = _fixture(db, second_active=active, second_role=role)
    result = _delete(client, tokens[0])
    assert result.status_code == 409
    assert "active admin" in result.json()["detail"]
    db.expire_all()
    assert db.get(User, users[0].id) is not None
    assert _active_admins(db, orgs[0].id) == 1
    assert db.query(AuditLog).filter_by(action="account_deleted").count() == 0


def test_audit_and_account_deletion_share_one_commit(client, db, monkeypatch):
    users, _, tokens = _fixture(db)
    user_id = users[0].id
    commit = Session.commit
    commits = []

    def record_commit(session):
        commits.append(1)
        return commit(session)

    monkeypatch.setattr(Session, "commit", record_commit)
    assert _delete(client, tokens[0]).status_code == 204
    assert len(commits) == 1
    db.expire_all()
    assert db.get(User, user_id) is None
    audit = db.query(AuditLog).filter_by(entity_id=user_id, action="account_deleted").one()
    assert audit.actor_id is None


def test_delete_failure_rolls_back_audit_and_preserves_account(client, db, monkeypatch):
    users, _, tokens = _fixture(db)
    user_id = users[0].id
    original_delete = Session.delete

    def fail_deletion(session, instance):
        if isinstance(instance, User):
            raise RuntimeError("Synthetic deletion failure")
        return original_delete(session, instance)

    monkeypatch.setattr(Session, "delete", fail_deletion)
    with pytest.raises(RuntimeError, match="Synthetic deletion failure"):
        _delete(client, tokens[0])
    db.expire_all()
    assert db.get(User, user_id) is not None
    assert db.query(AuditLog).filter_by(entity_id=user_id, action="account_deleted").count() == 0


@pytest.mark.parametrize("second_action", ["delete", "demote"])
def test_concurrent_departures_cannot_orphan_organizations(client, db, second_action):
    users, orgs, tokens = _fixture(db, org_count=2 if second_action == "delete" else 1)
    org_ids = [org.id for org in orgs]
    user_ids = [user.id for user in users]
    db.rollback()
    # Separate connections are essential; TestClient's shared StaticPool cannot
    # establish evidence about lock serialization.
    engine = create_engine(db.get_bind().url, poolclass=NullPool,
                           connect_args={"check_same_thread": False, "timeout": 10})
    configure_sqlite_foreign_keys(engine)
    authorized = Barrier(2)
    lock_orders = {}

    @event.listens_for(engine, "before_cursor_execute")
    def record_locks(_conn, _cursor, statement, parameters, _context, _many):
        if statement.startswith("UPDATE organizations SET updated_at=organizations.updated_at"):
            lock_orders.setdefault(get_ident(), []).append(parameters[0])

    def depart(index):
        with Session(engine) as session:
            principal = get_current_user(authorization=f"Bearer {tokens[index]}", db=session)
            authorized.wait(timeout=10)
            try:
                if index == 1 and second_action == "demote":
                    update_member_role(org_id=org_ids[0], user_id=user_ids[index],
                                       payload=UpdateMemberRequest(role=MemberRole.viewer),
                                       response=Response(), principal=principal, db=session)
                    return 200
                delete_account(payload=DeleteAccountRequest(password=PASSWORD),
                               response=Response(), principal=principal, db=session)
                return 204
            except HTTPException as exc:
                session.rollback()
                return exc.status_code

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(depart, [0, 1]))
    finally:
        engine.dispose()
    if second_action == "delete":
        assert sorted(outcomes) == [204, 409]
        assert len(lock_orders) == 2
        assert all(order == sorted(org_ids) for order in lock_orders.values())
    else:
        assert outcomes in ([204, 400], [409, 200])
    db.expire_all()
    assert all(_active_admins(db, org_id) == 1 for org_id in org_ids)
    assert db.query(AuditLog).filter(AuditLog.action.in_(["account_deleted", "role_change"])).count() == 1


def test_account_roles_are_rechecked_after_authorization(client, db):
    users, orgs, tokens = _fixture(db)
    principal = get_current_user(authorization=f"Bearer {tokens[0]}", db=db)
    other_membership = db.query(OrganizationMembership).filter_by(
        user_id=users[1].id, organization_id=orgs[0].id,
    ).one()
    with Session(db.get_bind()) as other:
        other.get(OrganizationMembership, other_membership.id).role = MemberRole.viewer
        other.commit()
    assert other_membership.role == MemberRole.admin
    with pytest.raises(HTTPException) as error:
        delete_account(payload=DeleteAccountRequest(password=PASSWORD),
                       response=Response(), principal=principal, db=db)
    assert error.value.status_code == 409
    db.rollback()


def test_new_membership_during_lock_acquisition_requires_retry(client, db):
    users, orgs, tokens = _fixture(db)
    extra_org = Organization(id=str(uuid4()), name="Concurrent invite", slug=uuid4().hex)
    db.add(extra_org)
    db.commit()
    user_id, extra_id = users[0].id, extra_org.id
    engine = db.get_bind()
    inserted = False

    def insert_before_lock(conn, _cursor, statement, _parameters, _context, _many):
        nonlocal inserted
        if not inserted and statement.startswith("UPDATE organizations SET updated_at=organizations.updated_at"):
            inserted = True
            # Controlled interleaving before the first parent lock. This is not
            # claimed as a PostgreSQL concurrency test.
            conn.execute(OrganizationMembership.__table__.insert().values(
                id=str(uuid4()), user_id=user_id, organization_id=extra_id,
                role=MemberRole.admin, is_default=False,
            ))

    event.listen(engine, "before_cursor_execute", insert_before_lock)
    try:
        response = _delete(client, tokens[0])
    finally:
        event.remove(engine, "before_cursor_execute", insert_before_lock)
    assert inserted
    assert response.status_code == 409
    assert response.json()["detail"] == "Memberships changed; retry account deletion"
    db.expire_all()
    assert db.get(User, user_id) is not None
    assert _active_admins(db, orgs[0].id) == 2


@pytest.mark.parametrize("change", ["inactive", "token_version", "password_hash"])
def test_account_credentials_are_rechecked_after_authorization(client, db, change):
    users, _, tokens = _fixture(db)
    principal = get_current_user(authorization=f"Bearer {tokens[0]}", db=db)
    with Session(db.get_bind()) as other:
        user = other.get(User, users[0].id)
        if change == "inactive":
            user.is_active = False
        elif change == "token_version":
            user.token_version += 1
        else:
            user.password_hash = hash_password("ChangedCredentialsOnly42!")
        other.commit()
    with pytest.raises(HTTPException) as error:
        delete_account(payload=DeleteAccountRequest(password=PASSWORD),
                       response=Response(), principal=principal, db=db)
    assert error.value.status_code == 401
    db.rollback()
