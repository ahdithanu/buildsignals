from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.models.permit_geocode import PermitGeocode
from app.services import sf_geocoding as geo
from app.services.demo_access import DEMO_ORG_ID, demo_read_only
from app.services.demo_geocoding import request_url as demo_request_url
from app.utils.org_scope import RequestContext, reset_current_context, set_current_context
from tests.test_parcel_reference import fixture_records


def inputs():
    permit = SimpleNamespace(id="permit", source_id="source", organization_id="default-org",
        address="100 MARKET ST", city="San Francisco", state="CA", postal_code="94103",
        is_active=True, latitude=None, longitude=None)
    source = SimpleNamespace(id="source", organization_id="default-org", key=geo.SOURCE_KEY,
        base_url=geo.SOURCE_URL, is_active=True)
    response = {"result": {"addressMatches": [{"matchedAddress": "100 MARKET ST, SAN FRANCISCO, CA, 94103",
        "addressComponents": {"city": "SAN FRANCISCO", "state": "CA", "zip": "94103"},
        "coordinates": {"x": -122.4, "y": 37.79}}]}}
    return permit, source, response


def stored(db):
    source, _, _, _, permit = fixture_records(db)
    source.key, source.base_url, source.record_type = geo.SOURCE_KEY, geo.SOURCE_URL, "permit"
    permit.address, permit.city, permit.state, permit.postal_code = "100 MARKET ST", "San Francisco", "CA", "94103"
    db.flush()
    return permit, source, inputs()[2]


def test_strict_sf_match_and_encoded_request():
    permit, source, response = inputs()
    assert geo.validated_match(permit, source, response)["latitude"] == 37.79
    assert "address=100+MARKET+ST%2C+San+Francisco%2C+CA+94103" in geo.request_url(permit, source)
    with pytest.raises(ValueError):
        demo_request_url(permit)


@pytest.mark.parametrize("response", [None, [], {}, {"result": None}, {"result": []},
    {"result": {"addressMatches": None}}, {"result": {"addressMatches": [None]}}])
def test_malformed_provider_responses_are_not_matches(response):
    permit, source, _ = inputs()
    assert geo.validated_match(permit, source, response) is None


@pytest.mark.parametrize("path,value", [
    (("coordinates", "x"), True), (("coordinates", "y"), float("nan")),
    (("coordinates", "x"), float("inf")), (("coordinates", "x"), -83),
    (("coordinates", "y"), 38), (("addressComponents", "city"), "Oakland"),
    (("addressComponents", "zip"), "94104"), (("addressComponents", "state"), "OH"),
    (("matchedAddress",), "200 MARKET ST, SAN FRANCISCO, CA, 94103"),
    (("matchedAddress",), "100 MARKET ST, OAKLAND, CA, 94103"),
])
def test_rejects_conflicting_or_invalid_matches(path, value):
    permit, source, response = inputs()
    row = response["result"]["addressMatches"][0]
    if len(path) == 2:
        row[path[0]][path[1]] = value
    else:
        row[path[0]] = value
    assert geo.validated_match(permit, source, response) is None


def test_ambiguous_match_is_not_resolved_by_first_result():
    permit, source, response = inputs()
    response["result"]["addressMatches"] *= 2
    assert geo.validated_match(permit, source, response) is None


@pytest.mark.parametrize("target,field,value", [
    ("permit", "organization_id", DEMO_ORG_ID), ("permit", "city", "Oakland"),
    ("permit", "postal_code", "94601"), ("permit", "postal_code", None),
    ("permit", "state", "OH"), ("permit", "is_active", False),
    ("source", "organization_id", "foreign"), ("source", "key", "unreviewed"),
    ("source", "base_url", "https://example.invalid"), ("source", "is_active", False),
])
def test_request_requires_exact_tenant_and_reviewed_sf_scope(target, field, value):
    permit, source, _ = inputs()
    setattr(permit if target == "permit" else source, field, value)
    with pytest.raises(ValueError):
        geo.request_url(permit, source)


def test_persists_derived_evidence_without_changing_source(db):
    permit, source, response = stored(db)
    raw_id, original_address = permit.latest_raw_record_id, permit.address
    assert geo.save_match(db, permit, response, geo.request_url(permit, source))
    db.flush()
    row = db.query(PermitGeocode).one()
    assert (permit.latitude, permit.longitude) == (None, None)
    assert permit.latest_raw_record_id == raw_id and permit.address == original_address
    assert row.source_url == geo.GEOCODER_URL  # No address query is retained in URLs.
    assert row.address_hash == geo.address_hash(permit)
    assert geo.is_current_geocode(permit, source, row)
    observed = row.observed_at
    assert geo.save_match(db, permit, response, geo.request_url(permit, source))
    assert db.query(PermitGeocode).count() == 1 and row.observed_at == observed
    permit.address = "200 MARKET ST"
    assert not geo.is_current_geocode(permit, source, row)


def test_scope_demo_and_native_coordinate_guards_precede_writes(db):
    permit, source, response = stored(db)
    token = set_current_context(RequestContext("foreign", "viewer"))
    try:
        with pytest.raises(ValueError):
            geo.save_match(db, permit, response, "not-a-request")
    finally:
        reset_current_context(token)
    demo_token = demo_read_only.set(True)
    try:
        with pytest.raises(PermissionError):
            geo.save_match(db, permit, response, geo.request_url(permit, source))
    finally:
        demo_read_only.reset(demo_token)
    permit.latitude = 37.79
    assert not geo.save_match(db, permit, response, geo.request_url(permit, source))
    assert db.query(PermitGeocode).count() == 0


def test_sql_address_hash_matches_python_and_postgresql_uses_native_hash(db):
    permit, _, _ = stored(db)
    permit.address = "100 CA\u00d1ADA ST"
    db.flush()
    assert db.scalar(select(geo.sql_address_hash(db)).where(type(permit).id == permit.id)) == geo.address_hash(permit)
    expression = geo.sql_address_hash(SimpleNamespace(get_bind=lambda: SimpleNamespace(dialect=postgresql.dialect())))
    compiled = str(expression.compile(dialect=postgresql.dialect()))
    assert "sha256(convert_to(" in compiled and "encode(" in compiled


def test_expired_future_or_wrong_provenance_geocodes_are_not_current(db):
    permit, source, response = stored(db)
    geo.save_match(db, permit, response, geo.request_url(permit, source))
    db.flush()
    row = db.query(PermitGeocode).one()
    now = datetime.now(timezone.utc)
    original = deepcopy(row.observed_at)
    for value in (now - timedelta(days=91), now + timedelta(hours=1)):
        row.observed_at = value
        assert not geo.is_current_geocode(permit, source, row, now=now)
    row.observed_at = original
    row.benchmark = "unknown"
    assert not geo.is_current_geocode(permit, source, row)
