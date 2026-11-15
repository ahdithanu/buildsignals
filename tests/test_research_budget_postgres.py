"""Opt-in PG reservation acceptance; no worker calls or HTTP-auth claims."""
import json
import threading
from contextlib import ExitStack, contextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text

from agent_runtime.research import validate_bundle
from app.models.audit_log import AuditLog
from app.models.deal import Deal
from app.models.organization import Organization
from app.models.user import User
from app.services import research_service
from tests.research_postgres_support import RUN_ID, URL, assert_blocked_by, tenant_session
from tests.snapshot_postgres_support import verified_snapshot_connection

pytestmark = pytest.mark.skipif(not URL, reason="Dedicated disposable snapshot PostgreSQL URL not set")
NOW = datetime(2026, 1, 2, 12, tzinfo=timezone.utc)


def _new_tenant():
    org, user, deal = (str(uuid4()) for _ in range(3))
    with tenant_session(org) as db:
        db.add(Organization(id=org, name="Synthetic research budget", slug=f"research-{org}"))
        db.add(User(id=user, email=f"{user}@example.invalid", full_name="Synthetic researcher",
                    password_hash="!nologin"))
        db.flush()
        db.add(Deal(id=deal, organization_id=org, name="Synthetic research context",
                    city="Austin", state="TX", property_type="retail", asking_price=1500000))
        db.commit()
    return org, user, deal


@pytest.fixture
def stored_research_tenant(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Reservation acceptance must not call a worker, source, or model")

    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    monkeypatch.setattr("app.services.llm_client.OpenRouterClient.chat_completion", forbidden)
    monkeypatch.setattr(research_service, "run_research_process", forbidden)
    monkeypatch.setattr(research_service.config, "AGENT_RESEARCH_DAILY_RUN_LIMIT", 1)
    monkeypatch.setattr(research_service, "_now", lambda: NOW)
    return _new_tenant()


def _reserve(db, tenant, request_id):
    org, user, deal = tenant
    return research_service.reserve(db, org_id=org, user_id=user, deal_id=deal,
                                    request_id=request_id)


def _reservations(db, org):
    return db.scalars(select(AuditLog).where(
        AuditLog.organization_id == org, AuditLog.entity_type == "research_run",
        AuditLog.action == "research_reserved",
    )).all()


@contextmanager
def _waiting_reservation(tenant, request_id, *, release_blocker):
    ready = threading.Event()
    state = {}

    def worker():
        try:
            with tenant_session(tenant[0]) as db:
                state["pid"] = db.scalar(text("SELECT pg_catalog.pg_backend_pid()"))
                ready.set()
                try:
                    state["result"] = _reserve(db, tenant, request_id)
                    state["status"] = 200
                except HTTPException as error:
                    state["status"] = error.status_code
                    state["headers"] = error.headers or {}
                state["transaction_open"] = db.in_transaction()
        except BaseException as error:
            state["error"] = error
            ready.set()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    try:
        assert ready.wait(5), "Reservation worker did not acquire its verified connection"
        if "error" in state:
            raise state["error"]
        yield state
    finally:
        try:
            release_blocker()
        finally:
            thread.join(12)
            assert not thread.is_alive(), "Reservation worker exceeded bounded database timeouts"
    if "error" in state:
        raise state["error"]


def _contending_reservations(monkeypatch, tenant, winner_request, waiting_request, *, after_wait=None):
    original_context = research_service._context
    state = None
    with tenant_session(tenant[0]) as winner:
        with ExitStack() as cleanup:
            def context(db, org_id, deal_id):
                nonlocal state
                bundle = original_context(db, org_id, deal_id)
                if db is winner:
                    # Pause only after the real reservation path owns the org
                    # lock; calling reserve with a prelocked session would lose
                    # that lock to its deliberate initial rollback.
                    state = cleanup.enter_context(_waiting_reservation(
                        tenant, waiting_request, release_blocker=winner.rollback,
                    ))
                    assert_blocked_by(winner, state, "organizations")
                    if after_wait is not None:
                        after_wait()
                return bundle

            monkeypatch.setattr(research_service, "_context", context)
            result = _reserve(winner, tenant, winner_request)
            assert not winner.in_transaction(), "Reservation must commit before returning for dispatch"
        assert state is not None
    assert state["transaction_open"] is False
    return result, state


@pytest.mark.parametrize("same_request,loser_status", [(True, 409), (False, 429)],
                         ids=["same-request", "different-request-last-slot"])
def test_org_lock_serializes_request_replay_and_last_daily_slot(
        stored_research_tenant, monkeypatch, same_request, loser_status):
    tenant = stored_research_tenant
    request_id = str(uuid4())
    waiting_id = request_id if same_request else str(uuid4())
    (run_id, bundle), waiter = _contending_reservations(
        monkeypatch, tenant, request_id, waiting_id,
    )
    assert validate_bundle(bundle).keys() == {f"deal:{tenant[2]}"}
    assert waiter["status"] == loser_status and "result" not in waiter
    if loser_status == 429:
        assert int(waiter["headers"]["Retry-After"]) == 43200
    with tenant_session(tenant[0]) as verify:
        reservation, = _reservations(verify, tenant[0])
        assert reservation.entity_id == run_id and reservation.request_id == request_id
        assert reservation.actor_id == tenant[1] and reservation.organization_id == tenant[0]
        assert json.loads(reservation.new_values)["deal_id"] == tenant[2]
        assert research_service.used_today(verify, tenant[0], NOW) == 1
        assert verify.scalars(select(AuditLog.action).where(
            AuditLog.organization_id == tenant[0], AuditLog.entity_type == "research_run",
        )).all() == ["research_reserved"]


def test_foreign_default_and_unset_contexts_cannot_admit_foreign_deal_or_reset_org_budget(
        stored_research_tenant):
    tenant = stored_research_tenant
    foreign = _new_tenant()
    request_id = str(uuid4())
    with tenant_session(tenant[0]) as db:
        run_id, _bundle = _reserve(db, tenant, request_id)

    with tenant_session(foreign[0]) as denied:
        # No application predicate: these reads independently exercise real RLS.
        assert denied.scalar(select(Deal.id).where(Deal.id == tenant[2])) is None
        assert denied.scalar(select(AuditLog.id).where(AuditLog.entity_id == run_id)) is None
        with pytest.raises(HTTPException) as error:
            research_service.reserve(denied, org_id=foreign[0], user_id=foreign[1],
                                     deal_id=tenant[2], request_id=request_id)
        assert error.value.status_code == 404
        assert not denied.in_transaction()
        assert research_service.used_today(denied, foreign[0], NOW) == 0
        # The same UUID belongs to another org, not a globally shared replay key.
        foreign_run_id, _bundle = _reserve(denied, foreign, request_id)

    with tenant_session("default-org") as denied:
        assert denied.scalar(select(Deal.id).where(Deal.id == tenant[2])) is None
        # AuditLog deliberately has a broader bootstrap RLS policy. Here the
        # proof is application-scoped admission denial, not raw audit isolation.
        with pytest.raises(HTTPException) as error:
            research_service.reserve(denied, org_id="default-org", user_id=tenant[1],
                                     deal_id=tenant[2], request_id=str(uuid4()))
        assert error.value.status_code == 404
        assert not denied.in_transaction()

    with verified_snapshot_connection(URL, RUN_ID) as connection:
        assert connection.scalar(text("SELECT count(*) FROM deals WHERE id=:id"),
                                 {"id": tenant[2]}) == 0
        assert connection.scalar(text("SELECT count(*) FROM audit_logs WHERE entity_id=:id"),
                                 {"id": run_id}) == 0

    for current, expected_run in ((tenant, run_id), (foreign, foreign_run_id)):
        with tenant_session(current[0]) as verify:
            reservation, = _reservations(verify, current[0])
            assert reservation.entity_id == expected_run and reservation.request_id == request_id
            assert research_service.used_today(verify, current[0], NOW) == 1


def test_utc_day_is_evaluated_after_org_lock_wait_and_replay_key_survives_rollover(
        stored_research_tenant, monkeypatch):
    tenant = stored_research_tenant
    before = NOW.replace(hour=23, minute=59, second=59)
    after = (before + timedelta(seconds=1)).replace(microsecond=0)
    clock = {"now": before}
    monkeypatch.setattr(research_service, "_now", lambda: clock["now"])
    request_id, waiting_id = str(uuid4()), str(uuid4())
    (run_id, _bundle), waiter = _contending_reservations(
        monkeypatch, tenant, request_id, waiting_id,
        after_wait=lambda: clock.update(now=after),
    )
    assert waiter["status"] == 200
    waiting_run, _bundle = waiter["result"]
    with tenant_session(tenant[0]) as verify:
        reservations = _reservations(verify, tenant[0])
        assert {row.entity_id for row in reservations} == {run_id, waiting_run}
        assert {row.request_id for row in reservations} == {request_id, waiting_id}
        assert research_service.used_today(verify, tenant[0], before) == 1
        assert research_service.used_today(verify, tenant[0], after) == 1
        with pytest.raises(HTTPException) as error:
            _reserve(verify, tenant, request_id)
        assert error.value.status_code == 409
        assert len(_reservations(verify, tenant[0])) == 2
