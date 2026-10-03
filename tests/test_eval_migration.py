"""Evaluation schema parity, tenant constraints, RLS DDL, and reversibility."""
from __future__ import annotations

import importlib.util
from io import StringIO
from pathlib import Path
from uuid import UUID

import pytest
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.exc import IntegrityError

from app.db import configure_sqlite_foreign_keys
from app.models.evaluation import EvalCase, EvalDataset, EvalMetric, EvalResult, EvalRun
from app.models.mixins import OrgMixin

_MODELS = (EvalDataset, EvalCase, EvalRun, EvalResult, EvalMetric)
_TABLES = tuple(model.__tablename__ for model in _MODELS)
_PATH = (
    Path(__file__).resolve().parent.parent
    / "alembic/versions/20260920_0001_ai_evaluations.py"
)


@pytest.fixture()
def migration():
    spec = importlib.util.spec_from_file_location("eval_migration", _PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def connection(migration):
    engine = sa.create_engine("sqlite://")
    configure_sqlite_foreign_keys(engine)
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE organizations (id VARCHAR(36) NOT NULL PRIMARY KEY)"))
        conn.execute(sa.text("CREATE TABLE users (id VARCHAR(36) NOT NULL PRIMARY KEY)"))
        conn.execute(sa.text("INSERT INTO organizations VALUES ('org-a'), ('org-b')"))
        conn.execute(sa.text("INSERT INTO users VALUES ('author')"))
        migration.op = Operations(MigrationContext.configure(conn))
        migration.upgrade()
        yield conn
    engine.dispose()


@pytest.fixture()
def seeded(connection):
    for org in ("a", "b"):
        common = {"organization_id": f"org-{org}"}
        connection.execute(EvalDataset.__table__.insert().values(
            **common, id=f"dataset-{org}", name="Dataset", workflow="copilot_answer",
            created_by="author",
        ))
        connection.execute(EvalCase.__table__.insert().values(
            **common, id=f"case-{org}", dataset_id=f"dataset-{org}", name="Case",
            input_json={}, expected_output={},
        ))
        connection.execute(EvalRun.__table__.insert().values(
            **common, id=f"run-{org}", dataset_id=f"dataset-{org}", created_by="author",
            mode="replay", model="test-model", prompt_version="v1", status="running",
            dataset_fingerprint="a" * 64, thresholds={},
        ))
        connection.execute(EvalResult.__table__.insert().values(
            **common, id=f"result-{org}", run_id=f"run-{org}", case_id=f"case-{org}",
            case_snapshot={}, status="passed", model="test-model", prompt_version="v1",
            latency_ms=1.5,
        ))
        connection.execute(EvalMetric.__table__.insert().values(
            **common, id=f"metric-{org}", result_id=f"result-{org}", name=f"accuracy-{org}", value=1,
        ))
    return connection


def test_migration_matches_model_metadata(connection):
    metadata = sa.MetaData()
    for name in ("organizations", "users"):
        sa.Table(name, metadata, sa.Column("id", sa.String(36), primary_key=True))
    for model in _MODELS:
        assert issubclass(model, OrgMixin)
        model.__table__.to_metadata(metadata)
    context = MigrationContext.configure(connection, opts={"compare_server_default": True})
    assert compare_metadata(context, metadata) == []
    # Alembic autogeneration does not compare CHECK constraints.
    inspector = sa.inspect(connection)
    for model in _MODELS:
        expected = {
            constraint.name: str(constraint.sqltext)
            for constraint in model.__table__.constraints
            if isinstance(constraint, sa.CheckConstraint)
        }
        actual = {
            constraint["name"]: constraint["sqltext"]
            for constraint in inspector.get_check_constraints(model.__tablename__)
        }
        assert actual == expected


def test_migration_round_trip_with_data(seeded, migration):
    assert migration.revision == "20260920_0001"
    assert migration.down_revision == "20260915_0001"
    migration.downgrade()
    assert set(sa.inspect(seeded).get_table_names()) == {"organizations", "users"}
    migration.upgrade()
    assert set(_TABLES) <= set(sa.inspect(seeded).get_table_names())
    test_migration_matches_model_metadata(seeded)


@pytest.mark.parametrize(("model", "column", "foreign_id"), [
    (EvalCase, "dataset_id", "dataset-b"),
    (EvalRun, "dataset_id", "dataset-b"),
    (EvalResult, "run_id", "run-b"),
    (EvalResult, "case_id", "case-b"),
    (EvalMetric, "result_id", "result-b"),
])
def test_parent_fk_rejects_other_tenant(seeded, model, column, foreign_id):
    table = model.__table__
    with pytest.raises(IntegrityError, match="FOREIGN KEY"):
        seeded.execute(table.update().where(table.c.organization_id == "org-a").values(
            **{column: foreign_id}
        ))


@pytest.mark.parametrize("model", [EvalDataset, EvalResult, EvalMetric])
def test_unique_constraints(seeded, model):
    table = model.__table__
    row = dict(seeded.execute(sa.select(table).where(
        table.c.organization_id == "org-a"
    )).mappings().one())
    row["id"] = "duplicate"
    with pytest.raises(IntegrityError, match="UNIQUE"):
        seeded.execute(table.insert().values(**row))


@pytest.mark.parametrize(("model", "column", "value"), [
    (EvalDataset, "workflow", "unsupported"),
    (EvalRun, "mode", "unsupported"),
    (EvalRun, "status", "passed"),
    (EvalResult, "status", "completed"),
    (EvalMetric, "value", -0.01),
    (EvalMetric, "value", 1.01),
    (EvalMetric, "value", float("inf")),
])
def test_check_constraints(seeded, model, column, value):
    with pytest.raises(IntegrityError, match="CHECK"):
        seeded.execute(model.__table__.update().values(**{column: value}))


@pytest.mark.parametrize("value", [0.0, 0.5, 1.0])
def test_normalized_metric_accepts_boundaries(seeded, value):
    seeded.execute(EvalMetric.__table__.update().values(value=value))
    assert seeded.execute(sa.select(EvalMetric.value).distinct()).scalar_one() == value


def test_defaults_nullable_output_and_user_deletion(seeded):
    dataset = seeded.execute(sa.select(EvalDataset.__table__)).mappings().first()
    case = seeded.execute(sa.select(EvalCase.__table__)).mappings().first()
    run = seeded.execute(sa.select(EvalRun.__table__)).mappings().first()
    result = seeded.execute(sa.select(EvalResult.__table__)).mappings().first()
    assert dataset["description"] == ""
    assert case["critical"] is True
    assert case["retrieved_context"] == []
    assert run["summary"] == {}
    assert run["gate_passed"] is False
    assert run["finished_at"] is None
    assert result["retrieved_context"] == []
    for column in ("actual_output", "error_code", "tokens_input", "tokens_output", "cost_usd"):
        assert result[column] is None
    assert seeded.execute(sa.text(
        "SELECT actual_output IS NULL FROM eval_result WHERE id = 'result-a'"
    )).scalar_one() == 1
    seeded.execute(sa.text("DELETE FROM users WHERE id = 'author'"))
    for model in (EvalDataset, EvalRun):
        assert seeded.execute(sa.select(model.created_by).distinct()).scalar_one() is None
    for model in _MODELS:
        identifier = model.__table__.c.id.default.arg(None)
        assert str(UUID(identifier)) == identifier
        for column in model.__table__.c:
            if isinstance(column.type, sa.DateTime):
                assert column.type.timezone is True
                if column.default is not None:
                    assert column.default.arg(None).utcoffset().total_seconds() == 0


def test_server_defaults_without_orm(connection):
    connection.execute(sa.text(
        "INSERT INTO eval_dataset (id, organization_id, name, workflow, created_at) "
        "VALUES ('dataset', 'org-a', 'Dataset', 'score_explanation', CURRENT_TIMESTAMP)"
    ))
    connection.execute(sa.text(
        "INSERT INTO eval_case "
        "(id, organization_id, dataset_id, name, input_json, expected_output, "
        "retrieved_context, created_at) VALUES "
        "('case', 'org-a', 'dataset', 'Case', '{}', '{}', '[]', CURRENT_TIMESTAMP)"
    ))
    connection.execute(sa.text(
        "INSERT INTO eval_run (id, organization_id, dataset_id, mode, model, prompt_version, "
        "status, dataset_fingerprint, thresholds, started_at) VALUES "
        "('run', 'org-a', 'dataset', 'live', 'test', 'v1', 'running', :fingerprint, '{}', "
        "CURRENT_TIMESTAMP)"
    ), {"fingerprint": "a" * 64})
    assert connection.execute(sa.select(EvalDataset.description)).scalar_one() == ""
    assert connection.execute(sa.select(EvalCase.critical)).scalar_one() is True
    assert connection.execute(sa.select(EvalRun.summary)).scalar_one() == {}
    assert connection.execute(sa.select(EvalRun.gate_passed)).scalar_one() is False


@pytest.mark.parametrize("parent", ["organizations", "eval_dataset"])
def test_parent_delete_cascades_only_its_tenant(seeded, parent):
    identifier = "org-a" if parent == "organizations" else "dataset-a"
    seeded.execute(sa.text(f"DELETE FROM {parent} WHERE id = :id"), {"id": identifier})
    for model in _MODELS:
        assert seeded.execute(sa.select(model.organization_id)).scalars().all() == ["org-b"]


def test_postgres_rls_and_reversible_ddl(migration):
    output = StringIO()
    context = MigrationContext.configure(dialect_name="postgresql", opts={
        "as_sql": True, "output_buffer": output,
    })
    migration.op = Operations(context)
    migration.upgrade()
    upgrade = output.getvalue()
    for table in _TABLES:
        assert f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY' in upgrade
        assert f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY' in upgrade
        assert (
            f'CREATE POLICY tenant_isolation ON "{table}" '
            "USING (organization_id = current_setting('app.current_org', true)) "
            "WITH CHECK (organization_id = current_setting('app.current_org', true))"
        ) in upgrade
    assert "default-org" not in upgrade
    output.seek(0)
    output.truncate()
    migration.downgrade()
    drops = [line for line in output.getvalue().splitlines() if line.startswith("DROP TABLE")]
    assert drops == [f"DROP TABLE {table};" for table in reversed(_TABLES)]
