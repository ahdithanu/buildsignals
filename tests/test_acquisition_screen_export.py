import hashlib
import json
from datetime import datetime, timezone

import pytest

from app.models.acquisition_screen import AcquisitionScreenSnapshot
from app.models.audit_log import AuditLog
from app.models.deal import Deal
from app.models.organization_membership import MemberRole, OrganizationMembership
from app.services.rate_limiter import limiter


@pytest.fixture(autouse=True)
def reset_limiter():
    limiter.clear()
    yield
    limiter.clear()


def register(client, email):
    result = client.post('/auth/register', json={
        'email': email, 'password': 'CorrectHorseBattery42',
        'full_name': 'Pilot Analyst', 'organization_name': email,
    })
    assert result.status_code == 201, result.text
    return {'Authorization': f"Bearer {result.json()['access_token']}"}


def test_export_real_auth_is_scoped_audited_and_preserves_unknowns(client, db):
    headers = register(client, 'screen@example.com')
    created = client.post('/deals', headers=headers, json={
        'name': 'Pilot', 'city': 'Columbus', 'state': 'OH', 'sq_ft': 15000,
        'year_built': 1990, 'asking_price': 2500000,
    })
    assert created.status_code == 201, created.text
    deal_id = created.json()['id']
    url = f'/deals/{deal_id}/acquisition-screen/export'
    params = {'profile': 'small_bay_retail', 'market_city': 'Columbus', 'market_state': 'OH'}
    exported = client.post(url, headers=headers, params=params)
    assert exported.status_code == 200, exported.text
    assert exported.headers['cache-control'] == 'no-store'
    assert exported.headers['content-disposition'] == 'attachment; filename="acquisition-screen.json"'
    snapshot = exported.json()
    assert snapshot['screen']['counts'] == {'pass': 4, 'fail': 0, 'unknown': 14}
    assert snapshot['screen']['evidence_verified'] is False
    assert snapshot['screen']['criteria'][0]['basis'] == 'deal.sq_ft'
    assert snapshot['target_market'] == {'city': 'Columbus', 'state': 'OH'}
    audit = db.query(AuditLog).filter_by(action='acquisition_screen_export', entity_id=deal_id).one()
    assert json.loads(audit.new_values)['content_sha256'] == hashlib.sha256(exported.content).hexdigest()
    assert audit.actor_id is not None

    other = register(client, 'other-screen@example.com')
    assert client.post(url, headers=other).status_code == 404
    assert client.post(url).status_code == 401
    assert client.post(url, headers=headers, params={'profile': 'invalid'}).status_code == 422
    assert db.query(AuditLog).filter_by(action='acquisition_screen_export').count() == 1

    deal = db.get(Deal, deal_id)
    member = db.query(OrganizationMembership).filter_by(organization_id=deal.organization_id).one()
    member.role = MemberRole.viewer
    db.commit()
    assert client.post(url, headers=headers).status_code == 403
    member.role = MemberRole.editor
    db.commit()
    assert client.post(url, headers=headers).status_code == 200
    deal.deleted_at = datetime.now(timezone.utc)
    db.commit()
    assert client.post(url, headers=headers).status_code == 404


def test_history_preserves_exact_snapshot_and_scopes_access(client, db):
    headers = register(client, 'history@example.com')
    created = client.post('/deals', headers=headers, json={
        'name': 'Historical screen', 'city': 'Columbus', 'state': 'OH',
        'units': 24, 'year_built': 1995, 'asking_price': 2000000,
    })
    assert created.status_code == 201, created.text
    deal_id = created.json()['id']
    base = f'/deals/{deal_id}/acquisition-screen'
    first = client.post(base + '/export', headers=headers)
    assert first.status_code == 200
    snapshot_id = first.headers['x-acquisition-snapshot-id']
    saved = db.get(AcquisitionScreenSnapshot, snapshot_id)
    assert saved.content.encode() == first.content
    assert saved.content_sha256 == hashlib.sha256(first.content).hexdigest()
    deal = db.get(Deal, deal_id)
    deal.asking_price = 9000000
    db.commit()
    second = client.post(base + '/export', headers=headers)
    assert second.status_code == 200
    assert second.content != first.content
    history = client.get(base + '/history', headers=headers, params={'limit': 1})
    assert history.status_code == 200
    assert history.headers['cache-control'] == 'no-store'
    assert history.json()['has_more'] is True
    assert history.json()['items'][0]['id'] == second.headers['x-acquisition-snapshot-id']
    assert 'content' not in history.json()['items'][0]
    page_two = client.get(base + '/history', headers=headers, params={'limit': 1, 'skip': 1})
    assert page_two.json()['items'][0]['id'] == snapshot_id
    assert page_two.json()['has_more'] is False
    detail = base + '/history/' + snapshot_id
    assert client.get(detail, headers=headers).content == first.content
    assert client.get(detail).status_code == 401
    other = register(client, 'foreign-history@example.com')
    assert client.get(detail, headers=other).status_code == 404
    assert client.get(base + '/history', headers=other).status_code == 404
    assert client.get(base + '/history', headers=headers, params={'limit': 101}).status_code == 422
    member = db.query(OrganizationMembership).filter_by(organization_id=deal.organization_id).one()
    member.role = MemberRole.viewer
    db.commit()
    assert client.get(detail, headers=headers).content == first.content
    assert client.post(base + '/export', headers=headers).status_code == 403
    assert client.put(detail, headers=headers, json={}).status_code == 405
    assert client.delete(detail, headers=headers).status_code == 405
    saved.content = '{}'
    db.commit()
    assert client.get(detail, headers=headers).status_code == 500
    deal.deleted_at = datetime.now(timezone.utc)
    db.commit()
    assert client.get(base + '/history', headers=headers).status_code == 404
    assert client.get(detail, headers=headers).status_code == 404


def test_snapshot_participates_in_org_portability_and_erasure(client, db):
    headers = register(client, 'portable-history@example.com')
    created = client.post('/deals', headers=headers, json={'name': 'Portable screen'})
    assert created.status_code == 201
    deal_id = created.json()['id']
    exported = client.post(f'/deals/{deal_id}/acquisition-screen/export', headers=headers)
    assert exported.status_code == 200
    org_id = db.get(Deal, deal_id).organization_id
    snapshot_id = exported.headers['x-acquisition-snapshot-id']
    portable = client.get(f'/organizations/{org_id}/export', headers=headers)
    assert portable.status_code == 200, portable.text
    snapshots = portable.json()['acquisition_screen_snapshots']
    assert len(snapshots) == 1
    assert snapshots[0]['id'] == snapshot_id
    assert snapshots[0]['content'].encode() == exported.content
    erased = client.post(f'/organizations/{org_id}/delete', headers=headers,
                         json={'confirm': 'portable-history@example.com'})
    assert erased.status_code == 200, erased.text
    assert erased.json()['rows_deleted']['acquisition_screen_snapshots'] == 1
    assert db.query(AcquisitionScreenSnapshot).filter_by(id=snapshot_id).count() == 0
