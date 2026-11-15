"""Opt-in guarded PG/RLS acceptance; the parent provisions and migrates the target.

Only SNAPSHOT_TEST_POSTGRES_URL / SNAPSHOT_TEST_RUN_ID select a database. The
shared harness rejects malformed/ambient targets before connecting and verifies
the database nonce and restricted current/session role on every physical socket.
No schema, role, external source, migration or runtime is provisioned here.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.ingestion import (
    IngestionRun,
    IngestionSource,
    RawSourceRecord,
    RawSourceRecordObservation,
)
from app.models.organization import Organization
from app.models.parcel import ParcelFact, ParcelRecord
from app.services.demo_access import demo_read_only
from app.services.parcel_use_context import get_parcel_use_context
from app.utils.org_scope import RequestContext, reset_current_context, set_current_context
from tests.research_postgres_support import RUN_ID, URL, tenant_session
from tests.snapshot_postgres_support import verified_snapshot_connection

pytestmark = pytest.mark.skipif(not URL, reason="Dedicated disposable snapshot PostgreSQL URL not set")

NOW = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)
PAST = NOW - timedelta(days=1)
PROVENANCE_MODELS = (ParcelRecord, ParcelFact, IngestionSource, RawSourceRecord)


@contextmanager
def _read_only_tenant(org):
    token = demo_read_only.set(True)
    try:
        with tenant_session(org) as db:
            assert db.scalar(text("SHOW transaction_read_only")) == "on"
            yield db
            assert db.scalar(text("SHOW transaction_read_only")) == "on"
    finally:
        demo_read_only.reset(token)


def _new_tenant(label):
    ids = {key: str(uuid4()) for key in ("org", "source", "run", "raw", "parcel", "fact")}
    with tenant_session(ids["org"]) as db:
        db.add(Organization(id=ids["org"], name="Synthetic parcel context", slug=f"ctx-{ids['org']}"))
        db.flush()
        db.add(IngestionSource(
            id=ids["source"], organization_id=ids["org"], key="synthetic-context-parcels",
            name="Synthetic parcel context", adapter="manual", record_type="parcel",
            settings={"private": "retained-private-configuration"},
        ))
        db.flush()
        db.add(IngestionRun(
            id=ids["run"], organization_id=ids["org"], source_id=ids["source"], status="completed",
        ))
        db.flush()
        db.add(RawSourceRecord(
            id=ids["raw"], organization_id=ids["org"], source_id=ids["source"],
            run_id=ids["run"], external_record_id="synthetic-context-parcel",
            record_type="parcel", content_hash="a" * 64, received_at=PAST,
            payload={"private": "retained-private-raw-evidence", "zoning_code": label},
        ))
        db.flush()
        db.add(ParcelRecord(
            id=ids["parcel"], organization_id=ids["org"], source_id=ids["source"],
            latest_raw_record_id=ids["raw"], external_parcel_id="synthetic-context-parcel",
            jurisdiction="Synthetic authority", state="NJ", zoning_code=label,
            last_verified_at=PAST,
        ))
        db.flush()
        db.add(ParcelFact(
            id=ids["fact"], organization_id=ids["org"], parcel_id=ids["parcel"],
            raw_source_record_id=ids["raw"], fact_type="zoning", value={"zoning_code": label},
            source_system="synthetic-context-parcels", source_url="https://example.invalid/zoning",
            confidence=1, observed_at=PAST, last_verified_at=PAST, valid_from=PAST, is_current=True,
        ))
        db.commit()
    return ids


@pytest.fixture
def parcel_tenants(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Parcel PostgreSQL acceptance must not call sources or models")

    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    monkeypatch.setattr("app.services.llm_client.get_default_llm_client", forbidden)
    return _new_tenant("SYNTHETIC-B2"), _new_tenant("FOREIGN-SECRET-ZONE")


def _state(db, org):
    models = (
        ParcelRecord, ParcelFact, IngestionSource, IngestionRun, RawSourceRecord,
        RawSourceRecordObservation, AuditLog,
    )
    return {
        model.__tablename__: [dict(row) for row in db.execute(
            select(model.__table__).where(model.organization_id == org).order_by(
                model.raw_source_record_id if model is RawSourceRecordObservation else model.id,
            ),
        ).mappings()]
        for model in models
    }


def _assert_not_assessed(result):
    assert result.potential_uses == []
    assert result.potential_uses_status == "not_assessed"
    assert result.ai_used is False
    assert {
        "zoning_assignment_unverified", "use_rules_missing",
        "overlays_unverified", "site_constraints_unverified",
    } <= set(result.gaps)


def _assert_hidden(db, ids):
    for model, key in zip(PROVENANCE_MODELS, ("parcel", "fact", "source", "raw"), strict=True):
        # No application org predicate: visibility is enforced by actual RLS.
        assert db.scalar(select(model.id).where(model.id == ids[key])) is None


def test_service_reads_under_restricted_role_and_actual_read_only_transaction(parcel_tenants):
    own, _foreign = parcel_tenants
    with _read_only_tenant(own["org"]) as db:
        identity = db.execute(text(
            "SELECT current_user, session_user, r.rolsuper, r.rolbypassrls "
            "FROM pg_catalog.pg_roles r WHERE r.rolname = current_user"
        )).one()
        assert identity[0] == identity[1]
        assert identity[2] is False and identity[3] is False
        rls = db.execute(text(
            "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_catalog.pg_class "
            "WHERE oid IN ('parcel_records'::regclass, 'parcel_facts'::regclass, "
            "'ingestion_sources'::regclass, 'raw_source_records'::regclass)"
        )).all()
        assert len(rls) == 4
        assert all(enabled is True and forced is True for _table, enabled, forced in rls)
        for model, key in zip(PROVENANCE_MODELS, ("parcel", "fact", "source", "raw"), strict=True):
            assert db.scalar(select(model.id).where(model.id == own[key])) == own[key]
        before = _state(db, own["org"])
        result = get_parcel_use_context(db, own["parcel"], as_of=NOW)
        _assert_not_assessed(result)
        assert result.status == "reported"
        assert result.reported_zoning_codes == ["SYNTHETIC-B2"]
        assert [item.fact_id for item in result.evidence] == [own["fact"]]
        assert result.evidence[0].observed_at == PAST
        assert _state(db, own["org"]) == before
        assert not db.new and not db.dirty and not db.deleted
    with _read_only_tenant(own["org"]) as verify:
        assert _state(verify, own["org"]) == before


def test_foreign_default_and_unset_tenants_are_denied_by_rls(parcel_tenants):
    own, foreign = parcel_tenants
    with _read_only_tenant(own["org"]) as db:
        before = _state(db, own["org"])
    for denied_org in (foreign["org"], "default-org"):
        with _read_only_tenant(denied_org) as db:
            _assert_hidden(db, own)
            assert get_parcel_use_context(db, own["parcel"], as_of=NOW) is None

    token = set_current_context(RequestContext(own["org"], "synthetic-unset-rls-test"))
    try:
        with verified_snapshot_connection(URL, RUN_ID) as connection:
            with connection.begin():
                connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                assert connection.scalar(text("SELECT current_setting('app.current_org', true)")) in (None, "")
                # Deliberately no tenant after_begin listener. Even a matching
                # application context cannot bypass an unset database tenant.
                with Session(bind=connection, autoflush=False) as db:
                    _assert_hidden(db, own)
                    assert get_parcel_use_context(db, own["parcel"], as_of=NOW) is None
    finally:
        reset_current_context(token)
    with _read_only_tenant(own["org"]) as verify:
        assert _state(verify, own["org"]) == before


@pytest.mark.parametrize("problem", [
    "foreign_raw", "foreign_source", "wrong_raw_source", "wrong_source_system", "missing_evidence",
    "same_source_other_parcel", "wrong_raw_record_type", "oversized_fact_json",
])
def test_incomplete_provenance_never_leaks_foreign_labels_or_changes_evidence(parcel_tenants, problem):
    own, foreign = parcel_tenants
    if problem == "foreign_source":
        hidden_source = str(uuid4())
        with tenant_session(foreign["org"]) as foreign_setup:
            foreign_setup.add(IngestionSource(
                id=hidden_source, organization_id=foreign["org"], key="synthetic-hidden-source",
                name="Synthetic foreign source", adapter="manual", record_type="parcel",
            ))
            foreign_setup.commit()
    with tenant_session(own["org"]) as setup:
        fact = setup.get(ParcelFact, own["fact"])
        if problem == "foreign_raw":
            fact.raw_source_record_id = foreign["raw"]
        elif problem == "foreign_source":
            setup.get(ParcelRecord, own["parcel"]).source_id = hidden_source
        elif problem == "wrong_raw_source":
            source = IngestionSource(
                organization_id=own["org"], key="synthetic-other-context-source",
                name="Synthetic other source", adapter="manual", record_type="parcel",
            )
            setup.add(source)
            setup.flush()
            raw = RawSourceRecord(
                organization_id=own["org"], source_id=source.id, run_id=own["run"],
                external_record_id="synthetic-context-parcel", record_type="parcel",
                content_hash="b" * 64, payload={"zoning_code": "WRONG-RAW-SECRET"},
            )
            setup.add(raw)
            setup.flush()
            fact.raw_source_record_id = raw.id
        elif problem in ("same_source_other_parcel", "wrong_raw_record_type"):
            raw = RawSourceRecord(
                organization_id=own["org"], source_id=own["source"], run_id=own["run"],
                external_record_id=("WRONG-PARCEL-SECRET" if problem == "same_source_other_parcel"
                                    else "synthetic-context-parcel"),
                record_type="parcel" if problem == "same_source_other_parcel" else "permit",
                content_hash="c" * 64, payload={"zoning_code": "WRONG-RAW-SECRET"},
            )
            setup.add(raw)
            setup.flush()
            fact.raw_source_record_id = raw.id
        elif problem == "oversized_fact_json":
            fact.value = {"zoning_code": "SYNTHETIC-B2", "padding": "x" * 17000}
        elif problem == "wrong_source_system":
            fact.source_system = "wrong-source-system"
        else:
            setup.delete(fact)
        setup.commit()

    with _read_only_tenant(foreign["org"]) as db:
        foreign_before = _state(db, foreign["org"])
    with _read_only_tenant(own["org"]) as db:
        before = _state(db, own["org"])
        if problem == "foreign_raw":
            assert db.scalar(select(RawSourceRecord.id).where(RawSourceRecord.id == foreign["raw"])) is None
        if problem == "foreign_source":
            assert db.scalar(select(IngestionSource.id).where(IngestionSource.id == hidden_source)) is None
        result = get_parcel_use_context(db, own["parcel"], as_of=NOW)
        _assert_not_assessed(result)
        assert result.status == "incomplete"
        assert result.recorded_zoning_code == "SYNTHETIC-B2"
        assert result.reported_zoning_codes == result.evidence == []
        assert "zoning_evidence_missing" in result.gaps
        if problem != "missing_evidence":
            assert "source_evidence_incomplete" in result.gaps
        serialized = result.model_dump_json()
        for secret in (*foreign.values(), own["fact"], "FOREIGN-SECRET-ZONE", "WRONG-RAW-SECRET"):
            assert secret not in serialized
        if problem == "foreign_source":
            assert hidden_source not in serialized
        assert _state(db, own["org"]) == before
    for ids, expected in ((own, before), (foreign, foreign_before)):
        with _read_only_tenant(ids["org"]) as verify:
            assert _state(verify, ids["org"]) == expected


def test_missing_raw_reference_is_rejected_without_disabling_foreign_keys(parcel_tenants):
    own, _foreign = parcel_tenants
    with _read_only_tenant(own["org"]) as db:
        before = _state(db, own["org"])
    with tenant_session(own["org"]) as db:
        db.get(ParcelFact, own["fact"]).raw_source_record_id = str(uuid4())
        with pytest.raises(IntegrityError) as failure:
            db.flush()
        assert failure.value.orig.pgcode == "23503"
        db.rollback()
    with _read_only_tenant(own["org"]) as verify:
        assert _state(verify, own["org"]) == before
        result = get_parcel_use_context(verify, own["parcel"], as_of=NOW)
        _assert_not_assessed(result)
        assert result.status == "reported"


@pytest.mark.parametrize("count", [50, 51])
def test_actual_fact_query_has_limit_and_overflow_fails_closed(parcel_tenants, count):
    own, _foreign = parcel_tenants
    with tenant_session(own["org"]) as setup:
        for index in range(1, count):
            setup.add(ParcelFact(
                organization_id=own["org"], parcel_id=own["parcel"], raw_source_record_id=own["raw"],
                fact_type="zoning", value={"zoning_code": "SYNTHETIC-B2"},
                source_system="synthetic-context-parcels", confidence=0.01,
                observed_at=PAST, last_verified_at=PAST, valid_from=PAST + timedelta(seconds=index),
                is_current=True,
            ))
        setup.commit()
    with _read_only_tenant(own["org"]) as db:
        before = _state(db, own["org"])
        connection = db.connection()
        statements = []

        def capture(_conn, cursor, statement, parameters, _context, _executemany):
            statements.append((statement, dict(parameters), cursor.rowcount))

        event.listen(connection, "after_cursor_execute", capture)
        try:
            result = get_parcel_use_context(db, own["parcel"], as_of=NOW)
        finally:
            event.remove(connection, "after_cursor_execute", capture)
        _assert_not_assessed(result)
        assert len(statements) == 2
        assert all(sql.lstrip().upper().startswith("SELECT") for sql, _params, _rows in statements)
        assert all("FOR UPDATE" not in sql.upper() for sql, _params, _rows in statements)
        fact_query, = [(sql, params, rows) for sql, params, rows in statements if "FROM parcel_facts" in sql]
        sql, params, returned_rows = fact_query
        assert "LIMIT" in sql.upper() and 51 in params.values()
        assert returned_rows == count
        assert len(result.evidence) == min(count, 50)
        assert result.status == ("reported" if count == 50 else "incomplete")
        assert ("evidence_limit_reached" in result.gaps) == (count > 50)
        assert _state(db, own["org"]) == before
    with _read_only_tenant(own["org"]) as verify:
        assert _state(verify, own["org"]) == before
