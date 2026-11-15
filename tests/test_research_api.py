import json
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app import config
from app.models.audit_log import AuditLog
from app.models.organization_membership import MemberRole, OrganizationMembership
from app.services import research_service
from tests.test_research_context import deal, identity


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setattr('app.middleware.auth_context.ALLOW_ANONYMOUS', False)
    for key, value in {
        'AGENT_RESEARCH_API_ENABLED': True, 'AGENT_RESEARCH_CONTEXT_ENABLED': True,
        'AGENT_RESEARCH_DAILY_RUN_LIMIT': 1, 'AGENT_RESEARCH_PYTHON': sys.executable,
        'OPENROUTER_API_KEY': 'offline-test-only', 'IS_DEPLOYED': False,
    }.items():
        monkeypatch.setattr(config, key, value, raising=False)


def output(bundle):
    row = bundle['evidence'][0]
    findings = {'facts': [{'source_id': row['id'], 'quote': 'Research example'}],
                'unknowns': ['Occupancy unknown'], 'questions': ['Request rent roll']}
    return {'schema_version': 'research-output-v1', 'model_generated': True,
            'research_only': True, 'evidence_kind': bundle['evidence_kind'],
            'context_authenticity': 'not_verified_by_local_runner',
            'stages': [{'stage': name, 'findings': deepcopy(findings)}
                       for name in ('Evidence analyst', 'Diligence reviewer')],
            'usage': [dict(requested_model='fake/primary', served_model='fake/resolved',
                           provider='Fake', latency_ms=1, prompt_tokens=100,
                           completion_tokens=50, total_tokens=150, cost=None,
                           response_id=None) for _ in range(2)],
            'limitations': ['Saved workspace facts only']}


def setup(client):
    user, headers = identity(client, 'research-run')
    deal_id = deal(client, headers)
    return user, headers, f'/v1/deals/{deal_id}/research'


def test_success_reserves_before_worker_and_persists_only_usage(client, db, monkeypatch):
    user, headers, path = setup(client)
    before = client.get(path.removesuffix('/research'), headers=headers).json()
    seen = []

    def run(bundle, **_settings):
        reservation = db.query(AuditLog).filter_by(action='research_reserved').one()
        assert reservation.organization_id == user['organization_id']
        seen.append(bundle)
        return output(bundle)

    monkeypatch.setattr(research_service, 'run_research_process', run)
    request_id = str(uuid4())
    response = client.post(path, headers=headers, json={'request_id': request_id})
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    assert len(seen) == 1 and response.json()['result']['usage'][0]['cost'] is None
    audits = db.query(AuditLog).filter_by(organization_id=user['organization_id']).all()
    relevant = [row for row in audits if row.entity_type == 'research_run']
    assert {row.action for row in relevant} == {'research_reserved', 'research_completed'}
    assert all(row.actor_id == user['user_id'] and row.request_id == request_id for row in relevant)
    text = json.dumps([row.new_values for row in relevant])
    assert 'Research example' not in text and '100 Main St' not in text
    assert 'offline-test-only' not in text
    assert client.get(path.removesuffix('/research'), headers=headers).json() == before
    assert client.get(path + '/capabilities', headers=headers).json()['remaining_runs'] == 0
    assert client.post(path, headers=headers, json={'request_id': request_id}).status_code == 409
    assert client.post(path, headers=headers, json={'request_id': str(uuid4())}).status_code == 429
    assert len(seen) == 1


@pytest.mark.parametrize('key,value', [
    ('AGENT_RESEARCH_API_ENABLED', False), ('AGENT_RESEARCH_CONTEXT_ENABLED', False),
    ('AGENT_RESEARCH_DAILY_RUN_LIMIT', 0), ('AGENT_RESEARCH_PYTHON', ''),
    ('OPENROUTER_API_KEY', ''), ('IS_DEPLOYED', True),
])
def test_unconfigured_or_deployed_runtime_never_launches(client, db, monkeypatch, key, value):
    _, headers, path = setup(client)
    monkeypatch.setattr(config, key, value)
    monkeypatch.setattr(research_service, 'run_research_process', lambda *_a, **_k: pytest.fail('must not launch'))
    assert client.get(path + '/capabilities', headers=headers).json()['enabled'] is False
    assert client.post(path, headers=headers, json={'request_id': str(uuid4())}).status_code == 404
    assert db.query(AuditLog).filter_by(entity_type='research_run').count() == 0


def test_failure_is_sanitized_and_consumes_reservation(client, db, monkeypatch):
    _, headers, path = setup(client)

    def fail(*_a, **_k):
        raise ValueError('SECRET provider error /keys/private')

    monkeypatch.setattr(research_service, 'run_research_process', fail)
    response = client.post(path, headers=headers, json={'request_id': str(uuid4())})
    assert response.status_code == 503
    assert 'SECRET' not in response.text and 'private' not in response.text
    assert response.headers['retry-after'] == '60'
    assert db.query(AuditLog).filter_by(action='research_failed').count() == 1
    assert client.get(path + '/capabilities', headers=headers).json()['remaining_runs'] == 0


def test_foreign_and_viewer_and_anonymous_never_reserve(client, db, monkeypatch):
    _, headers, path = setup(client)
    other, foreign = identity(client, 'foreign-research')
    monkeypatch.setattr(research_service, 'run_research_process', lambda *_a, **_k: pytest.fail('must not launch'))
    assert client.post(path, headers=foreign, json={'request_id': str(uuid4())}).status_code == 404
    db.query(OrganizationMembership).filter_by(user_id=other['user_id']).one().role = MemberRole.viewer
    db.commit()
    assert client.post(path, headers=foreign, json={'request_id': str(uuid4())}).status_code == 403
    monkeypatch.setattr('app.middleware.auth_context.ALLOW_ANONYMOUS', True)
    assert client.post(path, json={'request_id': str(uuid4())}).status_code == 401
    assert db.query(AuditLog).filter_by(entity_type='research_run').count() == 0


@pytest.mark.parametrize('payload', [{}, {'request_id': 'bad'},
                                  {'request_id': str(uuid4()), 'org_id': 'foreign'},
                                  {'request_id': str(uuid4()), 'model': 'other'}])
def test_request_rejects_client_authority_fields(client, payload):
    _, headers, path = setup(client)
    assert client.post(path, headers=headers, json=payload).status_code == 422


@pytest.mark.parametrize('corrupt', [
    lambda result: result['stages'][1]['findings']['facts'][0].update(quote='Guaranteed 20% returns'),
    lambda result: result['usage'][0].update(cost=float('nan')),
    lambda result: result['usage'][0].update(prompt_tokens=True),
    lambda result: result['usage'][0].update(content='SECRET raw output'),
    lambda result: result.update(research_only=False),
    lambda result: result['stages'].pop(),
])
def test_parent_rejects_hostile_worker_output(client, db, monkeypatch, corrupt):
    _, headers, path = setup(client)

    def bad(bundle, **_kwargs):
        result = output(bundle)
        corrupt(result)
        return result

    monkeypatch.setattr(research_service, 'run_research_process', bad)
    response = client.post(path, headers=headers, json={'request_id': str(uuid4())})
    assert response.status_code == 503
    assert db.query(AuditLog).filter_by(action='research_reserved').count() == 1
    assert db.query(AuditLog).filter_by(action='research_completed').count() == 0
    assert 'SECRET' not in response.text


def test_admission_commit_failure_never_dispatches(client, db, monkeypatch):
    from sqlalchemy.orm import Session
    _, headers, path = setup(client)
    monkeypatch.setattr(research_service, 'run_research_process', lambda *_a, **_k: pytest.fail('must not launch'))
    monkeypatch.setattr(Session, 'commit', lambda *_a: (_ for _ in ()).throw(RuntimeError('SECRET')))
    assert client.post(path, headers=headers, json={'request_id': str(uuid4())}).status_code == 503
    assert db.query(AuditLog).filter_by(entity_type='research_run').count() == 0


def test_outcome_commit_failure_does_not_redispatch(client, db, monkeypatch):
    from sqlalchemy.orm import Session
    _, headers, path = setup(client)
    commit = Session.commit
    commits, launches = [], []

    def save(session):
        commits.append(1)
        if len(commits) == 2:
            raise RuntimeError('SECRET outcome storage failed')
        return commit(session)

    def run(bundle, **_kwargs):
        launches.append(1)
        return output(bundle)

    monkeypatch.setattr(Session, 'commit', save)
    monkeypatch.setattr(research_service, 'run_research_process', run)
    request_id = str(uuid4())
    assert client.post(path, headers=headers, json={'request_id': request_id}).status_code == 503
    assert db.query(AuditLog).filter_by(action='research_reserved').count() == 1
    assert client.post(path, headers=headers, json={'request_id': request_id}).status_code == 409
    assert len(launches) == 1


def test_daily_reset_does_not_reset_request_id_replay_guard(client, monkeypatch):
    _, headers, path = setup(client)
    today = datetime(2026, 11, 14, 23, 59, tzinfo=timezone.utc)
    monkeypatch.setattr(research_service, '_now', lambda: today)
    monkeypatch.setattr(research_service, 'run_research_process', lambda bundle, **_k: output(bundle))
    request_id = str(uuid4())
    assert client.post(path, headers=headers, json={'request_id': request_id}).status_code == 200
    today += timedelta(minutes=2)
    assert client.get(path + '/capabilities', headers=headers).json()['remaining_runs'] == 1
    assert client.post(path, headers=headers, json={'request_id': request_id}).status_code == 409
    assert client.post(path, headers=headers, json={'request_id': str(uuid4())}).status_code == 200


def test_foreign_relationships_never_enter_research_context(client, db, monkeypatch):
    from app.models.signal import Signal
    _, headers, path = setup(client)
    foreign, _ = identity(client, 'drifted-research')
    db.add(Signal(organization_id=foreign['organization_id'], deal_id=path.split('/')[-2],
                  signal_type='news', description='SECRET foreign signal'))
    db.commit()

    def run(bundle, **_kwargs):
        assert 'SECRET' not in json.dumps(bundle)
        return output(bundle)

    monkeypatch.setattr(research_service, 'run_research_process', run)
    assert client.post(path, headers=headers, json={'request_id': str(uuid4())}).status_code == 200
