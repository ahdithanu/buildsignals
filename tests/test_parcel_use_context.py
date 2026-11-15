from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session

from app.db import Base, configure_sqlite_foreign_keys
from app.models.ingestion import IngestionRun, IngestionSource, RawSourceRecord
from app.models.organization import Organization
from app.models.parcel import ParcelFact, ParcelRecord
from app.schemas.parcel_use_context import ParcelUseContextResponse
from app.services.parcel_use_context import get_parcel_use_context
from app.utils.org_scope import RequestContext, reset_current_context, set_current_context

NOW = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)
PAST = NOW - timedelta(days=2)
BASE_GAPS = [
    "zoning_assignment_unverified",
    "use_rules_missing",
    "overlays_unverified",
    "site_constraints_unverified",
]


@pytest.fixture()
def context_db():
    engine = create_engine("sqlite://")
    configure_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    token = set_current_context(RequestContext("context-org", "context-user"))
    with Session(engine) as db:
        db.add_all([
            Organization(id=org, name=org, slug=org)
            for org in ("context-org", "foreign-org")
        ])
        db.commit()
        yield db
    reset_current_context(token)
    engine.dispose()


def _parcel(db, *, org="context-org", **changes):
    external_id = str(uuid4())
    source = IngestionSource(
        organization_id=org, key=f"private-key-{uuid4()}", name="Synthetic assessor",
        adapter="csv", record_type="parcel", settings={"private": "private-config"},
    )
    db.add(source)
    db.flush()
    run = IngestionRun(organization_id=org, source_id=source.id, status="completed")
    db.add(run)
    db.flush()
    raw = RawSourceRecord(
        organization_id=org, source_id=source.id, run_id=run.id,
        external_record_id=external_id, record_type="parcel", content_hash="a" * 64,
        payload={"private": "private-payload", "zoning_code": "RAW-NOT-EVIDENCE"},
        received_at=PAST,
    )
    db.add(raw)
    db.flush()
    values = dict(
        organization_id=org, source_id=source.id, latest_raw_record_id=raw.id,
        external_parcel_id=external_id, jurisdiction="Synthetic city", state="TX",
        zoning_code=None, land_use=None, last_verified_at=PAST,
    )
    values.update(changes)
    parcel = ParcelRecord(**values)
    db.add(parcel)
    db.commit()
    return parcel, source, raw


def _fact(db, parcel, source, raw, *, kind="zoning", label="CS", **changes):
    values = dict(
        organization_id=parcel.organization_id, parcel_id=parcel.id,
        raw_source_record_id=raw.id, fact_type=kind,
        value={"zoning_code" if kind == "zoning" else "land_use": label},
        source_system=source.key, source_url="https://example.gov/parcels/1",
        confidence=0.9, observed_at=PAST, last_verified_at=PAST,
        valid_from=PAST, is_current=True,
    )
    values.update(changes)
    fact = ParcelFact(**values)
    db.add(fact)
    db.commit()
    return fact


def _context(db, parcel):
    result = get_parcel_use_context(db, parcel.id, as_of=NOW)
    assert isinstance(result, ParcelUseContextResponse)
    assert result.as_of == NOW
    assert result.method_version == "parcel-use-context-v1"
    assert result.potential_uses == []
    assert result.potential_uses_status == "not_assessed"
    assert result.ai_used is False
    assert result.gaps[:4] == BASE_GAPS
    return result


def test_consistent_source_backed_labels_are_reported_not_permitted(context_db):
    db = context_db
    parcel, source, raw = _parcel(db, zoning_code="CS", land_use="Retail")
    zoning = _fact(db, parcel, source, raw)
    land_use = _fact(db, parcel, source, raw, kind="land_use", label="Retail")
    result = _context(db, parcel)
    assert result.status == "reported"
    assert result.recorded_zoning_code == "CS"
    assert result.reported_zoning_codes == ["CS"]
    assert result.recorded_land_uses == ["Retail"]
    assert result.jurisdiction == "Synthetic city"
    assert result.state == "TX"
    assert result.gaps == BASE_GAPS
    assert {item.fact_id for item in result.evidence} == {zoning.id, land_use.id}
    for item in result.evidence:
        assert item.source_url == "https://example.gov/parcels/1"
        assert item.confidence == 0.9
        assert item.observed_at == PAST
        assert item.last_verified_at == PAST
    serialized = result.model_dump_json()
    for private in (source.key, source.id, raw.id, "private-config", "private-payload"):
        assert private not in serialized
    assert set(result.evidence[0].model_dump()) == {
        "fact_id", "kind", "recorded_value", "source_url", "confidence",
        "observed_at", "last_verified_at",
    }


def test_canonical_only_is_incomplete(context_db):
    parcel, _, _ = _parcel(context_db, zoning_code="CS", land_use="Retail")
    result = _context(context_db, parcel)
    assert result.status == "incomplete"
    assert result.recorded_zoning_code == "CS"
    assert result.reported_zoning_codes == []
    assert result.recorded_land_uses == ["Retail"]
    assert result.evidence == []
    assert "zoning_evidence_missing" in result.gaps


def test_no_labels_or_evidence_is_missing_and_never_reads_raw_labels(context_db):
    parcel, _, _ = _parcel(context_db)
    result = _context(context_db, parcel)
    assert result.status == "missing"
    assert result.recorded_zoning_code is None
    assert result.reported_zoning_codes == result.recorded_land_uses == result.evidence == []
    assert "zoning_evidence_missing" in result.gaps


@pytest.mark.parametrize("historical", [
    {"is_current": False}, {"is_current": False, "valid_to": PAST},
])
def test_historical_facts_are_excluded(context_db, historical):
    parcel, source, raw = _parcel(context_db)
    _fact(context_db, parcel, source, raw, label="HISTORICAL", **historical)
    result = _context(context_db, parcel)
    assert result.status == "missing"
    assert result.evidence == []


@pytest.mark.parametrize("canonical,labels", [("CS", ["GR"]), (None, ["CS", "GR"])])
def test_zoning_disagreement_is_conflicting(context_db, canonical, labels):
    parcel, source, raw = _parcel(context_db, zoning_code=canonical)
    for index, label in enumerate(labels):
        _fact(context_db, parcel, source, raw, label=label,
              valid_from=PAST + timedelta(seconds=index))
    result = _context(context_db, parcel)
    assert result.status == "conflicting"
    assert result.recorded_zoning_code == canonical
    assert result.reported_zoning_codes == sorted(labels)
    assert "zoning_evidence_conflicting" in result.gaps


def test_land_use_evidence_is_context_without_zoning(context_db):
    parcel, source, raw = _parcel(context_db)
    _fact(context_db, parcel, source, raw, kind="land_use", label="Retail")
    result = _context(context_db, parcel)
    assert result.status == "incomplete"
    assert result.recorded_land_uses == ["Retail"]
    assert result.reported_zoning_codes == []
    assert "zoning_evidence_missing" in result.gaps


@pytest.mark.parametrize("changes", [
    {"value": {"zoning_code": ""}}, {"value": {"zoning_code": "  "}},
    {"value": {"zoning_code": "x" * 256}}, {"value": {"zoning_code": 123}},
    {"value": {"zoning_code": ["CS"]}}, {"value": {"zoning_code": True}},
    {"value": {"municipal_id": "CS"}}, {"value": ["CS"]}, {"value": None},
    {"confidence": -0.01}, {"confidence": 1.01},
    {"observed_at": NOW + timedelta(seconds=1)},
    {"last_verified_at": NOW + timedelta(seconds=1)},
    {"valid_from": NOW + timedelta(seconds=1)},
    {"valid_to": PAST}, {"valid_to": NOW + timedelta(seconds=1)},
    {"source_system": "wrong-source"},
])
def test_invalid_fact_is_incomplete_without_unsafe_values(context_db, changes):
    parcel, source, raw = _parcel(context_db)
    fact = _fact(context_db, parcel, source, raw, **changes)
    result = _context(context_db, parcel)
    assert result.status == "incomplete"
    assert result.evidence == result.reported_zoning_codes == []
    assert fact.id not in result.model_dump_json()
    assert "source_evidence_incomplete" in result.gaps


@pytest.mark.parametrize("column,value", [
    ("observed_at", "not-a-date"), ("last_verified_at", "not-a-date"),
    ("valid_from", "not-a-date"), ("observed_at", "99999-01-01"),
    ("valid_to", "not-a-date"),
    ("confidence", "NaN"), ("confidence", "Infinity"),
    ("confidence", "not-a-number"), ("value", "{broken-json"),
])
def test_malformed_storage_fails_closed_without_decode_errors(context_db, column, value):
    parcel, source, raw = _parcel(context_db)
    fact = _fact(context_db, parcel, source, raw)
    context_db.execute(text(f"UPDATE parcel_facts SET {column} = :value WHERE id = :id"),
                       {"value": value, "id": fact.id})
    context_db.commit()
    result = _context(context_db, parcel)
    assert result.status == "incomplete"
    assert result.evidence == []
    assert "source_evidence_incomplete" in result.gaps


@pytest.mark.parametrize("mismatch", ["foreign-raw", "other-source", "foreign-source", "missing-raw"])
def test_raw_and_source_provenance_must_match_without_leaking(context_db, mismatch):
    db = context_db
    parcel, source, raw = _parcel(db)
    other, other_source, other_raw = _parcel(db, org="foreign-org" if "foreign" in mismatch else "context-org")
    if mismatch == "foreign-source":
        parcel.source_id = other_source.id
        db.commit()
    elif mismatch == "foreign-raw":
        # Same source ID still cannot make a foreign-organization raw row valid.
        other_raw = RawSourceRecord(
            organization_id="foreign-org", source_id=source.id, run_id=other_raw.run_id,
            external_record_id=parcel.external_parcel_id, record_type="parcel",
            content_hash="b" * 64, payload={"private": "foreign"},
        )
        db.add(other_raw)
        db.commit()
    elif mismatch == "other-source":
        other_raw = RawSourceRecord(
            organization_id=parcel.organization_id, source_id=other_source.id, run_id=other_raw.run_id,
            external_record_id=parcel.external_parcel_id, record_type="parcel",
            content_hash="b" * 64, payload={"private": "other-source"},
        )
        db.add(other_raw)
        db.commit()
    fact = _fact(db, parcel, source, raw if mismatch in ("foreign-source", "missing-raw") else other_raw,
                 label="INVALID-SECRET-LABEL")
    if mismatch == "missing-raw":
        db.commit()
        db.execute(text("PRAGMA foreign_keys = OFF"))
        db.execute(text("UPDATE parcel_facts SET raw_source_record_id = 'missing' WHERE id = :id"),
                   {"id": fact.id})
        db.commit()
    result = _context(db, parcel)
    assert result.status == "incomplete"
    assert result.reported_zoning_codes == result.evidence == []
    serialized = result.model_dump_json()
    for private in (fact.id, other.id, other_raw.id, other_source.id, "INVALID-SECRET-LABEL"):
        assert private not in serialized


@pytest.mark.parametrize("problem", ["other-parcel", "wrong-record-type"])
def test_raw_provenance_requires_exact_parcel_identity_and_record_type(context_db, problem):
    parcel, source, raw = _parcel(context_db)
    other_raw = RawSourceRecord(
        organization_id=parcel.organization_id, source_id=source.id, run_id=raw.run_id,
        external_record_id="OTHER-PARCEL-SECRET" if problem == "other-parcel" else parcel.external_parcel_id,
        record_type="parcel" if problem == "other-parcel" else "permit",
        content_hash="f" * 64, payload={"zoning_code": "WRONG-PARCEL-SECRET"},
    )
    context_db.add(other_raw)
    context_db.commit()
    fact = _fact(context_db, parcel, source, other_raw, label="WRONG-PARCEL-SECRET")
    result = _context(context_db, parcel)
    assert result.status == "incomplete"
    assert result.reported_zoning_codes == result.evidence == []
    assert "source_evidence_incomplete" in result.gaps
    assert fact.id not in result.model_dump_json()
    assert "WRONG-PARCEL-SECRET" not in result.model_dump_json()


@pytest.mark.parametrize("problem", ["deep-json", "oversized-json"])
def test_untrusted_json_is_bounded_and_decode_recursion_fails_closed(context_db, problem, monkeypatch):
    import json
    import sys

    from app.services import parcel_use_context as service

    parcel, source, raw = _parcel(context_db)
    fact = _fact(context_db, parcel, source, raw)
    if problem == "deep-json":
        depth = sys.getrecursionlimit() + 100
        stored_json = '{"zoning_code":"CS","nested":' + "[" * depth + "0" + "]" * depth + "}"
    else:
        stored_json = json.dumps({"zoning_code": "CS", "padding": "x" * 17000})
    context_db.execute(text("UPDATE parcel_facts SET value = :value WHERE id = :id"),
                       {"value": stored_json, "id": fact.id})
    context_db.commit()
    original_loads = json.loads
    if problem == "deep-json":
        # Exercise the standard-library decoder's recursion failure consistently
        # across Python builds with different C-decoder recursion limits.
        decoder = json.JSONDecoder()
        decoder.scan_once = json.scanner.py_make_scanner(decoder)
        original_loads = decoder.decode

    def bounded_loads(value, *args, **kwargs):
        if isinstance(value, str):
            assert len(value) <= 16384, "Oversized fact JSON must not enter the decoder"
        return original_loads(value, *args, **kwargs)

    monkeypatch.setattr(service.json, "loads", bounded_loads)
    result = _context(context_db, parcel)
    assert result.status == "incomplete"
    assert result.reported_zoning_codes == result.evidence == []
    assert "source_evidence_incomplete" in result.gaps


@pytest.mark.parametrize("count", [50, 51, 75])
def test_relevant_current_evidence_is_bounded(context_db, count):
    parcel, source, raw = _parcel(context_db)
    for index in range(count):
        _fact(context_db, parcel, source, raw, valid_from=PAST + timedelta(seconds=index))
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append((statement, parameters))

    event.listen(context_db.bind, "before_cursor_execute", capture)
    try:
        result = _context(context_db, parcel)
    finally:
        event.remove(context_db.bind, "before_cursor_execute", capture)
    fact_queries = [(sql, params) for sql, params in statements if "FROM parcel_facts" in sql]
    assert len(fact_queries) == 1
    assert "LIMIT" in fact_queries[0][0]
    assert 51 in fact_queries[0][1]
    assert len(result.evidence) <= 50
    assert result.status == ("reported" if count == 50 else "incomplete")
    assert ("evidence_limit_reached" in result.gaps) == (count > 50)


def test_irrelevant_history_foreign_facts_and_other_parcels_do_not_count(context_db):
    parcel, source, raw = _parcel(context_db)
    other, _, _ = _parcel(context_db)
    valid = _fact(context_db, parcel, source, raw)
    for index in range(55):
        _fact(context_db, parcel, source, raw, kind="ownership", label="NOT-ZONING",
              valid_from=PAST + timedelta(seconds=index))
        _fact(context_db, parcel, source, raw, label="HISTORICAL", is_current=False,
              valid_from=PAST - timedelta(seconds=index + 1))
        _fact(context_db, parcel, source, raw, label="FOREIGN-SECRET", organization_id="foreign-org",
              valid_from=PAST + timedelta(seconds=index + 1))
    _fact(context_db, other, source, raw, label="OTHER-PARCEL")
    result = _context(context_db, parcel)
    assert result.status == "reported"
    assert [item.fact_id for item in result.evidence] == [valid.id]
    assert result.reported_zoning_codes == ["CS"]


@pytest.mark.parametrize("changes", [{"is_active": False}, {"retired_at": PAST}, {"org": "foreign-org"}])
def test_unavailable_parcels_return_none(context_db, changes):
    parcel, _, _ = _parcel(context_db, **changes)
    assert get_parcel_use_context(context_db, parcel.id, as_of=NOW) is None
    assert get_parcel_use_context(context_db, "does-not-exist", as_of=NOW) is None


@pytest.mark.parametrize("confidence", [0.0, 0.01, 1.0])
def test_no_arbitrary_confidence_or_freshness_threshold(context_db, confidence):
    parcel, source, raw = _parcel(context_db)
    _fact(context_db, parcel, source, raw, confidence=confidence,
          observed_at=NOW - timedelta(days=3650), source_url=None)
    result = _context(context_db, parcel)
    assert result.status == "reported"
    assert result.evidence[0].confidence == confidence
    assert result.evidence[0].source_url is None


def test_read_only_with_dirty_session_and_no_network(context_db, monkeypatch):
    parcel, source, raw = _parcel(context_db, zoning_code="CS")
    _fact(context_db, parcel, source, raw)
    context_db.refresh(parcel)
    parcel.zoning_code = "UNFLUSHED"
    pending = Organization(id="pending-org", name="Pending", slug="pending-org")
    context_db.add(pending)
    statements = []

    def reject(*args, **kwargs):
        pytest.fail("Parcel use context must not write or call external services")

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)
        assert statement.lstrip().upper().startswith("SELECT")

    monkeypatch.setattr("socket.create_connection", reject)
    monkeypatch.setattr("socket.socket.connect", reject)
    monkeypatch.setattr(context_db, "flush", reject)
    monkeypatch.setattr(context_db, "commit", reject)
    event.listen(context_db.bind, "before_cursor_execute", capture)
    try:
        result = _context(context_db, parcel)
    finally:
        event.remove(context_db.bind, "before_cursor_execute", capture)
    assert result.recorded_zoning_code == "CS"
    assert result.status == "reported"
    assert parcel.zoning_code == "UNFLUSHED"
    assert pending in context_db.new
    assert len(statements) == 2
    assert all("payload" not in sql and "settings" not in sql for sql in statements)


def test_tenant_switch_cannot_reuse_cached_parcel_or_evidence(context_db):
    parcel, source, raw = _parcel(context_db)
    _fact(context_db, parcel, source, raw)
    assert _context(context_db, parcel).status == "reported"
    token = set_current_context(RequestContext("foreign-org", "foreign-user"))
    try:
        assert get_parcel_use_context(context_db, parcel.id, as_of=NOW) is None
    finally:
        reset_current_context(token)


def test_default_as_of_is_the_server_clock(context_db):
    parcel, _, _ = _parcel(context_db)
    before = datetime.now(timezone.utc)
    result = get_parcel_use_context(context_db, parcel.id)
    after = datetime.now(timezone.utc)
    assert before <= result.as_of <= after


def test_response_schema_rejects_positive_use_and_ai_claims(context_db):
    parcel, _, _ = _parcel(context_db)
    body = _context(context_db, parcel).model_dump()
    for change in ({"potential_uses": ["Retail"]}, {"potential_uses_status": "allowed"}, {"ai_used": True}):
        with pytest.raises(ValidationError):
            ParcelUseContextResponse(**(body | change))
