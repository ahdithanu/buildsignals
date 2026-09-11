"""MFA transactions on independent connections, plus authenticated code budgets.

Postgres cases use a private, disposable schema when TEST_POSTGRES_URL is set.
No migrations or existing application tables are changed by this suite.
"""
from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pyotp
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException, Response
from sqlalchemy import create_engine, delete, event, select, update
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema, DropSchema

from app.db import Base, configure_sqlite_foreign_keys
from app.models.audit_log import AuditLog
from app.models.organization import Organization
from app.models.organization_membership import MemberRole, OrganizationMembership
from app.models.user import User
from app.routes import auth, twofa
from app.services.mfa_secrets import read_secret, store_secret
from app.services.rate_limiter import InMemoryRateLimiter
from app.services.security import hash_password

SECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"
NEXT_SECRET = "KRSXG5DSNFXGOIDBKRSXG5DSNFXGOIDB"
PASSWORD = "CorrectHorseBattery42"
NOW = 1_800_000_000
CODE = pyotp.TOTP(SECRET).at(NOW)
NEXT_CODE = pyotp.TOTP(NEXT_SECRET).at(NOW)


@pytest.fixture(autouse=True)
def runtime(monkeypatch):
    monkeypatch.setenv("MFA_ENCRYPTION_KEYS", json.dumps({"test": Fernet.generate_key().decode()}))
    monkeypatch.setenv("MFA_ACTIVE_KEY_ID", "test")
    monkeypatch.setenv("MFA_ALLOW_LEGACY_PLAINTEXT", "false")
    monkeypatch.setattr(twofa, "limiter", InMemoryRateLimiter())
    monkeypatch.setattr(auth, "limiter", InMemoryRateLimiter())
    monkeypatch.setattr(twofa.pyotp, "random_base32", lambda: NEXT_SECRET)
    original_verify = pyotp.TOTP.verify
    monkeypatch.setattr(
        twofa.pyotp.TOTP, "verify",
        lambda self, code, **kwargs: original_verify(self, code, for_time=NOW, **kwargs),
    )
    assert CODE != NEXT_CODE


@pytest.fixture(params=["sqlite", "postgresql"])
def mfa_engine(request, tmp_path):
    schema = None
    if request.param == "sqlite":
        engine = create_engine(
            f"sqlite:///{tmp_path / 'mfa-transactions.db'}",
            connect_args={"check_same_thread": False, "timeout": 5},
        )
        configure_sqlite_foreign_keys(engine)
        scoped = engine
    else:
        url = os.environ.get("TEST_POSTGRES_URL")
        if not url:
            pytest.skip("TEST_POSTGRES_URL not set; skipping Postgres MFA transactions")
        engine = create_engine(url, connect_args={"options": "-c lock_timeout=5000 -c statement_timeout=10000"})
        schema = "mfa_test_" + uuid4().hex
        with engine.begin() as connection:
            connection.execute(CreateSchema(schema))
        scoped = engine.execution_options(schema_translate_map={None: schema})
    try:
        Base.metadata.create_all(scoped, tables=[Organization.__table__, User.__table__, AuditLog.__table__])
        yield scoped
    finally:
        if schema:
            with engine.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))
        engine.dispose()


def seed(engine, *, enabled=False):
    with Session(engine) as db:
        db.add(Organization(id="org", name="MFA Test", slug="mfa-test"))
        user = User(id="user", email="mfa@example.com", full_name="MFA Test", password_hash=hash_password(PASSWORD), totp_enabled=enabled)
        store_secret(user, SECRET)
        db.add(user)
        db.commit()


def principal(db):
    return {"user": db.get(User, "user"), "user_id": "user", "org_id": "org", "role": "viewer"}


def invoke(action, db, actor, *, code=CODE, password=PASSWORD):
    if action == "setup":
        return twofa.setup(Response(), db=db, principal=actor)
    if action == "verify":
        return twofa.verify(twofa.VerifyRequest(code=code), db=db, principal=actor)
    return twofa.disable(twofa.DisableRequest(password=password, code=code), db=db, principal=actor)


def state(engine):
    with Session(engine) as db:
        user = db.get(User, "user")
        return user.totp_enabled, user.totp_secret, user.totp_secret_ciphertext, user.updated_at


def audits(engine):
    with Session(engine) as db:
        return [(row.action, row.actor_id, row.organization_id, row.old_values, row.new_values)
                for row in db.scalars(select(AuditLog)).all()]


@pytest.mark.parametrize("action", ["setup", "verify", "disable"])
def test_each_change_commits_state_and_secret_free_audit_once(mfa_engine, action):
    seed(mfa_engine, enabled=action == "disable")
    with Session(mfa_engine) as db:
        actor = principal(db)
        commits = []
        event.listen(db, "after_commit", lambda session: commits.append(True))
        result = invoke(action, db, actor)
        assert len(commits) == 1
        user = db.get(User, "user")
        assert user.totp_enabled == (action == "verify")
        expected_secret = NEXT_SECRET if action == "setup" else SECRET if action == "verify" else None
        assert read_secret(user) == expected_secret
        assert user.totp_secret is None
        if action == "setup":
            assert result.secret == NEXT_SECRET
    audit_action = {"setup": "2fa_setup", "verify": "2fa_enabled", "disable": "2fa_disabled"}[action]
    assert audits(mfa_engine) == [(audit_action, "user", "org", None, None)]


@pytest.mark.parametrize("action", ["setup", "verify", "disable"])
@pytest.mark.parametrize("failure_at", ["audit", "commit"])
def test_state_and_audit_roll_back_together_after_flush(mfa_engine, monkeypatch, action, failure_at):
    seed(mfa_engine, enabled=action == "disable")
    before = state(mfa_engine)
    original_log = twofa.log_change

    def fail_audit(db, *args, **kwargs):
        original_log(db, *args, **kwargs)
        db.flush()
        raise RuntimeError("Synthetic audit failure")

    def fail_commit(db):
        db.flush()
        raise RuntimeError("Synthetic commit failure")

    with Session(mfa_engine) as db:
        actor = principal(db)
        if failure_at == "audit":
            monkeypatch.setattr(twofa, "log_change", fail_audit)
        else:
            event.listen(db, "before_commit", fail_commit, once=True)
        with pytest.raises(RuntimeError, match="Synthetic"):
            invoke(action, db, actor)
        assert not db.in_transaction(), "Failed state/audit must be rolled back by the handler"
    assert state(mfa_engine) == before
    assert audits(mfa_engine) == []


@pytest.mark.parametrize("action", ["setup", "verify", "disable"])
@pytest.mark.parametrize("revocation", ["inactive", "deleted"])
def test_stale_authentication_snapshot_cannot_mutate_inactive_or_deleted_user(mfa_engine, action, revocation):
    seed(mfa_engine, enabled=action == "disable")
    with Session(mfa_engine) as stale:
        actor = principal(stale)
        assert actor["user"].is_active
        with Session(mfa_engine) as current:
            statement = delete(User).where(User.id == "user") if revocation == "deleted" else update(User).where(User.id == "user").values(is_active=False)
            current.execute(statement)
            current.commit()
        with pytest.raises(HTTPException) as error:
            invoke(action, stale, actor)
        assert error.value.status_code == 401
    assert audits(mfa_engine) == []


@pytest.mark.parametrize("changed", ["password", "secret"])
def test_disable_rechecks_current_credentials_instead_of_cached_user(mfa_engine, changed):
    seed(mfa_engine, enabled=True)
    with Session(mfa_engine) as stale:
        actor = principal(stale)
        with Session(mfa_engine) as current:
            user = current.get(User, "user")
            if changed == "password":
                user.password_hash = hash_password("AnotherCorrectPassword42")
            else:
                store_secret(user, NEXT_SECRET)
            current.commit()
        before = state(mfa_engine)
        with pytest.raises(HTTPException) as error:
            invoke("disable", stale, actor)
        assert error.value.status_code == 401
    assert state(mfa_engine) == before
    assert audits(mfa_engine) == []


@pytest.mark.parametrize("winner,contender,expected_error", [
    ("verify", "setup", 400),
    ("setup", "verify", 400),
    ("verify", "verify", 409),
    ("disable", "verify", 409),
    ("disable", "disable", 409),
])
def test_concurrent_changes_serialize_and_reload_under_lock(mfa_engine, monkeypatch, winner, contender, expected_error):
    seed(mfa_engine, enabled=winner == "disable")
    loaded, writing, release_writer, start_contender, attempting, finished = (Event() for _ in range(6))
    original_log = twofa.log_change

    def pause_before_commit(db, *args, **kwargs):
        entry = original_log(db, *args, **kwargs)
        if db.info.get("writer"):
            db.flush()
            writing.set()
            assert release_writer.wait(5), "Timed out waiting to release writer"
        return entry

    monkeypatch.setattr(twofa, "log_change", pause_before_commit)

    def run_contender():
        with Session(mfa_engine) as db:
            actor = principal(db)
            loaded.set()
            assert start_contender.wait(5), "Timed out before contender"
            attempting.set()
            try:
                invoke(contender, db, actor)
                return 200 if contender == "setup" else 204
            except HTTPException as error:
                return error.status_code
            finally:
                finished.set()

    def run_writer():
        with Session(mfa_engine) as db:
            db.info["writer"] = True
            invoke(winner, db, principal(db))

    with ThreadPoolExecutor(max_workers=2) as pool:
        later = pool.submit(run_contender)
        try:
            assert loaded.wait(5), "Contender did not load its stale snapshot"
            first = pool.submit(run_writer)
            assert writing.wait(5), "Writer did not reach its uncommitted state"
            start_contender.set()
            assert attempting.wait(5)
            assert not finished.wait(0.2), "Contender escaped the held user lock"
        finally:
            release_writer.set()
            start_contender.set()
        first.result(timeout=5)
        assert later.result(timeout=5) == expected_error
    with Session(mfa_engine) as db:
        user = db.get(User, "user")
        assert user.totp_enabled == (winner == "verify")
        assert read_secret(user) == (SECRET if winner == "verify" else NEXT_SECRET if winner == "setup" else None)
    expected_action = {"setup": "2fa_setup", "verify": "2fa_enabled", "disable": "2fa_disabled"}[winner]
    assert audits(mfa_engine) == [(expected_action, "user", "org", None, None)]


def register(client, email):
    response = client.post("/auth/register", json={"email": email, "password": PASSWORD, "full_name": "MFA Budget Test"})
    assert response.status_code == 201, response.text
    return response.json()


def auth_headers(account):
    return {"Authorization": f"Bearer {account['access_token']}"}


@pytest.mark.parametrize("action", ["verify", "disable"])
def test_code_budget_is_bounded_per_user_before_credential_work(client, monkeypatch, action):
    account = register(client, "budget@example.com")
    headers = auth_headers(account)
    assert client.post("/auth/2fa/setup", headers=headers).status_code == 200
    if action == "disable":
        assert client.post("/auth/2fa/verify", headers=headers, json={"code": NEXT_CODE}).status_code == 204
        twofa.limiter.clear()
    payload = {"code": "not-a-code", **({"password": "wrong-password"} if action == "disable" else {})}
    for i in range(twofa.CODE_ATTEMPT_LIMIT):
        response = client.post(f"/auth/2fa/{action}", headers={**headers, "X-Forwarded-For": f"192.0.2.{i}"}, json=payload)
        assert response.status_code == (401 if action == "disable" else 400)

    def must_not_lock(*args):
        raise AssertionError("Rate-limited requests must not acquire a user lock")

    monkeypatch.setattr(twofa, "_locked_user", must_not_lock)
    response = client.post(f"/v1/auth/2fa/{action}", headers=headers, json=payload)
    assert response.status_code == 429
    assert 1 <= int(response.headers["Retry-After"]) <= twofa.CODE_ATTEMPT_WINDOW
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"detail": "Too many authenticator attempts. Try again later."}


def test_code_budget_cannot_be_reset_by_setup_endpoint_org_or_token_switch(client, db):
    first = register(client, "first-budget@example.com")
    second = register(client, "second-budget@example.com")
    headers = auth_headers(first)
    assert client.post("/auth/2fa/setup", headers=headers).status_code == 200
    for _ in range(twofa.CODE_ATTEMPT_LIMIT):
        assert client.post("/auth/2fa/verify", headers=headers, json={"code": "invalid"}).status_code == 400
    # A new pending secret does not grant a fresh guessing budget.
    assert client.post("/auth/2fa/setup", headers=headers).status_code == 200
    db.add(OrganizationMembership(user_id=first["user_id"], organization_id=second["organization_id"], role=MemberRole.viewer))
    db.commit()
    switched = client.post("/auth/switch-org", headers=headers, json={"organization_id": second["organization_id"]})
    assert switched.status_code == 200
    switched_headers = {"Authorization": f"Bearer {switched.json()['access_token']}"}
    for action, payload in (("verify", {"code": NEXT_CODE}), ("disable", {"password": PASSWORD, "code": NEXT_CODE})):
        assert client.post(f"/auth/2fa/{action}", headers=switched_headers, json=payload).status_code == 429
    assert client.get("/auth/2fa/status", headers=switched_headers).status_code == 200
    # A different account has its own bucket, even from the same IP.
    second_headers = auth_headers(second)
    assert client.post("/auth/2fa/setup", headers=second_headers).status_code == 200
    assert client.post("/auth/2fa/verify", headers=second_headers, json={"code": NEXT_CODE}).status_code == 204


@pytest.mark.parametrize("action", ["verify", "disable"])
def test_code_budget_never_replaces_authentication(client, action):
    payload = {"code": "000001", "password": PASSWORD}
    assert client.post(f"/auth/2fa/{action}", json=payload).status_code == 401
    assert client.post(f"/auth/2fa/{action}", headers={"Authorization": "Bearer invalid"}, json=payload).status_code == 401
