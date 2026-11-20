"""Opt-in restricted-role/RLS and read-only coverage acceptance; no provisioning."""
from contextlib import contextmanager
from uuid import uuid4

import pytest
from sqlalchemy import event, select, text

from app import config
from app.models.ingestion import PermitRecord, RawSourceRecord
from app.models.parcel import ParcelRecord
from app.models.planning import PlanningRecord
from app.services.demo_access import demo_read_only
from app.services.map_coverage import get_map_coverage, list_map_records
from app.services.permit_density import get_permit_density
from tests.research_postgres_support import RUN_ID, URL, tenant_session
from tests.snapshot_postgres_support import verified_snapshot_connection
from tests.test_map_coverage import inventory_writer

pytestmark = pytest.mark.skipif(not URL, reason="Dedicated disposable snapshot PostgreSQL URL not set")


@contextmanager
def _read_only(org):
    token = demo_read_only.set(True)
    try:
        with tenant_session(org) as db:
            assert db.scalar(text("SHOW transaction_read_only")) == "on"
            yield db
            assert db.scalar(text("SHOW transaction_read_only")) == "on"
    finally:
        demo_read_only.reset(token)


@pytest.fixture
def inventory_tenants(monkeypatch):
    monkeypatch.setattr(config, "SF_DERIVED_LOCATIONS_ENABLED", False)

    def forbidden(*_args, **_kwargs):
        pytest.fail("Coverage PostgreSQL tests must not call sources or models")

    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    monkeypatch.setattr("app.services.llm_client.get_default_llm_client", forbidden)
    own, foreign = str(uuid4()), str(uuid4())
    with tenant_session(own) as db:
        add = inventory_writer(db, own)
        for index in range(105):
            add("parcel", jurisdiction=f"Authority {index:03}")
        permit = add("permit", state=None, jurisdiction=None, latitude=None, longitude=None)
        planning = add("planning", state="TX", jurisdiction="Austin")
        ids = {"permit": permit.id, "planning": planning.id,
               "raw": permit.latest_raw_record_id}
        db.commit()
    with tenant_session(foreign) as db:
        add = inventory_writer(db, foreign)
        row = add("parcel", state="NJ", jurisdiction="FOREIGN_SECRET_AUTHORITY")
        foreign_ids = {"parcel": row.id, "raw": row.latest_raw_record_id}
        db.commit()
    return own, foreign, ids, foreign_ids


def test_actual_pg_aggregate_counts_and_pagination_are_read_only_and_bounded(inventory_tenants):
    own, _foreign, _ids, _foreign_ids = inventory_tenants
    with _read_only(own) as db:
        connection = db.connection()
        assert connection.execute(text(
            "SELECT NOT rolsuper AND NOT rolbypassrls, current_user=session_user "
            "FROM pg_catalog.pg_roles WHERE rolname=current_user"
        )).one() == (True, True)
        statements = []

        def capture(_connection, cursor, statement, _parameters, _context, _many):
            statements.append((statement, cursor.rowcount))

        event.listen(connection, "after_cursor_execute", capture)
        try:
            coverage = get_map_coverage(db, state="FL", limit=100)
            page = list_map_records(db, limit=100)
        finally:
            event.remove(connection, "after_cursor_execute", capture)
        assert coverage.totals.parcel_count == 105
        assert coverage.totals.permit_count == coverage.totals.unmapped_count == 0
        assert coverage.totals.planning_count == 0
        assert coverage.total_groups == 105 and coverage.next_offset == 100
        assert len(coverage.groups) == 100 and coverage.truncated
        assert {row.state for row in coverage.states} == {"FL", "TX", "__unknown__"}
        assert page.total == 107 and len(page.items) == 100
        assert len(statements) == 6
        assert all(sql.lstrip().upper().startswith("SELECT") for sql, _rows in statements)
        assert all(0 <= rows <= 100 for _sql, rows in statements)
        assert any("GROUP BY" in sql.upper() and "LIMIT" in sql.upper() for sql, _rows in statements)
        assert not db.new and not db.dirty and not db.deleted
        last = get_map_coverage(db, state="FL", limit=100, offset=100)
        assert len(last.groups) == 5 and last.total_groups == 105
        assert last.next_offset is None and last.previous_offset == 0
        unknown = get_map_coverage(db, state="__unknown__")
        assert unknown.totals.permit_count == unknown.totals.unmapped_count == 1
        assert unknown.groups[0].jurisdiction == "__unknown__"
        assert unknown.groups[0].latitude is unknown.groups[0].longitude is None
        assert list_map_records(db, state="__unknown__", jurisdiction="__unknown__").total == 1


def test_actual_rls_hides_foreign_inventory_and_cannot_supply_location_or_labels(inventory_tenants):
    own, foreign, ids, foreign_ids = inventory_tenants
    with _read_only(own) as db:
        assert db.scalar(select(ParcelRecord.id).where(ParcelRecord.id == foreign_ids["parcel"])) is None
        assert db.scalar(select(RawSourceRecord.id).where(RawSourceRecord.id == foreign_ids["raw"])) is None
        coverage = get_map_coverage(db)
        assert "FOREIGN_SECRET_AUTHORITY" not in coverage.model_dump_json()
        assert foreign_ids["parcel"] not in list_map_records(db).model_dump_json()
    with _read_only(foreign) as db:
        assert db.scalar(select(PermitRecord.id).where(PermitRecord.id == ids["permit"])) is None
        assert db.scalar(select(PlanningRecord.id).where(PlanningRecord.id == ids["planning"])) is None
        assert get_map_coverage(db).totals.parcel_count == 1
        assert list_map_records(db).total == 1
    with _read_only("default-org") as db:
        assert db.scalar(select(ParcelRecord.id).where(ParcelRecord.id == foreign_ids["parcel"])) is None
        assert db.scalar(select(PermitRecord.id).where(PermitRecord.id == ids["permit"])) is None


def test_unset_database_tenant_denies_even_a_matching_app_context(inventory_tenants):
    own, _foreign, ids, foreign_ids = inventory_tenants
    with tenant_session(own):
        with verified_snapshot_connection(URL, RUN_ID) as connection:
            with connection.begin():
                connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                assert connection.scalar(text("SELECT current_setting('app.current_org',true)")) in (None, "")
                for table, identity in (("permit_records", ids["permit"]),
                                        ("parcel_records", foreign_ids["parcel"])):
                    # Table identifiers are fixed test literals, never user input.
                    assert connection.scalar(text(f"SELECT id FROM {table} WHERE id=:id"), {"id": identity}) is None


def test_density_aggregates_all_rows_under_actual_rls_and_readonly(monkeypatch):
    monkeypatch.setattr(config, "SF_DERIVED_LOCATIONS_ENABLED", False)
    own, foreign = str(uuid4()), str(uuid4())
    with tenant_session(own) as db:
        add = inventory_writer(db, own)
        for index in range(230):
            add("permit", state="TX", latitude=30 + index / 1000, longitude=-97)
        for _index in range(140):
            add("permit", state="OH", latitude=None, longitude=None)
        db.commit()
    with tenant_session(foreign) as db:
        inventory_writer(db, foreign)("permit", state="TX", latitude=32, longitude=-98)
        db.commit()
    with _read_only(own) as db:
        connection = db.connection()
        statements = []

        def capture(_connection, cursor, statement, _parameters, _context, _many):
            statements.append((statement, cursor.rowcount))

        event.listen(connection, "after_cursor_execute", capture)
        try:
            density = get_permit_density(db)
            texas = get_permit_density(db, state="TX")
            ohio = get_permit_density(db, state="OH")
        finally:
            event.remove(connection, "after_cursor_execute", capture)
        assert density.total_permits == 370
        assert density.mapped_permits == sum(cell.count for cell in density.cells) == 230
        assert density.unmapped_permits == 140
        assert texas.total_permits == texas.mapped_permits == 230
        assert ohio.total_permits == ohio.unmapped_permits == 140 and not ohio.cells
        assert len(statements) == 3
        assert all(sql.lstrip().upper().startswith("SELECT") for sql, _rows in statements)
        assert all(0 <= rows <= 2050 for _sql, rows in statements)
        assert all("GROUP BY" in sql.upper() and "LIMIT" in sql.upper() for sql, _rows in statements)
        assert not db.new and not db.dirty and not db.deleted
    with _read_only(foreign) as db:
        assert get_permit_density(db).total_permits == 1
    with tenant_session(own):
        with verified_snapshot_connection(URL, RUN_ID) as connection:
            with connection.begin():
                connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                assert connection.scalar(text("SELECT count(*) FROM permit_records")) == 0
