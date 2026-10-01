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
        parcels=1,
        geocoded_parcels=0,
        saved_searches=0,
        has_geocoded_signals=True,
        has_geocoded_parcels=False,
        has_saved_searches=False,
        ready_for_ranked_map=False,
    )
    permit.is_active = False
    parcel.is_active = False
    db.flush()
    assert map_readiness(db) == dict(
        permits=0,
        geocoded_permits=0,
        parcels=0,
        geocoded_parcels=0,
        saved_searches=0,
        has_geocoded_signals=False,
        has_geocoded_parcels=False,
        has_saved_searches=False,
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
