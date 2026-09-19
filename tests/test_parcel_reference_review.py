from uuid import uuid4

import pytest

from app.models.audit_log import AuditLog
from app.models.graph import GraphEntityType, GraphRelationship
from app.models.ingestion import IngestionRun, IngestionSource, RawSourceRecord
from app.models.user import User
from app.schemas.graph import GraphEntityCreate
from app.schemas.parcel_reference import ParcelReferenceAcceptance
from app.services.graph_service import link_entity_to_record, resolve_entity
from app.services.parcel_reference_review import accept_parcel_reference
from app.utils.org_scope import RequestContext, reset_current_context, set_current_context
from tests.test_parcel_reference import fixture_records


def setup_review(db):
    parcels, _, now, parcel, permit = fixture_records(db)
    source = IngestionSource(organization_id="default-org", key="review-permits", name="Review permits",
                             adapter="csv", record_type="permit")
    user = User(email="review@example.test", full_name="Reviewer", password_hash="unused")
    db.add_all([source, user])
    db.flush()
    run = IngestionRun(organization_id="default-org", source_id=source.id, status="completed", trigger="manual")
    db.add(run)
    db.flush()
    raw = RawSourceRecord(organization_id="default-org", source_id=source.id, run_id=run.id,
                          external_record_id="permit-1", record_type="permit", content_hash="e" * 64,
                          payload={"parcel_id": "001"}, received_at=now)
    db.add(raw)
    db.flush()
    permit.source_id = source.id
    permit.latest_raw_record_id = raw.id
    entity, _ = resolve_entity(db, GraphEntityCreate(
        entity_type=GraphEntityType.permit, display_name="Reviewed permit",
        source_system=source.key, source_id=permit.id,
    ))
    link_entity_to_record(db, entity.id, "permit", permit.id, source.key)
    db.flush()
    payload = ParcelReferenceAcceptance(
        parcel_source_id=parcels.id, parcel_id=parcel.id,
        expected_permit_raw_id=raw.id, expected_parcel_raw_id=parcel.latest_raw_record_id,
        confidence=0.9, reason="Reviewed source identifiers and matching site address",
    )
    return permit, parcel, user, payload


def test_acceptance_keeps_both_sources_and_actor_without_copying_coordinates(db):
    permit, parcel, user, payload = setup_review(db)
    link = accept_parcel_reference(db, permit.id, payload, actor_id=user.id)
    assert len(link.evidence) == 2
    assert {e.payload["raw_source_record_id"] for e in link.evidence} == {
        permit.latest_raw_record_id, parcel.latest_raw_record_id,
    }
    assert all(e.payload["actor_id"] == user.id for e in link.evidence)
    assert db.query(AuditLog).filter_by(action="parcel_reference_accepted").one().actor_id == user.id
    assert permit.latitude is None and permit.longitude is None
    assert link.last_verified_at is not None
    same = accept_parcel_reference(db, permit.id, payload, actor_id=user.id)
    assert same.id == link.id
    db.expire(link, ["evidence"])
    assert len(link.evidence) == 4


@pytest.mark.parametrize("change", ["stale", "address", "retired"])
def test_unsafe_acceptance_does_not_write_review(db, change):
    permit, parcel, user, payload = setup_review(db)
    if change == "stale":
        payload.expected_parcel_raw_id = str(uuid4())
    elif change == "address":
        parcel.address = "900 Different Road"
    else:
        parcel.is_active = False
    db.flush()
    before = db.query(GraphRelationship).count()
    with pytest.raises((ValueError, LookupError)):
        accept_parcel_reference(db, permit.id, payload, actor_id=user.id)
    assert db.query(GraphRelationship).count() == before
    assert db.query(AuditLog).filter_by(action="parcel_reference_accepted").count() == 0


def test_acceptance_cannot_cross_tenants(db):
    permit, _, user, payload = setup_review(db)
    token = set_current_context(RequestContext("other-org", user.id))
    try:
        with pytest.raises(LookupError):
            accept_parcel_reference(db, permit.id, payload, actor_id=user.id)
    finally:
        reset_current_context(token)


def test_ambiguous_physical_group_cannot_be_accepted(db):
    from tests.test_parcel_lineage import _parcel, _raw

    permit, parcel, user, payload = setup_review(db)
    raw = parcel.latest_raw_record
    other_raw = _raw(db, parcel.source, raw.run, "unit-2", "f" * 64, raw.received_at)
    other = _parcel(db, parcel.source, other_raw, "unit-2", raw.received_at)
    other.parcel_group_id = parcel.external_parcel_id
    db.flush()
    with pytest.raises(ValueError, match="exactly one"):
        accept_parcel_reference(db, permit.id, payload, actor_id=user.id)
    assert db.query(AuditLog).filter_by(action="parcel_reference_accepted").count() == 0


def test_acceptance_requires_authentication(client):
    response = client.post("/ingestion/permits/missing/parcel-acceptance", json={})
    assert response.status_code == 401


@pytest.mark.parametrize("role,status", [("viewer", 403), ("editor", 200)])
def test_acceptance_endpoint_enforces_role_and_returns_graph_evidence(client, db, role, status):
    from app.main import app
    from app.utils.auth_deps import get_current_user

    permit, _, user, payload = setup_review(db)
    app.dependency_overrides[get_current_user] = lambda: {
        "user": user, "org_id": "default-org", "role": role,
    }
    try:
        response = client.post(f"/ingestion/permits/{permit.id}/parcel-acceptance", json=payload.model_dump())
        assert response.status_code == status, response.text
        if status == 200:
            assert len(response.json()["evidence"]) == 2
            assert response.headers["cache-control"] == "no-store"
        else:
            assert db.query(AuditLog).filter_by(action="parcel_reference_accepted").count() == 0
    finally:
        app.dependency_overrides.pop(get_current_user, None)
