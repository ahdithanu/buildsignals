"""Complete stored-permit aggregates, not paginated pins or new source calls."""
from datetime import datetime, timezone
from math import nextafter

import pytest
from pydantic import ValidationError
from sqlalchemy import event

from app import config
from app.models.ingestion import PermitRecord
from app.models.organization_membership import OrganizationMembership
from app.models.parcel import ParcelRecord
from app.models.planning import PlanningRecord
from app.models.user import User
from app.schemas.permit_density import PermitDensityResponse
from app.services.demo_access import (
    DEMO_ORG_ID,
    DEMO_USER_ID,
    demo_path_allowed,
    demo_read_only,
)
from app.services.map_coverage import STATE_LABELS
from app.services.permit_density import CELL_DEGREES, MAX_CELLS, get_permit_density
from app.services.security import create_access_token
from app.utils.org_scope import RequestContext, reset_current_context, set_current_context
from tests.test_demo import demo as demo  # noqa: F401
from tests.test_demo import headers as demo_headers
from tests.test_map_coverage import _headers, inventory_writer
from tests.test_sf_map_locations import sf_location as sf_location  # noqa: F401


@pytest.fixture
def records(db, monkeypatch):
    monkeypatch.setattr(config, "SF_DERIVED_LOCATIONS_ENABLED", False)

    def forbidden(*_args, **_kwargs):
        pytest.fail("Density must not call providers or models")

    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    monkeypatch.setattr("app.services.llm_client.get_default_llm_client", forbidden)
    return inventory_writer(db)


def assert_complete(result):
    assert result.complete is True
    assert result.measured_at.tzinfo is not None
    assert result.total_permits == result.mapped_permits + result.unmapped_permits
    assert result.mapped_permits == result.source_coordinate_count + result.estimated_count
    assert sum(cell.count for cell in result.cells) == result.mapped_permits
    assert sum(cell.source_coordinate_count for cell in result.cells) == result.source_coordinate_count
    assert sum(cell.estimated_count for cell in result.cells) == result.estimated_count
    assert len(result.cells) <= MAX_CELLS == 2048
    assert result.cell_degrees in CELL_DEGREES
    assert len({cell.id for cell in result.cells}) == len(result.cells)
    for cell in result.cells:
        assert cell.count == cell.source_coordinate_count + cell.estimated_count
        assert cell.south <= cell.latitude <= cell.north
        assert cell.west <= cell.longitude <= cell.east
        assert cell.north - cell.south <= result.cell_degrees + 1e-9
        assert cell.east - cell.west <= result.cell_degrees + 1e-9


def test_complete_inventory_over_100_across_states_and_unmapped(db, records):
    for index in range(121):
        records(state=" fl " if index < 80 else "TX", latitude=28 + index * .05,
                longitude=-100 + index * .1)
    for state in ("FL", "TX", None):
        records(state=state, latitude=None, longitude=None)
    records("planning")
    records("parcel")
    result = get_permit_density(db)
    assert_complete(result)
    assert result.state is None
    assert result.total_permits == 124
    assert result.mapped_permits == result.source_coordinate_count == 121
    assert result.unmapped_permits == 3 and result.estimated_count == 0
    florida = get_permit_density(db, state=" fL ")
    assert_complete(florida)
    assert florida.state == "FL" and florida.total_permits == 81
    assert florida.mapped_permits == 80 and florida.unmapped_permits == 1
    assert get_permit_density(db, state="TX").total_permits == 42


def test_all_state_codes_and_unknown_bucket(db, records):
    for state in STATE_LABELS:
        records(state=state)
    for state in (None, "", " ", "PR", "California", "invalid"):
        records(state=state, latitude=None)
    assert get_permit_density(db).total_permits == 57
    for state in STATE_LABELS:
        result = get_permit_density(db, state=state.lower())
        assert result.state == state and result.total_permits == 1
    unknown = get_permit_density(db, state=" __UnKnOwN__ ")
    assert_complete(unknown)
    assert unknown.state == "__unknown__" and unknown.unmapped_permits == 6


@pytest.mark.parametrize("state", ["", " ", "ZZ", "California", "PR", "FL' OR 1=1", 1, True])
def test_invalid_state_rejected_before_sql(db, state):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Invalid filter reached SQL")

    connection = db.connection()
    event.listen(connection, "before_cursor_execute", forbidden)
    try:
        with pytest.raises(ValueError):
            get_permit_density(db, state=state)
    finally:
        event.remove(connection, "before_cursor_execute", forbidden)


@pytest.mark.parametrize("latitude,longitude", [
    (None, None), (None, -81), (28, None), (86, -81), (-86, -81),
    (28, 181), (28, -181), (-90, 180), (90, 180),
    (float("inf"), -81), (28, float("nan")),
])
def test_invalid_coordinates_remain_in_unmapped_totals(db, records, latitude, longitude):
    records(latitude=latitude, longitude=longitude)
    result = get_permit_density(db)
    assert_complete(result)
    assert result.total_permits == result.unmapped_permits == 1
    assert result.cells == []


@pytest.mark.parametrize("field,value", [
    ("is_active", False), ("retired_at", datetime.now(timezone.utc)),
])
def test_noncurrent_permits_excluded(db, records, field, value):
    records(**{field: value})
    result = get_permit_density(db)
    assert_complete(result)
    assert result.total_permits == 0


def test_grid_aggregates_exact_counts_with_stable_bounds_and_ids(db, records):
    for _ in range(4):
        records(latitude=28.501, longitude=-81.301)
    records(latitude=28.502, longitude=-81.302)
    records(latitude=-28.501, longitude=81.301)
    first = get_permit_density(db)
    second = get_permit_density(db)
    assert_complete(first)
    assert first.cell_degrees == .025
    assert sorted(cell.count for cell in first.cells) == [1, 5]
    assert first.cells == second.cells
    for latitude, longitude in ((28.501, -81.301), (28.502, -81.302), (-28.501, 81.301)):
        assert sum(cell.south <= latitude <= cell.north and cell.west <= longitude <= cell.east
                   for cell in first.cells) == 1


@pytest.mark.parametrize("degrees", CELL_DEGREES)
def test_world_edges_are_bounded_and_counted_once(db, records, monkeypatch, degrees):
    monkeypatch.setattr("app.services.permit_density.CELL_DEGREES", (degrees,))
    for latitude in (-85, 0, 85):
        for longitude in (-180, 0, 180):
            records(latitude=latitude, longitude=longitude)
    records(latitude=nextafter(85, 0), longitude=nextafter(180, 0))
    result = get_permit_density(db)
    assert_complete(result)
    assert result.cell_degrees == degrees
    assert result.total_permits == result.mapped_permits == 10
    assert all(-85 <= cell.south < cell.north <= 85 and
               -180 <= cell.west < cell.east <= 180 for cell in result.cells)


def test_adaptive_grid_never_truncates_and_scans_are_fixed_bounded(db, records):
    template = records(latitude=None, longitude=None)
    rows = [dict(
        id=f"density-grid-{i}-{j}", organization_id=template.organization_id,
        source_id=template.source_id, latest_raw_record_id=template.latest_raw_record_id,
        external_record_id=f"density-grid-{i}-{j}", normalization_hash="c" * 64,
        state="FL", latitude=-84.9 + i * 2, longitude=-179.9 + j * 4,
    ) for i in range(85) for j in range(90)]
    db.execute(PermitRecord.__table__.insert(), rows)
    db.flush()
    statements = []

    def capture(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    connection = db.connection()
    event.listen(connection, "before_cursor_execute", capture)
    try:
        result = get_permit_density(db)
    finally:
        event.remove(connection, "before_cursor_execute", capture)
    assert_complete(result)
    assert result.mapped_permits == len(rows) == 7650
    assert result.total_permits == 7651 and result.unmapped_permits == 1
    assert result.cell_degrees == 8
    assert len(statements) == len(CELL_DEGREES) == 9
    assert all("GROUP BY" in sql.upper() and "LIMIT" in sql.upper() for sql in statements)


@pytest.mark.parametrize("mapped_count,expected_degrees", [(2048, .025), (2049, .05)])
def test_cell_limit_boundary_preserves_unmapped_and_every_mapped_count(
    db, records, mapped_count, expected_degrees,
):
    template = records(latitude=None, longitude=None)
    db.execute(PermitRecord.__table__.insert(), [dict(
        id=f"density-bound-{index}", organization_id=template.organization_id,
        source_id=template.source_id, latest_raw_record_id=template.latest_raw_record_id,
        external_record_id=f"density-bound-{index}", normalization_hash="c" * 64,
        state="FL", latitude=30.001, longitude=-170.001 + index * .03,
    ) for index in range(mapped_count)])
    result = get_permit_density(db)
    assert_complete(result)
    assert result.mapped_permits == mapped_count
    assert result.unmapped_permits == 1 and result.total_permits == mapped_count + 1
    assert result.cell_degrees == expected_degrees
    if mapped_count == 2048:
        assert len(result.cells) == MAX_CELLS


def test_native_inventory_survives_paused_source_and_readonly_connection(db, records):
    permit = records()
    permit.source.is_active = False
    db.commit()
    connection = db.connection()
    connection.exec_driver_sql("PRAGMA query_only = ON")
    try:
        result = get_permit_density(db)
    finally:
        connection.exec_driver_sql("PRAGMA query_only = OFF")
    assert_complete(result)
    assert result.total_permits == result.source_coordinate_count == 1


def test_tenant_isolation_select_only_no_orm_materialization_or_autoflush(db, records):
    own = records()
    inventory_writer(db, "foreign-density")(latitude=10, longitude=10)
    own.project_name = "Pending local edit must not be flushed"
    statements, loaded = [], []

    def capture(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    def loading(_target, _context):
        loaded.append(True)

    connection = db.connection()
    event.listen(connection, "before_cursor_execute", capture)
    event.listen(PermitRecord, "load", loading)
    try:
        result = get_permit_density(db)
        token = set_current_context(RequestContext("foreign-density", "viewer"))
        try:
            foreign = get_permit_density(db)
        finally:
            reset_current_context(token)
    finally:
        event.remove(connection, "before_cursor_execute", capture)
        event.remove(PermitRecord, "load", loading)
    assert_complete(result)
    assert result.total_permits == foreign.total_permits == 1
    assert result.cells != foreign.cells and not loaded
    assert len(statements) == 2
    assert all(sql.lstrip().upper().startswith("SELECT") for sql in statements)
    assert own in db.dirty


@pytest.mark.parametrize("mutation", ["valid", "native", "stale", "foreign", "disabled", "partial"])
def test_coordinate_provenance_and_derived_qualification(db, sf_location, monkeypatch, mutation):
    source, permit, geocode = sf_location
    if mutation == "native":
        permit.latitude, permit.longitude = 37.78, -122.41
    elif mutation == "stale":
        geocode.address_hash = "0" * 64
    elif mutation == "foreign":
        geocode.organization_id = "foreign-org"
    elif mutation == "disabled":
        monkeypatch.setattr(config, "SF_DERIVED_LOCATIONS_ENABLED", False)
    elif mutation == "partial":
        permit.latitude = 37.78
    db.flush()
    result = get_permit_density(db)
    assert_complete(result)
    assert result.total_permits == 1
    assert result.source_coordinate_count == (mutation == "native")
    assert result.estimated_count == (mutation == "valid")
    assert result.unmapped_permits == (mutation not in {"native", "valid"})


def test_mixed_native_and_derived_same_cell_provenance_reconciles(db, sf_location):
    _, _, geocode = sf_location
    inventory_writer(db)(state="CA", latitude=geocode.latitude, longitude=geocode.longitude)
    result = get_permit_density(db, state="ca")
    assert_complete(result)
    assert result.total_permits == result.mapped_permits == 2
    assert result.source_coordinate_count == result.estimated_count == 1
    cell, = result.cells
    assert cell.count == 2 and cell.source_coordinate_count == cell.estimated_count == 1


def test_empty_inventory_and_missing_state(db):
    for state in (None, "NJ"):
        result = get_permit_density(db, state=state)
        assert_complete(result)
        assert result.cells == [] and result.total_permits == 0


def test_api_auth_validation_privacy_and_foreign_query_cannot_select_tenant(client, db, records):
    records()
    inventory_writer(db, "foreign-density")(state="TX")
    headers = _headers(db)
    assert client.get("/v1/acquisition-map/permit-density").status_code == 401
    response = client.get("/v1/acquisition-map/permit-density?organization_id=foreign-density&state=fl",
                          headers=headers)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    result = PermitDensityResponse.model_validate(response.json())
    assert_complete(result)
    assert result.total_permits == 1 and result.state == "FL"
    for private in ("source_id", "raw_record", "source_url", "private-provider-", "DO_NOT_EXPOSE_RAW"):
        assert private not in response.text
    for state in ("ZZ", "California", "", "%20%20", "A" * 21):
        assert client.get("/acquisition-map/permit-density?state=" + state,
                          headers=headers).status_code == 422
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert client.request(method, "/acquisition-map/permit-density", headers=headers).status_code == 405


def test_demo_service_is_readonly_native_only_and_tenant_scoped(db, records):
    records()
    inventory_writer(db, DEMO_ORG_ID)(latitude=10, longitude=20)
    token = set_current_context(RequestContext(DEMO_ORG_ID, "demo"))
    demo_token = demo_read_only.set(True)
    try:
        result = get_permit_density(db)
    finally:
        demo_read_only.reset(demo_token)
        reset_current_context(token)
    assert_complete(result)
    assert result.total_permits == result.source_coordinate_count == 1


def test_demo_writes_remain_denied(client, demo):
    headers = demo_headers(client)
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert client.request(method, "/acquisition-map/permit-density", headers=headers).status_code == 403


@pytest.mark.parametrize("prefix", ["", "/v1"])
@pytest.mark.parametrize("endpoint", ["coverage", "permit-density"])
def test_demo_http_get_is_complete_tenant_scoped_select_only(
    client, db, demo, records, prefix, endpoint,
):
    add = inventory_writer(db, DEMO_ORG_ID)
    add(state="FL")
    add(state=None, latitude=None, longitude=None)
    add("planning", state="WA")
    add("parcel", state="TX")
    foreign = inventory_writer(db, "foreign-density-http")
    foreign(state="NJ", jurisdiction="PRIVATE_FOREIGN_AUTHORITY")
    foreign("planning", state="NJ")
    foreign("parcel", state="NJ")
    records(state="NJ")
    db.commit()
    headers = demo_headers(client)
    statements, loaded = [], []

    def capture(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    def loading(_target, _context):
        loaded.append(True)

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", capture)
    for model in (PermitRecord, PlanningRecord, ParcelRecord):
        event.listen(model, "load", loading)
    try:
        response = client.get(
            f"{prefix}/acquisition-map/{endpoint}", headers={
                **headers, "X-Organization-Id": "foreign-density-http",
            }, params={"kind": "permit", "organization_id": "foreign-density-http",
                       "org_id": "foreign-density-http", "limit": 1},
        )
        unknown = client.get(f"{prefix}/acquisition-map/{endpoint}", headers=headers,
                             params={"kind": "permit", "state": "__unknown__"})
        foreign_state = client.get(f"{prefix}/acquisition-map/{endpoint}", headers=headers,
                                   params={"kind": "permit", "state": "NJ"})
    finally:
        event.remove(engine, "before_cursor_execute", capture)
        for model in (PermitRecord, PlanningRecord, ParcelRecord):
            event.remove(model, "load", loading)
    assert response.status_code == unknown.status_code == foreign_state.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert statements and all(sql.lstrip().upper().startswith("SELECT") for sql in statements)
    assert not loaded
    body = response.json()
    if endpoint == "coverage":
        assert body["totals"] == dict(permit_count=3, planning_count=0, parcel_count=0,
                                      mapped_count=1, unmapped_count=2)
        assert "NJ" not in {row["state"] for row in body["states"]}
        assert unknown.json()["totals"]["permit_count"] == 1
        assert foreign_state.json()["totals"]["permit_count"] == 0
    else:
        result = PermitDensityResponse.model_validate(body)
        assert_complete(result)
        assert result.total_permits == 3 and result.mapped_permits == 1
        assert result.source_coordinate_count == 1 and result.estimated_count == 0
        assert unknown.json()["total_permits"] == 1
        assert foreign_state.json()["total_permits"] == 0
    for private in ("PRIVATE_FOREIGN_AUTHORITY", "DO_NOT_EXPOSE_RAW", "source_id",
                    "source_url", "raw_record", "private-provider-"):
        assert private not in response.text


@pytest.mark.parametrize("prefix", ["", "/v1"])
@pytest.mark.parametrize("endpoint", ["coverage", "permit-density"])
def test_demo_http_head_is_policy_allowed_but_route_remains_get_only(client, demo, prefix, endpoint):
    path = f"{prefix}/acquisition-map/{endpoint}"
    assert demo_path_allowed("GET", path)
    assert demo_path_allowed("HEAD", path)
    response = client.head(path, headers=demo_headers(client))
    assert response.status_code == 405
    assert response.headers["allow"] == "GET"
    assert response.headers["cache-control"] == "no-store"
    assert response.content == b""


@pytest.mark.parametrize("prefix", ["", "/v1"])
@pytest.mark.parametrize("endpoint", ["coverage", "permit-density"])
def test_demo_http_write_methods_rejected_before_any_database_query(
    client, db, demo, prefix, endpoint,
):
    headers = demo_headers(client)
    statements = []

    def capture(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", capture)
    try:
        for method in ("POST", "PUT", "PATCH", "DELETE", "TRACE", "CONNECT"):
            path = f"{prefix}/acquisition-map/{endpoint}"
            assert not demo_path_allowed(method, path)
            response = client.request(method, path, headers=headers, json={"state": "FL"})
            assert response.status_code == 403
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert statements == []


@pytest.mark.parametrize("prefix", ["", "/v1"])
def test_demo_http_other_acquisition_routes_remain_denied(client, demo, prefix):
    headers = demo_headers(client)
    for path in ("/acquisition-map/records", "/acquisition-map/signals",
                 "/acquisition-map/readiness", "/acquisition-map/zip3-heatmap",
                 "/acquisition-map/coverage/records", "/acquisition-map/coverage-export",
                 "/acquisition-map/permit-density/records", "/acquisition-map/permit-density-export",
                 "/parcels/private-parcel/use-context", "/nearby-parcel-searches"):
        for method in ("GET", "HEAD"):
            assert not demo_path_allowed(method, prefix + path)
            assert client.request(method, prefix + path, headers=headers).status_code == 403


@pytest.mark.parametrize("endpoint", ["coverage", "permit-density"])
def test_demo_http_auth_and_filter_statuses_fail_closed(client, db, demo, monkeypatch, endpoint):
    path = f"/v1/acquisition-map/{endpoint}"
    headers = demo_headers(client)
    for method in ("GET", "HEAD"):
        assert client.request(method, path).status_code == 401
        assert client.request(method, path, headers={"Authorization": "Bearer invalid"}).status_code == 401
    for query in ({"state": "ZZ"}, {"state": "California"}, {"state": ""}):
        response = client.get(path, headers=headers, params=query)
        assert response.status_code == 422
        assert response.headers["cache-control"] == "no-store"
    for org_id, user_id in (("foreign-density-http", DEMO_USER_ID), (DEMO_ORG_ID, "foreign-user")):
        forged_scope = {"Authorization": "Bearer " + create_access_token(
            user_id=user_id, org_id=org_id, demo=True,
        )}
        assert client.get(path, headers=forged_scope).status_code == 401
    expired = {"Authorization": "Bearer " + create_access_token(
        user_id=DEMO_USER_ID, org_id=DEMO_ORG_ID, demo=True, expires_minutes=-1,
    )}
    assert client.get(path, headers=expired).status_code == 401
    monkeypatch.setattr(config, "DEMO_ENABLED", False)
    assert client.get(path, headers=headers).status_code == 401


@pytest.mark.parametrize("endpoint", ["coverage", "permit-density"])
@pytest.mark.parametrize("revocation,expected_status", [("user", 401), ("membership", 403)])
def test_demo_http_rechecks_current_user_and_membership(
    client, db, demo, endpoint, revocation, expected_status,
):
    headers = demo_headers(client)
    if revocation == "user":
        db.get(User, DEMO_USER_ID).is_active = False
    else:
        membership = db.query(OrganizationMembership).filter_by(
            user_id=DEMO_USER_ID, organization_id=DEMO_ORG_ID,
        ).one()
        db.delete(membership)
    db.commit()
    response = client.get(f"/v1/acquisition-map/{endpoint}", headers=headers)
    assert response.status_code == expected_status
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("changes", [
    {"total_permits": 2}, {"mapped_permits": 2}, {"source_coordinate_count": 0},
    {"estimated_count": 1}, {"complete": False}, {"cell_degrees": 3},
    {"cells": []},
])
def test_response_rejects_incomplete_or_inconsistent_contract(db, records, changes):
    records()
    payload = get_permit_density(db).model_dump()
    payload.update(changes)
    with pytest.raises(ValidationError):
        PermitDensityResponse.model_validate(payload)


def test_response_rejects_cell_overflow_and_invalid_cell_bounds(db, records):
    records()
    payload = get_permit_density(db).model_dump()
    cell = payload["cells"][0]
    with pytest.raises(ValidationError):
        PermitDensityResponse.model_validate({**payload, "cells": [cell] * 2049})
    for changes in ({"count": 2}, {"latitude": 91}, {"north": cell["south"]},
                    {"estimated_count": -1}, {"east": 181}):
        with pytest.raises(ValidationError):
            PermitDensityResponse.model_validate({**payload, "cells": [{**cell, **changes}]})
