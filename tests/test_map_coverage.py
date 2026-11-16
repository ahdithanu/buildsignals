"""Stored-inventory coverage, independent of catalog admission and map pin limits."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import event

from app import config
from app.main import app
from app.models.ingestion import IngestionRun, IngestionSource, PermitRecord, RawSourceRecord
from app.models.organization import Organization
from app.models.organization_membership import MemberRole, OrganizationMembership
from app.models.parcel import ParcelRecord
from app.models.planning import PlanningRecord
from app.models.user import User
from app.services.map_coverage import get_map_coverage, list_map_records
from app.services.map_signals import list_map_signals
from app.services.security import create_access_token
from app.utils.org_scope import RequestContext, reset_current_context, set_current_context
from tests.test_demo import demo as demo  # noqa: F401
from tests.test_demo import headers as demo_headers
from tests.test_sf_map_locations import sf_location as sf_location  # noqa: F401


def inventory_writer(db, org="default-org"):
    if db.get(Organization, org) is None:
        db.add(Organization(id=org, name="Synthetic coverage", slug=f"coverage-{org}"))
        db.flush()
    sources = {}

    def add(kind="permit", **values):
        if kind not in sources:
            source = IngestionSource(
                organization_id=org, key=f"coverage-{kind}", name="Synthetic coverage",
                adapter="manual", record_type=kind,
            )
            db.add(source)
            db.flush()
            run = IngestionRun(organization_id=org, source_id=source.id, status="completed")
            db.add(run)
            db.flush()
            sources[kind] = source, run
        source, run = sources[kind]
        identity = values.pop("id", str(uuid4()))
        raw = RawSourceRecord(
            organization_id=org, source_id=source.id, run_id=run.id,
            external_record_id=f"private-provider-{identity}", record_type=kind,
            content_hash="a" * 64, payload={"private": "DO_NOT_EXPOSE_RAW"},
        )
        db.add(raw)
        db.flush()
        common = dict(id=identity, organization_id=org, source_id=source.id,
                      latest_raw_record_id=raw.id, state="FL", jurisdiction="Orlando",
                      address="100 Synthetic Rd", city="Orlando", latitude=28.5, longitude=-81.3)
        common.update(values)
        if kind == "parcel":
            row = ParcelRecord(external_parcel_id=raw.external_record_id, **common)
        else:
            common.update(external_record_id=raw.external_record_id, normalization_hash="b" * 64)
            row = (PermitRecord(project_name="Synthetic permit", **common) if kind == "permit"
                   else PlanningRecord(title="Synthetic planning", event_type="hearing", **common))
        db.add(row)
        db.flush()
        return row

    return add


@pytest.fixture
def records(db, monkeypatch):
    monkeypatch.setattr(config, "SF_DERIVED_LOCATIONS_ENABLED", False)

    def forbidden(*_args, **_kwargs):
        pytest.fail("Coverage must not call external sources or models")

    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    monkeypatch.setattr("app.services.llm_client.get_default_llm_client", forbidden)
    return inventory_writer(db)


def _headers(db, org="default-org"):
    identity = str(uuid4())
    db.add(User(id=identity, email=f"{identity}@example.invalid", full_name="Coverage viewer",
                password_hash="!nologin", is_active=True))
    db.flush()
    db.add(OrganizationMembership(organization_id=org, user_id=identity,
                                  role=MemberRole.viewer, is_default=True))
    db.commit()
    return {"Authorization": "Bearer " + create_access_token(user_id=identity, org_id=org)}


def test_totals_are_complete_beyond_pin_limit_and_do_not_require_ranked_parcels(db, records):
    for index in range(105):
        records("parcel", id=f"parcel-{index:03}")
    records("permit", latitude=None, longitude=None)
    records("planning", state="TX", jurisdiction="Austin")
    result = get_map_coverage(db, limit=1)
    assert result.totals.model_dump() == dict(
        permit_count=1, planning_count=1, parcel_count=105, mapped_count=106, unmapped_count=1,
    )
    assert len(result.groups) == 1 and result.total_groups == 2 and result.truncated
    assert result.next_offset == 1 and result.previous_offset is None
    assert {row.state for row in result.states} == {"FL", "TX"}
    assert sum(row.parcel_count for row in result.states) == 105
    assert result.measured_at.tzinfo is not None


def test_states_are_global_but_totals_and_groups_honor_state_and_kind(db, records):
    records("permit", state="FL")
    records("parcel", state="TX")
    records("planning", state="CA")
    result = get_map_coverage(db, state=" fl ", kind="permit")
    assert {row.state for row in result.states} == {"FL", "TX", "CA"}
    assert result.totals.permit_count == result.totals.mapped_count == 1
    assert result.totals.parcel_count == result.totals.planning_count == 0
    assert result.grouping == "jurisdiction" and result.total_groups == 1
    assert result.groups[0].jurisdiction == "Orlando"
    assert get_map_coverage(db, state="NJ").groups == []


def test_all_51_state_codes_and_unknown_remain_in_global_overview(db, records):
    codes = "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()
    for code in codes:
        records(state=code)
    records(state=None, latitude=None, longitude=None)
    result = get_map_coverage(db, state="FL", kind="parcel", limit=1, offset=100000)
    assert len(result.states) == 52
    assert {row.state for row in result.states} == set(codes) | {"__unknown__"}
    assert result.totals.permit_count == 0 and result.groups == []


def test_unknown_state_and_jurisdiction_are_bounded_observed_buckets(db, records):
    for state in (None, "", " ", "nonsense", "PR", "California"):
        records(state=state, jurisdiction=None, latitude=None, longitude=None)
    records(state=" dc ", jurisdiction="  ")
    records(state="fl", jurisdiction="Orlando")
    result = get_map_coverage(db)
    assert {row.state for row in result.states} == {"__unknown__", "DC", "FL"}
    unknown = next(row for row in result.states if row.state == "__unknown__")
    assert unknown.permit_count == unknown.unmapped_count == 6
    assert unknown.latitude is unknown.longitude is None
    drill = get_map_coverage(db, state="__unknown__")
    assert drill.groups[0].jurisdiction == "__unknown__"
    assert list_map_records(db, state="__unknown__", jurisdiction="__unknown__").total == 6


def test_jurisdiction_groups_are_db_aggregated_paginated_and_not_city_inferred(db, records):
    for index in range(105):
        records(jurisdiction=f"Authority {index:03}", city="Not a jurisdiction")
    first = get_map_coverage(db, state="FL", limit=100)
    last = get_map_coverage(db, state="FL", limit=100, offset=100)
    assert first.total_groups == last.total_groups == 105
    assert len(first.groups) == 100 and len(last.groups) == 5
    assert first.next_offset == 100 and last.previous_offset == 0 and last.next_offset is None
    assert {row.id for row in first.groups}.isdisjoint(row.id for row in last.groups)
    assert all(row.label != "Not a jurisdiction" for row in first.groups)
    assert first.totals.permit_count == last.totals.permit_count == 105


def test_group_coordinates_are_means_of_only_eligible_stored_points(db, records):
    records(latitude=20, longitude=-80)
    records("planning", latitude=40, longitude=-100)
    records("parcel", latitude=None, longitude=-100)
    group = get_map_coverage(db).groups[0]
    assert (group.latitude, group.longitude) == (30, -90)
    assert group.mapped_count == 2 and group.unmapped_count == 1


@pytest.mark.parametrize("kind", ["permit", "planning", "parcel"])
@pytest.mark.parametrize("latitude,longitude", [
    (None, None), (None, -81), (28, None), (86, -81), (-86, -81),
    (28, 181), (28, -181), (float("inf"), -81), (28, float("nan")),
])
def test_missing_invalid_coordinates_remain_unmapped_inventory(db, records, kind, latitude, longitude):
    record = records(kind, latitude=latitude, longitude=longitude)
    coverage = get_map_coverage(db)
    assert coverage.totals.mapped_count == 0 and coverage.totals.unmapped_count == 1
    assert coverage.groups[0].latitude is coverage.groups[0].longitude is None
    item, = list_map_records(db).items
    assert item.id == record.id and item.latitude is item.longitude is item.location_method is None


@pytest.mark.parametrize("kind", ["permit", "parcel"])
@pytest.mark.parametrize("field", ["is_active", "retired_at"])
def test_retired_and_inactive_records_are_not_current_inventory(db, records, kind, field):
    records(kind, **{field: False if field == "is_active" else datetime.now(timezone.utc)})
    assert get_map_coverage(db).totals.mapped_count == 0
    assert get_map_coverage(db).states == []
    assert list_map_records(db).total == 0


def test_paused_sources_do_not_hide_native_inventory(db, records):
    for kind in ("permit", "planning", "parcel"):
        row = records(kind)
        db.get(IngestionSource, row.source_id).is_active = False
    db.flush()
    assert get_map_coverage(db).totals.mapped_count == 3
    assert list_map_records(db).total == 3


def test_stable_record_pagination_includes_unmapped_and_exact_jurisdictions(db, records):
    a = records("permit", id="same-id", jurisdiction=" Orlando ", latitude=None, longitude=None)
    b = records("planning", id="same-id", jurisdiction="orlando")
    records("parcel", id="same-id", jurisdiction="Orlando County")
    records("parcel", id="unknown-jurisdiction", jurisdiction=" ")
    first = list_map_records(db, jurisdiction=" ORLANDO ", limit=1)
    last = list_map_records(db, jurisdiction="orlando", limit=1, offset=1)
    assert first.total == last.total == 2
    assert {first.items[0].kind, last.items[0].kind} == {"permit", "planning"}
    assert {first.items[0].id, last.items[0].id} == {a.id, b.id}
    assert first.next_offset == 1 and last.previous_offset == 0 and last.next_offset is None
    assert list_map_records(db, jurisdiction="__unknown__").total == 1
    assert list_map_records(db, offset=100000).items == []


def test_record_totals_and_unmapped_tail_are_not_truncated_at_100(db, records):
    for index in range(105):
        records("parcel", id=f"parcel-{index:03}",
                latitude=None if index >= 100 else 28.5,
                longitude=None if index >= 100 else -81.3)
    first = list_map_records(db)
    last = list_map_records(db, offset=100)
    assert first.total == last.total == 105
    assert len(first.items) == 100 and len(last.items) == 5
    assert all(row.latitude is row.longitude is None for row in last.items)
    assert {row.id for row in first.items}.isdisjoint(row.id for row in last.items)
    assert last.next_offset is None and last.previous_offset == 0


def test_services_are_tenant_scoped_and_do_not_write_or_materialize_models(db, records):
    records("parcel")
    other = inventory_writer(db, "foreign-coverage")
    other("permit", jurisdiction="PRIVATE_FOREIGN_AUTHORITY")
    db.flush()
    statements, loaded = [], []

    def capture(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    def loading(_target, _context):
        loaded.append(True)

    connection = db.connection()
    event.listen(connection, "before_cursor_execute", capture)
    for model in (PermitRecord, PlanningRecord, ParcelRecord):
        event.listen(model, "load", loading)
    try:
        result = get_map_coverage(db)
        page = list_map_records(db)
    finally:
        event.remove(connection, "before_cursor_execute", capture)
        for model in (PermitRecord, PlanningRecord, ParcelRecord):
            event.remove(model, "load", loading)
    assert result.totals.parcel_count == 1 and result.totals.permit_count == 0
    assert page.total == 1 and not loaded
    assert all(sql.lstrip().upper().startswith(("SELECT", "WITH")) for sql in statements)
    assert any("GROUP BY" in sql.upper() and "LIMIT" in sql.upper() for sql in statements)
    assert "PRIVATE_FOREIGN_AUTHORITY" not in result.model_dump_json()
    assert not db.new and not db.dirty and not db.deleted
    token = set_current_context(RequestContext("no-coverage-org", "viewer"))
    try:
        assert get_map_coverage(db).states == []
        assert list_map_records(db).total == 0
    finally:
        reset_current_context(token)


def test_sf_derived_eligibility_matches_existing_signals(db, sf_location):
    source, permit, geocode = sf_location
    for target, field, invalid in ((None, None, None), (source, "is_active", False),
                                    (geocode, "address_hash", "0" * 64)):
        if target is not None:
            setattr(target, field, invalid)
            db.flush()
        signals = list_map_signals(db, state="CA")["items"]
        result = get_map_coverage(db, state="CA", kind="permit")
        page = list_map_records(db, state="CA", kind="permit")
        assert result.totals.permit_count == page.total == 1
        assert result.totals.mapped_count == len(signals)
        if signals:
            assert page.items[0].location_method == "census_address_range_estimate"
            assert page.items[0].latitude == signals[0]["latitude"]
        else:
            assert page.items[0].latitude is page.items[0].location_method is None
    assert permit.latitude is permit.longitude is None


@pytest.mark.parametrize("endpoint", ["coverage", "records"])
def test_http_authenticated_viewer_readonly_projection_and_filters(client, db, records, endpoint):
    parcel = records("parcel", latitude=None, longitude=None)
    headers = _headers(db)
    assert client.get(f"/acquisition-map/{endpoint}").status_code == 401
    response = client.get(f"/v1/acquisition-map/{endpoint}?kind=parcel&state=fl", headers=headers)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    for private in ("DO_NOT_EXPOSE_RAW", "source_id", "raw_record", "source_url", "private-provider-"):
        assert private not in response.text
    if endpoint == "records":
        assert response.json()["items"][0]["id"] == parcel.id
        parameters = app.openapi()["paths"]["/v1/acquisition-map/records"]["get"]["parameters"]
        assert {parameter["name"] for parameter in parameters if parameter["in"] == "query"} == {
            "state", "kind", "jurisdiction", "limit", "offset",
        }
        assert client.get("/acquisition-map/records?jurisdiction=other", headers=headers).json()["total"] == 0
    for query in ("limit=101", "offset=100001", "offset=-1", "state=ZZ", "state=California", "kind=owner"):
        assert client.get(f"/acquisition-map/{endpoint}?{query}", headers=headers).status_code == 422


def test_http_tenant_context_is_not_selected_by_query_parameters(client, db, records):
    own = records("parcel")
    foreign_writer = inventory_writer(db, "foreign-coverage")
    foreign = foreign_writer("planning", state="TX", jurisdiction="Foreign authority")
    headers = _headers(db)
    other_headers = _headers(db, "foreign-coverage")
    page = client.get("/acquisition-map/records?organization_id=foreign-coverage", headers=headers)
    assert page.status_code == 200 and [row["id"] for row in page.json()["items"]] == [own.id]
    other = client.get("/acquisition-map/records", headers=other_headers)
    assert other.status_code == 200 and [row["id"] for row in other.json()["items"]] == [foreign.id]
    overview = client.get("/acquisition-map/coverage", headers=headers)
    assert [row["state"] for row in overview.json()["states"]] == ["FL"]
    for query in ("jurisdiction=" + "a" * 256, "jurisdiction=%20%20"):
        assert client.get("/acquisition-map/records?" + query, headers=headers).status_code == 422


@pytest.mark.parametrize("endpoint", ["coverage", "records"])
def test_new_routes_remain_demo_denied(client, demo, endpoint):
    assert client.get(f"/acquisition-map/{endpoint}", headers=demo_headers(client)).status_code == 403


@pytest.mark.parametrize("arguments", [
    {"limit": 0}, {"limit": 101}, {"offset": -1}, {"offset": 100001}, {"state": "ZZ"}, {"kind": "owner"},
])
def test_service_bounds_are_enforced_before_queries(db, arguments):
    with pytest.raises(ValueError):
        get_map_coverage(db, **arguments)
    with pytest.raises(ValueError):
        list_map_records(db, **arguments)
