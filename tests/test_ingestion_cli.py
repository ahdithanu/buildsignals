from datetime import date
from types import SimpleNamespace

import pytest

from app.models.ingestion import IngestionSource
from app.models.organization import Organization
from app.schemas.ingestion import IngestionSourceCreate
from app.schemas.ingestion_candidate import IngestionSourceCandidate
from app.services.ingestion import cli
from app.services.ingestion.cli import build_parser
from app.services.ingestion.health import CandidateCanaryResult


def _catalog_source(
    key: str,
    *,
    signal_stage: str = "approved_only",
    max_pages_per_run: int = 10,
):
    return SimpleNamespace(
        key=key,
        settings={
            "collection_interval_minutes": 1440,
            "collection_sla_hours": 24,
            "retry_interval_minutes": 60,
            "schedule_mode": "automatic",
            "signal_stage": signal_stage,
            "max_pages_per_run": max_pages_per_run,
        },
    )


def _typed_catalog_source(key: str, jurisdiction: str) -> IngestionSourceCreate:
    return IngestionSourceCreate(
        key=key,
        name=key,
        adapter="csv",
        record_type="permit",
        jurisdiction=jurisdiction,
        base_url=f"https://{key}.example.gov/data.csv",
        settings={
            "connector": {},
            "collection_interval_minutes": 1440,
            "collection_sla_hours": 24,
            "retry_interval_minutes": 60,
            "schedule_mode": "automatic",
            "signal_stage": "approved_only",
            "max_pages_per_run": 10,
        },
    )


def _retry_candidate() -> IngestionSourceCandidate:
    return IngestionSourceCandidate(
        key="test_retry_candidate",
        name="Test Retry Candidate",
        adapter="csv",
        record_type="permit",
        jurisdiction="Test, OR",
        base_url="https://example.test/retry.csv",
        official_landing_page="https://example.test/retry",
        license="Test License",
        status="operational_retry",
        blocker_summary="Awaiting a successful operational retry.",
        early_warning_value="Test pre-approval records.",
        candidate_source_fields=["id"],
        probe_settings={
            "connector": {"source": "https://example.test/retry.csv"},
            "defaults": {"state": "OR", "approval_stage": "pre_approval"},
        },
        probe_field_mappings=[
            {"source_field": "id", "canonical_field": "source_record_id"}
        ],
        last_checked_on=date(2026, 7, 1),
        next_audit_on=date(2026, 7, 30),
        notes="Test candidate fixture.",
    )


def _approved_retry_manifest():
    return SimpleNamespace(
        candidate_retries=SimpleNamespace(
            candidate_keys=["test_retry_candidate"], sample_size=10
        ),
    )


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
    assert args.source_keys is None


def test_source_request_parser_defaults_to_markdown():
    args = build_parser().parse_args([
        "catalog",
        "source-request",
        "--candidate-key",
        "test_ak_records",
    ])

    assert args.catalog_command == "source-request"
    assert args.candidate_key == "test_ak_records"
    assert args.format == "markdown"
    assert args.output is None


def test_brand_backfill_parser_defaults_to_resumable_batch():
    args = build_parser().parse_args([
        "brands",
        "backfill",
        "--organization",
        "default-org",
    ])

    assert args.command == "brands"
    assert args.brand_command == "backfill"
    assert args.organization == "default-org"
    assert args.batch_size == 500
    assert args.max_records is None
    assert args.after_id is None
    assert args.dry_run is False


def test_brand_backfill_parser_accepts_resume_and_run_bounds():
    args = build_parser().parse_args([
        "brands",
        "backfill",
        "--organization",
        "default-org",
        "--batch-size",
        "250",
        "--max-records",
        "1000",
        "--after-id",
        "permit-cursor",
        "--dry-run",
    ])

    assert args.batch_size == 250
    assert args.max_records == 1000
    assert args.after_id == "permit-cursor"
    assert args.dry_run is True


def test_reference_backfill_parser_requires_type_and_supports_bounds():
    args = build_parser().parse_args([
        "references",
        "backfill",
        "--organization",
        "default-org",
        "--record-type",
        "planning",
        "--source-key",
        "city_planning_agendas",
        "--batch-size",
        "250",
        "--max-records",
        "1000",
        "--after-id",
        "planning-cursor",
        "--dry-run",
    ])

    assert args.command == "references"
    assert args.reference_command == "backfill"
    assert args.record_type == "planning"
    assert args.source_key == "city_planning_agendas"
    assert args.batch_size == 250
    assert args.max_records == 1000
    assert args.after_id == "planning-cursor"
    assert args.dry_run is True


def test_reference_backfill_parser_rejects_unsupported_record_type():
    with pytest.raises(SystemExit):
        build_parser().parse_args([
            "references",
            "backfill",
            "--organization",
            "default-org",
            "--record-type",
            "parcel",
        ])


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--batch-size", "0"),
        ("--batch-size", "5001"),
        ("--max-records", "0"),
    ],
)
def test_brand_backfill_parser_rejects_invalid_bounds(flag, value):
    with pytest.raises(SystemExit):
        build_parser().parse_args([
            "brands",
            "backfill",
            "--organization",
            "default-org",
            flag,
            value,
        ])


def test_source_request_writes_json_without_database(monkeypatch, tmp_path):
    candidate = _retry_candidate().model_copy(
        update={"status": "technical_hold", "probe_settings": None}
    )
    monkeypatch.setattr(cli, "load_candidate_catalog", lambda: [candidate])
    output = tmp_path / "source-request.json"

    exit_code = cli.main([
        "catalog",
        "source-request",
        "--candidate-key",
        candidate.key,
        "--format",
        "json",
        "--output",
        str(output),
    ])

    assert exit_code == 0
    payload = output.read_text(encoding="utf-8")
    assert '"candidate_key": "test_retry_candidate"' in payload
    assert '"reconciliation_requirements"' in payload


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


def test_scheduled_parser_requires_explicit_sources():
    args = build_parser().parse_args([
        "scheduled",
        "--organization",
        "default-org",
        "--source-key",
        "first_source",
        "--source-key",
        "second_source",
    ])

    assert args.command == "scheduled"
    assert args.source_keys == ["first_source", "second_source"]
    assert args.max_pages_per_source == 10
    assert args.reset_checkpoints is False


def test_scheduled_due_parser_defaults_to_one_executable_shard():
    args = build_parser().parse_args([
        "scheduled-due",
        "--organization",
        "default-org",
    ])

    assert args.command == "scheduled-due"
    assert args.source_keys is None
    assert args.shard_count == 1
    assert args.shard_index == 0
    assert args.plan_only is False
    assert args.max_pages_per_source is None
    assert args.rollout_wave is None


def test_scheduled_due_parser_accepts_reviewed_rollout_wave():
    args = build_parser().parse_args([
        "scheduled-due",
        "--organization",
        "default-org",
        "--rollout-wave",
        "2",
    ])

    assert args.rollout_wave == 2


def test_health_parser_supports_source_scoping():
    args = build_parser().parse_args([
        "health",
        "--organization",
        "default-org",
        "--source-key",
        "first_source",
        "--json",
    ])

    assert args.source_keys == ["first_source"]
    assert args.json is True


def test_retry_candidates_parser_accepts_deterministic_audit_date():
    args = build_parser().parse_args([
        "retry-candidates",
        "--organization",
        "default-org",
        "--candidate-key",
        "bend_or_planning_applications",
        "--as-of",
        "2026-08-02",
        "--sample-size",
        "5",
    ])

    assert args.command == "retry-candidates"
    assert args.as_of == date(2026, 8, 2)
    assert args.sample_size == 5
    assert args.force is False


def test_prepare_promotion_parser_is_offline_and_requires_review_artifacts():
    args = build_parser().parse_args([
        "catalog",
        "prepare-promotion",
        "--candidate-key",
        "bend_or_planning_applications",
        "--review-file",
        "review.json",
        "--output",
        "promoted.json",
    ])

    assert args.catalog_command == "prepare-promotion"
    assert args.candidate_key == "bend_or_planning_applications"
    assert not hasattr(args, "organization")


def test_prepare_promotion_command_does_not_open_database(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        cli,
        "prepare_promotion_manifest",
        lambda **kwargs: calls.append(kwargs) or [SimpleNamespace(key="candidate")],
    )
    monkeypatch.setattr(
        cli,
        "SessionLocal",
        lambda: (_ for _ in ()).throw(AssertionError("database should not open")),
    )
    review = tmp_path / "review.json"
    output = tmp_path / "promoted.json"

    result = cli.main([
        "catalog",
        "prepare-promotion",
        "--candidate-key",
        "candidate",
        "--review-file",
        str(review),
        "--output",
        str(output),
    ])

    assert result == 0
    assert calls[0]["candidate_key"] == "candidate"
    assert calls[0]["review_path"] == review
    assert calls[0]["output_path"] == output


def test_candidate_host_audit_is_offline(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_candidate_catalog", lambda: [_retry_candidate()])
    monkeypatch.setattr(
        cli,
        "SessionLocal",
        lambda: (_ for _ in ()).throw(AssertionError("database should not open")),
    )

    result = cli.main([
        "catalog",
        "candidate-host-audit",
        "--print-required-hosts",
    ])

    assert result == 0
    assert capsys.readouterr().out.strip() == "example.test"


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


def test_run_all_only_runs_selected_source_keys(db, monkeypatch):
    db.add(Organization(
        id="default-org", name="Default Organization", slug="default-org",
        is_active=True,
    ))
    db.add_all([
        IngestionSource(
            organization_id="default-org", key="a_source", name="A Source",
            adapter="csv", record_type="permit", is_active=True,
        ),
        IngestionSource(
            organization_id="default-org", key="b_source", name="B Source",
            adapter="csv", record_type="permit", is_active=True,
        ),
    ])
    db.commit()
    calls = []

    def fake_execute(_db, source, **kwargs):
        calls.append(source.key)
        return SimpleNamespace(
            status="completed", records_seen=1, records_inserted=1,
            records_updated=0, records_failed=0,
        )

    monkeypatch.setattr(cli, "SessionLocal", lambda: db)
    monkeypatch.setattr(cli, "execute_source_run", fake_execute)

    result = cli.main([
        "run-all", "--organization", "default-org",
        "--source-key", "b_source",
    ])

    assert result == 0
    assert calls == ["b_source"]


def test_scheduled_syncs_catalog_runs_sources_and_checks_health(db, monkeypatch):
    db.add(Organization(
        id="default-org", name="Default Organization", slug="default-org",
        is_active=True,
    ))
    db.add(IngestionSource(
        organization_id="default-org", key="wa_source", name="WA Source",
        adapter="csv", record_type="permit", is_active=True,
    ))
    db.commit()
    events = []

    monkeypatch.setattr(cli, "SessionLocal", lambda: db)
    catalog_entry = SimpleNamespace(key="wa_source")
    monkeypatch.setattr(cli, "load_catalog", lambda: [catalog_entry])
    monkeypatch.setattr(
        cli,
        "sync_catalog",
        lambda _db, entries: events.append(("sync", entries)) or SimpleNamespace(
            created=0, updated=0, unchanged=1,
        ),
    )
    monkeypatch.setattr(
        cli,
        "execute_source_run",
        lambda _db, source, **kwargs: events.append(("run", source.key, kwargs))
        or SimpleNamespace(
            status="completed", records_seen=1, records_inserted=1,
            records_updated=0, records_failed=0,
        ),
    )
    monkeypatch.setattr(
        cli,
        "evaluate_source_health",
        lambda _db, source: events.append(("health", source.key)) or SimpleNamespace(
            source_key=source.key, status="healthy", ingestion_age_hours=0.0,
            run_failure_rate=0.0, reasons=[],
        ),
    )

    result = cli.main([
        "scheduled", "--organization", "default-org",
        "--source-key", "wa_source", "--max-pages-per-source", "4",
    ])

    assert result == 0
    assert events[0] == ("sync", [catalog_entry])
    assert events[1][0:2] == ("run", "wa_source")
    assert events[1][2]["max_pages"] == 4
    assert events[1][2]["trigger"] == "scheduled"
    assert events[2] == ("health", "wa_source")


def test_scheduled_returns_critical_health_exit_code(db, monkeypatch):
    db.add(Organization(
        id="default-org", name="Default Organization", slug="default-org",
        is_active=True,
    ))
    db.add(IngestionSource(
        organization_id="default-org", key="wa_source", name="WA Source",
        adapter="csv", record_type="permit", is_active=True,
    ))
    db.commit()

    monkeypatch.setattr(cli, "SessionLocal", lambda: db)
    monkeypatch.setattr(
        cli, "load_catalog", lambda: [SimpleNamespace(key="wa_source")]
    )
    monkeypatch.setattr(
        cli, "sync_catalog",
        lambda _db, _entries: SimpleNamespace(created=0, updated=0, unchanged=1),
    )
    monkeypatch.setattr(
        cli, "execute_source_run",
        lambda *_args, **_kwargs: SimpleNamespace(
            status="completed", records_seen=0, records_inserted=0,
            records_updated=0, records_failed=0,
        ),
    )
    monkeypatch.setattr(
        cli, "evaluate_source_health",
        lambda _db, source: SimpleNamespace(
            source_key=source.key, status="critical", ingestion_age_hours=50.0,
            run_failure_rate=0.0, reasons=["Latest successful ingestion is 50 hours old"],
        ),
    )

    result = cli.main([
        "scheduled", "--organization", "default-org",
        "--source-key", "wa_source",
    ])

    assert result == 2


def test_scheduled_rejects_unknown_key_before_catalog_sync(db, monkeypatch):
    db.add(Organization(
        id="default-org", name="Default Organization", slug="default-org",
        is_active=True,
    ))
    db.commit()
    sync_calls = []

    monkeypatch.setattr(cli, "SessionLocal", lambda: db)
    monkeypatch.setattr(
        cli, "load_catalog", lambda: [SimpleNamespace(key="known_source")]
    )
    monkeypatch.setattr(
        cli, "sync_catalog",
        lambda *_args, **_kwargs: sync_calls.append(True),
    )

    result = cli.main([
        "scheduled", "--organization", "default-org",
        "--source-key", "missing_b", "--source-key", "missing_a",
    ])

    assert result == 1
    assert sync_calls == []


def test_scheduled_due_plan_only_syncs_and_does_not_execute(db, monkeypatch, capsys):
    db.add(Organization(
        id="default-org", name="Default Organization", slug="default-org",
        is_active=True,
    ))
    db.add(IngestionSource(
        organization_id="default-org", key="due_source", name="Due Source",
        adapter="csv", record_type="permit", is_active=True,
        settings={
            "collection_interval_minutes": 1440,
            "retry_interval_minutes": 60,
            "schedule_mode": "automatic",
        },
    ))
    db.commit()
    catalog_entry = _catalog_source("due_source")
    calls = []

    monkeypatch.setattr(cli, "SessionLocal", lambda: db)
    monkeypatch.setattr(cli, "load_catalog", lambda: [catalog_entry])
    monkeypatch.setattr(
        cli,
        "sync_catalog",
        lambda _db, entries, **kwargs: calls.append(("sync", entries, kwargs)) or SimpleNamespace(
            created=0, updated=0, unchanged=1,
        ),
    )
    monkeypatch.setattr(
        cli,
        "execute_source_run",
        lambda *_args, **_kwargs: calls.append(("run", None)),
    )

    result = cli.main([
        "scheduled-due", "--organization", "default-org", "--plan-only",
        "--as-of", "2026-08-11T12:00:00+00:00",
    ])

    assert result == 0
    assert calls == [("sync", [catalog_entry], {})]
    assert '"due_reason": "never_run"' in capsys.readouterr().out


def test_scheduled_due_plan_only_includes_unsynced_catalog_sources_then_rolls_back(
    db, monkeypatch, capsys,
):
    db.add(Organization(
        id="default-org", name="Default Organization", slug="default-org",
        is_active=True,
    ))
    db.commit()
    catalog_entry = _typed_catalog_source("new_source", "Austin, TX")

    monkeypatch.setattr(cli, "SessionLocal", lambda: db)
    monkeypatch.setattr(cli, "load_catalog", lambda: [catalog_entry])

    result = cli.main([
        "scheduled-due", "--organization", "default-org", "--plan-only",
        "--as-of", "2026-08-11T12:00:00+00:00",
    ])

    assert result == 0
    output = capsys.readouterr().out
    assert '"catalog_synced": true' in output
    assert '"due_source_count": 1' in output
    assert '"source_key": "new_source"' in output
    assert db.query(IngestionSource).filter_by(key="new_source").first() is None


def test_scheduled_due_rejects_historical_execution(db, monkeypatch):
    db.add(Organization(
        id="default-org", name="Default Organization", slug="default-org",
        is_active=True,
    ))
    db.commit()
    sync_calls = []
    monkeypatch.setattr(cli, "SessionLocal", lambda: db)
    monkeypatch.setattr(
        cli,
        "sync_catalog",
        lambda *_args, **_kwargs: sync_calls.append(True),
    )

    result = cli.main([
        "scheduled-due", "--organization", "default-org",
        "--as-of", "2026-08-11T12:00:00+00:00",
    ])

    assert result == 1
    assert sync_calls == []


def test_scheduled_preflight_runs_before_catalog_sync(db, monkeypatch):
    db.add(Organization(
        id="default-org", name="Default Organization", slug="default-org",
        is_active=True,
    ))
    db.commit()
    sync_calls = []
    monkeypatch.setattr(cli, "SessionLocal", lambda: db)
    monkeypatch.setattr(cli, "load_catalog", lambda: [_catalog_source("due_source")])
    monkeypatch.setattr(
        cli,
        "_enforce_catalog_host_policy",
        lambda _entries: (_ for _ in ()).throw(ValueError("blocked by host policy")),
    )
    monkeypatch.setattr(
        cli,
        "sync_catalog",
        lambda *_args, **_kwargs: sync_calls.append(True),
    )

    result = cli.main([
        "scheduled", "--organization", "default-org", "--source-key", "due_source",
    ])

    assert result == 1
    assert sync_calls == []


def test_catalog_scope_matches_stage_and_shard():
    entries = [
        _catalog_source("approved_a", signal_stage="approved_only"),
        _catalog_source("approved_b", signal_stage="approved_only"),
        _catalog_source("preapproval", signal_stage="pre_approval_and_approved"),
    ]
    expected = [
        entry.key for entry in entries
        if entry.settings["signal_stage"] == "approved_only"
        and cli.source_shard(entry.key, 2) == 1
    ]

    scoped = cli._scope_catalog_entries(
        entries,
        stage="approved_only",
        shard_count=2,
        shard_index=1,
    )

    assert [entry.key for entry in scoped] == expected


def test_catalog_scope_applies_rollout_wave_to_the_executable_set(monkeypatch):
    entries = [
        _typed_catalog_source("wave_one", "Austin, TX"),
        _typed_catalog_source("wave_two", "Los Angeles, CA"),
    ]

    scoped = cli._scope_catalog_entries(entries, rollout_wave=2)

    assert [entry.key for entry in scoped] == ["wave_two"]


def test_catalog_scope_rejects_explicit_source_outside_rollout_wave():
    entries = [_typed_catalog_source("wave_one", "Austin, TX")]

    with pytest.raises(ValueError, match="outside the selected"):
        cli._scope_catalog_entries(
            entries,
            source_keys=["wave_one"],
            rollout_wave=2,
        )


def test_scheduled_due_executes_only_due_catalog_sources(db, monkeypatch):
    db.add(Organization(
        id="default-org", name="Default Organization", slug="default-org",
        is_active=True,
    ))
    due = IngestionSource(
        organization_id="default-org", key="due_source", name="Due Source",
        adapter="csv", record_type="permit", is_active=True,
        settings={
            "collection_interval_minutes": 1440,
            "retry_interval_minutes": 60,
            "schedule_mode": "automatic",
            "max_pages_per_run": 3,
        },
    )
    runtime_only = IngestionSource(
        organization_id="default-org", key="runtime_only", name="Runtime Only",
        adapter="csv", record_type="permit", is_active=True,
        settings={
            "collection_interval_minutes": 1440,
            "retry_interval_minutes": 60,
            "schedule_mode": "automatic",
        },
    )
    db.add_all([due, runtime_only])
    db.commit()
    calls = []

    monkeypatch.setattr(cli, "SessionLocal", lambda: db)
    monkeypatch.setattr(
        cli, "load_catalog", lambda: [
            _catalog_source("due_source", max_pages_per_run=3)
        ]
    )
    monkeypatch.setattr(
        cli,
        "sync_catalog",
        lambda *_args, **_kwargs: SimpleNamespace(created=0, updated=0, unchanged=1),
    )
    monkeypatch.setattr(cli, "resolve_resume_checkpoint", lambda *_args: None)
    monkeypatch.setattr(
        cli,
        "execute_source_run",
        lambda _db, source, **kwargs: calls.append((source.key, kwargs))
        or SimpleNamespace(
            status="completed", records_seen=1, records_inserted=1,
            records_updated=0, records_failed=0,
        ),
    )
    monkeypatch.setattr(
        cli,
        "evaluate_source_health",
        lambda _db, source: SimpleNamespace(
            source_key=source.key, status="healthy", ingestion_age_hours=0.0,
            run_failure_rate=0.0, reasons=[],
        ),
    )

    result = cli.main([
        "scheduled-due", "--organization", "default-org",
    ])

    assert result == 0
    assert [key for key, _kwargs in calls] == ["due_source"]
    assert calls[0][1]["max_pages"] == 3


def test_scheduled_due_executes_only_the_selected_rollout_wave(
    db, monkeypatch, capsys
):
    db.add(Organization(
        id="default-org", name="Default Organization", slug="default-org",
        is_active=True,
    ))
    for key in ("wave_one", "wave_two"):
        db.add(IngestionSource(
            organization_id="default-org", key=key, name=key,
            adapter="csv", record_type="permit", is_active=True,
            settings={
                "collection_interval_minutes": 1440,
                "retry_interval_minutes": 60,
                "schedule_mode": "automatic",
            },
        ))
    db.commit()
    calls = []
    synced_keys = []
    monkeypatch.setattr(cli, "SessionLocal", lambda: db)
    monkeypatch.setattr(
        cli,
        "load_catalog",
        lambda: [
            _typed_catalog_source("wave_one", "Austin, TX"),
            _typed_catalog_source("wave_two", "Los Angeles, CA"),
        ],
    )
    monkeypatch.setattr(
        cli,
        "require_current_rollout_manifest",
        lambda *_args, **_kwargs: SimpleNamespace(
            waves=[SimpleNamespace(source_keys=["wave_one"])]
        ),
    )
    monkeypatch.setattr(
        cli, "sync_catalog",
        lambda _db, entries, **_kwargs: synced_keys.extend(
            entry.key for entry in entries
        ) or SimpleNamespace(created=0, updated=0, unchanged=1),
    )
    monkeypatch.setattr(cli, "resolve_resume_checkpoint", lambda *_args: None)
    monkeypatch.setattr(
        cli, "execute_source_run",
        lambda _db, source, **_kwargs: calls.append(source.key) or SimpleNamespace(
            status="completed", records_seen=1, records_inserted=1,
            records_updated=0, records_failed=0,
        ),
    )
    monkeypatch.setattr(
        cli, "evaluate_source_health",
        lambda _db, source: SimpleNamespace(
            source_key=source.key, status="healthy", ingestion_age_hours=0.0,
            run_failure_rate=0.0, reasons=[],
        ),
    )

    result = cli.main([
        "scheduled-due", "--organization", "default-org", "--rollout-wave", "1",
    ])

    assert result == 0
    assert synced_keys == ["wave_one"]
    assert calls == ["wave_one"]
    assert '"catalog_source_count": 1' in capsys.readouterr().out


def test_production_scheduled_due_requires_explicit_wave(db, monkeypatch):
    db.add(Organization(
        id="default-org", name="Default Organization", slug="default-org",
        is_active=True,
    ))
    db.commit()
    monkeypatch.setattr(cli, "SessionLocal", lambda: db)
    monkeypatch.setattr(cli, "ENVIRONMENT", "production")
    monkeypatch.setattr(
        cli,
        "load_catalog",
        lambda: (_ for _ in ()).throw(AssertionError("catalog should not load")),
    )

    result = cli.main(["scheduled-due", "--organization", "default-org"])

    assert result == 1


def test_deployed_rollout_requires_matching_manifest_digest(monkeypatch):
    manifest = SimpleNamespace(manifest_digest="reviewed-digest")
    monkeypatch.setattr(cli, "ENVIRONMENT", "production")
    monkeypatch.delenv("INGESTION_ROLLOUT_MANIFEST_DIGEST", raising=False)

    with pytest.raises(ValueError, match="must be configured"):
        cli._enforce_rollout_manifest_attestation(manifest)

    monkeypatch.setenv("INGESTION_ROLLOUT_MANIFEST_DIGEST", "stale-digest")
    with pytest.raises(ValueError, match="does not match deployment"):
        cli._enforce_rollout_manifest_attestation(manifest)

    monkeypatch.setenv("INGESTION_ROLLOUT_MANIFEST_DIGEST", "reviewed-digest")
    cli._enforce_rollout_manifest_attestation(manifest)


def test_candidate_rollout_scope_pins_keys_and_sample_size():
    manifest = _approved_retry_manifest()
    candidate = _retry_candidate()

    cli._validate_candidate_rollout_scope(manifest, [candidate], sample_size=10)
    with pytest.raises(ValueError, match="sample size"):
        cli._validate_candidate_rollout_scope(manifest, [candidate], sample_size=5)
    with pytest.raises(ValueError, match="absent from the reviewed"):
        cli._validate_candidate_rollout_scope(
            manifest,
            [candidate.model_copy(update={"key": "unapproved"})],
            sample_size=10,
        )


def test_scheduled_due_concurrent_claim_is_not_health_failure(db, monkeypatch):
    db.add(Organization(
        id="default-org", name="Default Organization", slug="default-org",
        is_active=True,
    ))
    db.add(IngestionSource(
        organization_id="default-org", key="due_source", name="Due Source",
        adapter="csv", record_type="permit", is_active=True,
    ))
    db.commit()
    health_calls = []
    monkeypatch.setattr(cli, "SessionLocal", lambda: db)
    monkeypatch.setattr(cli, "load_catalog", lambda: [_catalog_source("due_source")])
    monkeypatch.setattr(
        cli, "sync_catalog",
        lambda *_args, **_kwargs: SimpleNamespace(created=0, updated=0, unchanged=1),
    )
    monkeypatch.setattr(
        cli, "execute_source_run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            cli.ActiveRunConflict("already claimed")
        ),
    )
    monkeypatch.setattr(
        cli, "evaluate_source_health",
        lambda *_args, **_kwargs: health_calls.append(True),
    )

    result = cli.main(["scheduled-due", "--organization", "default-org"])

    assert result == 0
    assert health_calls == []


def test_run_all_explicit_filter_does_not_succeed_when_stage_excludes_it(
    db, monkeypatch
):
    db.add(Organization(
        id="default-org", name="Default Organization", slug="default-org",
        is_active=True,
    ))
    db.add(IngestionSource(
        organization_id="default-org", key="approved_source", name="Approved Source",
        adapter="csv", record_type="permit", is_active=True,
        settings={"signal_stage": "approved_only"},
    ))
    db.commit()
    monkeypatch.setattr(cli, "SessionLocal", lambda: db)

    result = cli.main([
        "run-all", "--organization", "default-org",
        "--source-key", "approved_source",
        "--stage", "pre_approval_and_approved",
    ])

    assert result == 1


def test_select_due_candidates_returns_only_overdue_runnable_probes(db, monkeypatch):
    monkeypatch.setattr(cli, "load_candidate_catalog", lambda: [_retry_candidate()])
    monkeypatch.setattr(cli, "list_candidate_canary_attempts", lambda *_args, **_kwargs: [])

    selected = cli._select_due_candidates(db, as_of=date(2026, 8, 2))

    assert [candidate.key for candidate in selected] == ["test_retry_candidate"]


def test_successful_post_audit_candidate_canary_stops_future_retries(db, monkeypatch):
    attempt = SimpleNamespace(
        ok=True,
        created_at=SimpleNamespace(date=lambda: date(2026, 8, 2)),
    )
    monkeypatch.setattr(
        cli, "list_candidate_canary_attempts", lambda *_args, **_kwargs: [attempt]
    )
    monkeypatch.setattr(cli, "load_candidate_catalog", lambda: [_retry_candidate()])

    selected = cli._select_due_candidates(
        db,
        as_of=date(2026, 8, 3),
        candidate_keys=["test_retry_candidate"],
    )

    assert selected == []

    forced = cli._select_due_candidates(
        db,
        as_of=date(2026, 8, 3),
        candidate_keys=["test_retry_candidate"],
        force=True,
    )
    assert [candidate.key for candidate in forced] == ["test_retry_candidate"]


def test_retry_candidates_records_transport_failure_and_continues(db, monkeypatch):
    db.add(Organization(
        id="default-org", name="Default Organization", slug="default-org",
        is_active=True,
    ))
    db.commit()
    recorded = []

    monkeypatch.setattr(cli, "SessionLocal", lambda: db)
    monkeypatch.setattr(cli, "load_candidate_catalog", lambda: [_retry_candidate()])
    monkeypatch.setattr(
        cli, "require_current_rollout_manifest",
        lambda *_args, **_kwargs: _approved_retry_manifest(),
    )
    monkeypatch.setattr(cli, "list_candidate_canary_attempts", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        cli,
        "validate_candidate_source_canary",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("feed offline")),
    )
    monkeypatch.setattr(
        cli,
        "record_candidate_canary_attempt",
        lambda _db, candidate, result, **kwargs: recorded.append(
            (candidate.key, result, kwargs)
        ),
    )

    result = cli.main([
        "retry-candidates", "--organization", "default-org",
        "--candidate-key", "test_retry_candidate",
        "--as-of", "2026-08-02",
    ])

    assert result == 1
    assert recorded[0][0] == "test_retry_candidate"
    assert recorded[0][1].ok is False
    assert recorded[0][1].errors == ["RuntimeError: feed offline"]
    assert recorded[0][2]["sample_size"] == 10


def test_retry_candidates_returns_success_after_persisted_canary(db, monkeypatch):
    db.add(Organization(
        id="default-org", name="Default Organization", slug="default-org",
        is_active=True,
    ))
    db.commit()
    recorded = []
    canary = CandidateCanaryResult(
        candidate_key="test_retry_candidate",
        candidate_name="Test Retry Candidate",
        ok=True,
        records_fetched=5,
        records_valid=5,
        records_failed=0,
        approval_stages={"pre_approval": 5},
        sample_record_ids=["1"],
        next_checkpoint=None,
        errors=[],
    )

    monkeypatch.setattr(cli, "SessionLocal", lambda: db)
    monkeypatch.setattr(cli, "load_candidate_catalog", lambda: [_retry_candidate()])
    monkeypatch.setattr(
        cli, "require_current_rollout_manifest",
        lambda *_args, **_kwargs: _approved_retry_manifest(),
    )
    monkeypatch.setattr(cli, "list_candidate_canary_attempts", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(cli, "validate_candidate_source_canary", lambda *_args, **_kwargs: canary)
    monkeypatch.setattr(
        cli,
        "record_candidate_canary_attempt",
        lambda _db, candidate, result, **kwargs: recorded.append((candidate.key, result)),
    )

    result = cli.main([
        "retry-candidates", "--organization", "default-org",
        "--candidate-key", "test_retry_candidate",
        "--as-of", "2026-08-02",
    ])

    assert result == 0
    assert recorded == [("test_retry_candidate", canary)]


def test_retry_candidates_host_preflight_blocks_before_network(db, monkeypatch):
    db.add(Organization(
        id="default-org", name="Default Organization", slug="default-org",
        is_active=True,
    ))
    db.commit()
    network_calls = []
    monkeypatch.setattr(cli, "SessionLocal", lambda: db)
    monkeypatch.setattr(cli, "load_candidate_catalog", lambda: [_retry_candidate()])
    monkeypatch.setattr(
        cli, "require_current_rollout_manifest",
        lambda *_args, **_kwargs: _approved_retry_manifest(),
    )
    monkeypatch.setattr(cli, "list_candidate_canary_attempts", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        cli,
        "_enforce_catalog_host_policy",
        lambda entries: (_ for _ in ()).throw(ValueError("blocked candidate host")),
    )
    monkeypatch.setattr(
        cli,
        "validate_candidate_source_canary",
        lambda *_args, **_kwargs: network_calls.append(True),
    )

    result = cli.main([
        "retry-candidates",
        "--organization",
        "default-org",
        "--as-of",
        "2026-08-02",
    ])

    assert result == 1
    assert network_calls == []


def test_retry_candidates_must_be_named_in_current_manifest(db, monkeypatch):
    db.add(Organization(
        id="default-org", name="Default Organization", slug="default-org",
        is_active=True,
    ))
    db.commit()
    network_calls = []
    monkeypatch.setattr(cli, "SessionLocal", lambda: db)
    monkeypatch.setattr(cli, "load_candidate_catalog", lambda: [_retry_candidate()])
    monkeypatch.setattr(cli, "list_candidate_canary_attempts", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        cli,
        "require_current_rollout_manifest",
        lambda *_args, **_kwargs: SimpleNamespace(
            candidate_retries=SimpleNamespace(candidate_keys=[], sample_size=10),
        ),
    )
    monkeypatch.setattr(
        cli,
        "validate_candidate_source_canary",
        lambda *_args, **_kwargs: network_calls.append(True),
    )

    result = cli.main([
        "retry-candidates",
        "--organization",
        "default-org",
        "--as-of",
        "2026-08-02",
    ])

    assert result == 1
    assert network_calls == []
