"""National heatmap snapshots across a deterministic inter-statement commit.

Use only the dedicated, verified PostgreSQL target when configured; otherwise
exercise real independent connections to disposable SQLite in WAL mode.
"""
from contextlib import contextmanager
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, text, update
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app import config
from app.db import Base, configure_sqlite_foreign_keys
from app.models.ingestion import PermitRecord
from app.services.demo_access import demo_read_only
from app.services.map_coverage import get_map_coverage
from app.utils.org_scope import RequestContext, reset_current_context, set_current_context
from tests.research_postgres_support import URL, tenant_session
from tests.test_map_coverage import inventory_writer


@pytest.fixture
def snapshot_sessions(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SF_DERIVED_LOCATIONS_ENABLED", False)

    def forbidden(*_args, **_kwargs):
        pytest.fail("Heatmap snapshot tests must not call sources or models")

    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    monkeypatch.setattr("app.services.llm_client.get_default_llm_client", forbidden)
    engine = None
    if not URL:
        engine = create_engine(
            f"sqlite:///{tmp_path / 'heatmap-snapshot.db'}",
            poolclass=NullPool, connect_args={"timeout": 2},
        )
        configure_sqlite_foreign_keys(engine)
        with engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA journal_mode=WAL").scalar() == "wal"
        Base.metadata.create_all(engine)

    @contextmanager
    def sessions(org, *, read_only=False):
        read_token = demo_read_only.set(read_only)
        try:
            if URL:
                with tenant_session(org) as db:
                    # Pin the production isolation level, not a stronger test-only snapshot.
                    db.get_bind().execution_options(isolation_level="READ COMMITTED")
                    assert db.scalar(text("SHOW transaction_isolation")) == "read committed"
                    assert db.scalar(text("SHOW transaction_read_only")) == ("on" if read_only else "off")
                    yield db
            else:
                token = set_current_context(RequestContext(org, "synthetic-heatmap-test"))
                try:
                    with Session(engine, autoflush=False, expire_on_commit=False) as db:
                        if read_only:
                            db.connection().exec_driver_sql("PRAGMA query_only=ON")
                        yield db
                finally:
                    reset_current_context(token)
        finally:
            demo_read_only.reset(read_token)

    try:
        yield sessions
    finally:
        if engine is not None:
            engine.dispose()


def _counts(*, permit=0, planning=0, parcel=0, mapped=0):
    return dict(permit_count=permit, planning_count=planning, parcel_count=parcel,
                mapped_count=mapped, unmapped_count=permit + planning + parcel - mapped)


@pytest.mark.parametrize("kind", ["permit", "all"])
@pytest.mark.parametrize("limit,offset", [(100, 0), (1, 0), (1, 1), (100, 100000)])
def test_national_totals_and_page_share_snapshot_despite_concurrent_commit(
    snapshot_sessions, kind, limit, offset,
):
    org = str(uuid4())
    with snapshot_sessions(org) as db:
        add = inventory_writer(db, org)
        add(state="FL")
        unmapped = add(state="OH", latitude=None, longitude=None)
        retired_id = unmapped.id
        add("planning", state="CA")
        add("parcel", state="WA")
        db.commit()

    expected = {"FL": _counts(permit=1, mapped=1), "OH": _counts(permit=1)}
    if kind == "all":
        expected.update(CA=_counts(planning=1, mapped=1), WA=_counts(parcel=1, mapped=1))
    expected_states = sorted(expected)
    expected_totals = {name: sum(counts[name] for counts in expected.values())
                       for name in _counts()}

    with snapshot_sessions(org, read_only=True) as reader:
        connection = reader.connection()
        reader_pid = connection.scalar(text("SELECT pg_backend_pid()")) if URL else None
        statements, committed = [], []

        def commit_after_first_inventory_select(_connection, cursor, statement, _params, _context, _many):
            if "coverage_inventory" not in statement:
                return
            statements.append((statement, cursor.rowcount))
            if committed:
                return
            # No sleep or scheduler race: commit after execution fixes the first
            # SELECT's snapshot, but before the service can execute another SELECT.
            with snapshot_sessions(org) as writer:
                other = writer.connection()
                assert other.connection.driver_connection is not connection.connection.driver_connection
                if URL:
                    assert other.scalar(text("SELECT pg_backend_pid()")) != reader_pid
                result = writer.execute(update(PermitRecord).where(
                    PermitRecord.organization_id == org,
                ).values(state="TX", latitude=None, longitude=None))
                assert result.rowcount == 2
                retired = writer.execute(update(PermitRecord).where(
                    PermitRecord.organization_id == org, PermitRecord.id == retired_id,
                ).values(is_active=False))
                assert retired.rowcount == 1
                writer.commit()
                committed.append(True)

        event.listen(connection, "after_cursor_execute", commit_after_first_inventory_select)
        try:
            result = get_map_coverage(reader, kind=kind, limit=limit, offset=offset)
        finally:
            event.remove(connection, "after_cursor_execute", commit_after_first_inventory_select)

        assert committed == [True]
        assert result.grouping == "state"
        assert result.totals.model_dump() == expected_totals
        assert result.total_groups == len(expected)
        page = expected_states[offset:offset + limit]
        assert [group.state for group in result.groups] == page
        for group in result.groups:
            assert {name: getattr(group, name) for name in _counts()} == expected[group.state]
        if limit == 100 and offset == 0:
            for name in _counts():
                assert sum(getattr(group, name) for group in result.groups) == getattr(result.totals, name)
        assert result.truncated is (len(page) < len(expected))
        assert result.next_offset == (offset + limit if offset + limit < len(expected) else None)
        assert result.previous_offset == (max(0, offset - limit) if offset else None)
        assert len(statements) == (2 if kind == "permit" else 1)
        assert all("GROUP BY" in sql.upper() and "LIMIT" in sql.upper() for sql, _rows in statements)
        if URL:
            assert all(0 <= rows <= 52 for _sql, rows in statements)
        if kind == "permit":
            assert {state.state for state in result.states} == {"CA", "TX", "WA"}
        assert not reader.new and not reader.dirty and not reader.deleted

        # A fresh request observes the committed move, proving the writer really
        # changed the same tenant rather than merely mutating a mocked response.
        reader.rollback()
        fresh = get_map_coverage(reader, kind=kind)
        fresh_states = {"TX"} | ({"CA", "WA"} if kind == "all" else set())
        assert {group.state for group in fresh.groups} == fresh_states
        assert fresh.total_groups == len(fresh_states)
        assert fresh.totals.permit_count == 1
        assert fresh.totals.unmapped_count == 1
        assert fresh.totals.mapped_count == (2 if kind == "all" else 0)
