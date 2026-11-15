"""Opt-in disposable-PG criteria CAS; direct calls do not qualify HTTP auth."""
import json
import threading
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text

from app.models.audit_log import AuditLog
from app.models.buy_box import BuyBox
from app.models.organization import Organization
from app.models.user import User
from app.routes.buy_box import update_acquisition_criteria
from app.schemas.buy_box import AcquisitionCriteria, AcquisitionCriteriaUpdate
from tests.research_postgres_support import RUN_ID, URL, assert_blocked_by, tenant_session
from tests.snapshot_postgres_support import verified_snapshot_connection

pytestmark = pytest.mark.skipif(not URL, reason="Dedicated disposable snapshot PostgreSQL URL not set")

BASELINE = AcquisitionCriteria(
    profile="small_multifamily", market_city="Columbus", market_state="OH",
    min_price=1000000, max_price=3000000, min_size=10, max_size=20,
    min_year_built=1980,
).model_dump()
WINNER = BASELINE | {"min_size": 15}
LOSER = BASELINE | {"max_size": 30}


def _scalar_state(box):
    return {column.key: deepcopy(getattr(box, column.key)) for column in BuyBox.__table__.columns}


def _payload(criteria):
    return AcquisitionCriteriaUpdate(acquisition_criteria=criteria, expected_criteria=BASELINE)


@pytest.fixture
def stored_box(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Criteria acceptance must not call external sources or models")

    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    monkeypatch.setattr("app.services.llm_client.get_default_llm_client", forbidden)
    org, owner, editor, box_id = (str(uuid4()) for _ in range(4))
    with tenant_session(org) as db:
        db.add(Organization(id=org, name="Synthetic criteria concurrency", slug=f"criteria-{org}"))
        for actor in (owner, editor):
            db.add(User(id=actor, email=f"{actor}@example.invalid", full_name="Synthetic editor",
                        password_hash="!nologin"))
        db.flush()
        box = BuyBox(
            id=box_id, organization_id=org, user_id=owner,
            asset_type="legacy office", locations="Austin TX", min_price=100,
            max_price=900, min_irr=0.12, deal_type="acquisition", notes="Preserve legacy fields",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            acquisition_criteria=deepcopy(BASELINE),
        )
        db.add(box)
        db.commit()
        return org, owner, editor, box_id, _scalar_state(box)


@contextmanager
def _waiting_edit(identity, *, release_blocker):
    org, owner, _editor, box_id, _before = identity
    ready = threading.Event()
    state = {}

    def worker():
        try:
            with tenant_session(org) as db:
                state["pid"] = db.scalar(text("SELECT pg_catalog.pg_backend_pid()"))
                cached = db.get(BuyBox, box_id)
                assert cached is not None
                state["before_wait"] = deepcopy(cached.acquisition_criteria)
                ready.set()
                try:
                    update_acquisition_criteria(box_id, _payload(LOSER), db,
                                                {"user_id": owner})
                    state["status"] = 200
                except HTTPException as error:
                    state["status"] = error.status_code
                # Strong reference survives the wait: stale ORM state must be reloaded.
                state["after_wait"] = deepcopy(cached.acquisition_criteria)
                db.rollback()
        except BaseException as error:
            state["error"] = error
            ready.set()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    try:
        assert ready.wait(5), "Criteria worker did not acquire its verified connection"
        if "error" in state:
            raise state["error"]
        yield state
    finally:
        try:
            release_blocker()
        finally:
            thread.join(12)
            assert not thread.is_alive(), "Criteria worker exceeded bounded database timeouts"
    if "error" in state:
        raise state["error"]


def test_waiting_edit_reloads_committed_criteria_and_audits_only_winner(stored_box):
    org, _owner, editor, box_id, before = stored_box
    with tenant_session(org) as locker:
        locked = locker.scalars(select(BuyBox).where(BuyBox.id == box_id).with_for_update()).one()
        assert _scalar_state(locked) == before
        try:
            with _waiting_edit(stored_box, release_blocker=locker.rollback) as state:
                assert state["before_wait"] == BASELINE
                assert_blocked_by(locker, state, "buy_boxes")
                # The real route performs the winning update, audit and commit.
                result = update_acquisition_criteria(box_id, _payload(WINNER), locker,
                                                     {"user_id": editor})
                assert _scalar_state(result) == before | {"acquisition_criteria": WINNER}
            assert state["status"] == 409
            assert state["after_wait"] == WINNER
        finally:
            locker.rollback()

    with tenant_session(org) as verify:
        current = verify.get(BuyBox, box_id)
        assert current is not None
        assert _scalar_state(current) == before | {"acquisition_criteria": WINNER}
        audit = verify.scalars(select(AuditLog).where(
            AuditLog.entity_type == "buy_box", AuditLog.entity_id == box_id,
        )).one()
        assert audit.organization_id == org
        assert audit.actor_id == editor
        assert audit.action == "update_acquisition_criteria"
        assert json.loads(audit.old_values) == {"acquisition_criteria": BASELINE}
        assert json.loads(audit.new_values) == {"acquisition_criteria": WINNER}


def test_fresh_foreign_default_and_unset_tenants_cannot_see_or_edit_box(stored_box):
    org, owner, _editor, box_id, before = stored_box
    for denied_org in (str(uuid4()), "default-org"):
        with tenant_session(denied_org) as denied:
            # No application org predicate: this SELECT independently exercises RLS.
            assert denied.scalar(select(BuyBox.id).where(BuyBox.id == box_id)) is None
            with pytest.raises(HTTPException) as error:
                update_acquisition_criteria(box_id, _payload(WINNER), denied,
                                            {"user_id": owner})
            assert error.value.status_code == 404
            denied.rollback()
    with verified_snapshot_connection(URL, RUN_ID) as connection:
        # No tenant listener or set_config: a new physical connection must deny by default.
        assert connection.scalar(text("SELECT count(*) FROM buy_boxes WHERE id=:id"),
                                 {"id": box_id}) == 0
    with tenant_session(org) as verify:
        assert _scalar_state(verify.get(BuyBox, box_id)) == before
        assert verify.scalars(select(AuditLog).where(AuditLog.entity_id == box_id)).all() == []
