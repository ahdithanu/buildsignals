"""Opt-in verified disposable-PG ordering; HTTP authorization is tested separately."""
import hashlib
import json
import threading
from contextlib import ExitStack, contextmanager
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from fastapi import HTTPException, Response
from sqlalchemy import inspect, select, text

from app.models.acquisition_screen import AcquisitionScreenSnapshot
from app.models.audit_log import AuditLog
from app.models.buy_box import BuyBox
from app.models.deal import Deal
from app.models.organization import Organization
from app.models.user import User
from app.routes import buy_box as routes
from app.schemas.buy_box import (
    AcquisitionCriteria,
    AcquisitionCriteriaRetire,
    AcquisitionCriteriaUpdate,
)
from tests.research_postgres_support import URL, assert_blocked_by, tenant_session
from tests.test_acquisition_criteria import CRITERIA

pytestmark = pytest.mark.skipif(not URL, reason="Dedicated disposable snapshot PostgreSQL URL not set")

BASELINE = AcquisitionCriteria(**CRITERIA).model_dump()


@pytest.fixture
def stored_box(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Retirement acceptance must not call external sources or models")

    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    monkeypatch.setattr("app.services.llm_client.get_default_llm_client", forbidden)
    org, owner, box_id, deal_id = (str(uuid4()) for _ in range(4))
    with tenant_session(org) as db:
        db.add(Organization(id=org, name="Synthetic retirement", slug=f"retire-{org}"))
        db.add(User(id=owner, email=f"{owner}@example.invalid", full_name="Synthetic owner",
                    password_hash="!nologin"))
        db.flush()
        db.add(BuyBox(id=box_id, organization_id=org, user_id=owner,
                      acquisition_criteria=BASELINE, notes="Retain legacy notes"))
        db.add(Deal(id=deal_id, organization_id=org, name="Synthetic serialized export"))
        db.commit()
    return org, owner, box_id, deal_id


def _retire(db, identity):
    _org, owner, box_id, _deal_id = identity
    return routes.retire_acquisition_criteria(
        box_id, AcquisitionCriteriaRetire(expected_criteria=BASELINE), db, {"user_id": owner},
    )


def _export(db, identity):
    _org, owner, box_id, deal_id = identity
    return routes.export_acquisition_screen(
        deal_id, "small_multifamily", None, None, {"user_id": owner}, db, box_id,
    )


@contextmanager
def _waiting_call(identity, operation, *, release_blocker):
    org, owner, box_id, _deal_id = identity
    ready = threading.Event()
    state = {}

    def worker():
        try:
            with tenant_session(org) as db:
                state["pid"] = db.scalar(text("SELECT pg_catalog.pg_backend_pid()"))
                cached = db.get(BuyBox, box_id)
                assert cached is not None
                state["before_wait"] = cached.retired_at
                state["before_criteria"] = cached.acquisition_criteria
                ready.set()
                try:
                    if operation == "export":
                        _export(db, identity)
                    elif operation == "retire":
                        result = _retire(db, identity)
                        state["returned_timestamp"] = result.retired_at
                    else:
                        routes.update_acquisition_criteria(
                            box_id, AcquisitionCriteriaUpdate(
                                expected_criteria=BASELINE,
                                acquisition_criteria=BASELINE | {"max_size": 30},
                            ), db, {"user_id": owner},
                        )
                    state["status"] = 200
                except HTTPException as error:
                    state["status"] = error.status_code
                # Keep a strong reference to prove the stale identity-map row was refreshed.
                state["after_wait"] = cached.retired_at
                state["after_criteria"] = cached.acquisition_criteria
                db.rollback()
        except BaseException as error:
            state["error"] = error
            ready.set()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    try:
        assert ready.wait(5), "Retirement worker did not acquire its verified connection"
        if "error" in state:
            raise state["error"]
        yield state
    finally:
        try:
            release_blocker()
        finally:
            thread.join(12)
            assert not thread.is_alive(), "Retirement worker exceeded bounded database timeouts"
    if "error" in state:
        raise state["error"]


def test_export_holds_actual_lock_through_snapshot_and_audit_commit(stored_box, monkeypatch):
    org, owner, box_id, deal_id = stored_box
    original = routes.log_change
    waiting = []
    with tenant_session(org) as db, ExitStack() as stack:
        def inspect_export_audit(*args, **kwargs):
            audit = original(*args, **kwargs)
            if args[3] == "acquisition_screen_export":
                assert db.in_transaction()
                state = stack.enter_context(_waiting_call(stored_box, "retire", release_blocker=db.rollback))
                assert state["before_wait"] is None
                # No test-acquired lock: the real export lookup must hold this lock.
                assert_blocked_by(db, state, "buy_boxes")
                waiting.append(state)
            return audit

        monkeypatch.setattr(routes, "log_change", inspect_export_audit)
        exported = _export(db, stored_box)
        assert exported.status_code == 200
    state, = waiting
    assert state["status"] == 200
    assert state["after_wait"] is not None
    with tenant_session(org) as verify:
        box = verify.get(BuyBox, box_id)
        assert box.retired_at == state["returned_timestamp"]
        assert box.acquisition_criteria == BASELINE
        snapshot = verify.scalars(select(AcquisitionScreenSnapshot).where(
            AcquisitionScreenSnapshot.deal_id == deal_id,
        )).one()
        assert snapshot.content.encode() == exported.body
        assert snapshot.content_sha256 == hashlib.sha256(exported.body).hexdigest()
        audit = verify.scalars(select(AuditLog).where(
            AuditLog.action == "acquisition_screen_export", AuditLog.entity_id == deal_id,
        )).one()
        assert audit.actor_id == owner
        assert json.loads(audit.new_values)["snapshot_id"] == snapshot.id
        assert len(verify.scalars(select(AuditLog).where(
            AuditLog.entity_type == "buy_box", AuditLog.entity_id == box_id,
        )).all()) == 1


@pytest.mark.parametrize("operation,status", [("export", 409), ("edit", 409), ("retire", 200)])
def test_retirement_first_refreshes_waiting_export_edit_and_exact_retry(stored_box, operation, status):
    org, _owner, box_id, deal_id = stored_box
    with tenant_session(org) as locker:
        locker.scalars(select(BuyBox).where(BuyBox.id == box_id).with_for_update()).one()
        with _waiting_call(stored_box, operation, release_blocker=locker.rollback) as state:
            assert state["before_wait"] is None
            assert_blocked_by(locker, state, "buy_boxes")
            retired = _retire(locker, stored_box)
            timestamp = retired.retired_at
        assert state["status"] == status
        assert state["after_wait"] == timestamp
        if operation == "retire":
            assert state["returned_timestamp"] == timestamp
    with tenant_session(org) as verify:
        box = verify.get(BuyBox, box_id)
        assert box.retired_at == timestamp
        assert box.acquisition_criteria == BASELINE
        audit = verify.scalars(select(AuditLog).where(
            AuditLog.entity_type == "buy_box", AuditLog.entity_id == box_id,
        )).one()
        assert audit.action == "retire_acquisition_criteria"
        assert json.loads(audit.old_values) == {"retired_at": None}
        assert verify.scalars(select(AcquisitionScreenSnapshot).where(
            AcquisitionScreenSnapshot.deal_id == deal_id,
        )).all() == []
        assert verify.scalars(select(AuditLog).where(
            AuditLog.action == "acquisition_screen_export", AuditLog.entity_id == deal_id,
        )).all() == []


def test_edit_first_makes_waiting_retirement_stale_without_retirement_audit(stored_box):
    org, owner, box_id, _deal_id = stored_box
    replacement = BASELINE | {"max_size": 30}
    with tenant_session(org) as locker:
        locker.scalars(select(BuyBox).where(BuyBox.id == box_id).with_for_update()).one()
        with _waiting_call(stored_box, "retire", release_blocker=locker.rollback) as state:
            assert state["before_criteria"] == BASELINE
            assert_blocked_by(locker, state, "buy_boxes")
            routes.update_acquisition_criteria(
                box_id, AcquisitionCriteriaUpdate(
                    expected_criteria=BASELINE, acquisition_criteria=replacement,
                ), locker, {"user_id": owner},
            )
        assert state["status"] == 409
        assert state["after_wait"] is None
        assert state["after_criteria"] == replacement
    with tenant_session(org) as verify:
        box = verify.get(BuyBox, box_id)
        assert box.acquisition_criteria == replacement
        assert box.retired_at is None
        audit = verify.scalars(select(AuditLog).where(
            AuditLog.entity_type == "buy_box", AuditLog.entity_id == box_id,
        )).one()
        assert audit.action == "update_acquisition_criteria"
        assert json.loads(audit.old_values) == {"acquisition_criteria": BASELINE}
        assert json.loads(audit.new_values) == {"acquisition_criteria": replacement}


def test_get_screen_works_in_actual_demo_read_only_transaction(stored_box):
    from app.services.demo_access import demo_read_only

    org, _owner, box_id, deal_id = stored_box
    token = demo_read_only.set(True)
    try:
        with tenant_session(org) as db:
            assert db.scalar(text("SHOW transaction_read_only")) == "on"
            response = Response()
            screened = routes.acquisition_screen(
                deal_id, response, "small_multifamily", None, None, db, box_id,
            )
            assert screened["criteria_snapshot"] == BASELINE
            assert response.headers["Cache-Control"] == "no-store"
            assert db.scalar(text("SHOW transaction_read_only")) == "on"
            db.rollback()
    finally:
        demo_read_only.reset(token)


def test_migration_downgrade_upgrade_operations_are_transactionally_rolled_back(stored_box):
    org, _owner, box_id, _deal_id = stored_box
    migration = ScriptDirectory.from_config(Config("alembic.ini")).get_revision("20261115_0001").module
    with tenant_session(org) as db:
        before = dict(db.execute(select(BuyBox.__table__).where(BuyBox.id == box_id)).mappings().one())
        connection = db.connection()
        try:
            with Operations.context(MigrationContext.configure(connection)):
                migration.downgrade()
                assert "retired_at" not in {col["name"] for col in inspect(connection).get_columns("buy_boxes")}
                migration.upgrade()
            columns = {col["name"]: col for col in inspect(connection).get_columns("buy_boxes")}
            assert columns["retired_at"]["nullable"] is True
            assert columns["retired_at"]["type"].timezone is True
            after = dict(db.execute(select(BuyBox.__table__).where(BuyBox.id == box_id)).mappings().one())
            assert after == before
        finally:
            # Transactional DDL restores all prior fixture rows/timestamps and the schema.
            db.rollback()
