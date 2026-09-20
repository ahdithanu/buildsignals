import pytest
from fastapi import HTTPException, Response

from app.models.deal import Deal
from app.routes.buy_box import acquisition_screen
from app.services.acquisition_screening import screen_acquisition
from app.utils.org_scope import RequestContext, reset_current_context, set_current_context


def test_missing_data_is_unknown_not_failure():
    result = screen_acquisition(Deal(id='test', name='Unknown'), 'small_bay_retail')
    assert result['counts']['fail'] == result['counts']['pass'] == 0
    assert result['status'] == 'needs_diligence'
    assert result['evidence_verified'] is False


@pytest.mark.parametrize('units,expected', [(15, 'fail'), (16, 'pass'), (32, 'pass'), (33, 'fail'), (None, 'unknown'), (0, 'unknown')])
def test_multifamily_boundaries(units, expected):
    result = screen_acquisition(Deal(id='d', name='Test', units=units), 'small_multifamily')
    assert result['criteria'][0]['status'] == expected


def test_retail_numeric_fit_never_implies_verified_acquisition():
    deal = Deal(id='d', name='Retail', sq_ft=15000, year_built=1990, asking_price=2500000,
                city='Columbus', state='OH')
    result = screen_acquisition(deal, 'small_bay_retail', 'columbus', 'oh')
    assert result['counts']['pass'] == 4
    assert result['counts']['unknown'] > 10
    assert result['status'] == 'needs_diligence'
    assert result['criteria'][0]['basis'] == 'deal.sq_ft'


def test_market_does_not_substring_match():
    deal = Deal(id='d', name='Test', city='Columbus', state='OH')
    result = screen_acquisition(deal, 'small_multifamily', 'Colum', 'OH')
    assert next(c for c in result['criteria'] if c['key'] == 'market')['status'] == 'fail'


def test_route_requires_auth(client):
    assert client.get('/deals/missing/acquisition-screen').status_code == 401


def test_invalid_profile_rejected():
    with pytest.raises(ValueError):
        screen_acquisition(Deal(name='test'), 'unsupported')


def test_deal_screen_is_tenant_scoped_and_excludes_deleted(db):
    from datetime import datetime, timezone

    deal = Deal(id='screen-deal', organization_id='default-org', name='Test')
    db.add(deal)
    db.flush()
    def read():
        return acquisition_screen(deal.id, Response(), 'small_multifamily', None, None, db)
    assert read()['deal_id'] == deal.id
    token = set_current_context(RequestContext('other-org', 'other-user'))
    try:
        with pytest.raises(HTTPException) as exc:
            read()
        assert exc.value.status_code == 404
    finally:
        reset_current_context(token)
    deal.deleted_at = datetime.now(timezone.utc)
    db.flush()
    with pytest.raises(HTTPException) as exc:
        read()
    assert exc.value.status_code == 404
