from datetime import datetime, timedelta, timezone

import pytest

from app.models.audit_log import AuditLog
from app.models.ingestion import IngestionRun, IngestionSource, RawSourceRecord
from app.models.organization_membership import MemberRole, OrganizationMembership
from app.models.parcel import ParcelFact, ParcelRecord
from app.services.security import decode_access_token
from tests.test_acquisition_screen_export import register
from tests.test_demo import demo as demo  # noqa: F401
from tests.test_demo import headers as demo_headers


@pytest.fixture
def parcel_context(client, db, monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail('Parcel context must not request external data or models')
    monkeypatch.setattr('urllib.request.urlopen', forbidden)
    monkeypatch.setattr('app.services.llm_client.get_default_llm_client', forbidden)
    headers = register(client, 'synthetic-parcel-context@example.com')
    org = decode_access_token(headers['Authorization'].split()[1])['org_id']
    now = datetime.now(timezone.utc) - timedelta(minutes=1)
    source = IngestionSource(organization_id=org, key='synthetic-zoning', name='Synthetic parcel evidence',
                             adapter='manual', record_type='parcel')
    db.add(source); db.flush()
    run = IngestionRun(organization_id=org, source_id=source.id, status='completed')
    db.add(run); db.flush()
    raw = RawSourceRecord(organization_id=org, source_id=source.id, run_id=run.id,
                          external_record_id='synthetic-parcel', record_type='parcel',
                          content_hash='a' * 64, payload={'zoning_code': 'SYNTHETIC-B2'}, received_at=now)
    db.add(raw); db.flush()
    parcel = ParcelRecord(organization_id=org, source_id=source.id, latest_raw_record_id=raw.id,
                          external_parcel_id='synthetic-parcel', jurisdiction='Synthetic authority',
                          state='NJ', zoning_code='SYNTHETIC-B2', latitude=39.9, longitude=-75.0)
    db.add(parcel); db.flush()
    db.add(ParcelFact(organization_id=org, parcel_id=parcel.id, raw_source_record_id=raw.id,
                      fact_type='zoning', value={'zoning_code': 'SYNTHETIC-B2'}, source_system=source.key,
                      source_url='https://example.invalid/synthetic-zoning', confidence=1,
                      observed_at=now, last_verified_at=now, valid_from=now, is_current=True))
    db.commit()
    return headers, parcel.id, org


def test_context_is_read_only_scoped_and_never_establishes_potential_uses(client, db, parcel_context):
    headers, parcel_id, _org = parcel_context
    tables = (ParcelRecord, ParcelFact, RawSourceRecord, IngestionSource, IngestionRun, AuditLog)
    before = [db.query(table).count() for table in tables]
    response = client.get(f'/parcels/{parcel_id}/use-context', headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['parcel_id'] == parcel_id
    assert data['status'] == 'reported'
    assert data['reported_zoning_codes'] == ['SYNTHETIC-B2']
    assert data['potential_uses'] == [] and data['potential_uses_status'] == 'not_assessed'
    assert data['ai_used'] is False
    assert 'use_rules_missing' in data['gaps'] and 'zoning_assignment_unverified' in data['gaps']
    assert response.headers['cache-control'] == 'no-store'
    assert 'source_system' not in response.text and 'payload' not in response.text
    assert [db.query(table).count() for table in tables] == before


def test_context_allows_current_viewer_but_not_another_organization(client, db, parcel_context):
    headers, parcel_id, org = parcel_context
    membership = db.query(OrganizationMembership).filter_by(organization_id=org).one()
    membership.role = MemberRole.viewer
    db.commit()
    assert client.get(f'/parcels/{parcel_id}/use-context', headers=headers).status_code == 200
    other = register(client, 'synthetic-foreign-context@example.com')
    assert client.get(f'/parcels/{parcel_id}/use-context', headers=other).status_code == 404
    assert client.get('/parcels/missing/use-context', headers=headers).status_code == 404
    assert client.get(f'/parcels/{parcel_id}/use-context').status_code == 401


@pytest.mark.parametrize('field', ['is_active', 'retired_at'])
def test_context_does_not_revive_retired_inventory(client, db, parcel_context, field):
    headers, parcel_id, _org = parcel_context
    row = db.get(ParcelRecord, parcel_id)
    setattr(row, field, False if field == 'is_active' else datetime.now(timezone.utc))
    db.commit()
    assert client.get(f'/parcels/{parcel_id}/use-context', headers=headers).status_code == 404


def test_new_context_endpoint_remains_denied_for_demo(client, demo):
    response = client.get('/parcels/00000000-0000-0000-0000-000000000001/use-context',
                          headers=demo_headers(client))
    assert response.status_code == 403
