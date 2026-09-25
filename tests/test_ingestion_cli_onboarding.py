from __future__ import annotations

import json

import httpx
import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import sessionmaker

from app.models.audit_log import AuditLog
from app.models.ingestion import IngestionSource, SourceFieldMapping
from app.models.ingestion_onboarding import (
    OrganizationIngestionEnrollment,
    OrganizationIngestionEnrollmentSource,
)
from app.models.organization import Organization
from app.models.organization_membership import MemberRole, OrganizationMembership
from app.models.user import User
from app.services.ingestion import cli, onboarding, service
from app.services.ingestion.scheduling import source_shard
from app.utils.org_scope import (
    RequestContext,
    get_current_context,
    reset_current_context,
    set_current_context,
)

ORG_ID = "onboarding-org"
ORG_SLUG = "onboarding-customer"
OTHER_ORG_ID = "other-onboarding-org"
ADMIN_ID = "onboarding-admin"
OTHER_ADMIN_ID = "other-onboarding-admin"
MODES = ("plan", "activate", "dry-run")


def _argv(mode, *, organization=ORG_SLUG, actor=ADMIN_ID, scope=None):
    args = [
        "onboarding", "plan" if mode == "plan" else "activate",
        "--organization", organization,
    ]
    if mode != "plan":
        args += ["--actor-user-id", actor]
    if mode == "dry-run":
        args += ["--dry-run"]
    return args + (scope if scope is not None else [
        "--coverage-mode", "selected_states", "--region", "TX",
        "--record-type", "permit", "--rollout-wave", "1",
    ])


def _state(db):
    db.expire_all()
    return {
        model.__tablename__: db.execute(
            model.__table__.select().order_by(*model.__table__.primary_key.columns)
        ).mappings().all()
        for model in (
            IngestionSource, SourceFieldMapping,
            OrganizationIngestionEnrollment, OrganizationIngestionEnrollmentSource,
            AuditLog,
        )
    }


@pytest.fixture()
def onboarding_db(db, monkeypatch):
    # Catch accidental use of the CLI's synthetic system-user ID as an FK.
    db.execute(text("PRAGMA foreign_keys = ON"))
    assert db.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
    db.add_all([
        Organization(id=ORG_ID, name="Customer", slug=ORG_SLUG, is_active=True),
        Organization(
            id=OTHER_ORG_ID, name="Other Customer", slug="other-customer",
            is_active=True,
        ),
        Organization(id="inactive-org", name="Inactive", slug="inactive", is_active=False),
        User(
            id=ADMIN_ID, email="onboarding-admin@example.test", full_name="Admin",
            password_hash="unused", is_active=True,
        ),
        User(
            id=OTHER_ADMIN_ID, email="other-admin@example.test", full_name="Other Admin",
            password_hash="unused", is_active=True,
        ),
    ])
    db.flush()
    db.add_all([
        OrganizationMembership(
            organization_id=ORG_ID, user_id=ADMIN_ID, role=MemberRole.admin,
        ),
        OrganizationMembership(
            organization_id=OTHER_ORG_ID, user_id=OTHER_ADMIN_ID, role=MemberRole.admin,
        ),
    ])
    db.commit()
    engine = db.get_bind()
    monkeypatch.setattr(cli, "SessionLocal", sessionmaker(bind=engine, autoflush=False))
    monkeypatch.setattr(cli, "ENVIRONMENT", "development")

    def no_fetch(*_args, **_kwargs):
        pytest.fail("Onboarding must not fetch or dispatch ingestion")

    monkeypatch.setattr(cli, "execute_source_run", no_fetch)
    monkeypatch.setattr(service, "execute_source_run", no_fetch)
    monkeypatch.setattr(cli, "dispatch_enrolled_ingestion", no_fetch)
    monkeypatch.setattr(httpx.Client, "send", no_fetch)

    writes = []
    commits = []

    def record_write(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().split()[0].upper() in {"INSERT", "UPDATE", "DELETE"}:
            writes.append(statement)

    def record_commit(_conn):
        commits.append(True)

    event.listen(engine, "before_cursor_execute", record_write)
    event.listen(engine, "commit", record_commit)
    outer = RequestContext(OTHER_ORG_ID, OTHER_ADMIN_ID)
    token = set_current_context(outer)
    try:
        yield db, writes, commits
        assert get_current_context() == outer
    finally:
        reset_current_context(token)
        event.remove(engine, "before_cursor_execute", record_write)
        event.remove(engine, "commit", record_commit)


@pytest.mark.parametrize("command", ["plan", "activate"])
def test_onboarding_requires_explicit_organization(command):
    with pytest.raises(SystemExit) as exc:
        cli.build_parser().parse_args(["onboarding", command])
    assert exc.value.code == 2


def test_activation_requires_explicit_actor():
    with pytest.raises(SystemExit) as exc:
        cli.build_parser().parse_args(["onboarding", "activate", "--organization", ORG_ID])
    assert exc.value.code == 2


@pytest.mark.parametrize("mode", ["plan", "activate"])
@pytest.mark.parametrize("organization", [ORG_ID, ORG_SLUG])
def test_onboarding_resolves_only_selected_tenant(
    onboarding_db, monkeypatch, capsys, mode, organization,
):
    db, writes, commits = onboarding_db
    observed = []
    activate = cli.activate_ingestion_onboarding

    def capture_context(*args, **kwargs):
        observed.append((get_current_context(), kwargs["organization_id"]))
        return activate(*args, **kwargs)

    monkeypatch.setattr(cli, "activate_ingestion_onboarding", capture_context)
    assert cli.main(_argv(mode, organization=organization)) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["organization_id"] == ORG_ID
    assert report["plan"]["source_count"] > 0
    assert report["plan"]["requested_regions"] == ["TX"]
    if mode == "plan":
        assert observed == []
        assert writes == commits == []
    else:
        assert observed == [(RequestContext(ORG_ID, ADMIN_ID), ORG_ID)]
        assert len(commits) == 1
        assert {row.organization_id for row in db.query(IngestionSource)} == {ORG_ID}
        assert {row.organization_id for row in db.query(OrganizationIngestionEnrollment)} == {ORG_ID}
        assert {row.organization_id for row in db.query(OrganizationIngestionEnrollmentSource)} == {ORG_ID}
        audit = db.query(AuditLog).one()
        assert audit.organization_id == audit.entity_id == ORG_ID
        assert audit.actor_id == ADMIN_ID


def test_plan_validates_and_reports_regions_types_waves_and_shards(onboarding_db, capsys):
    db, writes, commits = onboarding_db
    before = _state(db)
    scope = [
        "--coverage-mode", "selected_states",
        "--region", "Texas", "--region", "District of Columbia",
        "--record-type", "permit", "--record-type", "planning",
        "--rollout-wave", "1", "--rollout-wave", "2", "--shard-count", "7",
    ]
    assert cli.main(_argv("plan", scope=scope)) == 0
    report = json.loads(capsys.readouterr().out)
    plan = report["plan"]
    assert report["dry_run"] is True
    assert len(report["catalog_manifest_digest"]) == 64
    assert plan["requested_regions"] == ["DC", "TX"]
    assert plan["rollout_waves"] == [1, 2]
    assert plan["shard_count"] == 7
    assert plan["source_count"] > 0
    for source in plan["sources"]:
        assert source["region"] in {"DC", "TX"}
        assert source["record_type"] in {"permit", "planning"}
        assert source["rollout_wave"] in {1, 2}
        assert source["shard_index"] == source_shard(source["source_key"], 7)
    assert _state(db) == before
    assert writes == commits == []


def test_plan_defaults_to_nationwide_all_types_and_waves(onboarding_db, capsys):
    _db, writes, commits = onboarding_db
    assert cli.main(_argv("plan", scope=[])) == 0
    plan = json.loads(capsys.readouterr().out)["plan"]
    assert plan["coverage_mode"] == "nationwide"
    assert plan["requested_regions"] == list(onboarding.ONBOARDING_REGIONS)
    assert plan["rollout_waves"] == [1, 2, 3, 4]
    assert plan["shard_count"] == 4
    assert {source["record_type"] for source in plan["sources"]} == {
        "permit", "planning", "parcel",
    }
    assert writes == commits == []


@pytest.mark.parametrize("existing", [False, True])
def test_activation_dry_run_does_not_write_even_temporarily(onboarding_db, capsys, existing):
    db, writes, commits = onboarding_db
    if existing:
        assert cli.main(_argv("activate")) == 0
        capsys.readouterr()
        writes.clear()
        commits.clear()
    before = _state(db)
    args = _argv("dry-run", scope=[
        "--coverage-mode", "selected_states", "--region", "GA",
    ])
    assert cli.main(args) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["dry_run"] is True
    assert report["enrollment"] is None
    assert report["catalog_created"] == report["plan"]["source_count"] > 0
    assert report["enrollment_sources_created"] == 0
    assert _state(db) == before
    assert writes == commits == []


def test_activation_is_idempotent_and_audited_like_api(onboarding_db, capsys):
    db, _writes, commits = onboarding_db
    assert cli.main(_argv("activate")) == 0
    first = json.loads(capsys.readouterr().out)
    first_state = _state(db)
    db.rollback()
    assert cli.main(_argv("activate")) == 0
    second = json.loads(capsys.readouterr().out)
    second_state = _state(db)
    count = first["plan"]["source_count"]
    assert first["enrollment_sources_created"] == count > 0
    assert first["catalog_created"] == count
    assert second["catalog_created"] == second["catalog_updated"] == 0
    assert second["catalog_unchanged"] == count
    assert second["enrollment_sources_created"] == second["enrollment_sources_updated"] == 0
    assert second["enrollment_sources_removed"] == 0
    assert second["enrollment_sources_unchanged"] == count
    assert second["enrollment"]["created_by"] == ADMIN_ID
    assert second["enrollment"]["catalog_manifest_digest"] == second["catalog_manifest_digest"]
    assert second["dry_run"] is False
    assert first_state["ingestion_sources"] == second_state["ingestion_sources"]
    assert first_state["organization_ingestion_enrollment_sources"] == second_state["organization_ingestion_enrollment_sources"]
    assert len(second_state["organization_ingestion_enrollments"]) == 1
    audits = db.query(AuditLog).order_by(AuditLog.created_at).all()
    assert [row.action for row in audits] == ["created", "updated"]
    for audit in audits:
        assert audit.entity_type == "ingestion_enrollment"
        assert audit.entity_id == audit.organization_id == ORG_ID
        assert audit.actor_id == ADMIN_ID
        assert json.loads(audit.new_values) == {
            "coverage_mode": "selected_states",
            "state_codes": ["TX"],
            "record_types": ["permit"],
            "rollout_waves": [1],
            "shard_count": 4,
            "enabled": True,
            "source_count": count,
            "missing_regions": [],
        }
    assert len(commits) == 2


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("scope", [
    ["--coverage-mode", "selected_states"],
    ["--region", "TX"],
    ["--coverage-mode", "selected_states", "--region", "ZZ"],
    ["--record-type", "unknown"],
    ["--record-type", "permit", "--record-type", "permit"],
    ["--rollout-wave", "0"],
    ["--rollout-wave", "5"],
    ["--rollout-wave", "1", "--rollout-wave", "1"],
    ["--shard-count", "0"],
    ["--shard-count", "129"],
    ["--shard-index", "0"],
    ["--path", "/tmp/unreviewed-catalog.json"],
])
def test_invalid_scope_is_rejected_without_writes(onboarding_db, mode, scope):
    db, writes, commits = onboarding_db
    before = _state(db)
    try:
        result = cli.main(_argv(mode, scope=scope))
    except SystemExit as exc:
        result = exc.code
    assert result in {1, 2}
    assert _state(db) == before
    assert writes == commits == []


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("organization", ["missing", "inactive", "inactive-org"])
def test_unknown_or_inactive_tenant_is_rejected(onboarding_db, capsys, mode, organization):
    _db, writes, commits = onboarding_db
    assert cli.main(_argv(mode, organization=organization)) == 1
    assert "Active organization not found" in capsys.readouterr().out
    assert writes == commits == []


def test_ambiguous_tenant_selector_is_rejected(onboarding_db):
    db, writes, commits = onboarding_db
    db.add(Organization(id=ORG_SLUG, slug="conflicting-id", name="Conflicting"))
    db.commit()
    writes.clear()
    commits.clear()
    assert cli.main(_argv("activate")) == 1
    assert writes == commits == []


@pytest.mark.parametrize("mode", ["activate", "dry-run"])
@pytest.mark.parametrize("actor_kind", ["missing", "other-tenant", "inactive", "editor", "viewer"])
def test_activation_requires_active_tenant_admin(onboarding_db, capsys, mode, actor_kind):
    db, writes, commits = onboarding_db
    actor = ADMIN_ID
    if actor_kind == "missing":
        actor = "missing-user"
    elif actor_kind == "other-tenant":
        actor = OTHER_ADMIN_ID
    elif actor_kind == "inactive":
        db.get(User, ADMIN_ID).is_active = False
    else:
        db.query(OrganizationMembership).filter_by(user_id=ADMIN_ID).one().role = MemberRole(actor_kind)
    db.commit()
    writes.clear()
    commits.clear()
    assert cli.main(_argv(mode, actor=actor)) == 1
    assert "active admin of the selected organization" in capsys.readouterr().out
    assert writes == commits == []


@pytest.mark.parametrize("mode", MODES)
def test_stale_manifest_blocks_onboarding_without_writes(onboarding_db, monkeypatch, capsys, mode):
    _db, writes, commits = onboarding_db

    def stale_manifest(*_args, **_kwargs):
        raise ValueError("Production rollout manifest is stale or missing")

    monkeypatch.setattr(cli, "require_current_rollout_manifest", stale_manifest)
    assert cli.main(_argv(mode)) == 1
    assert "manifest is stale or missing" in capsys.readouterr().out
    assert writes == commits == []


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("digest", [None, "wrong-digest"])
def test_production_manifest_attestation_is_required(onboarding_db, monkeypatch, capsys, mode, digest):
    _db, writes, commits = onboarding_db
    monkeypatch.setattr(cli, "ENVIRONMENT", "production")
    if digest is None:
        monkeypatch.delenv("INGESTION_ROLLOUT_MANIFEST_DIGEST", raising=False)
    else:
        monkeypatch.setenv("INGESTION_ROLLOUT_MANIFEST_DIGEST", digest)
    assert cli.main(_argv(mode)) == 1
    assert "digest" in capsys.readouterr().out.lower()
    assert writes == commits == []


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_attested_activation_needs_no_fetch_policy(onboarding_db, monkeypatch, capsys, environment):
    _db, _writes, commits = onboarding_db
    manifest = cli.require_current_rollout_manifest(
        cli.load_catalog(), candidates=cli.load_candidate_catalog()
    )
    monkeypatch.setattr(cli, "ENVIRONMENT", environment)
    monkeypatch.setenv("INGESTION_ROLLOUT_MANIFEST_DIGEST", manifest.manifest_digest)
    monkeypatch.setenv("INGESTION_ALLOWED_HOSTS", "")
    monkeypatch.delenv("INGESTION_HOST_POLICY_DIGEST", raising=False)
    assert cli.main(_argv("activate")) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["enrollment"]["catalog_manifest_digest"] == manifest.manifest_digest
    assert report["enrollment_sources_created"] > 0
    assert len(commits) == 1


def test_activation_keeps_service_context_check(onboarding_db, monkeypatch, capsys):
    _db, writes, commits = onboarding_db
    activate = cli.activate_ingestion_onboarding

    def wrong_context(*args, **kwargs):
        token = set_current_context(RequestContext(OTHER_ORG_ID, OTHER_ADMIN_ID))
        try:
            return activate(*args, **kwargs)
        finally:
            reset_current_context(token)

    monkeypatch.setattr(cli, "activate_ingestion_onboarding", wrong_context)
    assert cli.main(_argv("activate")) == 1
    assert "must match the active tenant" in capsys.readouterr().out
    assert writes == commits == []


def test_activation_keeps_service_manifest_check(onboarding_db, monkeypatch, capsys):
    _db, writes, commits = onboarding_db

    def stale_manifest(*_args, **_kwargs):
        raise ValueError("Production rollout manifest is stale or missing")

    monkeypatch.setattr(onboarding, "require_current_rollout_manifest", stale_manifest)
    assert cli.main(_argv("activate")) == 1
    assert "manifest is stale or missing" in capsys.readouterr().out
    assert writes == commits == []


def test_audit_failure_rolls_back_catalog_and_enrollment(onboarding_db, monkeypatch, capsys):
    db, writes, commits = onboarding_db
    before = _state(db)

    def failed_audit(*_args, **_kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(cli, "log_change", failed_audit)
    assert cli.main(_argv("activate")) == 1
    assert "audit unavailable" in capsys.readouterr().out
    assert writes
    assert commits == []
    assert _state(db) == before
