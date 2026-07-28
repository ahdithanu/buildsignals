from types import SimpleNamespace

from app.models.ingestion import IngestionSource
from app.models.organization import Organization
from app.services.ingestion import cli
from app.services.ingestion.cli import build_parser


def test_run_all_parser_defaults_to_bounded_resumable_collection():
    args = build_parser().parse_args([
        "run-all",
        "--organization",
        "default-org",
    ])

    assert args.command == "run-all"
    assert args.max_pages_per_source == 10
    assert args.stage == "all"
    assert args.reset_checkpoints is False


def test_run_all_parser_supports_full_preapproval_reconciliation():
    args = build_parser().parse_args([
        "run-all",
        "--organization",
        "default-org",
        "--max-pages-per-source",
        "100",
        "--stage",
        "pre_approval_and_approved",
        "--reset-checkpoints",
    ])

    assert args.max_pages_per_source == 100
    assert args.stage == "pre_approval_and_approved"
    assert args.reset_checkpoints is True


def test_run_all_continues_after_one_source_errors(db, monkeypatch):
    db.add(Organization(
        id="default-org", name="Default Organization", slug="default-org",
        is_active=True,
    ))
    db.add_all([
        IngestionSource(
            organization_id="default-org", key="a_source", name="A Source",
            adapter="csv", record_type="permit", is_active=True,
            settings={"signal_stage": "pre_approval_and_approved"},
        ),
        IngestionSource(
            organization_id="default-org", key="b_source", name="B Source",
            adapter="csv", record_type="permit", is_active=True,
            settings={"signal_stage": "pre_approval_and_approved"},
        ),
    ])
    db.commit()
    calls = []

    def fake_execute(_db, source, **kwargs):
        calls.append((source.key, kwargs))
        if source.key == "a_source":
            raise RuntimeError("source unavailable")
        return SimpleNamespace(
            status="completed", records_seen=2, records_inserted=2,
            records_updated=0, records_failed=0,
        )

    monkeypatch.setattr(cli, "SessionLocal", lambda: db)
    monkeypatch.setattr(cli, "execute_source_run", fake_execute)

    result = cli.main([
        "run-all", "--organization", "default-org",
        "--stage", "pre_approval_and_approved",
    ])

    assert result == 1
    assert [key for key, _kwargs in calls] == ["a_source", "b_source"]
    assert all(kwargs["trigger"] == "scheduled" for _key, kwargs in calls)
