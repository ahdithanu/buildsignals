import pytest

from scripts.franklin_parcel_qualification import county_reference, qualify_sample


@pytest.mark.parametrize("reference", [None, 10066782, "010-066782", "01006678200", " 010066782", "01006678X"])
def test_rejects_unsupported_namespace(reference):
    assert county_reference(reference) is None


def test_preserves_leading_zero():
    assert county_reference("010066782") == "010-066782"


def test_sample_counts_and_no_acceptance():
    permits = [
        {"parcel_id": "010000001", "address": "55 E STATE ST"},
        {"parcel_id": "010000002", "address": "1066 NORTON RD"},
        {"parcel_id": "010000003", "address": "ONE ST"},
        {"parcel_id": "010000004", "address": "OTHER ST"},
        {"parcel_id": "010000005", "address": None},
        {"parcel_id": None},
    ]
    rows = [
        ("010-000001", "55 E STATE ST"),
        ("010-000002", "1058 - 1110 NORTON RD"),
        ("010-000003", "ONE ST"), ("010-000003", "ONE ST"),
        ("010-000005", "FIVE ST"),
    ]
    response = {"features": [{"attributes": {"PARCELID": key, "SITEADDRESS": address}}
                             for key, address in rows]}
    report = qualify_sample(permits, response)
    assert report["evaluated_permits"] == 6
    assert all(value == 1 for value in report["counts"].values())
    assert report["identity_verified"] is False
    assert report["production_eligible"] is False


@pytest.mark.parametrize("response", [
    {"error": {"code": 403}}, {"features": [], "exceededTransferLimit": True},
    {}, {"features": [{"attributes": {}}]},
])
def test_failure_is_not_zero_matches(response):
    with pytest.raises(ValueError):
        qualify_sample([], response)
