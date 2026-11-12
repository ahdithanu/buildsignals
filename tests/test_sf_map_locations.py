"""Offline acceptance of derived SF map locations, not provider availability."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.encoders import jsonable_encoder
from sqlalchemy import case, create_mock_engine, func, or_
from sqlalchemy.orm import Session

from app import config
from app.models.ingestion import PermitRecord
from app.models.organization import Organization
from app.models.organization_membership import MemberRole, OrganizationMembership
from app.models.permit_geocode import PermitGeocode
from app.models.planning import PlanningRecord
from app.models.user import User
from app.services import sf_geocoding as geo
from app.services.demo_access import demo_read_only
from app.services.map_readiness import map_readiness
from app.services.map_signals import list_map_signals, permit_location_query
from app.services.security import create_access_token
from app.utils.org_scope import RequestContext, reset_current_context, set_current_context
from tests.test_parcel_reference import fixture_records


@pytest.fixture
def sf_location(db, monkeypatch):
    monkeypatch.setattr(config, 'SF_DERIVED_LOCATIONS_ENABLED', True)
    source, _, _, _, permit = fixture_records(db)
    source.key, source.base_url, source.record_type = geo.SOURCE_KEY, geo.SOURCE_URL, 'permit'
    permit.address, permit.city = '100 MARKET ST', 'San Francisco'
    permit.state, permit.postal_code = 'CA', '94103'
    permit.source_url = 'https://data.sf.gov/d/i98e-djp9'
    db.flush()
    _save_estimate(db, permit, source)
    return source, permit, db.query(PermitGeocode).one()


def _save_estimate(db, permit, source):
    response = {'result': {'addressMatches': [{
        'matchedAddress': f'{permit.address}, SAN FRANCISCO, CA, 94103',
        'addressComponents': {'city': 'SAN FRANCISCO', 'state': 'CA', 'zip': '94103'},
        'coordinates': {'x': -122.4, 'y': 37.79},
    }]}}
    assert geo.save_match(db, permit, response, geo.request_url(permit, source))
    db.flush()


def _additional_permit(db, source, original, identity):
    permit = PermitRecord(
        id=identity, organization_id=original.organization_id, source_id=source.id,
        latest_raw_record_id=original.latest_raw_record_id, external_record_id=identity,
        normalization_hash='c' * 64, address='100 MARKET ST', city='San Francisco',
        state='CA', postal_code='94103',
    )
    db.add(permit)
    db.flush()
    _save_estimate(db, permit, source)
    return permit


def test_current_estimate_is_explicit_private_and_not_source_coordinate(db, sf_location):
    _, permit, geocode = sf_location
    result = list_map_signals(db, state='ca')
    assert len(result['items']) == 1
    item = result['items'][0]
    assert item['id'] == permit.id
    assert item['location_method'] == 'census_address_range_estimate'
    assert (item['latitude'], item['longitude']) == (37.79, -122.4)
    assert item['source_url'] == permit.source_url
    assert (permit.latitude, permit.longitude) == (None, None)
    assert not {'matched_address', 'benchmark', 'address_hash', 'response_hash',
                'geocoder_url', 'observed_at'} & item.keys()
    payload = str(jsonable_encoder(result))
    assert geo.GEOCODER_URL not in payload
    assert geocode.matched_address not in payload
    assert geocode.response_hash not in payload
    readiness = map_readiness(db)
    assert readiness['source_geocoded_permits'] == 0
    assert readiness['derived_geocoded_permits'] == readiness['geocoded_permits'] == 1
    assert readiness['geocoded_signals'] == len(result['items'])


def test_flag_off_ignores_estimates_and_does_not_join_tables(db, sf_location, monkeypatch):
    monkeypatch.setattr(config, 'SF_DERIVED_LOCATIONS_ENABLED', False)
    query, _, _ = permit_location_query(db)
    sql = str(query.statement)
    assert 'permit_geocodes' not in sql and 'ingestion_sources' not in sql
    assert list_map_signals(db)['items'] == []
    readiness = map_readiness(db)
    assert readiness['permits'] == 1
    assert readiness['source_geocoded_permits'] == readiness['derived_geocoded_permits'] == 0
    assert readiness['has_geocoded_signals'] is False


def test_customer_route_returns_location_method_without_geocoder_details(client, db, sf_location):
    _, permit, geocode = sf_location
    db.add(User(id='map-customer', email='map-customer@example.com', full_name='Map customer',
                password_hash='!nologin', is_active=True))
    db.add(OrganizationMembership(organization_id=permit.organization_id, user_id='map-customer',
                                  role=MemberRole.viewer, is_default=True))
    db.commit()
    headers = {'Authorization': 'Bearer ' + create_access_token(
        user_id='map-customer', org_id=permit.organization_id,
    )}
    response = client.get('/v1/acquisition-map/signals', headers=headers)
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    assert response.json()['items'][0]['location_method'] == 'census_address_range_estimate'
    for private in (geo.GEOCODER_URL, geocode.matched_address, geocode.response_hash,
                    geocode.address_hash, geocode.benchmark):
        assert private not in response.text
    readiness = client.get('/v1/acquisition-map/readiness', headers=headers)
    assert readiness.status_code == 200
    assert readiness.json()['derived_geocoded_permits'] == 1


def test_native_non_sf_and_planning_locations_remain_available(db, sf_location):
    source, derived, _ = sf_location
    native = _additional_permit(db, source, derived, 'native-permit')
    native.latitude, native.longitude = 40, -83
    native.city, native.state = 'Columbus', 'OH'
    db.add(PlanningRecord(
        organization_id=derived.organization_id, source_id=source.id,
        latest_raw_record_id=derived.latest_raw_record_id,
        external_record_id='native-planning', normalization_hash='d' * 64,
        title='Planning hearing', event_type='hearing', latitude=40.1, longitude=-83, state='OH',
    ))
    db.flush()
    items = list_map_signals(db)['items']
    assert len(items) == 3
    assert sum(item['location_method'] == 'source_coordinate' for item in items) == 2
    assert len(list_map_signals(db, state='OH')['items']) == 2
    readiness = map_readiness(db)
    assert readiness['source_geocoded_permits'] == readiness['derived_geocoded_permits'] == 1
    assert readiness['geocoded_permits'] == 2
    assert readiness['geocoded_planning_records'] == 1
    assert readiness['geocoded_signals'] == len(items)


@pytest.mark.parametrize('latitude,longitude', [
    (37.78, None), (None, -122.41), (86, -122.41), (37.78, 181),
])
def test_partial_or_invalid_native_coordinates_never_fall_back(db, sf_location, latitude, longitude):
    _, permit, _ = sf_location
    permit.latitude, permit.longitude = latitude, longitude
    db.flush()
    assert list_map_signals(db)['items'] == []
    assert map_readiness(db)['geocoded_permits'] == 0


def test_valid_native_coordinates_win_without_double_counting(db, sf_location):
    _, permit, _ = sf_location
    permit.latitude, permit.longitude = 37.78, -122.41
    db.flush()
    items = list_map_signals(db)['items']
    assert len(items) == 1
    assert items[0]['location_method'] == 'source_coordinate'
    assert (items[0]['latitude'], items[0]['longitude']) == (37.78, -122.41)
    readiness = map_readiness(db)
    assert readiness['source_geocoded_permits'] == readiness['geocoded_permits'] == 1
    assert readiness['derived_geocoded_permits'] == 0


@pytest.mark.parametrize('target,field,value', [
    ('permit', 'address', '200 MARKET ST'),
    ('permit', 'is_active', False),
    ('source', 'is_active', False),
    ('source', 'key', 'unreviewed'),
    ('source', 'base_url', 'https://example.invalid'),
    ('geocode', 'address_hash', '0' * 64),
    ('geocode', 'benchmark', 'unknown'),
    ('geocode', 'source_url', 'https://example.invalid'),
    ('geocode', 'latitude', 38),
    ('geocode', 'response_hash', 'invalid'),
    ('geocode', 'observed_at', datetime.now(timezone.utc) - timedelta(days=91)),
])
def test_ineligible_estimates_are_excluded_from_map_and_readiness(db, sf_location, target, field, value):
    source, permit, geocode = sf_location
    setattr({'source': source, 'permit': permit, 'geocode': geocode}[target], field, value)
    db.flush()
    assert list_map_signals(db)['items'] == []
    readiness = map_readiness(db)
    assert readiness['derived_geocoded_permits'] == readiness['geocoded_permits'] == 0
    assert readiness['has_geocoded_signals'] is False


@pytest.mark.parametrize('foreign_target', ['geocode', 'source'])
def test_foreign_join_rows_cannot_supply_locations(db, sf_location, foreign_target):
    source, _, geocode = sf_location
    db.add(Organization(id='foreign-org', name='Foreign', slug='foreign-org'))
    db.flush()
    (geocode if foreign_target == 'geocode' else source).organization_id = 'foreign-org'
    db.flush()
    assert list_map_signals(db)['items'] == []
    assert map_readiness(db)['derived_geocoded_permits'] == 0


def test_foreign_request_and_demo_do_not_expose_estimates(db, sf_location):
    token = set_current_context(RequestContext('foreign-org', 'viewer'))
    try:
        assert list_map_signals(db)['items'] == []
        assert map_readiness(db)['permits'] == 0
    finally:
        reset_current_context(token)
    demo_token = demo_read_only.set(True)
    try:
        assert list_map_signals(db)['items'] == []
        assert map_readiness(db)['derived_geocoded_permits'] == 0
    finally:
        demo_read_only.reset(demo_token)


def test_stale_rows_are_filtered_before_bounded_pagination(db, sf_location):
    source, stale, geocode = sf_location
    first = _additional_permit(db, source, stale, 'valid-first')
    second = _additional_permit(db, source, stale, 'valid-second')
    now = datetime.now(timezone.utc)
    stale.updated_at = now
    first.updated_at, second.updated_at = now - timedelta(hours=1), now - timedelta(hours=2)
    geocode.address_hash = '0' * 64
    db.flush()
    first_page = list_map_signals(db, limit=1)
    assert [item['id'] for item in first_page['items']] == [first.id]
    assert first_page['next_offset'] == 1
    assert first_page['truncated_layers'] == ['permit']
    second_page = list_map_signals(db, limit=1, offset=1)
    assert [item['id'] for item in second_page['items']] == [second.id]
    assert second_page['next_offset'] is None
    assert second_page['previous_offset'] == 0
    assert list_map_signals(db, limit=1, offset=2)['items'] == []
    readiness = map_readiness(db)
    assert readiness['permits'] == 3
    assert readiness['source_geocoded_permits'] == 0
    assert readiness['derived_geocoded_permits'] == readiness['geocoded_permits'] == 2


def test_postgresql_map_and_readiness_compile_without_connecting(monkeypatch):
    monkeypatch.setattr(config, 'SF_DERIVED_LOCATIONS_ENABLED', True)
    engine = create_mock_engine(
        'postgresql+psycopg2://', lambda *_args, **_kwargs: pytest.fail('SQL execution forbidden'),
    )
    with Session(bind=engine) as session:
        query, native, derived = permit_location_query(session)
        statement = query.filter(or_(native, derived)).order_by(
            PermitRecord.updated_at.desc(), PermitRecord.id,
        ).offset(5).limit(3).statement
        compiled = statement.compile(dialect=engine.dialect)
        sql = str(compiled)
        assert 'encode(sha256(convert_to(' in sql
        assert 'buildsignals_sha256' not in sql
        assert 'permit_records.postal_code ~ ' in sql
        assert 'permit_geocodes.response_hash ~ ' in sql
        assert 'permit_records.latitude IS NULL AND permit_records.longitude IS NULL' in sql
        assert 'permit_geocodes.address_hash = encode(' in sql
        assert 'permit_geocodes.observed_at >=' in sql
        assert 'permit_geocodes.observed_at <=' in sql
        assert 'permit_geocodes.organization_id = permit_records.organization_id' in sql
        assert 'ingestion_sources.organization_id = permit_records.organization_id' in sql
        assert 'LEFT OUTER JOIN permit_geocodes' in sql
        assert 'LEFT OUTER JOIN ingestion_sources' in sql
        assert sql.index('WHERE') < sql.index('permit_geocodes.address_hash =') < sql.index('LIMIT')
        bounded_sql = str(statement.compile(
            dialect=engine.dialect, compile_kwargs={'literal_binds': True},
        ))
        assert bounded_sql.rstrip().endswith('LIMIT 3 OFFSET 5')
        assert geo.SOURCE_KEY in compiled.params.values()
        assert geo.SOURCE_URL in compiled.params.values()
        counts_sql = str(query.with_entities(
            func.count(PermitRecord.id), func.sum(case((native, 1), else_=0)),
            func.sum(case((derived, 1), else_=0)),
        ).statement.compile(dialect=engine.dialect))
        assert 'sum(CASE WHEN' in counts_sql
        assert 'permit_geocodes.address_hash = encode(sha256(convert_to(' in counts_sql
        assert 'LIMIT' not in counts_sql
