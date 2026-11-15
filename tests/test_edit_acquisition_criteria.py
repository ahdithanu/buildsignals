import hashlib
import json
from copy import deepcopy

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.db import get_db
from app.main import app
from app.models.acquisition_screen import AcquisitionScreenSnapshot
from app.models.audit_log import AuditLog
from app.models.buy_box import BuyBox
from app.models.organization_membership import MemberRole, OrganizationMembership
from tests.test_acquisition_criteria import CRITERIA
from tests.test_acquisition_screen_export import register


@pytest.fixture
def owned_box(client):
    headers = register(client, 'criteria-edit@example.com')
    response = client.post('/buy-box', headers=headers, json={
        'asset_type': 'legacy office', 'locations': 'Austin TX',
        'min_price': 100, 'max_price': 900, 'min_irr': 0.12,
        'deal_type': 'acquisition', 'notes': 'Preserve legacy notes',
        'acquisition_criteria': CRITERIA,
    })
    assert response.status_code == 201, response.text
    return headers, response.json()


def edit_url(box):
    return f"/buy-box/{box['id']}/acquisition-criteria"


def edit_body(box):
    return {
        'expected_criteria': deepcopy(box['acquisition_criteria']),
        'acquisition_criteria': box['acquisition_criteria'] | {'min_size': 15},
    }


def audits(db, box):
    return db.query(AuditLog).filter_by(entity_type='buy_box', entity_id=box['id']).all()


def test_edit_only_criteria_and_audit_old_new_actor(client, db, owned_box):
    headers, box = owned_box
    body = edit_body(box)
    response = client.put(edit_url(box), headers=headers, json=body)
    assert response.status_code == 200, response.text
    assert response.json() == box | {'acquisition_criteria': body['acquisition_criteria']}
    assert client.get('/buy-box', headers=headers).json() == [response.json()]
    db.expire_all()
    assert db.get(BuyBox, box['id']).acquisition_criteria == body['acquisition_criteria']
    audit, = audits(db, box)
    assert audit.organization_id == box['organization_id']
    assert audit.actor_id == box['user_id']
    assert json.loads(audit.old_values) == {'acquisition_criteria': body['expected_criteria']}
    assert json.loads(audit.new_values) == {'acquisition_criteria': body['acquisition_criteria']}


def test_stale_edit_and_same_put_retry_are_conflicts_without_second_mutation(client, db, owned_box):
    headers, box = owned_box
    body = edit_body(box)
    assert client.put(edit_url(box), headers=headers, json=body).status_code == 200
    for rejected in (body, body | {'acquisition_criteria': CRITERIA | {'market_city': 'Cincinnati'}}):
        assert client.put(edit_url(box), headers=headers, json=rejected).status_code == 409
    db.expire_all()
    assert db.get(BuyBox, box['id']).acquisition_criteria == body['acquisition_criteria']
    assert len(audits(db, box)) == 1


@pytest.mark.parametrize('role,status', [(MemberRole.editor, 200), (MemberRole.viewer, 403)])
def test_current_membership_controls_edit(client, db, owned_box, role, status):
    headers, box = owned_box
    member = db.query(OrganizationMembership).filter_by(organization_id=box['organization_id']).one()
    member.role = role
    db.commit()
    response = client.put(edit_url(box), headers=headers, json=edit_body(box))
    assert response.status_code == status, response.text
    if status == 403:
        db.expire_all()
        assert db.get(BuyBox, box['id']).acquisition_criteria == box['acquisition_criteria']
        assert audits(db, box) == []


def test_missing_foreign_and_unauthenticated_cannot_edit(client, db, owned_box):
    headers, box = owned_box
    other = register(client, 'criteria-edit-foreign@example.com')
    assert client.put(edit_url(box), headers=other, json=edit_body(box)).status_code == 404
    assert client.put('/buy-box/missing/acquisition-criteria', headers=headers,
                      json=edit_body(box)).status_code == 404
    assert client.put(edit_url(box), json=edit_body(box)).status_code == 401
    db.expire_all()
    assert db.get(BuyBox, box['id']).acquisition_criteria == box['acquisition_criteria']
    assert audits(db, box) == []


@pytest.mark.parametrize('stored', [None, {}, {'profile': 'invalid'}])
def test_unstructured_or_invalid_stored_criteria_are_not_adopted(client, db, owned_box, stored):
    headers, box = owned_box
    row = db.get(BuyBox, box['id'])
    row.acquisition_criteria = stored
    db.commit()
    response = client.put(edit_url(box), headers=headers, json=edit_body(box))
    assert response.status_code == 422, response.text
    db.refresh(row)
    assert row.acquisition_criteria == stored
    assert audits(db, box) == []


@pytest.mark.parametrize('field', ['acquisition_criteria', 'expected_criteria'])
@pytest.mark.parametrize('invalid', [
    None, {}, {'min_size': 15},
    CRITERIA | {'min_size': True},
    CRITERIA | {'max_size': 1},
    CRITERIA | {'min_price': 4000000},
    CRITERIA | {'max_price': 'NaN'},
    CRITERIA | {'market_city': '  '},
    CRITERIA | {'market_state': 'oh'},
    CRITERIA | {'version': 2},
    CRITERIA | {'min_year_built': '1980'},
    CRITERIA | {'organization_id': 'injected'},
])
def test_both_criteria_require_full_validation(client, db, owned_box, field, invalid):
    headers, box = owned_box
    body = edit_body(box) | {field: invalid}
    response = client.put(edit_url(box), headers=headers, json=body)
    assert response.status_code == 422, response.text
    db.expire_all()
    assert db.get(BuyBox, box['id']).acquisition_criteria == box['acquisition_criteria']
    assert audits(db, box) == []


@pytest.mark.parametrize('field', ['acquisition_criteria', 'expected_criteria'])
def test_both_criteria_are_required(client, owned_box, field):
    headers, box = owned_box
    body = edit_body(box)
    del body[field]
    assert client.put(edit_url(box), headers=headers, json=body).status_code == 422


@pytest.mark.parametrize('field,value', [
    ('id', 'injected'), ('organization_id', 'foreign'), ('user_id', 'foreign'),
    ('created_at', '2000-01-01T00:00:00Z'), ('notes', 'changed'),
    ('asset_type', 'retail'), ('locations', 'Cincinnati OH'), ('min_price', 1),
    ('max_price', 2), ('min_irr', 0.5), ('deal_type', 'changed'),
])
def test_top_level_injection_is_forbidden(client, db, owned_box, field, value):
    headers, box = owned_box
    response = client.put(edit_url(box), headers=headers, json=edit_body(box) | {field: value})
    assert response.status_code == 422, response.text
    assert client.get('/buy-box', headers=headers).json() == [box]
    assert audits(db, box) == []


def test_expected_criteria_use_validated_structured_comparison(client, owned_box):
    headers, box = owned_box
    body = edit_body(box)
    body['expected_criteria'] = CRITERIA | {'market_city': ' Columbus '}
    response = client.put(edit_url(box), headers=headers, json=body)
    assert response.status_code == 200, response.text


def test_cached_row_is_refreshed_and_query_requests_row_lock(client, db, owned_box):
    headers, box = owned_box
    cached = db.get(BuyBox, box['id'])
    latest = box['acquisition_criteria'] | {'max_size': 30}
    with Session(db.get_bind()) as writer:
        row = writer.get(BuyBox, box['id'])
        row.acquisition_criteria = latest
        writer.commit()
    assert cached.acquisition_criteria == box['acquisition_criteria']
    observed = []

    # Capture the ORM statement before SQLite drops FOR UPDATE during compilation.
    def inspect_query(state):
        if state.is_select and any(mapper.class_ is BuyBox for mapper in state.all_mappers):
            observed.append(state.statement._for_update_arg is not None)

    def shared_db():
        yield db

    original = app.dependency_overrides[get_db]
    app.dependency_overrides[get_db] = shared_db
    event.listen(db, 'do_orm_execute', inspect_query)
    try:
        response = client.put(edit_url(box), headers=headers, json=edit_body(box))
        assert response.status_code == 409, response.text
        assert cached.acquisition_criteria == latest
        assert observed == [True]
        assert audits(db, box) == []
    finally:
        event.remove(db, 'do_orm_execute', inspect_query)
        app.dependency_overrides[get_db] = original


def test_demo_write_is_denied_before_edit(client, db, owned_box, monkeypatch):
    from app import config
    from app.services.demo_access import DEMO_ORG_ID, DEMO_USER_ID
    from app.services.security import create_access_token

    _, box = owned_box
    monkeypatch.setattr(config, 'DEMO_ENABLED', True)
    token = create_access_token(user_id=DEMO_USER_ID, org_id=DEMO_ORG_ID, demo=True)
    response = client.put(edit_url(box), headers={'Authorization': f'Bearer {token}'},
                          json=edit_body(box))
    assert response.status_code == 403, response.text
    assert 'read-only' in response.json()['detail']
    db.expire_all()
    assert db.get(BuyBox, box['id']).acquisition_criteria == box['acquisition_criteria']
    assert audits(db, box) == []


def test_saved_export_bytes_and_hash_survive_edit_while_live_screen_changes(client, db, owned_box):
    headers, box = owned_box
    created = client.post('/deals', headers=headers, json={
        'name': 'Synthetic criteria edit', 'city': 'Columbus', 'state': 'OH',
        'units': 12, 'asking_price': 2000000, 'year_built': 1990,
    })
    assert created.status_code == 201, created.text
    base = f"/deals/{created.json()['id']}/acquisition-screen"
    params = {'buy_box_id': box['id']}
    exported = client.post(base + '/export', headers=headers, params=params)
    assert exported.status_code == 200, exported.text
    snapshot_id = exported.headers['x-acquisition-snapshot-id']
    digest = hashlib.sha256(exported.content).hexdigest()
    download_url = base + '/history/' + snapshot_id
    assert client.get(download_url, headers=headers).content == exported.content
    assert exported.json()['screen']['criteria'][0]['status'] == 'pass'
    assert client.put(edit_url(box), headers=headers, json=edit_body(box)).status_code == 200
    live = client.get(base, headers=headers, params=params)
    assert live.status_code == 200, live.text
    assert live.json()['criteria_snapshot'] == edit_body(box)['acquisition_criteria']
    assert live.json()['criteria'][0]['status'] == 'fail'
    downloaded = client.get(download_url, headers=headers)
    assert downloaded.status_code == 200
    assert downloaded.content == exported.content
    assert hashlib.sha256(downloaded.content).hexdigest() == digest
    db.expire_all()
    saved = db.get(AcquisitionScreenSnapshot, snapshot_id)
    assert saved.content.encode() == exported.content
    assert saved.content_sha256 == digest
