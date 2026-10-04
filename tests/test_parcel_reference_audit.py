from uuid import uuid4

import pytest

from app.models.ingestion import IngestionSource, PermitRecord
from app.schemas.parcel_reference import ParcelReferenceAudit
from app.services.parcel_reference import audit_parcel_references
from app.utils.org_scope import RequestContext, reset_current_context, set_current_context
from tests.test_parcel_lineage import _parcel, _raw
from tests.test_parcel_reference import fixture_records


def setup_audit(db):
    parcel_source, _, _, parcel, permit = fixture_records(db)
    source = IngestionSource(
        organization_id="default-org", key="audit-permits", name="Audit permits",
        adapter="csv", record_type="permit",
    )
    db.add(source)
    db.flush()
    permit.source_id = source.id
    db.flush()
    return source, parcel_source, parcel, permit


def test_audit_counts_are_paginated_and_evidence_backed(db):
    source, parcels, _, permit = setup_audit(db)
    for ref in (None, "unmatched"):
        db.add(PermitRecord(
            id=str(uuid4()), organization_id="default-org", source_id=source.id,
            external_record_id=str(uuid4()), normalization_hash="a" * 64,
            latest_raw_record_id=permit.latest_raw_record_id, parcel_id=ref,
        ))
    db.flush()
    all_items = []
    cursor = None
    while True:
        result = ParcelReferenceAudit.model_validate(audit_parcel_references(
            db, source.id, parcels.id, limit=1, after_id=cursor,
        ))
        assert result.evaluated_permits == sum(result.counts.values()) == 1
        assert result.coverage_verified is False
        all_items.extend(result.items)
        if not result.has_more:
            assert result.next_after_id is None
            break
        assert result.next_after_id != cursor
        cursor = result.next_after_id
    assert sorted(item.category for item in all_items) == [
        "address_corroborated", "missing_reference", "no_match",
    ]
    assert len({item.result.permit_id for item in all_items}) == 3


def test_absent_parcel_evidence_is_not_zero_match_rate(db):
    source, parcels, parcel, _ = setup_audit(db)
    parcel.is_active = False
    db.flush()
    result = audit_parcel_references(db, source.id, parcels.id)
    assert result["status"] == "parcel_evidence_unavailable"
    assert result["evaluated_permits"] == sum(result["counts"].values()) == 0
    assert result["items"] == []


def test_conflict_and_missing_address_are_separate_buckets(db):
    source, parcels, parcel, _ = setup_audit(db)
    parcel.address = None
    db.flush()
    assert audit_parcel_references(db, source.id, parcels.id)["counts"]["missing_address_evidence"] == 1
    parcel.state = "OH"
    db.flush()
    assert audit_parcel_references(db, source.id, parcels.id)["counts"]["conflicting_address"] == 1


def test_audit_is_tenant_scoped_and_bounded(db):
    source, parcels, _, _ = setup_audit(db)
    with pytest.raises(ValueError):
        audit_parcel_references(db, source.id, parcels.id, limit=101)
    token = set_current_context(RequestContext("other-org", "user"))
    try:
        with pytest.raises(LookupError):
            audit_parcel_references(db, source.id, parcels.id)
    finally:
        reset_current_context(token)


def test_audit_requires_authentication(client):
    response = client.get("/ingestion/sources/missing/parcel-reference-audit?parcel_source_id=missing")
    assert response.status_code == 401


def test_multiple_matching_units_are_counted_once_as_ambiguous(db):
    source, parcels, parcel, _ = setup_audit(db)
    raw = parcel.latest_raw_record
    second_raw = _raw(db, parcels, raw.run, "002", "c" * 64, raw.received_at)
    second = _parcel(db, parcels, second_raw, "002", raw.received_at)
    second.parcel_group_id = "001"
    db.flush()
    result = audit_parcel_references(db, source.id, parcels.id)
    assert result["counts"]["ambiguous"] == 1
    assert sum(result["counts"].values()) == 1


def test_wrong_source_evidence_does_not_enable_measurement(db):
    source, parcels, parcel, _ = setup_audit(db)
    original = parcel.latest_raw_record
    wrong_source_raw = _raw(db, source, original.run, "wrong-source", "d" * 64, original.received_at)
    parcel.latest_raw_record_id = wrong_source_raw.id
    db.flush()
    result = audit_parcel_references(db, source.id, parcels.id)
    assert result["status"] == "parcel_evidence_unavailable"
