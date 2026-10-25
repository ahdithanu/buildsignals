from types import SimpleNamespace

import pytest

from app.models.ingestion import IngestionSource
from app.models.organization import Organization
from app.services.ingestion import cli


@pytest.mark.parametrize(
    "status,records_failed,expected_exit",
    [
        ("completed", 0, 0),
        ("completed", 1, 1),
        ("partial", 0, 1),
        ("partial", 1, 1),
        ("partial_with_errors", 0, 1),
        ("partial_with_errors", 1, 1),
        ("failed", 0, 1),
        ("running", 0, 1),
        ("pending", 0, 1),
        ("unexpected_status", 0, 1),
    ],
)
def test_direct_run_succeeds_only_when_completed_without_errors(
    db, monkeypatch, capsys, status, records_failed, expected_exit,
):
    db.add(Organization(
        id="exit-status-org", name="Exit Status Org", slug="exit-status-org",
        is_active=True,
    ))
    db.add(IngestionSource(
        organization_id="exit-status-org", key="exit_status_source",
        name="Exit Status Source", adapter="csv", record_type="permit",
        is_active=True,
    ))
    db.commit()
    run = SimpleNamespace(
        id="exit-status-run", status=status, records_seen=2,
        records_inserted=1, records_updated=0, records_failed=records_failed,
    )
    monkeypatch.setattr(cli, "SessionLocal", lambda: db)
    monkeypatch.setattr(cli, "execute_source_run", lambda *_args, **_kwargs: run)

    exit_code = cli.main([
        "run", "--organization", "exit-status-org",
        "--source-key", "exit_status_source",
    ])

    assert f"run {run.id}: status={status}" in capsys.readouterr().out
    assert exit_code == expected_exit
