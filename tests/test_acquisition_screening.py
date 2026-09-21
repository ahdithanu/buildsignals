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


@pytest.mark.parametrize('deal_city,deal_state,target_city,target_state', [
    (' ', 'OH', ' ', 'OH'), ('Columbus', ' ', 'Columbus', ' '),
    ('Columbus', 'OH', '\t', 'OH'), (' ', 'OH', 'Columbus', 'OH'),
    ('Columbus', None, 'Columbus', 'OH'),
])
def test_blank_locations_never_pass_or_fail(deal_city, deal_state, target_city, target_state):
    result = screen_acquisition(Deal(city=deal_city, state=deal_state), 'small_multifamily', target_city, target_state)
    criterion = next(c for c in result['criteria'] if c['key'] == 'market')
    assert criterion['status'] == 'unknown'
    assert criterion['basis'] is None


def test_location_trims_and_casefolds_without_changing_identity():
    result = screen_acquisition(Deal(city=' Columbus ', state=' oh '), 'small_multifamily', 'columbus ', 'OH')
    criterion = next(c for c in result['criteria'] if c['key'] == 'market')
    assert criterion['status'] == 'pass'
    assert criterion['value'] == 'Columbus, oh'
    assert result['method_version'] == 'acquisition-screen-v3'


@pytest.mark.parametrize('value', [True, False, '24', '', float('nan'), float('inf'), -1])
def test_unusable_numeric_inputs_are_unknown(value):
    result = screen_acquisition(Deal(units=value), 'small_multifamily')
    criterion = result['criteria'][0]
    assert criterion['status'] == 'unknown'
    assert criterion['value'] is None
    assert criterion['basis'] is None


def test_decimal_price_remains_supported():
    from decimal import Decimal

    result = screen_acquisition(Deal(asking_price=Decimal('2000000')), 'small_multifamily')
    assert next(c for c in result['criteria'] if c['key'] == 'asking_price')['status'] == 'pass'


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
