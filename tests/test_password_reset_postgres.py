"""Actual restricted-role HTTP recovery regressions; synthetic accounts only.

TEST_POSTGRES_URL is the sole target selector. Provision and migrate the owned
local target independently; this file never creates schema or removes foreign
fixtures. The snapshot nonce guard does not accept generic TEST_POSTGRES_URL
database names, so generic target syntax and physical identity are checked here.
"""
from __future__ import annotations

import hashlib
import os
import re
import secrets
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, event, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.config import REFRESH_COOKIE_NAME
from app.db import _set_rls_org, get_db
from app.main import app
from app.models.audit_log import AuditLog
from app.models.organization import Organization
from app.models.organization_membership import MemberRole, OrganizationMembership
from app.models.password_reset_token import PasswordResetToken
from app.models.user import User
from app.routes.password_reset import _recovery_audit_scope, _recovery_organization_id
from app.services.account_lockout import lockout
from app.services.audit_service import log_change
from app.services.rate_limiter import InMemoryRateLimiter, limiter
from app.services.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.utils.org_scope import (
    RequestContext,
    get_current_context,
    reset_current_context,
    set_current_context,
)

URL = os.environ.get("TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not URL, reason="Explicit owned local TEST_POSTGRES_URL required")
OLD_PASSWORD = "SyntheticOldPassword82!"
NEW_PASSWORD = "SyntheticReplacement93!"


def _target():
    """Fail closed before connecting; never fall back to DATABASE_URL or PG*."""
    try:
        target = make_url(URL)
        generic_nonce = (target.database or "").removeprefix("forgeos_test_")
        generic = (target.database or "").startswith("forgeos_test_") and UUID(hex=generic_nonce).version == 4
        ci = os.environ.get("GITHUB_ACTIONS") == "true" and target.database == "dealsignal_test"
        valid = (
            target.drivername == "postgresql+psycopg2" and target.host in {"127.0.0.1", "::1", "localhost"}
            and target.port is not None and bool(target.username) and bool(target.password)
            and not target.query and (generic or ci)
            and all(not name.startswith("PG") or not value for name, value in os.environ.items())
        )
    except Exception:
        valid = False
    if not valid:
        pytest.fail("Invalid explicit disposable password-recovery PostgreSQL target", pytrace=False)
    return target


def _verify_connection(target, connection, _record):
    cursor = connection.cursor()
    try:
        cursor.execute("BEGIN READ ONLY")
        cursor.execute(
            "SELECT current_database(), current_user, session_user, rolsuper, rolbypassrls "
            "FROM pg_catalog.pg_roles WHERE rolname=current_user"
        )
        identity = cursor.fetchone()
        if identity != (target.database, target.username, target.username, False, False):
            raise RuntimeError("Unverified restricted password-recovery PostgreSQL connection")
        cursor.execute(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_catalog.pg_class WHERE oid='audit_logs'::regclass"
        )
        if cursor.fetchone() != (True, True):
            raise RuntimeError("Password-recovery acceptance requires forced audit RLS")
    finally:
        connection.rollback()
        cursor.close()


@pytest.fixture(params=["default_priority", "joined_priority", "id_tiebreak"])
def recovery_account(request, monkeypatch):
    target = _target()
    engine = create_engine(target, poolclass=NullPool, echo=False, hide_parameters=True,
                           connect_args={"connect_timeout": 5, "options": "-c statement_timeout=10000 -c lock_timeout=5000"})
    event.listen(engine, "connect", lambda connection, record: _verify_connection(target, connection, record))
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    event.listen(factory, "after_begin", _set_rls_org)

    @contextmanager
    def scoped(org):
        token = set_current_context(RequestContext(org, "synthetic-password-recovery-test"))
        try:
            with factory() as db:
                yield db
        finally:
            reset_current_context(token)

    def no_external(*_args, **_kwargs):
        pytest.fail("Password-recovery PostgreSQL tests must not make external calls")

    monkeypatch.setattr("urllib.request.urlopen", no_external)
    monkeypatch.setattr("app.services.llm_client.get_default_llm_client", no_external)
    sender = SimpleNamespace(available=True, send=Mock())
    monkeypatch.setattr("app.routes.password_reset.get_email_service", lambda: sender)
    monkeypatch.setenv("APP_BASE_URL", "https://example.invalid")
    assert isinstance(limiter, InMemoryRateLimiter), "Recovery tests require the isolated in-memory limiter"
    limiter.clear()
    lockout.clear()
    user_id, caller_id = str(uuid4()), str(uuid4())
    org_ids = [str(uuid4()) for _ in range(5)]
    previous_override = app.dependency_overrides.get(get_db)

    def override_db():
        with factory() as db:
            yield db

    try:
        with scoped(org_ids[0]) as setup:
            assert setup.scalar(select(Organization.id).where(Organization.id == "default-org")) is None, (
                "Requires an owned target without default-org; never delete another fixture's organization"
            )
            setup.add_all([
                Organization(id=org, name="Synthetic recovery organization", slug=f"recovery-{org}",
                             is_active=index != 3)
                for index, org in enumerate(org_ids)
            ])
            setup.add_all([
                User(id=user_id, email=f"recovery-{user_id}@example.com", full_name="Synthetic recovery account",
                     password_hash=hash_password(OLD_PASSWORD), token_version=7),
                User(id=caller_id, email=f"caller-{caller_id}@example.com", full_name="Synthetic unrelated caller",
                     password_hash="!nologin"),
            ])
            setup.flush()
            membership_ids = sorted(str(uuid4()) for _ in range(3))
            base = datetime(2025, 1, 1, tzinfo=timezone.utc)
            for index in (2, 1, 0):
                default = request.param == "default_priority" and index == 1
                joined = base if request.param == "id_tiebreak" else base + timedelta(days=3 - index)
                setup.add(OrganizationMembership(
                    id=membership_ids[index], organization_id=org_ids[index], user_id=user_id,
                    role=MemberRole.editor, is_default=default, joined_at=joined,
                ))
            # An older default membership in an inactive organization must lose.
            setup.add(OrganizationMembership(organization_id=org_ids[3], user_id=user_id,
                                              role=MemberRole.admin, is_default=True, joined_at=base - timedelta(days=30)))
            setup.add(OrganizationMembership(organization_id=org_ids[4], user_id=caller_id,
                                              role=MemberRole.editor, is_default=True))
            setup.flush()
            selected = setup.scalar(select(OrganizationMembership.organization_id).join(
                Organization, Organization.id == OrganizationMembership.organization_id,
            ).where(OrganizationMembership.user_id == user_id, Organization.is_active.is_(True)).order_by(
                OrganizationMembership.is_default.desc(), OrganizationMembership.joined_at.asc(),
                OrganizationMembership.id.asc(),
            ).limit(1))
            assert selected == org_ids[{"default_priority": 1, "joined_priority": 2, "id_tiebreak": 0}[request.param]]
            setup.commit()
        app.dependency_overrides[get_db] = override_db
        context = set_current_context(None)
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                yield SimpleNamespace(client=client, sender=sender, scoped=scoped, user_id=user_id,
                                      email=f"recovery-{user_id}@example.com", org=selected,
                                      foreign_org=org_ids[4], caller_id=caller_id)
        finally:
            reset_current_context(context)
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override
        # Every deletion is constrained to this fixture's unique owned identities.
        for org in org_ids:
            with scoped(org) as cleanup:
                cleanup.execute(delete(AuditLog).where(AuditLog.entity_id.in_([user_id, caller_id])))
                cleanup.commit()
        with scoped(org_ids[0]) as cleanup:
            cleanup.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id.in_([user_id, caller_id])))
            cleanup.execute(delete(OrganizationMembership).where(OrganizationMembership.user_id.in_([user_id, caller_id])))
            cleanup.execute(delete(User).where(User.id.in_([user_id, caller_id])))
            cleanup.execute(delete(Organization).where(Organization.id.in_(org_ids)))
            cleanup.commit()
        engine.dispose()
        limiter.clear()
        lockout.clear()


def _headers(account, unrelated_context):
    if not unrelated_context:
        return {}
    return {"Authorization": "Bearer " + create_access_token(user_id=account.caller_id, org_id=account.foreign_org)}


def _assert_scoped_audit(account, action):
    with account.scoped(account.org) as db:
        rows = db.scalars(select(AuditLog).where(AuditLog.entity_id == account.user_id, AuditLog.action == action)).all()
        assert len(rows) == 1
        assert rows[0].organization_id == account.org and rows[0].actor_id == account.user_id
        assert db.scalar(select(Organization.id).where(Organization.id == "default-org")) is None
    with account.scoped(account.foreign_org) as db:
        # No application organization predicate: assert actual RLS read denial.
        assert db.scalars(select(AuditLog).where(AuditLog.entity_id == account.user_id, AuditLog.action == action)).all() == []


@pytest.mark.parametrize("unrelated_context", [False, True], ids=["anonymous", "unrelated-authenticated-org"])
def test_forgot_uses_stored_active_membership_without_default_org(recovery_account, unrelated_context):
    account = recovery_account
    response = account.client.post("/auth/password/forgot", json={"email": account.email},
                                   headers=_headers(account, unrelated_context))
    assert response.status_code == 204, "Forgot must not fail because default-org is absent"
    account.sender.send.assert_called_once()
    mail = account.sender.send.call_args.kwargs
    assert mail["to"] == account.email
    match = re.search(r"reset-password\?token=([A-Za-z0-9_-]+)", mail["text"])
    assert match is not None, "Fake mail must include a reset link"
    digest = hashlib.sha256(match.group(1).encode()).hexdigest()
    with account.scoped(account.org) as db:
        row = db.scalars(select(PasswordResetToken).where(PasswordResetToken.user_id == account.user_id)).one()
        assert row.token_hash == digest and row.used_at is None
    _assert_scoped_audit(account, "password_reset_requested")


@pytest.mark.parametrize("unrelated_context", [False, True], ids=["anonymous", "unrelated-authenticated-org"])
def test_reset_uses_stored_membership_revokes_sessions_and_is_single_use(recovery_account, unrelated_context):
    account = recovery_account
    plaintext = secrets.token_urlsafe(32)
    digest = hashlib.sha256(plaintext.encode()).hexdigest()
    old_refresh = create_refresh_token(user_id=account.user_id, org_id=account.org, token_version=7)
    with account.scoped(account.org) as db:
        db.add(PasswordResetToken(user_id=account.user_id, token_hash=digest,
                                  expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
        db.commit()
    payload = {"token": plaintext, "new_password": NEW_PASSWORD}
    response = account.client.post("/auth/password/reset", json=payload, headers=_headers(account, unrelated_context))
    assert response.status_code == 204, "Reset must not fail because default-org is absent"
    with account.scoped(account.org) as db:
        user = db.get(User, account.user_id)
        assert verify_password(NEW_PASSWORD, user.password_hash)
        assert not verify_password(OLD_PASSWORD, user.password_hash)
        assert user.token_version == 8
        assert db.scalars(select(PasswordResetToken).where(PasswordResetToken.token_hash == digest)).one().used_at is not None
    assert account.client.post("/auth/password/reset", json=payload).status_code == 400
    revoked = account.client.post("/v1/auth/refresh", headers={"Cookie": f"{REFRESH_COOKIE_NAME}={old_refresh}"})
    assert revoked.status_code == 401 and "revoked" in revoked.json()["detail"].lower()
    account.sender.send.assert_not_called()
    _assert_scoped_audit(account, "password_reset_completed")


def test_recovery_scope_restores_foreign_context_after_successful_commit(recovery_account):
    account = recovery_account
    with account.scoped(account.foreign_org) as db:
        previous = get_current_context()
        user = db.get(User, account.user_id)
        selected = _recovery_organization_id(db, user.id)
        assert selected == account.org and selected != previous.org_id
        assert db.scalar(text("SELECT current_setting('app.current_org')")) == previous.org_id
        with _recovery_audit_scope(db, selected, user.id):
            assert get_current_context() == RequestContext(selected, user.id)
            assert db.scalar(text("SELECT current_setting('app.current_org')")) == selected
            audit = log_change(db, "user", user.id, "synthetic_recovery_scope_commit",
                               actor_id=user.id, organization_id=selected)
            db.flush()
            audit_id = audit.id
            db.commit()
            assert not db.in_transaction()
        assert get_current_context() == previous
        assert not db.in_transaction()
        # A fresh transaction must inherit the restored foreign caller scope.
        assert db.scalar(text("SELECT current_setting('app.current_org')")) == previous.org_id
        assert db.scalar(select(AuditLog.id).where(AuditLog.id == audit_id)) is None
    with account.scoped(selected) as verify:
        audit = verify.get(AuditLog, audit_id)
        assert audit is not None and audit.organization_id == selected
        assert audit.actor_id == account.user_id


def test_recovery_scope_restores_rls_without_committing_existing_transaction(recovery_account):
    account = recovery_account
    with account.scoped(account.foreign_org) as db:
        previous = get_current_context()
        user = db.get(User, account.user_id)
        selected = _recovery_organization_id(db, user.id)
        assert selected == account.org and selected != previous.org_id
        assert db.scalar(text("SELECT current_setting('app.current_org')")) == previous.org_id
        transaction = db.get_transaction()
        with _recovery_audit_scope(db, selected, user.id):
            assert get_current_context() == RequestContext(selected, user.id)
            assert db.scalar(text("SELECT current_setting('app.current_org')")) == selected
            audit = log_change(db, "user", user.id, "synthetic_recovery_scope_uncommitted",
                               actor_id=user.id, organization_id=selected)
            db.flush()
            audit_id = audit.id
        assert get_current_context() == previous
        assert db.get_transaction() is transaction and transaction.is_active
        assert db.scalar(text("SELECT current_setting('app.current_org')")) == previous.org_id
        assert db.scalar(select(AuditLog.id).where(AuditLog.id == audit_id)) is None
        db.rollback()
    # The helper must not have committed the caller-owned transaction.
    with account.scoped(selected) as verify:
        assert verify.scalar(select(AuditLog.id).where(AuditLog.id == audit_id)) is None


def test_recovery_scope_rolls_back_error_and_restores_foreign_context(recovery_account):
    account = recovery_account
    with account.scoped(account.foreign_org) as db:
        previous = get_current_context()
        user = db.get(User, account.user_id)
        selected = _recovery_organization_id(db, user.id)
        original_version = user.token_version
        assert selected == account.org and selected != previous.org_id
        assert db.scalar(text("SELECT current_setting('app.current_org')")) == previous.org_id
        with pytest.raises(RuntimeError, match="Synthetic recovery rollback"):
            with _recovery_audit_scope(db, selected, user.id):
                assert get_current_context() == RequestContext(selected, user.id)
                assert db.scalar(text("SELECT current_setting('app.current_org')")) == selected
                user.token_version += 1
                audit = log_change(db, "user", user.id, "synthetic_recovery_scope_rollback",
                                   actor_id=user.id, organization_id=selected)
                db.flush()
                audit_id = audit.id
                raise RuntimeError("Synthetic recovery rollback")
        assert get_current_context() == previous
        assert not db.in_transaction()
        assert db.scalar(text("SELECT current_setting('app.current_org')")) == previous.org_id
        assert db.scalar(select(AuditLog.id).where(AuditLog.id == audit_id)) is None
        assert db.scalar(select(User.token_version).where(User.id == account.user_id)) == original_version
    with account.scoped(selected) as verify:
        assert verify.scalar(select(AuditLog.id).where(AuditLog.id == audit_id)) is None
        assert verify.get(User, account.user_id).token_version == original_version
