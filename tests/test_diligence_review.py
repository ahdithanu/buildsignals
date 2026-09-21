from datetime import datetime, timezone

from app.models.audit_log import AuditLog
from app.models.diligence_review import DiligenceReview
from app.models.document import Document
from app.models.organization_membership import MemberRole, OrganizationMembership
from tests.test_acquisition_screen_export import register, reset_limiter  # noqa: F401
from tests.test_document_evidence import PAYLOAD


def test_review_binds_evidence_actor_and_criterion_without_promoting_unknowns(client, db):
    headers = register(client, 'review-diligence@example.com')
    deal = client.post('/deals', headers=headers, json={'name': 'Review fixture'}).json()
    base = f"/deals/{deal['id']}"
    doc_id = client.post(base + '/document-excerpts', headers=headers, json=PAYLOAD).json()['id']
    evidence = client.get(base + f'/documents/{doc_id}/excerpt', headers=headers).json()['evidence']
    payload = {'document_id': doc_id, 'expected_text_sha256': evidence['text_sha256'],
               'criterion': 'occupancy', 'assessment': 'inconclusive',
               'rationale': 'One suite is not evidence of whole-property occupancy.'}
    url = base + '/diligence-reviews'
    assert client.post(url, headers=headers, json={**payload, 'expected_text_sha256': '0' * 64}).status_code == 409
    assert db.query(DiligenceReview).count() == 0
    created = client.post(url, headers=headers, json=payload)
    assert created.status_code == 201, created.text
    assert created.headers['cache-control'] == 'no-store'
    review = created.json()
    assert review['snapshot']['evidence'] == evidence
    assert review['snapshot']['changes_screening_result'] is False
    assert review['reviewer_id'] == evidence['submitted_by']
    assert db.query(AuditLog).filter_by(entity_id=review['id'], action='create').count() == 1
    second = client.post(url, headers=headers, json={**payload, 'assessment': 'contradicts'})
    assert second.status_code == 201
    listed = client.get(url, headers=headers, params={'limit': 1})
    assert listed.json()['has_more'] is True
    assert listed.json()['items'][0]['snapshot']['assessment'] == 'contradicts'
    assert client.get(url, headers=headers, params={'skip': 1, 'limit': 1}).json()['items'][0]['id'] == review['id']
    screened = client.get(base + '/acquisition-screen?profile=small_bay_retail', headers=headers).json()
    assert next(c for c in screened['criteria'] if c['key'] == 'occupancy')['status'] == 'unknown'
    other_deal = client.post('/deals', headers=headers, json={'name': 'Other deal'}).json()['id']
    assert client.post(f'/deals/{other_deal}/diligence-reviews', headers=headers, json=payload).status_code == 404
    other = register(client, 'other-diligence@example.com')
    assert client.post(url, headers=other, json=payload).status_code == 404
    assert client.get(url, headers=other).status_code == 404
    assert client.get(url).status_code == 401
    doc = db.get(Document, doc_id)
    member = db.query(OrganizationMembership).filter_by(organization_id=doc.organization_id).one()
    member.role = MemberRole.viewer
    db.commit()
    assert client.get(url, headers=headers).status_code == 200
    assert client.post(url, headers=headers, json=payload).status_code == 403
    member.role = MemberRole.admin
    doc.evidence_excerpt = {**doc.evidence_excerpt, 'text': 'corrupted'}
    db.commit()
    assert client.post(url, headers=headers, json=payload).status_code == 409
    assert db.query(DiligenceReview).count() == 2
    # The prior review is an exact snapshot, not a reference to mutable text.
    assert client.get(url, headers=headers).json()['items'][0]['snapshot']['evidence']['text'] == PAYLOAD['text']
    doc.deleted_at = datetime.now(timezone.utc)
    db.commit()
    assert client.get(url, headers=headers).json()['items'] == []
    assert client.post(url, headers=headers, json=payload).status_code == 404
