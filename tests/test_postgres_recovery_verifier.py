"""Offline CLI contract tests: never create an engine or load app configuration."""
import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock

import pytest


@pytest.fixture
def cli(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "scripts/verify_postgres_recovery.py"
    spec = importlib.util.spec_from_file_location("recovery_cli", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.os, "environ", {})
    monkeypatch.setattr(module.sys, "argv", [str(path), "--isolated-restored-copy"])
    module.create_engine = Mock(side_effect=AssertionError("Real engine forbidden"))
    module.verify_restored_postgres = Mock(side_effect=AssertionError("Real probe forbidden"))
    return module


@pytest.mark.parametrize("url", [
    None, "", "   ", "not-a-url", "sqlite:///:memory:",
    "postgresql:///restored", "postgresql://localhost",
    "postgresql://localhost:invalid/restored",
    "postgresql://localhost/restored?host=production",
    "postgresql://localhost/restored?hostaddr=192.0.2.1",
    "postgresql://localhost/restored?service=production",
    "postgresql://localhost/restored?port=5433",
    "postgresql://localhost/restored?dbname=production",
])
def test_invalid_target_refused_before_engine_creation(cli, url):
    if url is not None:
        cli.os.environ["RESTORE_DATABASE_URL"] = url
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
    cli.create_engine.assert_not_called()
    cli.verify_restored_postgres.assert_not_called()


def test_acknowledgment_is_required(cli):
    cli.sys.argv = ["verify_postgres_recovery.py"]
    cli.os.environ["RESTORE_DATABASE_URL"] = "postgresql://localhost/restored"
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
    cli.create_engine.assert_not_called()


@pytest.mark.parametrize("target", [
    "postgresql://original:secret@db.example/app",
    "postgresql+psycopg2://other:different@db.example/app",
    "postgresql://db.example:5432/app?sslmode=require",
    "postgresql://DB.EXAMPLE/app",
])
def test_same_database_refused_despite_url_variations(cli, target, capsys):
    cli.os.environ.update(DATABASE_URL="postgresql://original:secret@db.example/app",
                          RESTORE_DATABASE_URL=target)
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
    cli.create_engine.assert_not_called()
    assert "secret" not in capsys.readouterr().err


@pytest.mark.parametrize("passed,exit_code", [(True, 0), (False, 1), ("false", 1), (1, 1), (None, 1)])
def test_only_explicit_boolean_pass_is_accepted(cli, capsys, passed, exit_code):
    cli.os.environ.update(DATABASE_URL="postgresql://localhost/app",
                          RESTORE_DATABASE_URL="postgresql://localhost/restored")
    engine = Mock()
    cli.create_engine.side_effect = None
    cli.create_engine.return_value = engine
    report = {"passed": passed, "scope": "synthetic offline report"}
    cli.verify_restored_postgres.side_effect = None
    cli.verify_restored_postgres.return_value = report
    assert cli.main() == exit_code
    assert json.loads(capsys.readouterr().out) == report
    cli.verify_restored_postgres.assert_called_once_with(engine)
    engine.dispose.assert_called_once_with()


@pytest.mark.parametrize("stage", ["engine", "probe"])
def test_failures_are_redacted_and_created_engine_is_disposed(cli, capsys, stage):
    cli.os.environ["RESTORE_DATABASE_URL"] = "postgresql://user:private-password@localhost/restored"
    engine = Mock()
    failure = RuntimeError("private-password connection details")
    if stage == "engine":
        cli.create_engine.side_effect = failure
    else:
        cli.create_engine.side_effect = None
        cli.create_engine.return_value = engine
        cli.verify_restored_postgres.side_effect = failure
    assert cli.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "probe failed" in captured.err
    assert "private-password" not in captured.err
    if stage == "probe":
        engine.dispose.assert_called_once_with()
    else:
        cli.verify_restored_postgres.assert_not_called()


@pytest.mark.parametrize("report", [{}, None, [], {"passed": "true"}])
def test_missing_or_malformed_acceptance_fails_closed(cli, report):
    cli.os.environ["RESTORE_DATABASE_URL"] = "postgresql://localhost/restored"
    engine = Mock()
    cli.create_engine.side_effect = None
    cli.create_engine.return_value = engine
    cli.verify_restored_postgres.side_effect = None
    cli.verify_restored_postgres.return_value = report
    assert cli.main() == 1
    engine.dispose.assert_called_once_with()
