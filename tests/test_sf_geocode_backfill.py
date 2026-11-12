from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from app.models.ingestion import PermitRecord
from app.models.permit_geocode import PermitGeocode
from app.services.demo_access import DEMO_ORG_ID
from scripts import backfill_sf_geocode as worker
from scripts.backfill_sf_geocode import run
from tests.test_sf_geocoding import stored


def factory(db):
    class Borrowed:
        def __enter__(self):
            return db

        def __exit__(self, *_):
            pass
    return Borrowed


def postgres_guard_session(db, flags):
    class GuardSession:
        def get_bind(self):
            return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

        def execute(self, statement):
            sql = str(statement)
            assert "pg_catalog.row_security_active('public.permit_geocodes'::regclass)" in sql
            assert "pg_catalog.pg_roles" in sql and "current_user" in sql
            assert "pg_catalog.pg_class" in sql and "relforcerowsecurity" in sql
            return SimpleNamespace(one=lambda: tuple(flags))

        def __getattr__(self, name):
            return getattr(db, name)

    return GuardSession()


@pytest.mark.parametrize("flags", [
    [False, True, True, True, True],  # Metadata/role flags pass; effective RLS does not.
    [True, False, True, True, True],
    [True, True, False, True, True],
    [True, True, True, False, True],
    [True, True, True, True, False],
    [None, True, True, True, True],
])
def test_postgres_runtime_guard_rejects_before_fetch_or_write(db, monkeypatch, flags, capsys, caplog):
    _, _, response = stored(db)
    fetch = Mock(return_value=response)
    save = Mock(side_effect=AssertionError("write must not be reached"))
    monkeypatch.setattr(worker, "save_match", save)
    with pytest.raises(PermissionError, match="effective tenant RLS"):
        run("default-org", execute=True, fetch=fetch, sleep=lambda _: None,
            session_factory=factory(postgres_guard_session(db, flags)))
    assert not fetch.called and not save.called
    assert db.query(PermitGeocode).count() == 0
    output = capsys.readouterr()
    assert not output.out and not output.err and not caplog.text


def test_postgres_runtime_guard_accepts_effective_restricted_role(db):
    _, _, response = stored(db)
    fetch = Mock(return_value=response)
    result = run("default-org", execute=True, fetch=fetch, sleep=lambda _: None,
        session_factory=factory(postgres_guard_session(db, [True] * 5)))
    assert fetch.call_count == result["filings_located"] == 1
    assert db.query(PermitGeocode).count() == 1


def test_postgres_runtime_guard_rechecks_after_response_before_write(db):
    _, _, response = stored(db)
    flags = [True] * 5
    def fetch(_):
        flags[0] = False
        return response
    with pytest.raises(PermissionError, match="effective tenant RLS"):
        run("default-org", execute=True, fetch=fetch, sleep=lambda _: None,
            session_factory=factory(postgres_guard_session(db, flags)))
    assert db.query(PermitGeocode).count() == 0


def duplicate(db, permit, suffix, *, address=None):
    other = PermitRecord(id=f"permit-{suffix}", organization_id=permit.organization_id,
        source_id=permit.source_id, latest_raw_record_id=permit.latest_raw_record_id,
        external_record_id=f"record-{suffix}", normalization_hash="d" * 64,
        address=address or permit.address, city=permit.city, state=permit.state,
        postal_code=permit.postal_code, is_active=True)
    db.add(other)
    db.flush()
    return other


def test_default_plan_never_fetches_or_writes(db):
    stored(db)
    result = run("default-org", limit=2, fetch=lambda _: pytest.fail("network in plan"),
        sleep=lambda _: pytest.fail("sleep in plan"), session_factory=factory(db))
    assert result["mode"] == "plan" and result["addresses_planned"] == 1
    assert result["addresses_attempted"] == 0 and result["filings_located"] == 0
    assert db.query(PermitGeocode).count() == 0


def test_scoped_backfill_deduplicates_addresses_and_is_idempotent(db):
    permit, _, response = stored(db)
    duplicate(db, permit, "same-address")
    fetched = []
    def fetch(url):
        fetched.append(url)
        return deepcopy(response)
    result = run("default-org", limit=1, execute=True, fetch=fetch, sleep=lambda _: None,
        session_factory=factory(db))
    assert len(fetched) == 1 and result["filings_located"] == 2
    assert result["addresses_attempted"] == result["addresses_matched"] == 1
    assert db.query(PermitGeocode).count() == 2
    replay = run("default-org", limit=1, execute=True,
        fetch=lambda _: pytest.fail("repeat network"), sleep=lambda _: None, session_factory=factory(db))
    assert replay["addresses_attempted"] == 0 and replay["filings_located"] == 0
    assert permit.latitude is None and permit.longitude is None


def test_request_budget_and_scan_cursor_are_bounded(db):
    permit, _, _ = stored(db)
    permit.id = "permit-0"
    duplicate(db, permit, "1", address="200 MARKET ST")
    duplicate(db, permit, "2", address="300 MARKET ST")
    calls = []
    result = run("default-org", limit=1, execute=True,
        fetch=lambda url: calls.append(url) or {"result": {"addressMatches": []}},
        sleep=lambda _: None, session_factory=factory(db))
    assert len(calls) == 1 and result["addresses_attempted"] == 1
    assert result["next_after_permit_id"] == "permit-0"
    assert result["status"] == "partial"
    scan = run("default-org", limit=5, scan_limit=1,
        fetch=lambda _: pytest.fail("plan network"), session_factory=factory(db))
    assert scan["records_scanned"] == 1 and scan["next_after_permit_id"] == "permit-0"
    assert scan["status"] == "planned"


def test_provider_error_stops_without_logging_address_or_exception(db):
    permit, _, _ = stored(db)
    duplicate(db, permit, "other", address="200 MARKET ST")
    def fail(_):
        raise OSError("private address and provider credential must not appear")
    result = run("default-org", limit=5, execute=True, fetch=fail,
        sleep=lambda _: None, session_factory=factory(db))
    assert result["status"] == "provider_error" and result["addresses_attempted"] == 1
    assert "private" not in str(result) and "MARKET" not in str(result)
    assert db.query(PermitGeocode).count() == 0


def test_foreign_tenant_and_demo_scope_do_not_transmit(db):
    stored(db)
    with pytest.raises(ValueError):
        run(DEMO_ORG_ID, execute=True, session_factory=factory(db))
    with pytest.raises(ValueError):
        run("foreign-org", execute=True, session_factory=factory(db),
            fetch=lambda _: pytest.fail("foreign transmit"))


def test_address_change_in_flight_never_stores_the_old_match(db):
    permit, _, response = stored(db)
    def changed(_):
        permit.address = "200 MARKET ST"
        db.commit()
        return response
    result = run("default-org", execute=True, fetch=changed, sleep=lambda _: None,
        session_factory=factory(db))
    assert result["filings_located"] == 0 and result["held"] == 1
    assert db.query(PermitGeocode).count() == 0


def test_fetch_uses_the_pinned_bounded_client(monkeypatch):
    class Client:
        def __init__(self, **kwargs):
            assert kwargs == {"timeout": 12, "max_retries": 0,
                "allowed_hosts": frozenset({"geocoding.geo.census.gov"})}

        def get_bytes(self, url, *, max_bytes):
            assert url == "synthetic-request" and max_bytes == 65_536
            return b'{"result": {"addressMatches": []}}', None
    monkeypatch.setattr(worker, "RetryingHttpClient", Client)
    assert worker._fetch("synthetic-request") == {"result": {"addressMatches": []}}


@pytest.mark.parametrize("target,field,value", [
    ("permit", "address", "200 MARKET ST"), ("permit", "latitude", 37.78),
    ("permit", "is_active", False), ("source", "is_active", False),
])
def test_separate_session_changes_are_rechecked_before_write(db, target, field, value):
    permit, source, response = stored(db)
    db.commit()
    identity = permit.id if target == "permit" else source.id
    model = type(permit) if target == "permit" else type(source)
    def changed(_):
        with Session(db.get_bind()) as other:
            row = other.query(model).filter_by(id=identity, organization_id="default-org").one()
            setattr(row, field, value)
            other.commit()
        return response
    result = run("default-org", execute=True, fetch=changed, sleep=lambda _: None,
        session_factory=factory(db))
    assert result["filings_located"] == 0 and db.query(PermitGeocode).count() == 0


def test_cli_requires_both_transmission_and_write_confirmation(monkeypatch):
    monkeypatch.setattr("sys.argv", ["backfill", "--organization-id", "default-org", "--execute"])
    called = Mock(side_effect=AssertionError("run must not be reached"))
    monkeypatch.setattr(worker, "run", called)
    with pytest.raises(SystemExit) as error:
        worker.main()
    assert error.value.code == 2 and not called.called


def test_cli_error_has_no_address_url_credentials_or_traceback(monkeypatch, capsys, caplog):
    monkeypatch.setattr("sys.argv", ["backfill", "--organization-id", "default-org"])
    monkeypatch.setattr(worker, "run", Mock(side_effect=RuntimeError("private-address https://private.invalid credential")))
    with pytest.raises(SystemExit) as error:
        worker.main()
    assert error.value.code == 1
    out = capsys.readouterr()
    assert out.out == '{"status": "failed", "error_type": "RuntimeError"}\n'
    assert not out.err and not caplog.text


@pytest.mark.parametrize("limit,scan_limit", [(0, 1), (201, 1), (True, 1), (1, 0), (1, 5001)])
def test_invalid_bounds_fail_before_database_or_network(limit, scan_limit):
    with pytest.raises(ValueError):
        run("default-org", limit=limit, scan_limit=scan_limit,
            session_factory=lambda: pytest.fail("database"))
