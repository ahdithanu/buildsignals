import hashlib
import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.audit_log import AuditLog
from app.models.deal import Deal
from app.models.document import Document
from app.models.organization_membership import MemberRole, OrganizationMembership
from app.schemas.document_evidence import DocumentExcerptCreate
from tests.test_acquisition_screen_export import register, reset_limiter  # noqa: F401

PAYLOAD = {"source_title": "Redacted rent roll", "document_type": "rent_roll",
           "source_date": "2026-09-01", "locator": "Page 1, suite A",
           "text": "Suite A: annual base rent $24,000.\n", "authorized_to_store": True}


@pytest.mark.parametrize("update", [
    {"authorized_to_store": False}, {"authorized_to_store": "true"}, {"text": " "},
    {"text": "\x00"}, {"text": "a" * 20001}, {"text": "\U0001f600" * 20000},
    {"source_title": " "}, {"locator": " "}, {"document_type": "other"},
    {"source_date": "not-a-date"}, {"independently_verified": True},
])
def test_rejects_unbounded_unattributed_or_false_verification_inputs(update):
    with pytest.raises(ValidationError):
        DocumentExcerptCreate.model_validate({**PAYLOAD, **update})


def test_excerpt_is_attributed_scoped_and_never_claims_verified_diligence(client, db):
    headers = register(client, 'excerpt@example.com')
    deal = client.post('/deals', headers=headers, json={'name': 'Diligence fixture'}).json()
    base = f"/deals/{deal['id']}"
    result = client.post(base + '/document-excerpts', headers=headers, json=PAYLOAD)
    assert result.status_code == 201, result.text
    assert result.headers['cache-control'] == 'no-store'
    assert 'evidence_excerpt' not in result.json()
    assert result.json()['evidence_kind'] == 'analyst_provided_excerpt'
    doc_id = result.json()['id']
    url = base + f'/documents/{doc_id}/excerpt'
    retrieved = client.get(url, headers=headers)
    assert retrieved.status_code == 200
    assert retrieved.headers['cache-control'] == 'no-store'
    evidence = retrieved.json()['evidence']
    assert evidence['text'] == PAYLOAD['text']
    assert evidence['text_sha256'] == hashlib.sha256(PAYLOAD['text'].encode()).hexdigest()
    assert evidence['independently_verified'] is False
    assert evidence['original_file_received'] is False
    doc = db.get(Document, doc_id)
    assert evidence['submitted_by'] == doc.created_by
    assert doc.file_path is None and doc.size_bytes is None
    audit = db.query(AuditLog).filter_by(entity_id=doc_id, action='evidence_excerpt_created').one()
    assert json.loads(audit.new_values)['text_sha256'] == evidence['text_sha256']
    assert PAYLOAD['text'] not in audit.new_values
    screening = client.get(base + '/acquisition-screen?profile=small_bay_retail', headers=headers).json()
    assert screening['evidence_verified'] is False
    assert next(c for c in screening['criteria'] if c['key'] == 'occupancy')['status'] == 'unknown'
    other = register(client, 'foreign-excerpt@example.com')
    assert client.get(url, headers=other).status_code == 404
    assert client.post(base + '/document-excerpts', headers=other, json=PAYLOAD).status_code == 404
    assert client.get(url).status_code == 401
    assert client.post(base + '/document-excerpts', json=PAYLOAD).status_code == 401
    member = db.query(OrganizationMembership).filter_by(organization_id=doc.organization_id).one()
    member.role = MemberRole.viewer
    db.commit()
    assert client.get(url, headers=headers).status_code == 200
    assert client.post(base + '/document-excerpts', headers=headers, json=PAYLOAD).status_code == 403
    db.get(Deal, deal['id']).deleted_at = datetime.now(timezone.utc)
    db.commit()
    assert client.get(url, headers=headers).status_code == 404
