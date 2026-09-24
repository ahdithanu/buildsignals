"""Tenant isolation, time bounds, and unknown-telemetry behavior."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.models.evaluation import EvalCase, EvalDataset, EvalResult, EvalRun
from app.models.ingestion import IngestionRun, IngestionSource
from app.models.organization_membership import MemberRole, OrganizationMembership
from app.services.observability_service import get_overview
from app.services.rate_limiter import limiter


def _id():
    return str(uuid4())


def _register(client, suffix):
    response = client.post("/v1/auth/register", json={
        "email": f"observability-{suffix}@example.com",
        "password": "CorrectHorseBattery42",
        "full_name": "Observability Admin",
        "organization_name": f"Observability {suffix}",
    })
    assert response.status_code == 201, response.text
    return response.json()


def _headers(user):
    return {"Authorization": f"Bearer {user['access_token']}"}


def _seed(db, org_id, now, *, old=False):
    started = now - timedelta(days=45 if old else 1)
    dataset = EvalDataset(id=_id(), organization_id=org_id, name=f"set-{_id()}", workflow="opportunity_memo")
    case = EvalCase(id=_id(), organization_id=org_id, dataset_id=dataset.id, name="case",
                    input_json={}, expected_output={}, retrieved_context=[])
    run = EvalRun(id=_id(), organization_id=org_id, dataset_id=dataset.id, mode="replay",
                  model="test", prompt_version="v1", status="completed", dataset_fingerprint="x",
                  thresholds={}, gate_passed=True, started_at=started)
    result = EvalResult(id=_id(), organization_id=org_id, run_id=run.id, case_id=case.id,
                        case_snapshot={}, retrieved_context=[], status="passed", model="test",
                        prompt_version="v1", cost_usd=None, tokens_input=None, tokens_output=None,
                        latency_ms=None)
    source = IngestionSource(id=_id(), organization_id=org_id, key=f"source-{_id()}",
                             name="Source", adapter="test", record_type="permit")
    ingest = IngestionRun(id=_id(), organization_id=org_id, source_id=source.id,
                          status="running", started_at=started, heartbeat_at=started,
                          records_seen=4, records_failed=1, error_message="private source detail")
    db.add_all([dataset, case, run, result, source, ingest])
    db.commit()


@pytest.fixture(autouse=True)
def _strict_auth(monkeypatch):
    monkeypatch.setattr("app.middleware.auth_context.ALLOW_ANONYMOUS", False)
    limiter.clear()
    yield
    limiter.clear()


def test_overview_requires_admin_and_valid_window(client):
    assert client.get("/v1/observability/overview").status_code == 401
    admin = _register(client, "auth")
    assert client.get("/v1/observability/overview?days=2", headers=_headers(admin)).status_code == 422
    empty = client.get("/v1/observability/overview", headers=_headers(admin))
    assert empty.status_code == 200
    data = empty.json()
    assert data["evaluations"]["cost_usd_known"] is None
    assert data["evaluations"]["runs"] == 0


@pytest.mark.parametrize("role", [MemberRole.editor, MemberRole.viewer])
def test_membership_role_overrides_admin_token(client, db, role):
    user = _register(client, f"role-{role.value}")
    membership = db.query(OrganizationMembership).filter_by(user_id=user["user_id"]).one()
    membership.role = role
    db.commit()
    assert client.get("/v1/observability/overview", headers=_headers(user)).status_code == 403


def test_overview_is_tenant_scoped_and_unknown_is_not_zero(client, db):
    first = _register(client, "first")
    second = _register(client, "second")
    now = datetime.now(timezone.utc)
    _seed(db, first["organization_id"], now)
    _seed(db, first["organization_id"], now, old=True)
    _seed(db, second["organization_id"], now)

    response = client.get("/v1/observability/overview?days=7", headers=_headers(first))
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["evaluations"]["runs"] == 1
    assert data["evaluations"]["results"] == 1
    assert data["evaluations"]["replay_runs"] == 1
    assert data["evaluations"]["cost_usd_known"] is None
    assert data["evaluations"]["cost_unknown_results"] == 1
    assert data["evaluations"]["tokens_unknown_results"] == 1
    assert data["ingestion"]["runs"] == 1
    assert data["ingestion"]["stalled_runs"] == 1
    assert "private source detail" not in response.text
    assert sum(day["runs"] for day in data["evaluations"]["daily"]) == 1


def test_known_zero_cost_is_reported_and_partial_is_separate(db):
    now = datetime.now(timezone.utc)
    org_id = _id()
    _seed(db, org_id, now)
    result = db.query(EvalResult).filter_by(organization_id=org_id).one()
    result.cost_usd = 0.0
    result.tokens_input = 0
    result.tokens_output = 0
    result.latency_ms = 0.0
    run = db.query(IngestionRun).filter_by(organization_id=org_id).one()
    run.status = "partial_with_errors"
    db.commit()
    summary = get_overview(db, org_id, 7, now + timedelta(seconds=1))
    assert summary.evaluations.cost_usd_known == 0
    assert summary.evaluations.tokens_reported_results == 1
    assert summary.evaluations.avg_latency_ms_known == 0
    assert summary.ingestion.partial == 1
    assert summary.ingestion.partial_with_errors == 1
    assert summary.ingestion.failed == 0
    assert any(item.code == "partial_ingestion_errors" for item in summary.attention)
