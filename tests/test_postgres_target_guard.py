"""Pure disposable-target validation; no engine, database, or source calls."""
from dataclasses import FrozenInstanceError, fields
from types import MappingProxyType
from uuid import UUID

import pytest
import sqlalchemy
from sqlalchemy.engine import URL

from tests.postgres_target_guard import SnapshotPostgresTarget, validate_snapshot_test_target

RUN_ID = "12345678123442349234123456789abc"
DATABASE = f"bs_snapshot_test_{RUN_ID}"
PASSWORD = "private-password-marker"


def _url(**changes):
    parts = {"drivername": "postgresql+psycopg2", "username": "fixture_owner",
             "password": PASSWORD, "host": "127.0.0.1", "port": 55432,
             "database": DATABASE}
    parts.update(changes)
    return URL.create(**parts).render_as_string(hide_password=False)


@pytest.fixture(autouse=True)
def no_engine(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Target validation must never create an engine")
    monkeypatch.setattr(sqlalchemy, "create_engine", forbidden)


def _reject(url=None, run_id=RUN_ID, environ=None):
    with pytest.raises(ValueError) as caught:
        validate_snapshot_test_target(url, run_id, {} if environ is None else environ)
    assert str(caught.value) == "Invalid disposable snapshot PostgreSQL test target"
    assert PASSWORD not in str(caught.value)
    assert "private-ambient-marker" not in str(caught.value)
    assert caught.value.__context__ is None
    assert caught.value.__cause__ is None


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
@pytest.mark.parametrize("port", [1, 55432, 65535])
def test_explicit_numeric_loopback_target_is_frozen_and_password_redacted(host, port):
    raw = _url(host=host, port=port)
    target = validate_snapshot_test_target(raw, RUN_ID, {})
    assert isinstance(target, SnapshotPostgresTarget)
    assert isinstance(target.url, URL)
    assert target.url.host == host and target.url.port == port
    assert target.url.drivername == "postgresql+psycopg2"
    assert target.url.password == PASSWORD
    assert target.database == DATABASE and target.username == "fixture_owner"
    assert target.run_id == RUN_ID
    assert target.marker == f"BuildSignals disposable snapshot test:{RUN_ID}"
    assert not next(field for field in fields(target) if field.name == "url").repr
    assert PASSWORD not in repr(target) and raw not in repr(target)
    for name in ("url", "database", "username", "marker", "run_id"):
        with pytest.raises(FrozenInstanceError):
            setattr(target, name, "changed")


def test_structured_url_parsing_preserves_encoded_credentials_without_echoing_them():
    password = "private-password-marker:@/?#% space"
    target = validate_snapshot_test_target(_url(password=password), RUN_ID, {})
    assert target.url.password == password
    assert "private-password-marker" not in repr(target)


def test_supplied_environment_is_unchanged_and_unrelated_values_are_not_disclosed():
    environ = {"PGHOST": "", "PGPASSWORD": "", "HOME": "/private-ambient-marker"}
    before = dict(environ)
    target = validate_snapshot_test_target(_url(), RUN_ID, MappingProxyType(environ))
    assert target.database == DATABASE and environ == before
    assert "private-ambient-marker" not in repr(target)


@pytest.mark.parametrize("run_id", [
    None, 1, True, b"12345678123442349234123456789abc", UUID(RUN_ID),
    "", " " + RUN_ID, RUN_ID + " ", RUN_ID.upper(), str(UUID(RUN_ID)),
    "{" + RUN_ID + "}", "urn:uuid:" + str(UUID(RUN_ID)),
    RUN_ID[:-1], RUN_ID + "0", "g" * 32,
    "12345678123412349234123456789abc",  # Version 1, RFC variant.
    "12345678123442341234123456789abc",  # Version 4 bits, non-RFC variant.
    "1234567812344234c234123456789abc",  # Microsoft variant.
    "00000000000000000000000000000000",
])
def test_run_id_must_be_canonical_lowercase_uuid4_hex(run_id):
    _reject(_url(), run_id=run_id)


@pytest.mark.parametrize("database", [
    None, "", "dealsignal", "bs_snapshot_test_", DATABASE + "_extra", DATABASE.upper(),
    "bs_snapshot_test_22345678123442349234123456789abc",
    "other_" + RUN_ID, DATABASE + "/child", DATABASE + "#private-password-marker",
])
def test_database_must_match_the_exact_run_identity(database):
    _reject(_url(database=database))


@pytest.mark.parametrize("driver", [
    "postgresql", "postgres", "postgresql+psycopg", "postgresql+asyncpg",
    "postgresql+pg8000", "mysql+pymysql", "sqlite", "POSTGRESQL+psycopg2",
])
def test_only_the_explicit_psycopg2_driver_is_allowed(driver):
    _reject(_url(drivername=driver))


@pytest.mark.parametrize("host", [
    None, "", "localhost", "LOCALHOST", "127.0.0.2", "127.1", "2130706433",
    "0177.0.0.1", "0x7f000001", "0.0.0.0", "192.0.2.1", "db.example.invalid",
    "127.0.0.1.example.invalid", "::", "::ffff:127.0.0.1", "::1%lo0",
    "/tmp", "%2Ftmp", "127.0.0.1,127.0.0.2", "127.0.0.1 ",
])
def test_remote_alias_unix_socket_multihost_and_alternate_loopback_forms_are_rejected(host):
    _reject(_url(host=host))


@pytest.mark.parametrize("port", [None, 0, -1, 65536, 1000000])
def test_port_must_be_explicit_and_within_tcp_range(port):
    _reject(_url(port=port))


@pytest.mark.parametrize("part", ["username", "password"])
@pytest.mark.parametrize("value", [None, ""])
def test_credentials_must_both_be_nonempty(part, value):
    _reject(_url(**{part: value}))


@pytest.mark.parametrize("query", [
    "", "&", "=",
    "host=private-ambient-marker", "hostaddr=192.0.2.1", "port=5432",
    "dbname=private-ambient-marker", "service=private-ambient-marker",
    "sslmode=require", "options=-csearch_path%3Dpublic", "application_name=fixture",
    "host=127.0.0.1&host=192.0.2.1", "Host=private-ambient-marker",
])
def test_all_url_query_options_are_rejected_not_just_known_routing_keys(query):
    _reject(_url() + "?" + query)


@pytest.mark.parametrize("name", [
    "PG", "PGHOST", "PGHOSTADDR", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD",
    "PGPASSFILE", "PGSERVICE", "PGSERVICEFILE", "PGOPTIONS", "PGSSLMODE",
    "PGSSLROOTCERT", "PGAPPNAME", "PGCONNECT_TIMEOUT", "PGTARGETSESSIONATTRS",
    "PG_FUTURE_UNKNOWN_SETTING",
])
@pytest.mark.parametrize("value", ["private-ambient-marker", " ", "0"])
def test_any_nonempty_pg_environment_value_rejects_the_target(name, value):
    environ = {name: value, "UNRELATED": "unchanged"}
    before = dict(environ)
    _reject(_url(), environ=environ)
    assert environ == before


@pytest.mark.parametrize("url", [
    None, 1, True, {}, b"private-password-marker", URL.create("postgresql+psycopg2"),
    "", "private-password-marker", "postgresql+psycopg2://",
    f"postgresql+psycopg2://u:{PASSWORD}@127.0.0.1:private-ambient-marker/{DATABASE}",
    f"postgresql+psycopg2://u:{PASSWORD}@127.0.0.1:55432,127.0.0.1:55433/{DATABASE}",
    f"postgresql+psycopg2://u:{PASSWORD}@[::1]:invalid/{DATABASE}",
    f"postgresql+psycopg2://u:{PASSWORD}@/tmp/{DATABASE}",
])
def test_malformed_and_nonstring_urls_have_no_parser_exception_context(url):
    _reject(url)


@pytest.mark.parametrize("environ", ["private-ambient-marker", [], 1, {1: "private-ambient-marker"}])
def test_environment_must_be_a_mapping_with_string_names(environ):
    _reject(_url(), environ=environ)


def test_nonempty_pg_environment_is_rejected_even_when_url_would_override_it():
    _reject(_url(), environ={"PGHOST": "127.0.0.1"})


def test_loopback_acceptance_is_syntactic_and_does_not_attest_a_database_or_tunnel():
    # A loopback forwarder has the same URL shape: the parent must independently
    # prove database name, marker and restricted roles on every connection.
    target = validate_snapshot_test_target(_url(), RUN_ID, {})
    assert target.marker == f"BuildSignals disposable snapshot test:{RUN_ID}"
    assert set(vars(target)) == {"url", "database", "username", "marker", "run_id"}
