"""Offline API contract for explicit, evidence-backed search anchor preview."""
from unittest.mock import Mock

import pytest

from app.main import app
from app.schemas.parcel_anchor import NearbyParcelAnchorResponse
from app.utils.auth_deps import get_current_user


def anchor(**changes):
    return {
        'deal_id': 'deal-1', 'anchor_brand_match_id': 'match-1', 'permit_id': 'permit-1',
        'status': 'ready', 'reason': None, 'latitude': 28.46, 'longitude': -81.27,
        'method': 'reviewed_parcel_centroid', 'parcel_id': 'parcel-1',
        'relationship_id': 'relationship-1', 'permit_raw_record_id': 'permit-raw',
        'parcel_raw_record_id': 'parcel-raw', 'permit_normalization_hash': 'a' * 64,
        'parcel_normalization_hash': 'b' * 64, **changes,
    }


def test_preview_requires_authentication(client):
    assert client.get('/deals/deal-1/nearby-parcel-anchors/match-1').status_code == 401


def test_authenticated_preview_is_read_only_and_not_cached(client, monkeypatch):
    preview = Mock(return_value=anchor())
    monkeypatch.setattr('app.routes.parcels.get_deal_parcel_anchor', preview)
    app.dependency_overrides[get_current_user] = lambda: {'org_id': 'default-org', 'role': 'viewer'}
    try:
        response = client.get('/deals/deal-1/nearby-parcel-anchors/match-1')
        assert response.status_code == 200, response.text
        assert response.headers['cache-control'] == 'no-store'
        assert response.json() == anchor()
        assert preview.call_args.kwargs == {'deal_id': 'deal-1', 'brand_match_id': 'match-1'}
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_preview_scope_failure_returns_404(client, monkeypatch):
    monkeypatch.setattr('app.routes.parcels.get_deal_parcel_anchor', Mock(side_effect=LookupError('Signal not found')))
    app.dependency_overrides[get_current_user] = lambda: {'org_id': 'other-org', 'role': 'viewer'}
    try:
        response = client.get('/deals/deal-1/nearby-parcel-anchors/match-1')
        assert response.status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.parametrize('changes', [
    {'latitude': float('nan')}, {'longitude': float('inf')}, {'latitude': 91},
    {'status': 'ready', 'method': None}, {'parcel_raw_record_id': None},
    {'status': 'unavailable'}, {'unexpected': 'field'},
])
def test_anchor_contract_rejects_incomplete_or_unsafe_payload(changes):
    with pytest.raises(ValueError):
        NearbyParcelAnchorResponse.model_validate(anchor(**changes))


def test_native_anchor_needs_no_parcel_evidence():
    native = anchor(method='source_coordinate', parcel_id=None, relationship_id=None,
                    parcel_raw_record_id=None, permit_normalization_hash=None,
                    parcel_normalization_hash=None)
    assert NearbyParcelAnchorResponse.model_validate(native).method == 'source_coordinate'
