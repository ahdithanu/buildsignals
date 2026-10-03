import pytest

from app.models.ingestion import PermitRecord
from app.schemas.parcel_reference import PermitParcelCandidates
from app.services.parcel_reference import permit_parcel_candidates
from app.utils.org_scope import RequestContext, reset_current_context, set_current_context
from tests.test_parcel_lineage import _parcel, _raw, _setup


def fixture_records(db):
    source, run, now = _setup(db)
    raw = _raw(db, source, run, "001", "a" * 64, now)
    parcel = _parcel(db, source, raw, "001", now)
    permit = PermitRecord(
        organization_id="default-org", source_id=source.id,
        latest_raw_record_id=raw.id, external_record_id="permit-1",
        normalization_hash="b" * 64, parcel_id="001",
        address=parcel.address, city=parcel.city, state=parcel.state,
    )
    db.add(permit)
    db.flush()
    return source, run, now, parcel, permit


def test_exact_reference_is_evidence_backed_not_automatic_enrichment(db):
    source, _, _, parcel, permit = fixture_records(db)
    result = PermitParcelCandidates.model_validate(permit_parcel_candidates(db, permit.id, source.id))
    assert result.status == "candidate_requires_review"
    candidate = result.candidates[0]
    assert candidate.identity_assessment == "address_corroborated"
    assert candidate.raw_source_record_id == parcel.latest_raw_record_id
    assert candidate.has_valid_coordinates
    assert permit.latitude is None and permit.longitude is None
    assert not db.dirty


def test_reference_never_strips_leading_zeros_and_handles_missing(db):
    source, _, _, _, permit = fixture_records(db)
    permit.parcel_id = "1"
    db.flush()
    assert permit_parcel_candidates(db, permit.id, source.id)["status"] == "no_match"
    permit.parcel_id = None
    db.flush()
    assert permit_parcel_candidates(db, permit.id, source.id)["status"] == "missing_reference"


def test_conflicting_address_and_multiple_parcels_require_review(db):
    source, run, now, parcel, permit = fixture_records(db)
    parcel.state = "OH"
    parcel.address = "200 Different Street"
    db.flush()
    result = permit_parcel_candidates(db, permit.id, source.id)
    assert result["candidates"][0]["identity_assessment"] == "needs_review"
    assert result["candidates"][0]["address_comparison"] == "conflict"
    second = _parcel(db, source, _raw(db, source, run, "002", "c" * 64, now), "002", now)
    second.parcel_group_id = "001"
    db.flush()
    result = permit_parcel_candidates(db, permit.id, source.id)
    assert result["status"] == "ambiguous"
    assert len(result["candidates"]) == 2


def test_tenant_isolation_and_retired_parcels(db):
    source, _, _, parcel, permit = fixture_records(db)
    token = set_current_context(RequestContext("another-org", "user"))
    try:
        with pytest.raises(LookupError):
            permit_parcel_candidates(db, permit.id, source.id)
    finally:
        reset_current_context(token)
    parcel.is_active = False
    db.flush()
    assert permit_parcel_candidates(db, permit.id, source.id)["status"] == "no_match"


def test_parcel_candidates_require_authentication(client):
    response = client.get("/ingestion/permits/missing/parcel-candidates?parcel_source_id=missing")
    assert response.status_code == 401


@pytest.mark.parametrize("field,value", [("state", " "), ("city", None), ("address", "")])
def test_missing_evidence_is_not_a_conflict_or_a_match(db, field, value):
    source, _, _, parcel, permit = fixture_records(db)
    setattr(parcel, field, value)
    db.flush()
    candidate = permit_parcel_candidates(db, permit.id, source.id)["candidates"][0]
    assert candidate["address_comparison"] == "missing"
    assert candidate["identity_assessment"] == "needs_review"


def test_conflict_remains_visible_when_another_field_is_missing(db):
    source, _, _, parcel, permit = fixture_records(db)
    parcel.city = None
    parcel.state = "OH"
    db.flush()
    candidate = permit_parcel_candidates(db, permit.id, source.id)["candidates"][0]
    assert candidate["city_comparison"] == "missing"
    assert candidate["state_comparison"] == "conflict"
    assert candidate["address_comparison"] == "conflict"
