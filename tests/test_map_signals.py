import pytest

from app.models.planning import PlanningRecord
from app.services.map_signals import list_map_signals
from app.utils.org_scope import RequestContext, reset_current_context, set_current_context
from tests.test_parcel_reference import fixture_records


def test_signals_do_not_require_saved_searches(db):
    source, _, _, _, permit = fixture_records(db)
    permit.latitude, permit.longitude, permit.state = 40, -83, 'OH'
    db.add(PlanningRecord(
        organization_id='default-org', source_id=source.id,
        latest_raw_record_id=permit.latest_raw_record_id, external_record_id='agenda-1',
        normalization_hash='c' * 64, title='Planning hearing', event_type='hearing',
        latitude=40.1, longitude=-83, state='OH',
    ))
    db.flush()
    result = list_map_signals(db, state='oh')
    assert {item['kind'] for item in result['items']} == {'permit', 'planning'}
    assert all(item['raw_record_id'] == permit.latest_raw_record_id for item in result['items'])
    assert list_map_signals(db, state='TX')['items'] == []
    permit.is_active = False
    db.flush()
    assert [i['kind'] for i in list_map_signals(db)['items']] == ['planning']


def test_signals_scope_and_coordinate_validation(db):
    _, _, _, _, permit = fixture_records(db)
    permit.latitude, permit.longitude = 40, -83
    db.flush()
    token = set_current_context(RequestContext('another-org', 'user'))
    try:
        assert list_map_signals(db)['items'] == []
    finally:
        reset_current_context(token)
    for lat, lng in ((None, -83), (91, -83), (40, 181)):
        permit.latitude, permit.longitude = lat, lng
        db.flush()
        assert list_map_signals(db)['items'] == []


def test_signals_limit_and_authentication(client, db):
    assert client.get('/acquisition-map/signals').status_code == 401
    with pytest.raises(ValueError):
        list_map_signals(db, limit=101)


def test_truncation_is_reported_per_layer(db):
    source, _, _, _, permit = fixture_records(db)
    for index in range(2):
        db.add(PlanningRecord(
            organization_id='default-org', source_id=source.id,
            latest_raw_record_id=permit.latest_raw_record_id,
            external_record_id=f'agenda-{index}', normalization_hash='d' * 64,
            title=f'Hearing {index}', event_type='hearing', latitude=40, longitude=-83,
        ))
    db.flush()
    result = list_map_signals(db, limit=1)
    assert len(result['items']) == 1
    assert result['truncated_layers'] == ['planning']
