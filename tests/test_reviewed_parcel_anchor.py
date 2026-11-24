"""Synthetic boundary proofs only; these fixtures are not real parcel inventory."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event, update

from app.models.audit_log import AuditLog
from app.models.brand import BrandProfile, PermitBrandMatch
from app.models.deal import Deal
from app.models.graph import GraphRelationship, GraphRelationshipEvidence
from app.models.ingestion import PermitRecord, RawSourceRecord
from app.models.parcel import NearbyParcelSearch, ParcelRecord
from app.services.parcel_anchor import get_deal_parcel_anchor
from app.services.parcel_reference_review import accept_parcel_reference
from app.services.parcel_service import (
    create_nearby_parcel_search,
    maybe_create_default_nearby_parcel_search,
)
from app.utils.org_scope import RequestContext, reset_current_context, set_current_context
from tests.test_parcel_reference_review import setup_review


@pytest.fixture
def anchor_records(db):
    permit, parcel, user, payload = setup_review(db)
    permit.approval_stage = "pre_approval"
    parcel.normalization_hash = "c" * 64
    brand = BrandProfile(key="synthetic-retail", name="Synthetic Retail", normalized_name="synthetic retail")
    deal = Deal(name="Synthetic anchor boundary", address=permit.address, city=permit.city, state=permit.state)
    db.add_all([brand, deal])
    db.flush()
    match = PermitBrandMatch(
        permit_id=permit.id, brand_id=brand.id, first_raw_record_id=permit.latest_raw_record_id,
        latest_raw_record_id=permit.latest_raw_record_id, review_status="confirmed", confidence=0.95,
        matched_alias="Synthetic Retail", matched_field="description", excerpt="Synthetic only",
        detector_version="synthetic-v1",
    )
    db.add(match)
    db.flush()
    relationship = accept_parcel_reference(db, permit.id, payload, actor_id=user.id)
    db.flush()
    assert get_deal_parcel_anchor(db, deal.id, match.id)["status"] == "ready"
    return deal, match, permit, parcel, relationship


def preview(db, records):
    deal, match, *_ = records
    return get_deal_parcel_anchor(db, deal.id, match.id)


def search(db, records, **kwargs):
    deal, match, *_ = records
    return create_nearby_parcel_search(
        db, deal_id=deal.id, anchor_brand_match_id=match.id, radius_miles=0.25,
        persona="developer", minimum_land_area_sq_ft=None, zoning_codes=[], land_uses=[], limit=50,
        **kwargs,
    )


def test_reviewed_preview_and_explicit_search_preserve_coordinates_and_snapshots(db, anchor_records):
    deal, match, permit, parcel, relationship = anchor_records
    before = (permit.latitude, permit.longitude, permit.normalization_hash, permit.latest_raw_record_id)
    resolved = preview(db, anchor_records)
    assert resolved == {
        "deal_id": deal.id, "anchor_brand_match_id": match.id, "permit_id": permit.id,
        "status": "ready", "reason": None, "latitude": parcel.latitude, "longitude": parcel.longitude,
        "method": "reviewed_parcel_centroid", "parcel_id": parcel.id, "relationship_id": relationship.id,
        "permit_raw_record_id": permit.latest_raw_record_id, "parcel_raw_record_id": parcel.latest_raw_record_id,
        "permit_normalization_hash": permit.normalization_hash,
        "parcel_normalization_hash": parcel.normalization_hash,
    }
    with pytest.raises(ValueError, match="preview"):
        search(db, anchor_records)
    assert db.query(NearbyParcelSearch).count() == 0
    saved = search(db, anchor_records, expected_anchor=resolved)
    assert (saved.anchor_latitude, saved.anchor_longitude) == (parcel.latitude, parcel.longitude)
    assert saved.filters["anchor_resolution"] == resolved
    assert saved.candidates[0].explanation["anchor_resolution"] == resolved
    assert (permit.latitude, permit.longitude, permit.normalization_hash, permit.latest_raw_record_id) == before
    old_filters = json.dumps(saved.filters, sort_keys=True)
    parcel.latitude += 0.001
    db.flush()
    assert json.dumps(saved.filters, sort_keys=True) == old_filters
    assert saved.anchor_latitude == resolved["latitude"]
    with pytest.raises(ValueError, match="changed"):
        search(db, anchor_records, expected_anchor=resolved)
    assert db.query(NearbyParcelSearch).count() == 1


def test_native_precedence_and_backward_compatible_search(db, anchor_records):
    _, _, permit, parcel, relationship = anchor_records
    permit.latitude, permit.longitude = parcel.latitude + 0.001, parcel.longitude
    relationship.is_current = False
    db.flush()
    resolved = preview(db, anchor_records)
    assert resolved["method"] == "source_coordinate"
    assert resolved["parcel_id"] is None and resolved["relationship_id"] is None
    saved = search(db, anchor_records)
    assert saved.anchor_latitude == permit.latitude
    assert "anchor_resolution" not in saved.filters
    assert all("anchor_resolution" not in row.explanation for row in saved.candidates)


@pytest.mark.parametrize("latitude,longitude", [(30, None), (None, -97), (float("inf"), -97),
                                                   (30, float("-inf")), (91, -97), (30, 181)])
def test_invalid_or_partial_native_pair_never_falls_back(db, anchor_records, latitude, longitude):
    permit = anchor_records[2]
    permit.latitude, permit.longitude = latitude, longitude
    db.flush()
    assert preview(db, anchor_records)["status"] == "unavailable"
    with pytest.raises(ValueError):
        search(db, anchor_records)


@pytest.mark.parametrize("change", ["audit_missing", "audit_actor", "audit_review", "audit_hash",
    "evidence_review", "evidence_actor", "evidence_raw", "evidence_hash", "expired", "not_current",
    "permit_hash", "parcel_hash", "retired", "address", "source_inactive", "raw_scope", "typed"])
def test_reviewed_anchor_fails_closed(db, anchor_records, change):
    _, _, permit, parcel, relationship = anchor_records
    audit = db.query(AuditLog).filter_by(action="parcel_reference_accepted").one()
    evidence = db.query(GraphRelationshipEvidence).filter_by(relationship_id=relationship.id).first()
    if change == "audit_missing":
        db.delete(audit)
    elif change.startswith("audit_"):
        values = json.loads(audit.new_values)
        if change == "audit_actor":
            audit.actor_id = None
        else:
            values["review_id" if change == "audit_review" else "parcel_normalization_hash"] = "spoofed"
            audit.new_values = json.dumps(values)
    elif change.startswith("evidence_"):
        field = {"evidence_review": "review_id", "evidence_actor": "actor_id",
                 "evidence_raw": "raw_source_record_id", "evidence_hash": "parcel_normalization_hash"}[change]
        evidence.payload = {**evidence.payload, field: "spoofed"}
    elif change == "expired":
        relationship.verification_due_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    elif change == "not_current":
        relationship.is_current = False
    elif change == "permit_hash":
        permit.normalization_hash = "changed"
    elif change == "parcel_hash":
        parcel.normalization_hash = "changed"
    elif change == "retired":
        parcel.is_active = False
    elif change == "address":
        parcel.address = "Different Street"
    elif change == "source_inactive":
        parcel.source.is_active = False
    elif change == "raw_scope":
        raw = RawSourceRecord(
            organization_id="other-org", source_id=parcel.source_id,
            run_id=parcel.latest_raw_record.run_id, external_record_id=parcel.external_parcel_id,
            record_type="parcel", content_hash="f" * 64, payload={"synthetic": True},
        )
        db.add(raw)
        db.flush()
        parcel.latest_raw_record_id = raw.id
    else:
        relationship.target_entity.entity_type = "property"
    db.flush()
    resolved = preview(db, anchor_records)
    assert resolved["status"] == "unavailable"
    assert resolved["latitude"] is None and resolved["longitude"] is None
    with pytest.raises(ValueError):
        search(db, anchor_records, expected_anchor=resolved)
    assert db.query(NearbyParcelSearch).count() == 0


@pytest.mark.parametrize("field", ["latitude", "method", "parcel_id", "relationship_id",
                                  "permit_raw_record_id", "parcel_normalization_hash"])
def test_preview_binding_is_complete(db, anchor_records, field):
    expected = preview(db, anchor_records)
    expected[field] = "tampered"
    with pytest.raises(ValueError, match="changed"):
        search(db, anchor_records, expected_anchor=expected)
    assert db.query(NearbyParcelSearch).count() == 0


def test_tenant_and_deal_scope_and_brand_eligibility(db, anchor_records):
    deal, match, permit, _, _ = anchor_records
    token = set_current_context(RequestContext("other-org", "synthetic-user"))
    try:
        with pytest.raises(LookupError):
            preview(db, anchor_records)
    finally:
        reset_current_context(token)
    deal.address = "Unrelated Street"
    db.flush()
    with pytest.raises(LookupError):
        preview(db, anchor_records)
    deal.address = permit.address
    match.review_status = "candidate"
    permit.approval_stage = "approved"
    db.flush()
    assert preview(db, anchor_records)["status"] == "unavailable"
    permit.approval_stage = "pre_approval"
    db.flush()
    assert preview(db, anchor_records)["status"] == "ready"


@pytest.mark.parametrize("missing", ["deal", "match", "permit"])
def test_unknown_scope_raises_lookup_error_not_an_invalid_preview(db, anchor_records, missing):
    deal, match, permit, *_ = anchor_records
    if missing == "deal":
        deal_id, match_id = "missing", match.id
    elif missing == "match":
        deal_id, match_id = deal.id, "missing"
    else:
        permit.organization_id = "other-org"
        db.flush()
        deal_id, match_id = deal.id, match.id
    with pytest.raises(LookupError):
        get_deal_parcel_anchor(db, deal_id, match_id)


def test_default_seeding_does_not_use_reviewed_fallback(db, anchor_records):
    deal, match, *_ = anchor_records
    assert preview(db, anchor_records)["status"] == "ready"
    assert maybe_create_default_nearby_parcel_search(
        db, deal_id=deal.id, anchor_brand_match_id=match.id,
    ) is None
    assert db.query(NearbyParcelSearch).count() == 0


def test_revalidation_refreshes_stale_identity_map_and_failure_is_rollback_safe(db, anchor_records):
    expected = preview(db, anchor_records)
    parcel = anchor_records[3]
    db.execute(update(ParcelRecord).where(ParcelRecord.id == parcel.id).values(
        normalization_hash="concurrent-change"), execution_options={"synchronize_session": False})
    with db.begin_nested():
        with pytest.raises(ValueError, match="changed|unavailable"):
            search(db, anchor_records, expected_anchor=expected)
    assert parcel.normalization_hash == "concurrent-change"
    assert db.query(NearbyParcelSearch).count() == 0
    assert db.is_active


def test_reviewed_search_locks_permit_then_parcel_then_relationship(db, anchor_records):
    expected = preview(db, anchor_records)
    locks = []

    def capture(state):
        statement = state.statement
        if getattr(statement, "_for_update_arg", None) is not None:
            if len(locks) < 4:
                assert len(statement.column_descriptions) == 1
                assert statement.column_descriptions[0]["name"] == "id"
                assert len(str(statement).encode("utf-8")) < 1023
            locks.append(statement.column_descriptions[0]["entity"])

    event.listen(db, "do_orm_execute", capture)
    try:
        search(db, anchor_records, expected_anchor=expected)
    finally:
        event.remove(db, "do_orm_execute", capture)
    assert locks[:4] == [PermitRecord, PermitBrandMatch, ParcelRecord, GraphRelationship]


def test_distinct_review_ids_cannot_be_combined(db, anchor_records):
    relationship = anchor_records[4]
    evidence = db.query(GraphRelationshipEvidence).filter_by(relationship_id=relationship.id).all()
    parcel_row = next(row for row in evidence if row.payload["record_type"] == "parcel")
    original = parcel_row.payload
    new_review = "synthetic-second-review"
    values = {key: value for key, value in original.items() if key not in {"raw_source_record_id", "record_type"}}
    values["review_id"] = new_review
    parcel_row.payload = {**original, "review_id": new_review}
    parcel_row.source_id = f"{new_review}:{original['raw_source_record_id']}"
    db.add(AuditLog(
        entity_type="graph_relationship", entity_id=relationship.id, action="parcel_reference_accepted",
        actor_id=original["actor_id"], new_values=json.dumps(values),
    ))
    db.flush()
    assert preview(db, anchor_records)["status"] == "unavailable"


def test_multiple_current_reviewed_relationships_are_ambiguous(db, anchor_records):
    relationship = anchor_records[4]
    db.add(GraphRelationship(
        source_entity_id=relationship.source_entity_id, target_entity_id=relationship.target_entity_id,
        relationship_type=relationship.relationship_type, source_system=relationship.source_system,
        source_id="synthetic-spoofed-review", is_current=True,
    ))
    db.flush()
    assert preview(db, anchor_records)["status"] == "unavailable"


@pytest.mark.parametrize("overflow", ["evidence", "audit"])
def test_review_query_bounds_fail_closed(db, anchor_records, overflow):
    relationship = anchor_records[4]
    for index in range(65 if overflow == "evidence" else 33):
        if overflow == "evidence":
            db.add(GraphRelationshipEvidence(
                relationship_id=relationship.id, source_system="synthetic", source_id=f"extra-{index}",
                payload={},
            ))
        else:
            db.add(AuditLog(entity_type="graph_relationship", entity_id=relationship.id,
                            action="parcel_reference_accepted", new_values="{}"))
    db.flush()
    statements = []

    def capture(state):
        statements.append(str(state.statement))

    event.listen(db, "do_orm_execute", capture)
    try:
        assert preview(db, anchor_records)["status"] == "unavailable"
    finally:
        event.remove(db, "do_orm_execute", capture)
    for table in ("graph_relationship_evidence", "audit_logs"):
        queries = [sql for sql in statements if f"FROM {table}" in sql]
        assert queries and all("LIMIT" in sql for sql in queries)


def test_evidence_change_after_locks_is_revalidated(db, anchor_records, monkeypatch):
    from app.services import parcel_anchor

    expected = preview(db, anchor_records)
    original = parcel_anchor.get_deal_parcel_anchor
    calls = 0

    def change_on_revalidation(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            db.execute(update(GraphRelationship).where(GraphRelationship.id == anchor_records[4].id).values(
                is_current=False), execution_options={"synchronize_session": False})
        return original(*args, **kwargs)

    monkeypatch.setattr(parcel_anchor, "get_deal_parcel_anchor", change_on_revalidation)
    with pytest.raises(ValueError, match="changed"):
        search(db, anchor_records, expected_anchor=expected)
    assert calls == 2
    assert db.query(NearbyParcelSearch).count() == 0


def test_stale_cached_permit_address_cannot_authorize_an_unlinked_deal(db, anchor_records):
    permit = anchor_records[2]
    db.execute(update(PermitRecord).where(PermitRecord.id == permit.id).values(
        address="Different canonical street"), execution_options={"synchronize_session": False})
    with pytest.raises(LookupError):
        preview(db, anchor_records)


def test_actual_preview_route_returns_valid_known_preview_and_404_for_unknown_scope(client, db, anchor_records):
    from app.main import app
    from app.utils.auth_deps import get_current_user

    deal, match, *_ = anchor_records
    expected = preview(db, anchor_records)
    db.commit()
    app.dependency_overrides[get_current_user] = lambda: {"org_id": "default-org", "role": "viewer"}
    try:
        response = client.get(f"/deals/{deal.id}/nearby-parcel-anchors/{match.id}")
        assert response.status_code == 200, response.text
        assert response.json() == expected
        assert response.headers["cache-control"] == "no-store"
        for deal_id, match_id in (("missing", match.id), (deal.id, "missing")):
            missing = client.get(f"/deals/{deal_id}/nearby-parcel-anchors/{match_id}")
            assert missing.status_code == 404
            assert missing.headers["cache-control"] == "no-store"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_census_estimate_is_never_used_as_a_discovery_anchor(db, anchor_records):
    from app.models.permit_geocode import PermitGeocode

    permit, relationship = anchor_records[2], anchor_records[4]
    relationship.is_current = False
    db.add(PermitGeocode(
        permit_id=permit.id, latitude=30.2672, longitude=-97.7431, address_hash="a" * 64,
        response_hash="b" * 64, matched_address="Synthetic range estimate", benchmark="synthetic",
        source_url="https://example.invalid/census",
    ))
    db.flush()
    assert preview(db, anchor_records)["status"] == "unavailable"


def test_nonfinite_nan_is_not_a_valid_native_coordinate_pair():
    from app.services.parcel_anchor import _coordinates

    assert not _coordinates(float("nan"), -97.7)
    assert not _coordinates(30.2, float("nan"))


def test_preview_executes_only_reads_without_locks_or_business_mutations(db, anchor_records):
    statements = []
    connection = db.connection()

    def capture(_conn, _cursor, sql, _params, _context, _many):
        statements.append(sql)

    event.listen(connection, "before_cursor_execute", capture)
    try:
        assert preview(db, anchor_records)["status"] == "ready"
    finally:
        event.remove(connection, "before_cursor_execute", capture)
    assert statements and all(sql.lstrip().upper().startswith("SELECT") for sql in statements)
    assert all("FOR UPDATE" not in sql.upper() for sql in statements)
    assert not db.new and not db.dirty and not db.deleted


@pytest.mark.parametrize("age", ["expired", "future", "missing"])
def test_acceptance_audit_clock_cannot_be_refreshed_by_generic_graph_upsert(db, anchor_records, age):
    from app.schemas.graph import GraphEvidenceCreate, GraphRelationshipCreate
    from app.services.graph_service import create_relationship

    relationship = anchor_records[4]
    audit = db.query(AuditLog).filter_by(action="parcel_reference_accepted").one()
    now = datetime.now(timezone.utc)
    if age == "missing":
        db.delete(audit)
    else:
        audit.created_at = {"expired": now - timedelta(days=91), "future": now + timedelta(days=1)}[age]
    relationship.verification_due_at = now - timedelta(seconds=1)
    db.flush()
    refreshed = create_relationship(db, GraphRelationshipCreate(
        source_entity_id=relationship.source_entity_id, target_entity_id=relationship.target_entity_id,
        relationship_type=relationship.relationship_type, source_system=relationship.source_system,
        source_id=relationship.source_id,
        evidence=[GraphEvidenceCreate(source_system="synthetic-generic", source_id="generic-refresh", payload={})],
    ))
    db.flush()
    assert refreshed.verification_due_at.replace(tzinfo=timezone.utc) > now
    assert preview(db, anchor_records)["status"] == "unavailable"


@pytest.mark.parametrize("oversized", ["evidence", "audit"])
def test_oversized_review_content_is_rejected_from_database_metadata_before_body_fetch(db, anchor_records, oversized):
    relationship = anchor_records[4]
    if oversized == "evidence":
        row = db.query(GraphRelationshipEvidence).filter_by(relationship_id=relationship.id).first()
        row.payload = {**row.payload, "padding": "x" * 17000}
    else:
        row = db.query(AuditLog).filter_by(action="parcel_reference_accepted").one()
        row.new_values = json.dumps({**json.loads(row.new_values), "padding": "x" * 17000})
    db.flush()
    statements = []
    connection = db.connection()

    def capture(_conn, _cursor, sql, _params, _context, _many):
        statements.append(sql)

    event.listen(connection, "before_cursor_execute", capture)
    try:
        assert preview(db, anchor_records)["status"] == "unavailable"
    finally:
        event.remove(connection, "before_cursor_execute", capture)
    for table, column in (("graph_relationship_evidence", "payload"), ("audit_logs", "new_values")):
        queries = [sql for sql in statements if f"FROM {table}" in sql]
        assert queries and all("length(" in sql for sql in queries)
        assert all(f"AS {table}_{column}" not in sql for sql in queries)


def test_dismissal_between_preview_and_final_read_rejects_without_snapshots(db, anchor_records, monkeypatch):
    from app.services import parcel_anchor

    expected = preview(db, anchor_records)
    original = parcel_anchor.get_deal_parcel_anchor
    calls = 0

    def dismiss_on_revalidation(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            db.execute(update(PermitBrandMatch).where(PermitBrandMatch.id == anchor_records[1].id).values(
                review_status="dismissed"), execution_options={"synchronize_session": False})
        return original(*args, **kwargs)

    monkeypatch.setattr(parcel_anchor, "get_deal_parcel_anchor", dismiss_on_revalidation)
    with pytest.raises(ValueError, match="changed"):
        search(db, anchor_records, expected_anchor=expected)
    assert db.query(NearbyParcelSearch).count() == 0
