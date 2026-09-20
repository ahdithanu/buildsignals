import hashlib
import json
from datetime import datetime, timezone

import pytest

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
