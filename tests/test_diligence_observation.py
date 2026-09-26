import pytest
from pydantic import ValidationError

from app.schemas.diligence_review import DiligenceReviewCreate
from tests.test_acquisition_screen_export import register, reset_limiter  # noqa: F401
from tests.test_document_evidence import PAYLOAD

OBSERVATION = {
    'metric': 'leased_area_occupancy_percent', 'value': 80,
    'as_of': '2026-09-01', 'scope': 'partial',
    'methodology': '800 leased SF divided by 1000 SF in the supplied schedule.',
}
REVIEW = {'document_id': 'doc', 'expected_text_sha256': 'a' * 64,
          'criterion': 'occupancy', 'assessment': 'inconclusive',
          'rationale': 'A partial schedule does not establish whole-property occupancy.'}


@pytest.mark.parametrize('change', [
    {'value': True}, {'value': '80'}, {'value': -1}, {'value': 101},
    {'value': float('nan')}, {'value': float('inf')}, {'as_of': 'not-a-date'},
    {'scope': 'verified'}, {'methodology': '   '}, {'verified': True},
    {'metric': 'economic_occupancy'},
])
def test_observation_rejects_invalid_or_unqualified_values(change):
    with pytest.raises(ValidationError):
        DiligenceReviewCreate(**REVIEW, observation={**OBSERVATION, **change})


@pytest.mark.parametrize(('criterion', 'metric', 'value'), [
    ('bays', 'tenant_bay_count', 1.5), ('bays', 'tenant_bay_count', 10001),
    ('walt', 'base_rent_weighted_lease_term_years', 101),
    ('restaurants', 'leased_area_occupancy_percent', 20),
])
def test_observation_validates_metric_and_count(criterion, metric, value):
    with pytest.raises(ValidationError):
        DiligenceReviewCreate(**{**REVIEW, 'criterion': criterion},
                             observation={**OBSERVATION, 'metric': metric, 'value': value})


def test_observation_retains_zero_and_does_not_imply_verification():
    result = DiligenceReviewCreate(**REVIEW, observation={**OBSERVATION, 'value': 0})
    assert result.observation.value == 0
    assert result.observation.scope == 'partial'


def test_observation_survives_review_and_export_without_overriding_unknown(client):
    headers = register(client, 'observation@example.com')
    deal = client.post('/deals', headers=headers, json={'name': 'Observed fixture'}).json()
    base = f"/deals/{deal['id']}"
    document = client.post(base + '/document-excerpts', headers=headers, json=PAYLOAD).json()
    evidence = client.get(base + f"/documents/{document['id']}/excerpt", headers=headers).json()['evidence']
    payload = {**REVIEW, 'document_id': document['id'],
               'expected_text_sha256': evidence['text_sha256'], 'observation': OBSERVATION}
    saved = client.post(base + '/diligence-reviews', headers=headers, json=payload)
    assert saved.status_code == 201, saved.text
    snapshot = saved.json()['snapshot']
    assert snapshot['observation'] == OBSERVATION
    assert snapshot['independently_verified'] is False
    assert snapshot['evidence'] == evidence
    invalid = client.post(base + '/diligence-reviews', headers=headers,
                          json={**payload, 'criterion': 'restaurants'})
    assert invalid.status_code == 422
    reviews = client.get(base + '/diligence-reviews', headers=headers).json()['items']
    assert len(reviews) == 1
    assert reviews[0]['snapshot'] == snapshot
    screened = client.get(base + '/acquisition-screen?profile=small_bay_retail', headers=headers)
    assert screened.status_code == 200, screened.text
    occupancy = next(c for c in screened.json()['criteria'] if c['key'] == 'occupancy')
    assert occupancy['status'] == 'unknown'
    assert occupancy['reviewed_observations'][0]['observation'] == OBSERVATION
    assert occupancy['reviewed_observations'][0]['changes_screening_result'] is False
    assert 'unverified and do not change screening status' in occupancy['reason']
    assert screened.json()['reviewed_observations']['items'][0]['criterion'] == 'occupancy'
    exported = client.post(base + '/acquisition-screen/export?profile=small_bay_retail', headers=headers)
    assert exported.status_code == 200, exported.text
    result = exported.json()
    assert result['diligence_reviews']['items'][0]['snapshot']['observation'] == OBSERVATION
    exported_occupancy = next(c for c in result['screen']['criteria'] if c['key'] == 'occupancy')
    assert exported_occupancy['status'] == 'unknown'
    assert exported_occupancy['reviewed_observations'][0]['observation'] == OBSERVATION
