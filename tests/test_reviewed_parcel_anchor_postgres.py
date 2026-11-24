"""Opt-in verified PG/RLS/locking proofs with synthetic, not real, inventory.

Only SNAPSHOT_TEST_POSTGRES_URL and SNAPSHOT_TEST_RUN_ID select the independently
provisioned disposable target. No ambient URL, provisioning, or source calls.
"""
import json
import threading
import time
from contextlib import contextmanager
from uuid import uuid4

import pytest
from sqlalchemy import event, select, text

from app.models.audit_log import AuditLog
from app.models.brand import BrandProfile, PermitBrandMatch
from app.models.deal import Deal
from app.models.graph import GraphEntityType, GraphRelationship, GraphRelationshipEvidence
from app.models.ingestion import IngestionRun, IngestionSource, PermitRecord, RawSourceRecord
from app.models.organization import Organization
from app.models.parcel import NearbyParcelCandidate, NearbyParcelSearch, ParcelRecord
from app.models.user import User
from app.schemas.graph import GraphEntityCreate
from app.schemas.parcel_reference import ParcelReferenceAcceptance
from app.services.brand_intelligence import review_brand_match
from app.services.graph_service import link_entity_to_record, resolve_entity
from app.services.parcel_anchor import get_deal_parcel_anchor
from app.services.parcel_reference_review import accept_parcel_reference
from app.services.parcel_service import create_nearby_parcel_search
from tests.research_postgres_support import RUN_ID, URL, assert_blocked_by, tenant_session
from tests.snapshot_postgres_support import verified_snapshot_connection

pytestmark = pytest.mark.skipif(not URL, reason="Dedicated disposable snapshot PostgreSQL URL not set")


@pytest.fixture
def stored_anchor(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Anchor PostgreSQL acceptance must not call sources or models")

    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    monkeypatch.setattr("app.services.llm_client.get_default_llm_client", forbidden)
    ids = {key: str(uuid4()) for key in ("org", "user", "deal", "match", "permit", "parcel")}
    with tenant_session(ids["org"]) as db:
        db.add(Organization(id=ids["org"], name="Synthetic anchor acceptance", slug=f"anchor-{ids['org']}"))
        db.add(User(id=ids["user"], email=f"{ids['user']}@example.invalid",
                    full_name="Synthetic reviewer", password_hash="!nologin"))
        db.flush()
        raw_ids, sources = {}, {}
        for kind in ("permit", "parcel"):
            source = IngestionSource(organization_id=ids["org"], key=f"synthetic-anchor-{kind}",
                                     name=f"Synthetic {kind}", adapter="manual", record_type=kind)
            db.add(source)
            db.flush()
            run = IngestionRun(organization_id=ids["org"], source_id=source.id, status="completed")
            db.add(run)
            db.flush()
            raw = RawSourceRecord(
                organization_id=ids["org"], source_id=source.id, run_id=run.id,
                external_record_id=f"synthetic-{kind}", record_type=kind, content_hash="a" * 64,
                payload={"synthetic": True},
            )
            db.add(raw)
            db.flush()
            raw_ids[kind], sources[kind] = raw.id, source
        address = {"address": "1 Synthetic Street", "city": "Austin", "state": "TX"}
        permit = PermitRecord(
            id=ids["permit"], organization_id=ids["org"], source_id=sources["permit"].id,
            latest_raw_record_id=raw_ids["permit"], external_record_id="synthetic-permit",
            normalization_hash="b" * 64, parcel_id="synthetic-parcel", approval_stage="pre_approval", **address,
        )
        parcel = ParcelRecord(
            id=ids["parcel"], organization_id=ids["org"], source_id=sources["parcel"].id,
            latest_raw_record_id=raw_ids["parcel"], external_parcel_id="synthetic-parcel",
            normalization_hash="c" * 64, latitude=30.2672, longitude=-97.7431, **address,
        )
        brand = BrandProfile(organization_id=ids["org"], key="synthetic-retail",
                             name="Synthetic Retail", normalized_name="synthetic retail")
        db.add_all([permit, parcel, brand, Deal(id=ids["deal"], organization_id=ids["org"],
                                                name="Synthetic anchor", **address)])
        db.flush()
        db.add(PermitBrandMatch(
            id=ids["match"], organization_id=ids["org"], permit_id=permit.id, brand_id=brand.id,
            first_raw_record_id=raw_ids["permit"], latest_raw_record_id=raw_ids["permit"],
            review_status="confirmed", confidence=0.95, matched_alias="Synthetic Retail",
            matched_field="description", excerpt="Synthetic only", detector_version="synthetic-v1",
        ))
        db.flush()
        for kind, entity_type in (("permit", GraphEntityType.permit), ("parcel", GraphEntityType.parcel)):
            entity, _ = resolve_entity(db, GraphEntityCreate(
                entity_type=entity_type, display_name=f"Synthetic {kind}",
                source_system=sources[kind].key, source_id=ids[kind],
            ))
            link_entity_to_record(db, entity.id, kind, ids[kind], sources[kind].key)
        db.flush()
        relationship = accept_parcel_reference(db, permit.id, ParcelReferenceAcceptance(
            parcel_source_id=parcel.source_id, parcel_id=parcel.id,
            expected_permit_raw_id=raw_ids["permit"], expected_parcel_raw_id=raw_ids["parcel"],
            confidence=0.9, reason="Synthetic matching identifiers and full site address",
        ), actor_id=ids["user"])
        ids["relationship"] = relationship.id
        db.commit()
    return ids


def _search(db, ids, expected):
    return create_nearby_parcel_search(
        db, deal_id=ids["deal"], anchor_brand_match_id=ids["match"], radius_miles=0.25,
        persona="developer", minimum_land_area_sq_ft=None, zoning_codes=[], land_uses=[],
        limit=50, expected_anchor=expected,
    )


def test_audited_review_search_persists_without_copying_coordinates(stored_anchor):
    ids = stored_anchor
    with tenant_session(ids["org"]) as db:
        expected = get_deal_parcel_anchor(db, ids["deal"], ids["match"])
        assert expected["status"] == "ready" and expected["method"] == "reviewed_parcel_centroid"
        audit = db.scalars(select(AuditLog).where(AuditLog.entity_id == ids["relationship"],
                                                 AuditLog.action == "parcel_reference_accepted")).one()
        assert audit.actor_id == ids["user"]
        saved = _search(db, ids, expected)
        search_id = saved.id
        assert len(saved.candidates) == 1 and saved.candidates[0].parcel_id == ids["parcel"]
        db.commit()
    with tenant_session(ids["org"]) as verify:
        saved = verify.get(NearbyParcelSearch, search_id)
        assert saved.filters["anchor_resolution"] == expected
        assert saved.candidates[0].explanation["anchor_resolution"] == expected
        assert (saved.anchor_latitude, saved.anchor_longitude) == (expected["latitude"], expected["longitude"])
        permit = verify.get(PermitRecord, ids["permit"])
        assert permit.latitude is None and permit.longitude is None
        assert permit.normalization_hash == "b" * 64


def test_cross_org_and_unset_rls_cannot_read_anchor_records(stored_anchor):
    ids = stored_anchor
    for denied_org in (str(uuid4()), "default-org"):
        with tenant_session(denied_org) as db:
            # Deliberately no application tenant predicates: prove actual RLS.
            for model, key in ((PermitRecord, "permit"), (ParcelRecord, "parcel"),
                               (GraphRelationship, "relationship"), (Deal, "deal")):
                assert db.scalar(select(model.id).where(model.id == ids[key])) is None
            with pytest.raises(LookupError):
                get_deal_parcel_anchor(db, ids["deal"], ids["match"])
    with verified_snapshot_connection(URL, RUN_ID) as connection:
        assert connection.scalar(text("SELECT count(*) FROM parcel_records WHERE id=:id"),
                                 {"id": ids["parcel"]}) == 0


@contextmanager
def _waiting_search(ids, expected, release_blocker):
    ready, state = threading.Event(), {}

    def worker():
        try:
            with tenant_session(ids["org"]) as db:
                state["phase"] = "verified_session"

                def trace(_conn, _cursor, statement, _params, _context, _many):
                    state["last_sql"] = statement

                event.listen(db.connection(), "before_cursor_execute", trace)
                state["pid"] = db.scalar(text("SELECT pg_catalog.pg_backend_pid()"))
                cached = db.get(ParcelRecord, ids["parcel"])
                state["before_wait"] = cached.normalization_hash
                ready.set()
                state["phase"] = "search"
                try:
                    _search(db, ids, expected)
                    state["created"] = True
                except ValueError as error:
                    state["rejection"] = str(error)
                state["after_wait"] = cached.normalization_hash
                state["phase"] = "finished"
                db.rollback()
        except BaseException as error:
            state["error"] = error
            ready.set()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    try:
        assert ready.wait(5), "Search worker did not acquire a verified connection"
        if "error" in state:
            raise state["error"]
        yield state
    finally:
        try:
            release_blocker()
        finally:
            thread.join(12)
            assert not thread.is_alive(), "Search exceeded bounded database timeouts"
    if "error" in state:
        raise state["error"]


def test_locked_search_reloads_committed_parcel_evidence_and_rejects_stale_preview(stored_anchor):
    ids = stored_anchor
    with tenant_session(ids["org"]) as preview_db:
        expected = get_deal_parcel_anchor(preview_db, ids["deal"], ids["match"])
        assert expected["status"] == "ready"
    with tenant_session(ids["org"]) as locker:
        parcel = locker.scalars(select(ParcelRecord).where(ParcelRecord.id == ids["parcel"]).with_for_update()).one()
        with _waiting_search(ids, expected, locker.rollback) as state:
            assert state["before_wait"] == "c" * 64
            try:
                assert_blocked_by(locker, state, "parcel_records")
            except BaseException as error:
                activity = locker.execute(text(
                    "SELECT state, wait_event_type, wait_event, query FROM pg_catalog.pg_stat_activity WHERE pid=:pid"
                ), {"pid": state["pid"]}).first()
                error.add_note(f"Synthetic worker phase={state.get('phase')}; rejection={state.get('rejection')}; "
                               f"error_type={type(state.get('error')).__name__}; last_sql={state.get('last_sql')}; "
                               f"activity={tuple(activity) if activity else None}")
                raise
            parcel.normalization_hash = "d" * 64
            locker.commit()
        assert "created" not in state and "changed" in state["rejection"]
        assert state["after_wait"] == "d" * 64
    with tenant_session(ids["org"]) as verify:
        assert verify.scalars(select(NearbyParcelSearch)).all() == []
        assert verify.scalars(select(NearbyParcelCandidate)).all() == []
        assert verify.get(ParcelRecord, ids["parcel"]).normalization_hash == "d" * 64


def test_dismissal_committed_before_match_lock_is_acquired_rejects_search(stored_anchor):
    ids = stored_anchor
    with tenant_session(ids["org"]) as preview_db:
        expected = get_deal_parcel_anchor(preview_db, ids["deal"], ids["match"])
    with tenant_session(ids["org"]) as locker:
        assert locker.scalar(select(PermitBrandMatch.id).where(
            PermitBrandMatch.id == ids["match"],
        ).with_for_update()) == ids["match"]
        with _waiting_search(ids, expected, locker.rollback) as state:
            assert_blocked_by(locker, state, "permit_brand_matches")
            review_brand_match(locker, ids["match"], "dismissed")
            locker.commit()
        assert "created" not in state and "changed" in state["rejection"]
    with tenant_session(ids["org"]) as verify:
        assert verify.get(PermitBrandMatch, ids["match"]).review_status == "dismissed"
        assert verify.scalars(select(NearbyParcelSearch)).all() == []
        assert verify.scalars(select(NearbyParcelCandidate)).all() == []


@contextmanager
def _waiting_dismissal(ids, release_blocker):
    ready, finished, state = threading.Event(), threading.Event(), {}

    def worker():
        try:
            with tenant_session(ids["org"]) as db:
                state["pid"] = db.scalar(text("SELECT pg_catalog.pg_backend_pid()"))
                ready.set()
                result = review_brand_match(db, ids["match"], "dismissed")
                assert result is not None and result.review_status == "dismissed"
                db.commit()
                state["committed"] = True
        except BaseException as error:
            state["error"] = error
            ready.set()
        finally:
            finished.set()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    try:
        assert ready.wait(5), "Dismissal worker did not acquire a verified connection"
        if "error" in state:
            raise state["error"]
        yield state, finished
    finally:
        try:
            release_blocker()
        finally:
            thread.join(12)
            assert not thread.is_alive(), "Dismissal exceeded bounded database timeouts"
    if "error" in state:
        raise state["error"]


def _assert_dismissal_update_blocked_by(db, state):
    # The real review service waits on UPDATE, not SELECT FOR UPDATE. Observe
    # that exact SQL and blocker; the shared SELECT-lock assertion is unchanged.
    blocker = db.scalar(text("SELECT pg_catalog.pg_backend_pid()"))
    assert state["pid"] != blocker
    activity_limit = db.scalar(text("SELECT pg_catalog.pg_size_bytes(current_setting('track_activity_query_size'))"))
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        db.execute(text("SELECT pg_catalog.pg_stat_clear_snapshot()"))
        activity = db.execute(text(
            "SELECT pg_catalog.pg_blocking_pids(pid), query FROM pg_catalog.pg_stat_activity WHERE pid=:pid"
        ), {"pid": state["pid"]}).one()
        if blocker in activity[0]:
            assert len(activity[1].encode("utf-8")) < activity_limit - 1
            assert activity[1].lstrip().startswith("UPDATE permit_brand_matches SET review_status=")
            assert "WHERE permit_brand_matches.id =" in activity[1]
            return
        time.sleep(0.01)
    pytest.fail("No actual PostgreSQL blocker on the real dismissal UPDATE observed")


def test_match_dismissal_waits_until_audited_search_commits(stored_anchor):
    ids = stored_anchor
    with tenant_session(ids["org"]) as search_db:
        expected = get_deal_parcel_anchor(search_db, ids["deal"], ids["match"])
        saved = _search(search_db, ids, expected)
        search_id = saved.id
        with _waiting_dismissal(ids, search_db.rollback) as (state, finished):
            _assert_dismissal_update_blocked_by(search_db, state)
            assert not finished.is_set()
            assert search_db.get(PermitBrandMatch, ids["match"]).review_status == "confirmed"
            search_db.commit()
        assert state["committed"] is True
    with tenant_session(ids["org"]) as verify:
        assert verify.get(PermitBrandMatch, ids["match"]).review_status == "dismissed"
        saved = verify.get(NearbyParcelSearch, search_id)
        assert saved.filters["anchor_resolution"] == expected
        assert len(saved.candidates) == 1


@pytest.mark.parametrize("oversized", ["evidence", "audit"])
def test_database_byte_metadata_rejects_oversized_review_before_body_fetch(stored_anchor, oversized):
    ids = stored_anchor
    with tenant_session(ids["org"]) as setup:
        if oversized == "evidence":
            row = setup.scalars(select(GraphRelationshipEvidence).where(
                GraphRelationshipEvidence.relationship_id == ids["relationship"],
            )).first()
            row.payload = {**row.payload, "padding": "\u00e9" * 9000}
        else:
            row = setup.scalars(select(AuditLog).where(
                AuditLog.entity_id == ids["relationship"], AuditLog.action == "parcel_reference_accepted",
            )).one()
            row.new_values = json.dumps({**json.loads(row.new_values), "padding": "\u00e9" * 9000}, ensure_ascii=False)
            assert len(row.new_values) < 16384 < len(row.new_values.encode("utf-8"))
        setup.commit()
    with tenant_session(ids["org"]) as db:
        statements = []
        connection = db.connection()

        def capture(_conn, _cursor, sql, _params, _context, _many):
            statements.append(sql)

        event.listen(connection, "before_cursor_execute", capture)
        try:
            assert get_deal_parcel_anchor(db, ids["deal"], ids["match"])["status"] == "unavailable"
        finally:
            event.remove(connection, "before_cursor_execute", capture)
        for table, column in (("graph_relationship_evidence", "payload"), ("audit_logs", "new_values")):
            queries = [sql for sql in statements if f"FROM {table}" in sql]
            assert queries and all("octet_length(" in sql for sql in queries)
            assert all(f"AS {table}_{column}" not in sql for sql in queries)
        raw_checks = [sql for sql in statements if "FROM raw_source_records" in sql
                      and "raw_source_records.external_record_id =" in sql]
        assert len(raw_checks) == 2
        assert all("raw_source_records.payload" not in sql for sql in raw_checks)
