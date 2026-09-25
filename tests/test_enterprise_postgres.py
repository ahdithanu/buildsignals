"""Real PostgreSQL contention tests for enterprise mutation invariants.

Set TEST_POSTGRES_URL to an isolated, migrated PostgreSQL database owned by a
non-superuser without BYPASSRLS. Never point it at production. Tests create and
clean up only UUID-scoped synthetic records; they do not migrate or drop a DB.
Route/service functions run on independent connections with live JWT identity
checks. This tests transaction behavior, not the HTTP/middleware pipeline.
"""
from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from http.cookies import SimpleCookie
from itertools import combinations_with_replacement
from queue import Queue
from threading import Event
from typing import NamedTuple
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request, Response
from sqlalchemy import create_engine, delete, event, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.config import REFRESH_COOKIE_NAME
from app.models.audit_log import AuditLog
from app.models.browser_session import BrowserSession
from app.models.buildsignal import BuildSignalPublication, BuildSignalReview, BuildSignalRevision
from app.models.organization import Organization
from app.models.organization_membership import MemberRole, OrganizationMembership
from app.models.signal import Signal
from app.models.user import User
from app.routes.auth import delete_account
from app.routes.organizations import remove_member, update_member_role
from app.schemas.auth import DeleteAccountRequest
from app.schemas.buildsignal import PublicationCreate
from app.schemas.organization import UpdateMemberRequest
from app.services.assessment_publication import change_publication
from app.services.browser_sessions import (
    issue_browser_session,
    refresh_binding,
    revoke_browser_session,
)
from app.services.security import (
    create_access_token,
    decode_access_token,
    decode_refresh_token,
    hash_password,
)
from app.utils.auth_deps import get_current_user
from app.utils.org_scope import RequestContext, reset_current_context, set_current_context

POSTGRES_URL = os.environ.get("TEST_POSTGRES_URL")
PASSWORD = "SyntheticPostgresConcurrency42!"
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL not set")


@pytest.fixture(scope="module")
def enterprise_pg_engine():
    assert make_url(POSTGRES_URL).get_backend_name() == "postgresql"
    engine = create_engine(
        POSTGRES_URL, poolclass=NullPool, isolation_level="READ COMMITTED",
        connect_args={
            "connect_timeout": 5,
            "options": (
                "-c lock_timeout=8000 -c statement_timeout=12000 "
                "-c idle_in_transaction_session_timeout=20000 -c row_security=on"
            ),
        },
    )
    try:
        with engine.connect() as connection:
            roles = connection.execute(text(
                "SELECT rolsuper, rolbypassrls FROM pg_roles "
                "WHERE rolname IN (current_user, session_user)"
            )).all()
            assert roles and all(not row.rolsuper and not row.rolbypassrls for row in roles), (
                "Refusing enterprise PostgreSQL tests: superuser/BYPASSRLS invalidates evidence"
            )
            tables = {"signals", "buildsignal_revisions", "buildsignal_reviews", "buildsignal_publications"}
            policies = connection.execute(text(
                "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity "
                "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = current_schema() AND c.relname = ANY(:tables)"
            ), {"tables": sorted(tables)}).all()
            assert {row.relname for row in policies} == tables, "Apply released migrations first"
            assert all(row.relrowsecurity and row.relforcerowsecurity for row in policies)
        yield engine
    finally:
        engine.dispose()


@contextmanager
def _session(engine, org_id, user_id):
    token = set_current_context(RequestContext(org_id=org_id, user_id=user_id))
    try:
        with Session(engine) as session:
            # Test sessions are independent of the application's DATABASE_URL.
            # Restore SET LOCAL after commits, just as the request session does.
            @event.listens_for(session, "after_begin")
            def set_scope(_session, _transaction, connection):
                connection.execute(text("SELECT set_config('app.current_org', :org, true)"), {"org": org_id})

            yield session
    finally:
        reset_current_context(token)


@pytest.fixture
def enterprise_rows(enterprise_pg_engine):
    org_ids = []
    user_ids = []

    def seed(org_count=1):
        org_ids.extend(sorted(str(uuid4()) for _ in range(org_count)))
        user_ids.extend(str(uuid4()) for _ in range(3))
        password_hash = hash_password(PASSWORD)
        with _session(enterprise_pg_engine, org_ids[0], user_ids[0]) as db:
            db.add_all(Organization(id=oid, name="Synthetic concurrency workspace", slug=oid) for oid in org_ids)
            db.add_all(User(
                id=uid, email=f"enterprise-pg-{uid}@example.com", full_name="Synthetic concurrency user",
                password_hash=password_hash, is_active=index < 2,
            ) for index, uid in enumerate(user_ids))
            db.flush()
            for index, uid in enumerate(user_ids):
                # Opposite insertion order must not change the parent lock order.
                for oid in org_ids if index == 0 else reversed(org_ids):
                    db.add(OrganizationMembership(
                        user_id=uid, organization_id=oid, role=MemberRole.admin,
                    ))
            db.commit()
        return org_ids, user_ids

    try:
        yield seed
    finally:
        # Core deletes use the migrated CASCADE FKs, without traversing ORM
        # relationships or scanning/deleting any other tenant's data.
        with enterprise_pg_engine.begin() as connection:
            for oid in org_ids:
                connection.execute(text("SELECT set_config('app.current_org', :org, true)"), {"org": oid})
                connection.execute(delete(Organization).where(Organization.id == oid))
            if user_ids:
                connection.execute(delete(User).where(User.id.in_(user_ids)))
                assert not connection.execute(select(User.id).where(User.id.in_(user_ids))).first()
            if org_ids:
                assert not connection.execute(select(Organization.id).where(Organization.id.in_(org_ids))).first()


def _contend(engine, org_id, user_ids, lock_statement, operation):
    """Hold the parent until both authorized workers demonstrably wait for locks."""
    ready = Queue()

    def worker(index):
        with _session(engine, org_id, user_ids[index]) as db:
            token = create_access_token(user_id=user_ids[index], org_id=org_id)
            principal = get_current_user(authorization=f"Bearer {token}", db=db)
            ready.put(db.execute(text("SELECT pg_backend_pid()")).scalar_one())
            try:
                return operation(db, principal, index)
            except HTTPException as exc:
                db.rollback()
                return exc.status_code, exc.detail

    with _session(engine, org_id, user_ids[0]) as blocker:
        blocker.execute(lock_statement).one()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker, index) for index in range(2)]
            try:
                pids = [ready.get(timeout=5) for _ in range(2)]
                assert len(set(pids)) == 2, "Workers must use separate PostgreSQL connections"
                deadline = time.monotonic() + 5
                while True:
                    if any(future.done() for future in futures):
                        for future in futures:
                            if future.done():
                                future.result()
                        pytest.fail("Mutation completed before the parent lock was released")
                    waiting = blocker.execute(text(
                        "SELECT pid, cardinality(pg_blocking_pids(pid)) AS blockers "
                        "FROM pg_stat_activity WHERE pid = ANY(:pids)"
                    ), {"pids": pids}).all()
                    if len(waiting) == 2 and all(row.blockers > 0 for row in waiting):
                        break
                    assert time.monotonic() < deadline, "Both workers did not reach PostgreSQL lock contention"
                    time.sleep(0.02)
            finally:
                # Release even on assertion failure; all sessions also have
                # server-side lock/statement timeouts to bound worker teardown.
                blocker.rollback()
            return [future.result(timeout=15) for future in futures]


DEPARTURES = list(combinations_with_replacement(("demote", "remove", "delete"), 2))


@pytest.mark.parametrize("actions", DEPARTURES, ids=lambda pair: "-".join(pair))
@pytest.mark.parametrize("org_count", [1, 2], ids=["single-org", "multi-org"])
def test_concurrent_admin_departures_preserve_active_admin(
    enterprise_pg_engine, enterprise_rows, actions, org_count,
):
    org_ids, user_ids = enterprise_rows(org_count)
    org_id = org_ids[0]

    def depart(db, principal, index):
        action = actions[index]
        if action == "demote":
            update_member_role(
                org_id=org_id, user_id=user_ids[index], payload=UpdateMemberRequest(role=MemberRole.viewer),
                response=Response(), principal=principal, db=db,
            )
            return 200, None
        if action == "remove":
            remove_member(org_id=org_id, user_id=user_ids[index], principal=principal, db=db)
            return 204, None
        delete_account(
            payload=DeleteAccountRequest(password=PASSWORD), response=Response(), principal=principal, db=db,
        )
        return 204, None

    outcomes = _contend(
        enterprise_pg_engine, org_id, user_ids,
        select(Organization.id).where(Organization.id == org_id).with_for_update(), depart,
    )
    winners = [index for index, result in enumerate(outcomes) if result[0] in (200, 204)]
    assert len(winners) == 1, outcomes
    winner = winners[0]
    loser = 1 - winner
    assert outcomes[loser][0] == (409 if actions[loser] == "delete" else 400), outcomes
    assert "admin" in outcomes[loser][1].lower()
    with _session(enterprise_pg_engine, org_id, user_ids[loser]) as db:
        for oid in org_ids:
            active_admins = db.query(OrganizationMembership).join(User).filter(
                OrganizationMembership.organization_id == oid,
                OrganizationMembership.role == MemberRole.admin, User.is_active.is_(True),
            ).count()
            assert active_admins == (1 if oid == org_id or actions[winner] == "delete" else 2)
        assert db.get(User, user_ids[loser]).is_active
        membership = db.query(OrganizationMembership).filter_by(
            user_id=user_ids[winner], organization_id=org_id,
        ).one_or_none()
        if actions[winner] == "demote":
            assert membership.role == MemberRole.viewer
        else:
            assert membership is None
        assert (db.get(User, user_ids[winner]) is None) == (actions[winner] == "delete")
        audit = db.query(AuditLog).filter_by(organization_id=org_id).one()
        assert audit.action == {"demote": "role_change", "remove": "remove", "delete": "account_deleted"}[actions[winner]]
        assert audit.actor_id == (None if actions[winner] == "delete" else user_ids[winner])


@pytest.mark.parametrize("expected_version", [0, 1, 2], ids=["publish", "withdraw", "republish"])
def test_competing_publication_expected_version_allows_one_transition(
    enterprise_pg_engine, enterprise_rows, expected_version,
):
    org_ids, user_ids = enterprise_rows()
    org_id = org_ids[0]
    with _session(enterprise_pg_engine, org_id, user_ids[0]) as db:
        signal = Signal(organization_id=org_id, signal_type="synthetic-concurrency")
        db.add(signal)
        db.flush()
        revision = BuildSignalRevision(
            organization_id=org_id, signal_id=signal.id, author_id=user_ids[0],
            snapshot={"status": "draft", "synthetic": True},
        )
        db.add(revision)
        db.flush()
        review = BuildSignalReview(
            organization_id=org_id, revision_id=revision.id, reviewer_id=user_ids[1],
            decision="approved", rationale="Synthetic independent approval",
        )
        db.add(review)
        db.commit()
        revision_id, review_id = revision.id, review.id
        for version in range(expected_version):
            change_publication(db, revision_id, PublicationCreate(
                action="published" if version % 2 == 0 else "withdrawn",
                expected_version=version, rationale="Synthetic prior transition",
            ), user_ids[0])

    action = "published" if expected_version % 2 == 0 else "withdrawn"

    def publish(db, principal, _index):
        row = change_publication(db, revision_id, PublicationCreate(
            action=action, expected_version=expected_version, rationale="Synthetic competing transition",
        ), principal["user_id"])
        return 201, row.id

    outcomes = _contend(
        enterprise_pg_engine, org_id, user_ids,
        select(BuildSignalRevision.id).where(BuildSignalRevision.id == revision_id).with_for_update(), publish,
    )
    assert sorted(result[0] for result in outcomes) == [201, 409], outcomes
    assert "refresh" in next(result[1] for result in outcomes if result[0] == 409)
    with _session(enterprise_pg_engine, org_id, user_ids[0]) as db:
        history = db.query(BuildSignalPublication).filter_by(revision_id=revision_id).order_by(
            BuildSignalPublication.version,
        ).all()
        assert [row.version for row in history] == list(range(1, expected_version + 2))
        assert history[-1].action == action
        assert history[-1].id == next(result[1] for result in outcomes if result[0] == 201)
        assert history[-1].review_id == (review_id if action == "published" else None)
        assert db.query(AuditLog).filter_by(
            organization_id=org_id, entity_type="buildsignal_publication",
        ).count() == expected_version + 1
    with _session(enterprise_pg_engine, str(uuid4()), user_ids[0]) as db:
        assert db.query(BuildSignalPublication).filter_by(revision_id=revision_id).count() == 0
        assert db.get(BuildSignalRevision, revision_id) is None


class BrowserTokens(NamedTuple):
    browser_id: str
    epoch: int
    access: str
    cookie: str


class BrowserOutcome(NamedTuple):
    status: int
    tokens: BrowserTokens | None
    detail: str | None
    set_cookie: str | None


def _browser_request(browser_id, epoch, *, cookie=None, access=None):
    headers = {
        "x-browser-protocol": "1", "x-browser-id": browser_id,
        "x-browser-epoch": str(epoch),
    }
    if cookie:
        headers["cookie"] = f"{REFRESH_COOKIE_NAME}={cookie}"
    if access:
        headers["authorization"] = f"Bearer {access}"
    return Request({
        "type": "http", "method": "POST", "path": "/v1/auth/login", "query_string": b"",
        "headers": [(key.encode("ascii"), value.encode("ascii")) for key, value in headers.items()],
    })


def _browser_mutation(db, request, org_id, user_id, *, revoke=False):
    response = Response()
    try:
        if revoke:
            revoke_browser_session(db, request)
            return BrowserOutcome(204, None, None, response.headers.get("set-cookie"))
        user = db.get(User, user_id)
        assert user is not None and user.is_active
        result = issue_browser_session(
            db, request, response, user=user, org_id=org_id, role=MemberRole.admin.value,
        )
        cookie = SimpleCookie()
        cookie.load(response.headers["set-cookie"])
        raw_cookie = cookie[REFRESH_COOKIE_NAME].value
        access_claims, cookie_claims = decode_access_token(result.access_token), decode_refresh_token(raw_cookie)
        assert access_claims and cookie_claims
        assert all(access_claims[key] == cookie_claims[key] for key in ("sid", "sg", "bid", "be", "sub", "org_id", "tv"))
        assert response.headers["Cache-Control"] == "no-store"
        assert cookie[REFRESH_COOKIE_NAME]["httponly"]
        return BrowserOutcome(200, BrowserTokens(
            access_claims["bid"], access_claims["be"], result.access_token, raw_cookie,
        ), None, response.headers["set-cookie"])
    except HTTPException as exc:
        db.rollback()
        return BrowserOutcome(exc.status_code, None, exc.detail, response.headers.get("set-cookie"))


@pytest.fixture
def browser_families(enterprise_pg_engine, enterprise_rows):
    org_ids, user_ids = enterprise_rows()
    org_id, user_id = org_ids[0], user_ids[0]
    browser_ids = [str(uuid4()), str(uuid4())]
    tokens = []
    try:
        for browser_id in browser_ids:
            with _session(enterprise_pg_engine, org_id, user_id) as db:
                result = _browser_mutation(db, _browser_request(browser_id, 1), org_id, user_id)
                assert result.status == 200
                db.commit()
                tokens.append(result.tokens)
        yield org_id, user_id, tokens
    finally:
        # Browser families have SET NULL parent FKs, not CASCADE. Remove only
        # these known browser IDs before the parent fixture erases its users.
        with enterprise_pg_engine.begin() as connection:
            connection.execute(delete(BrowserSession).where(BrowserSession.browser_id.in_(browser_ids)))
            assert not connection.execute(select(BrowserSession.id).where(
                BrowserSession.browser_id.in_(browser_ids),
            )).first()


def _family_state(db, browser_id):
    return tuple(db.execute(select(BrowserSession.__table__).where(
        BrowserSession.browser_id == browser_id,
    )).one())


def _assert_browser_live(db, tokens):
    claims = decode_refresh_token(tokens.cookie)
    assert claims is not None
    principal = get_current_user(authorization=f"Bearer {tokens.access}", db=db)
    binding = refresh_binding(db, _browser_request(tokens.browser_id, tokens.epoch, cookie=tokens.cookie), claims)
    assert principal["user_id"] == claims["sub"]
    assert principal["org_id"] == claims["org_id"]
    assert binding == {key: claims[key] for key in ("sid", "sg", "bid", "be")}


def _assert_browser_superseded(db, tokens):
    with pytest.raises(HTTPException) as access_error:
        get_current_user(authorization=f"Bearer {tokens.access}", db=db)
    assert access_error.value.status_code == 401
    claims = decode_refresh_token(tokens.cookie)
    assert claims is not None
    with pytest.raises(HTTPException) as refresh_error:
        refresh_binding(db, _browser_request(tokens.browser_id, tokens.epoch, cookie=tokens.cookie), claims)
    assert refresh_error.value.status_code == 401


def _ordered_browser_race(engine, org_id, user_id, first_operation, second_operation, *, while_blocked=None):
    """First service holds an uncommitted family lock; second must wait on it."""
    first_ready, second_ready = Queue(), Queue()
    release = Event()

    def first():
        with _session(engine, org_id, user_id) as db:
            pid = db.execute(text("SELECT pg_backend_pid()")).scalar_one()
            result = first_operation(db)
            first_ready.put((pid, result))
            assert release.wait(timeout=15), "Controller failed to release browser family transaction"
            db.commit()
            return result

    def second(first_result):
        with _session(engine, org_id, user_id) as db:
            second_ready.put(db.execute(text("SELECT pg_backend_pid()")).scalar_one())
            result = second_operation(db, first_result)
            db.commit()
            return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(first)
        try:
            first_pid, first_result = first_ready.get(timeout=5)
            assert first_result.status in (200, 204), first_result.detail
            second_future = pool.submit(second, first_result)
            second_pid = second_ready.get(timeout=5)
            assert first_pid != second_pid
            # AUTOCOMMIT avoids a cached pg_stat_activity snapshot across polls.
            with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as observer:
                observer_pid = observer.execute(text("SELECT pg_backend_pid()")).scalar_one()
                assert observer_pid not in (first_pid, second_pid)
                deadline = time.monotonic() + 5
                while True:
                    if second_future.done():
                        second_future.result()
                        pytest.fail("Second browser mutation did not wait for the first family's lock")
                    blocked = observer.execute(text(
                        "SELECT wait_event_type, query, pg_blocking_pids(pid) AS blockers "
                        "FROM pg_stat_activity WHERE pid = :pid"
                    ), {"pid": second_pid}).mappings().one()
                    if first_pid in blocked["blockers"]:
                        assert blocked["wait_event_type"] == "Lock"
                        assert "browser_sessions" in blocked["query"]
                        assert "FOR UPDATE" in blocked["query"].upper()
                        break
                    assert time.monotonic() < deadline, "Second browser mutation never waited on the first connection"
                    time.sleep(0.02)
                if while_blocked is not None:
                    while_blocked()
                assert not first_future.done(), "First transaction committed before controller released it"
                assert not second_future.done(), "Second transaction escaped the family lock"
        finally:
            release.set()
        return first_future.result(timeout=15), second_future.result(timeout=15)


@pytest.mark.parametrize("epochs", [(2, 3), (3, 2), (3, 3)], ids=[
    "lower-commits-first", "higher-commits-first", "duplicate-epoch",
])
def test_postgres_browser_issuance_preserves_highest_committed_epoch(
    enterprise_pg_engine, browser_families, epochs,
):
    org_id, user_id, (original, independent) = browser_families
    with _session(enterprise_pg_engine, org_id, user_id) as db:
        independent_before = _family_state(db, independent.browser_id)

    def issue(db, epoch):
        return _browser_mutation(db, _browser_request(
            original.browser_id, epoch, cookie=original.cookie,
        ), org_id, user_id)

    outcomes = _ordered_browser_race(
        enterprise_pg_engine, org_id, user_id,
        lambda db: issue(db, epochs[0]), lambda db, _first: issue(db, epochs[1]),
    )
    assert [outcome.status for outcome in outcomes] == ([200, 200] if epochs[0] == 2 else [200, 409])
    highest = next(outcome.tokens for outcome in outcomes if outcome.tokens and outcome.tokens.epoch == 3)
    with _session(enterprise_pg_engine, org_id, user_id) as db:
        row = db.query(BrowserSession).filter_by(browser_id=original.browser_id).one()
        assert row.client_epoch == 3 and not row.revoked
        assert row.generation == (3 if epochs[0] == 2 else 2)
        assert row.user_id == user_id and row.organization_id == org_id
        _assert_browser_live(db, highest)
        _assert_browser_superseded(db, original)
        for outcome in outcomes:
            if outcome.tokens and outcome.tokens.epoch < 3:
                _assert_browser_superseded(db, outcome.tokens)
            if outcome.status == 409:
                assert outcome.set_cookie is None
                assert "superseded" in outcome.detail.lower()
        assert _family_state(db, independent.browser_id) == independent_before
        _assert_browser_live(db, independent)


@pytest.mark.parametrize("cookie_kind", ["captured", "replacement"])
def test_postgres_replayed_logout_cannot_revoke_newer_family(
    enterprise_pg_engine, browser_families, cookie_kind,
):
    org_id, user_id, (original, independent) = browser_families
    with _session(enterprise_pg_engine, org_id, user_id) as db:
        independent_before = _family_state(db, independent.browser_id)

    def issue(db):
        return _browser_mutation(db, _browser_request(original.browser_id, 3, cookie=original.cookie), org_id, user_id)

    def replay(db, issued):
        cookie = original.cookie if cookie_kind == "captured" else issued.tokens.cookie
        # A larger client epoch is not authority to revoke another generation.
        return _browser_mutation(db, _browser_request(
            original.browser_id, 100, cookie=cookie, access=original.access,
        ), org_id, user_id, revoke=True)

    issued, rejected = _ordered_browser_race(enterprise_pg_engine, org_id, user_id, issue, replay)
    assert issued.status == 200 and rejected.status == 409
    assert rejected.set_cookie is None
    with _session(enterprise_pg_engine, org_id, user_id) as db:
        before = _family_state(db, original.browser_id)
        assert replay(db, issued).status == 409  # Repeat after the newer login has committed.
        assert _family_state(db, original.browser_id) == before
        row = db.query(BrowserSession).filter_by(browser_id=original.browser_id).one()
        assert row.client_epoch == 3 and row.generation == 2 and not row.revoked
        _assert_browser_live(db, issued.tokens)
        _assert_browser_superseded(db, original)
        assert _family_state(db, independent.browser_id) == independent_before
        _assert_browser_live(db, independent)


def test_postgres_newer_login_after_concurrent_logout_stays_live(enterprise_pg_engine, browser_families):
    org_id, user_id, (original, independent) = browser_families
    with _session(enterprise_pg_engine, org_id, user_id) as db:
        independent_before = _family_state(db, independent.browser_id)

    def revoke(db):
        return _browser_mutation(db, _browser_request(
            original.browser_id, 2, cookie=original.cookie, access=original.access,
        ), org_id, user_id, revoke=True)

    def issue(db, _first):
        return _browser_mutation(db, _browser_request(original.browser_id, 3, cookie=original.cookie), org_id, user_id)

    revoked, issued = _ordered_browser_race(enterprise_pg_engine, org_id, user_id, revoke, issue)
    assert revoked.status == 204 and revoked.set_cookie is None
    assert issued.status == 200
    with _session(enterprise_pg_engine, org_id, user_id) as db:
        row = db.query(BrowserSession).filter_by(browser_id=original.browser_id).one()
        assert row.client_epoch == 3 and row.generation == 3 and not row.revoked
        _assert_browser_live(db, issued.tokens)
        _assert_browser_superseded(db, original)
        assert revoke(db).status == 409
        _assert_browser_live(db, issued.tokens)
        assert _family_state(db, independent.browser_id) == independent_before
        _assert_browser_live(db, independent)


def test_postgres_independent_device_rotates_while_other_family_is_locked(enterprise_pg_engine, browser_families):
    org_id, user_id, (original, independent) = browser_families
    independent_rotations = []

    def issue(db, epoch):
        return _browser_mutation(db, _browser_request(original.browser_id, epoch, cookie=original.cookie), org_id, user_id)

    def rotate_other_device():
        with _session(enterprise_pg_engine, org_id, user_id) as db:
            # The first family's uncommitted generation is invisible here.
            row = db.query(BrowserSession).filter_by(browser_id=original.browser_id).one()
            assert row.client_epoch == 1 and row.generation == 1
            _assert_browser_live(db, independent)
            rotated = _browser_mutation(db, _browser_request(
                independent.browser_id, 2, cookie=independent.cookie,
            ), org_id, user_id)
            assert rotated.status == 200
            db.commit()
            independent_rotations.append(rotated.tokens)

    issued, rejected = _ordered_browser_race(
        enterprise_pg_engine, org_id, user_id,
        lambda db: issue(db, 3), lambda db, _first: issue(db, 2), while_blocked=rotate_other_device,
    )
    assert issued.status == 200 and rejected.status == 409 and rejected.set_cookie is None
    assert len(independent_rotations) == 1
    with _session(enterprise_pg_engine, org_id, user_id) as db:
        _assert_browser_live(db, issued.tokens)
        _assert_browser_live(db, independent_rotations[0])
        _assert_browser_superseded(db, independent)
        row = db.query(BrowserSession).filter_by(browser_id=independent.browser_id).one()
        assert row.client_epoch == 2 and row.generation == 2 and not row.revoked
