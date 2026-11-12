"""SF location eligibility on migrated, restricted-role disposable PostgreSQL."""
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import sessionmaker

from app import config
from app.db import _set_rls_org
from app.models.ingestion import IngestionRun, IngestionSource, PermitRecord, RawSourceRecord
from app.models.organization import Organization
from app.models.permit_geocode import PermitGeocode
from app.services import sf_geocoding as geo
from app.services.demo_access import demo_read_only
from app.services.map_readiness import map_readiness
from app.services.map_signals import list_map_signals
from app.utils.org_scope import (
    RequestContext,
    get_org_id,
    reset_current_context,
    set_current_context,
)

URL = os.environ.get("TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(
    not URL, reason="Requires migrated, restricted-role local PostgreSQL",
)


@pytest.fixture
def pg_scope(monkeypatch):
    monkeypatch.setattr(config, "SF_DERIVED_LOCATIONS_ENABLED", True)
    org_id, other_org_id = str(uuid4()), str(uuid4())
    token = set_current_context(RequestContext(org_id, "sf-map-postgres-test"))
    demo_token = demo_read_only.set(False)
    engine = create_engine(URL)
    factory = sessionmaker(bind=engine)
    event.listen(factory, "after_begin", _set_rls_org)
    try:
        assert engine.dialect.name == "postgresql"
        with factory() as db:
            try:
                role = db.execute(text(
                    "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user"
                )).one()
                assert not role.rolsuper and not role.rolbypassrls
                policy = db.execute(text(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                    "WHERE oid='permit_geocodes'::regclass"
                )).one()
                assert policy.relrowsecurity and policy.relforcerowsecurity
                for identity in (org_id, other_org_id):
                    db.add(Organization(id=identity, name="SF map test", slug=f"sf-map-{identity}"))
                db.flush()
                yield db, org_id, other_org_id
            finally:
                db.rollback()
    finally:
        event.remove(factory, "after_begin", _set_rls_org)
        engine.dispose()
        demo_read_only.reset(demo_token)
        reset_current_context(token)


@contextmanager
def _as_org(db, org_id):
    # Change tenant inside the same rollback-only transaction, not via a commit.
    db.flush()
    previous_org = get_org_id()
    token = set_current_context(RequestContext(org_id, "sf-map-postgres-test"))
    try:
        db.execute(text("SELECT set_config('app.current_org', :org, true)"), {"org": org_id})
        yield
        db.flush()
    finally:
        reset_current_context(token)
        db.execute(text("SELECT set_config('app.current_org', :org, true)"), {"org": previous_org})


def _source(db, org_id):
    source = IngestionSource(
        organization_id=org_id, key=geo.SOURCE_KEY, name="Synthetic SF permits",
        adapter="socrata", record_type="permit", base_url=geo.SOURCE_URL, is_active=True,
    )
    db.add(source)
    db.flush()
    run = IngestionRun(organization_id=org_id, source_id=source.id, status="completed")
    db.add(run)
    db.flush()
    return source, run


def _permit(db, source, run, *, address="100 MARKET ST"):
    identity = str(uuid4())
    raw = RawSourceRecord(
        organization_id=source.organization_id, source_id=source.id, run_id=run.id,
        external_record_id=identity, content_hash="a" * 64,
        record_type="permit", payload={"synthetic": True},
    )
    db.add(raw)
    db.flush()
    permit = PermitRecord(
        organization_id=source.organization_id, source_id=source.id,
        latest_raw_record_id=raw.id, external_record_id=identity,
        normalization_hash="b" * 64, address=address, city="San Francisco",
        state="CA", postal_code="94103", is_active=True,
        source_url="https://data.sf.gov/d/i98e-djp9",
    )
    db.add(permit)
    db.flush()
    return permit


def _estimate(db, permit):
    row = PermitGeocode(
        organization_id=permit.organization_id, permit_id=permit.id,
        address_hash=geo.address_hash(permit), latitude=37.79, longitude=-122.4,
        matched_address=f"{permit.address}, SAN FRANCISCO, CA, 94103",
        benchmark=geo.BENCHMARK, source_url=geo.GEOCODER_URL,
        response_hash="c" * 64, observed_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.flush()
    return row


@pytest.mark.parametrize("address,city,state,postal_code", [
    ("100 MARKET ST", "San Francisco", "CA", "94103"),
    ("100 CA\u00d1ADA ST", "San Francisco", "CA", "94103"),
    ("100 CAN\u0303ADA ST \U0001f3e2", "San Francisco", "CA", "94103"),
    (None, None, None, None),
])
def test_postgres_native_address_sha_matches_python(pg_scope, address, city, state, postal_code):
    db, org_id, _ = pg_scope
    source, run = _source(db, org_id)
    permit = _permit(db, source, run, address=address)
    permit.city, permit.state, permit.postal_code = city, state, postal_code
    db.flush()
    expression = geo.sql_address_hash(db)
    assert "sha256(convert_to(" in str(expression.compile(dialect=db.get_bind().dialect))
    result = db.scalar(select(expression).where(PermitRecord.id == permit.id))
    assert result == geo.address_hash(permit)
    assert len(result) == 64


def test_postgres_current_and_stale_estimates_agree_with_readiness_and_flag(pg_scope, monkeypatch):
    db, org_id, _ = pg_scope
    source, run = _source(db, org_id)
    current = _permit(db, source, run, address="100 CA\u00d1ADA ST")
    stale = _permit(db, source, run)
    _estimate(db, current)
    stale_geocode = _estimate(db, stale)
    old_hash = stale_geocode.address_hash
    stale.address = "200 MARKET ST"
    db.flush()
    assert old_hash != geo.address_hash(stale)

    items = list_map_signals(db, state="CA")["items"]
    assert [item["id"] for item in items] == [current.id]
    assert items[0]["location_method"] == geo.LOCATION_METHOD
    assert (items[0]["latitude"], items[0]["longitude"]) == (37.79, -122.4)
    assert items[0]["source_url"] == current.source_url
    assert not {"matched_address", "address_hash", "response_hash", "geocoder_url"} & items[0].keys()
    counts = map_readiness(db)
    assert counts["permits"] == 2
    assert counts["source_geocoded_permits"] == 0
    assert counts["derived_geocoded_permits"] == counts["geocoded_permits"] == len(items) == 1
    assert counts["geocoded_parcels"] == counts["verified_available_parcels"] == 0
    assert (current.latitude, current.longitude) == (None, None)

    monkeypatch.setattr(config, "SF_DERIVED_LOCATIONS_ENABLED", False)
    assert list_map_signals(db)["items"] == []
    counts = map_readiness(db)
    assert counts["permits"] == 2
    assert counts["source_geocoded_permits"] == counts["derived_geocoded_permits"] == 0
    assert counts["geocoded_permits"] == 0


def test_postgres_native_coordinates_win_without_double_counting(pg_scope, monkeypatch):
    db, org_id, _ = pg_scope
    source, run = _source(db, org_id)
    permit = _permit(db, source, run)
    _estimate(db, permit)
    permit.latitude, permit.longitude = 37.78, -122.41
    db.flush()
    for enabled in (True, False):
        monkeypatch.setattr(config, "SF_DERIVED_LOCATIONS_ENABLED", enabled)
        items = list_map_signals(db)["items"]
        assert len(items) == 1
        assert items[0]["id"] == permit.id
        assert items[0]["location_method"] == "source_coordinate"
        assert (items[0]["latitude"], items[0]["longitude"]) == (37.78, -122.41)
        counts = map_readiness(db)
        assert counts["source_geocoded_permits"] == counts["geocoded_permits"] == 1
        assert counts["derived_geocoded_permits"] == 0


def test_postgres_forced_rls_hides_foreign_geocodes_without_app_filters(pg_scope):
    db, org_id, other_org_id = pg_scope
    source, run = _source(db, org_id)
    permit = _permit(db, source, run)
    own_geocode = _estimate(db, permit)
    with _as_org(db, other_org_id):
        foreign_source, foreign_run = _source(db, other_org_id)
        foreign_permit = _permit(db, foreign_source, foreign_run)
        foreign_geocode = _estimate(db, foreign_permit)
        assert db.execute(text(
            "SELECT id FROM permit_geocodes WHERE id=:id"
        ), {"id": foreign_geocode.id}).scalar_one() == foreign_geocode.id
        assert db.execute(text(
            "SELECT id FROM permit_geocodes WHERE id=:id"
        ), {"id": own_geocode.id}).first() is None

    # Neither query supplies an organization predicate or uses active_query.
    assert db.scalars(select(PermitGeocode.id)).all() == [own_geocode.id]
    assert db.execute(text(
        "SELECT id FROM permit_geocodes WHERE id=:id"
    ), {"id": foreign_geocode.id}).first() is None
    assert [item["id"] for item in list_map_signals(db)["items"]] == [permit.id]
    counts = map_readiness(db)
    assert counts["permits"] == counts["derived_geocoded_permits"] == 1
