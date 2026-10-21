from app.models.deal import Deal
from app.models.parcel import NearbyParcelCandidate, NearbyParcelSearch, ParcelFact
from app.models.planning import PlanningRecord
from app.services.map_readiness import map_readiness
from app.utils.org_scope import RequestContext, reset_current_context, set_current_context
from tests.test_parcel_reference import fixture_records


def test_inventory_coordinates_and_retirement(db):
    _, _, _, parcel, permit = fixture_records(db)
    permit.latitude, permit.longitude = 40, -83
    parcel.latitude, parcel.longitude = 91, -83
    db.flush()
    result = map_readiness(db)
    assert result == dict(
        permits=1,
        geocoded_permits=1,
        planning_records=0,
        geocoded_planning_records=0,
        signals=1,
        geocoded_signals=1,
        parcels=1,
        geocoded_parcels=0,
        saved_searches=0,
        nearby_candidate_parcels=0,
        verified_available_parcels=0,
        nearby_verified_available_parcels=0,
        has_geocoded_signals=True,
        has_geocoded_parcels=False,
        has_saved_searches=False,
        discovery_stage="parcel_records_not_geocoded",
        discovery_next_action="Ingest geocoded parcel records for the target jurisdictions.",
        ready_for_ranked_map=False,
    )
    permit.is_active = False
    parcel.is_active = False
    db.flush()
    assert map_readiness(db) == dict(
        permits=0,
        geocoded_permits=0,
        planning_records=0,
        geocoded_planning_records=0,
        signals=0,
        geocoded_signals=0,
        parcels=0,
        geocoded_parcels=0,
        saved_searches=0,
        nearby_candidate_parcels=0,
        verified_available_parcels=0,
        nearby_verified_available_parcels=0,
        has_geocoded_signals=False,
        has_geocoded_parcels=False,
        has_saved_searches=False,
        discovery_stage="signals_not_geocoded",
        discovery_next_action="Ingest or geocode permit and planning signals.",
        ready_for_ranked_map=False,
    )


def test_inventory_is_tenant_scoped(db):
    fixture_records(db)
    token = set_current_context(RequestContext('other-org', 'user'))
    try:
        assert map_readiness(db)["ready_for_ranked_map"] is False
        assert map_readiness(db)["permits"] == 0
        assert map_readiness(db)["parcels"] == 0
    finally:
        reset_current_context(token)


def test_inventory_requires_authentication(client):
    assert client.get('/acquisition-map/readiness').status_code == 401


def test_planning_records_count_as_early_geocoded_signals(db):
    source, _, _, parcel, permit = fixture_records(db)
    permit.is_active = False
    planning = PlanningRecord(
        organization_id="default-org",
        source_id=source.id,
        latest_raw_record_id=parcel.latest_raw_record_id,
        external_record_id="planning-1",
        normalization_hash="c" * 64,
        event_type="agenda_item",
        title="Retail site plan",
        latitude=39.96,
        longitude=-82.99,
    )
    db.add(planning)
    db.flush()

    result = map_readiness(db)

    assert result["permits"] == 0
    assert result["planning_records"] == 1
    assert result["signals"] == 1
    assert result["geocoded_signals"] == 1
    assert result["has_geocoded_signals"] is True


def test_readiness_distinguishes_nearby_candidates_from_verified_availability(db):
    _source, _run, now, parcel, permit = fixture_records(db)
    permit.latitude, permit.longitude = 39.96, -82.99
    parcel.latitude, parcel.longitude = 39.96, -82.99
    deal = Deal(organization_id="default-org", name="Readiness test deal")
    db.add(deal)
    db.flush()
    search = NearbyParcelSearch(
        organization_id="default-org",
        deal_id=deal.id,
        anchor_permit_id=permit.id,
        anchor_latitude=39.96,
        anchor_longitude=-82.99,
        radius_miles=2,
        persona="developer",
        result_limit=25,
        as_of=now,
        ranker_version="developer-v1",
    )
    db.add(search)
    db.flush()
    db.add(NearbyParcelCandidate(
        organization_id="default-org",
        search_id=search.id,
        parcel_id=parcel.id,
        rank=1,
        distance_miles=0.4,
        score=80,
        score_confidence=0.9,
        explanation={},
        ranker_version="developer-v1",
    ))
    db.flush()

    result = map_readiness(db)
    assert result["nearby_candidate_parcels"] == 1
    assert result["verified_available_parcels"] == 0
    assert result["nearby_verified_available_parcels"] == 0
    assert result["discovery_stage"] == "candidates_need_availability_evidence"

    db.add(ParcelFact(
        organization_id="default-org",
        parcel_id=parcel.id,
        raw_source_record_id=parcel.latest_raw_record_id,
        fact_type="availability",
        value={"status": "for_sale", "evidence_type": "listing"},
        source_system="listing",
        source_url="https://broker.example/listing/P-1",
        excerpt="For sale",
        confidence=0.9,
        observed_at=now,
        last_verified_at=now,
        valid_from=now,
        is_current=True,
    ))
    db.flush()
    result = map_readiness(db)
    assert result["verified_available_parcels"] == 1
    assert result["nearby_verified_available_parcels"] == 1
    assert result["discovery_stage"] == "verified_available_candidates"
