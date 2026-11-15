from __future__ import annotations

import pytest

from app.models.organization_membership import MemberRole, OrganizationMembership
from app.routes import deal_intelligence


def identity(client, label):
    response = client.post('/v1/auth/register', json={
        'email': f'research-{label}@example.com', 'password': 'CorrectHorseBattery42',
        'full_name': 'Research Admin', 'organization_name': f'Research {label}',
    })
    assert response.status_code == 201, response.text
    body = response.json()
    return body, {'Authorization': f"Bearer {body['access_token']}"}


def deal(client, headers):
    response = client.post('/v1/deals', headers=headers, json={
        'name': 'Research example', 'address': '100 Main St', 'city': 'Austin',
        'state': 'TX', 'property_type': 'retail', 'asking_price': 1500000,
    })
    assert response.status_code == 201, response.text
    return response.json()['id']


@pytest.fixture(autouse=True)
def auth_required(monkeypatch):
    monkeypatch.setattr('app.middleware.auth_context.ALLOW_ANONYMOUS', False)


def test_context_is_disabled_by_default(client):
    _, headers = identity(client, 'off')
    result = client.get('/v1/deals/unknown/research-context', headers=headers)
    assert result.status_code == 404


def test_context_is_scoped_read_only_and_not_a_research_execution(client, monkeypatch):
    monkeypatch.setattr(deal_intelligence.config, 'AGENT_RESEARCH_CONTEXT_ENABLED', True)
    _, a = identity(client, 'a')
    _, b = identity(client, 'b')
    deal_id = deal(client, a)
    before = client.get(f'/v1/deals/{deal_id}', headers=a).json()
    result = client.get(f'/v1/deals/{deal_id}/research-context', headers=a)
    assert result.status_code == 200, result.text
    body = result.json()
    assert body['schema_version'] == 'research-context-v1'
    assert body['evidence'][0]['id'] == f'deal:{deal_id}'
    assert 'Research example' in body['evidence'][0]['text']
    assert body['evidence_kind'] == 'saved_workspace_facts_not_independently_verified'
    assert result.headers['cache-control'] == 'no-store'
    assert client.get(f'/v1/deals/{deal_id}', headers=a).json() == before
    assert client.get(f'/v1/deals/{deal_id}/research-context', headers=b).status_code == 404
    assert client.get(f'/v1/deals/{deal_id}/research-context').status_code == 401


def test_context_does_not_allow_anonymous_development_passthrough(client, monkeypatch):
    monkeypatch.setattr(deal_intelligence.config, 'AGENT_RESEARCH_CONTEXT_ENABLED', True)
    monkeypatch.setattr('app.middleware.auth_context.ALLOW_ANONYMOUS', True)
    assert client.get('/v1/deals/unknown/research-context').status_code == 401


def test_context_rejects_deleted_deal(client, db, monkeypatch):
    from app.models.deal import Deal
    monkeypatch.setattr(deal_intelligence.config, 'AGENT_RESEARCH_CONTEXT_ENABLED', True)
    _, headers = identity(client, 'deleted')
    deal_id = deal(client, headers)
    from datetime import datetime, timezone
    db.get(Deal, deal_id).deleted_at = datetime.now(timezone.utc)
    db.commit()
    assert client.get(f'/v1/deals/{deal_id}/research-context', headers=headers).status_code == 404


def test_context_rejects_demo_even_with_elevated_membership(client, db, tmp_path, monkeypatch):
    from app import config
    from app.services.demo_access import DEMO_USER_ID
    from app.services.demo_seed import seed_demo
    from tests.demo_fixtures import create_snapshot
    monkeypatch.setattr(config, 'DEMO_ENABLED', True)
    monkeypatch.setattr(config, 'AGENT_RESEARCH_CONTEXT_ENABLED', True)
    path = tmp_path / 'demo.db'
    create_snapshot(path)
    seed_demo(db, [path])
    response = client.post('/auth/demo')
    assert response.status_code == 200
    db.query(OrganizationMembership).filter_by(user_id=DEMO_USER_ID).one().role = MemberRole.admin
    db.commit()
    headers = {'Authorization': f"Bearer {response.json()['access_token']}"}
    assert client.get('/v1/deals/unknown/research-context', headers=headers).status_code == 403


def test_editor_can_export_own_context(client, db, monkeypatch):
    monkeypatch.setattr(deal_intelligence.config, 'AGENT_RESEARCH_CONTEXT_ENABLED', True)
    user, headers = identity(client, 'editor')
    deal_id = deal(client, headers)
    db.query(OrganizationMembership).filter_by(user_id=user['user_id']).one().role = MemberRole.editor
    db.commit()
    assert client.get(f'/v1/deals/{deal_id}/research-context', headers=headers).status_code == 200


@pytest.mark.parametrize('role', [MemberRole.viewer])
def test_context_rejects_restricted_membership(client, db, monkeypatch, role):
    monkeypatch.setattr(deal_intelligence.config, 'AGENT_RESEARCH_CONTEXT_ENABLED', True)
    user, headers = identity(client, 'restricted')
    db.query(OrganizationMembership).filter_by(user_id=user['user_id']).one().role = role
    db.commit()
    assert client.get('/v1/deals/unknown/research-context', headers=headers).status_code == 403
