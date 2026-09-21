import pytest
from pydantic import ValidationError

from app.schemas.buy_box import AcquisitionCriteria
from app.services.rate_limiter import limiter

CRITERIA = dict(profile="small_multifamily", market_city="Columbus", market_state="OH",
                min_price=1000000, max_price=3000000, min_size=10, max_size=20,
                min_year_built=1980)


@pytest.mark.parametrize("changes", [
    {"min_price": 4000000}, {"min_size": 21}, {"market_city": "  "},
    {"max_price": float("inf")}, {"min_size": True}, {"profile": "office"},
    {"version": 2}, {"unknown": 1},
])
def test_invalid_criteria_rejected(changes):
    with pytest.raises(ValidationError):
        AcquisitionCriteria(**(CRITERIA | changes))


def test_persisted_criteria_drive_scoped_screen_and_export(client, db):
    from app.models.organization_membership import MemberRole, OrganizationMembership

    limiter.clear()
    def register(email):
        response = client.post('/auth/register', json={
            'email': email, 'password': 'CorrectHorseBattery42',
            'full_name': 'Criteria Test', 'organization_name': email,
        })
        assert response.status_code == 201, response.text
        return {'Authorization': f"Bearer {response.json()['access_token']}"}
    try:
        headers = register('criteria@example.com')
        response = client.post('/buy-box', headers=headers, json={'acquisition_criteria': CRITERIA})
        assert response.status_code == 201, response.text
        box = response.json()
        assert box['acquisition_criteria']['min_size'] == 10
        listing = client.get('/buy-box', headers=headers).json()
        assert listing[0]['acquisition_criteria'] == box['acquisition_criteria']
        deal = client.post('/deals', headers=headers, json={
            'name': 'Criteria fixture', 'city': 'Columbus', 'state': 'OH',
            'units': 12, 'asking_price': 2000000, 'year_built': 1990,
        }).json()
        url = f"/deals/{deal['id']}/acquisition-screen"
        assert client.get(f"/deals/{deal['id']}/match-buy-boxes", headers=headers).json()['matches'] == []
        result = client.get(url, headers=headers, params={'buy_box_id': box['id']})
        assert result.status_code == 200, result.text
        assert result.json()['counts']['pass'] == 4
        assert result.json()['criteria_snapshot'] == box['acquisition_criteria']
        assert client.get(url, headers=headers).json()['criteria'][0]['status'] == 'fail'
        exported = client.post(url + '/export', headers=headers, params={'buy_box_id': box['id']})
        assert exported.status_code == 200, exported.text
        assert exported.json()['screen']['buy_box_id'] == box['id']
        assert exported.json()['target_market'] == {'city': 'Columbus', 'state': 'OH'}
        other = register('criteria-other@example.com')
        assert client.get('/buy-box', headers=other).json() == []
        foreign_box = client.post('/buy-box', headers=other, json={'acquisition_criteria': CRITERIA}).json()
        assert client.get(url, headers=headers, params={'buy_box_id': foreign_box['id']}).status_code == 404
        assert client.post(url + '/export', headers=headers, params={'buy_box_id': foreign_box['id']}).status_code == 404
        legacy = client.post('/buy-box', headers=headers, json={'min_price': 100}).json()
        assert client.get(url, headers=headers, params={'buy_box_id': legacy['id']}).status_code == 422
        member = db.query(OrganizationMembership).filter_by(organization_id=box['organization_id']).one()
        member.role = MemberRole.viewer
        db.commit()
        assert client.post('/buy-box', headers=headers, json={'acquisition_criteria': CRITERIA}).status_code == 403
    finally:
        limiter.clear()
