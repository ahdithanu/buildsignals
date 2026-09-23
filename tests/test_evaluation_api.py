"""Authenticated evaluation API integration and read-only workflow guarantees."""
from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text

from app.models.audit_log import AuditLog
from app.models.contact import Contact
from app.models.deal import Deal, RiskLevel
from app.models.deal_assumptions import DealAssumptions
from app.models.deal_outputs import DealOutputs
from app.models.evaluation import EvalCase, EvalDataset, EvalMetric, EvalResult, EvalRun
from app.models.memo import Memo
from app.models.organization_membership import MemberRole, OrganizationMembership
from app.models.outreach_activity import OutreachActivity
from app.models.signal import Signal
from app.services import evaluation_service
from app.services.account_lockout import lockout
from app.services.eval_workflows import LIVE_WORKFLOWS
from app.services.rate_limiter import limiter

_ROOT = "/v1/evals"
_METRICS = {"quality", "citation_accuracy", "factual_coverage", "hallucination_risk", "rule_compliance"}
_PERFECT = {name: 0.0 if name == "hallucination_risk" else 1.0 for name in _METRICS}
_FAILED = {name: 1.0 if name == "hallucination_risk" else 0.0 for name in _METRICS}


@pytest.fixture(autouse=True)
def _reset_auth_state(monkeypatch):
    monkeypatch.setattr("app.middleware.auth_context.ALLOW_ANONYMOUS", False)
    limiter.clear()
    lockout.clear()
    yield
    limiter.clear()
    lockout.clear()


def _register(client, label="a"):
    response = client.post("/v1/auth/register", json={
        "email": f"eval-{label}@example.com", "password": "CorrectHorseBattery42",
        "full_name": f"Eval Admin {label}", "organization_name": f"Eval Org {label}",
    })
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture()
def admin(client):
    return _register(client)


def _headers(identity):
    return {"Authorization": f"Bearer {identity['access_token']}"}


def _case(name="Permit case", **overrides):
    return {
        "name": name,
        "input_json": {"question": "What is known?"},
        "expected_output": {
            "required_phrases": ["permit issued"],
            "required_citation_ids": ["permit:1"],
            "forbidden_phrases": ["guaranteed returns"],
        },
        "retrieved_context": [{"id": "permit:1", "text": "Permit issued. Financing unknown."}],
        "critical": True,
        **overrides,
    }


def _dataset_body(**overrides):
    return {"name": "Permit golden set", "workflow": "copilot_answer", "cases": [_case()], **overrides}


def _create(client, identity, **overrides):
    response = client.post(f"{_ROOT}/datasets", headers=_headers(identity), json=_dataset_body(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


def _output(**overrides):
    return {
        "text": "Permit issued. Financing unknown.",
        "citations": [{"source_id": "permit:1", "quote": "Permit issued"}],
        **overrides,
    }


def _replay(dataset, **overrides):
    return {
        "mode": "replay", "model": "captured-model-v1", "prompt_version": "prompt-v1",
        "outputs": {case["id"]: _output() for case in dataset["cases"]},
        **overrides,
    }


def _run(client, identity, dataset, payload=None):
    response = client.post(
        f"{_ROOT}/datasets/{dataset['id']}/runs", headers=_headers(identity),
        json=_replay(dataset) if payload is None else payload,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _get(client, identity, path, **params):
    response = client.get(f"{_ROOT}{path}", headers=_headers(identity), params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _protected_requests():
    return [
        ("GET", "/capabilities", {}),
        ("GET", "/datasets", {}),
        ("POST", "/datasets", {"json": _dataset_body()}),
        ("GET", "/datasets/missing", {}),
        ("POST", "/datasets/missing/runs", {"json": {"mode": "live"}}),
        ("POST", "/examples", {}),
        ("GET", "/runs", {}),
        ("GET", "/runs/missing", {}),
        ("GET", "/runs/missing/gate", {}),
        ("GET", "/compare", {"params": {"baseline_id": "missing", "candidate_id": "other"}}),
    ]


@pytest.mark.parametrize("allow_anonymous", [False, True])
@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer invalid-token"}])
def test_all_evaluation_routes_require_auth_even_in_demo(client, monkeypatch, allow_anonymous, headers):
    monkeypatch.setattr("app.middleware.auth_context.ALLOW_ANONYMOUS", allow_anonymous)
    for method, path, kwargs in _protected_requests():
        response = client.request(method, f"{_ROOT}{path}", headers=headers, **kwargs)
        assert response.status_code == 401, (method, path, response.text)


@pytest.mark.parametrize("role", [MemberRole.editor, MemberRole.viewer])
def test_all_evaluation_routes_require_admin(client, db, admin, role):
    membership = db.query(OrganizationMembership).filter_by(user_id=admin["user_id"]).one()
    membership.role = role
    db.commit()
    # The existing admin-labelled JWT must not override the current membership.
    for method, path, kwargs in _protected_requests():
        response = client.request(method, f"{_ROOT}{path}", headers=_headers(admin), **kwargs)
        assert response.status_code == 403, (method, path, response.text)
    assert db.query(EvalDataset).count() == db.query(EvalRun).count() == 0


def test_dataset_create_detail_uniqueness_and_tenant_scoped_collections(client, db, admin):
    dataset = _create(client, admin, description="Regression fixture", cases=[_case(), _case("Second")])
    assert dataset["description"] == "Regression fixture"
    assert len(dataset["cases"]) == 2
    assert all(case["dataset_id"] == dataset["id"] for case in dataset["cases"])
    assert _get(client, admin, f"/datasets/{dataset['id']}") == dataset
    assert [row["id"] for row in _get(client, admin, "/datasets")] == [dataset["id"]]
    duplicate = client.post(f"{_ROOT}/datasets", headers=_headers(admin), json=_dataset_body())
    assert duplicate.status_code == 409, duplicate.text
    other = _register(client, "b")
    assert _get(client, other, "/datasets") == []
    other_dataset = _create(client, other)
    assert other_dataset["id"] != dataset["id"]
    assert [row["id"] for row in _get(client, other, "/datasets")] == [other_dataset["id"]]
    row = db.get(EvalDataset, dataset["id"])
    assert (row.organization_id, row.created_by) == (admin["organization_id"], admin["user_id"])
    assert db.query(EvalCase).filter_by(dataset_id=dataset["id"]).count() == 2
    audit = db.query(AuditLog).filter_by(entity_type="eval_dataset", entity_id=dataset["id"]).one()
    assert audit.organization_id == admin["organization_id"]


def test_cross_tenant_dataset_run_detail_comparison_and_gate_are_hidden(client, db, admin):
    dataset = _create(client, admin)
    baseline = _run(client, admin, dataset)
    candidate = _run(client, admin, dataset)
    other = _register(client, "b")
    own_dataset = _create(client, other)
    own_run = _run(client, other, own_dataset)
    assert [row["id"] for row in _get(client, other, "/runs")] == [own_run["id"]]
    requests = [
        ("GET", f"/datasets/{dataset['id']}", {}),
        ("POST", f"/datasets/{dataset['id']}/runs", {"json": _replay(dataset)}),
        ("GET", "/runs", {"params": {"dataset_id": dataset["id"]}}),
        ("GET", f"/runs/{baseline['id']}", {}),
        ("GET", f"/runs/{baseline['id']}/gate", {}),
        ("GET", "/compare", {"params": {"baseline_id": baseline["id"], "candidate_id": candidate["id"]}}),
        ("GET", "/compare", {"params": {"baseline_id": baseline["id"], "candidate_id": own_run["id"]}}),
        ("GET", "/compare", {"params": {"baseline_id": own_run["id"], "candidate_id": baseline["id"]}}),
    ]
    for method, path, kwargs in requests:
        response = client.request(method, f"{_ROOT}{path}", headers=_headers(other), **kwargs)
        assert response.status_code == 404, (method, path, response.text)
    with pytest.raises(HTTPException) as denied:
        evaluation_service.enforce_run_gate(db, other["organization_id"], baseline["id"])
    assert denied.value.status_code == 404
    assert db.query(EvalRun).count() == 3


@pytest.mark.parametrize("coverage", ["missing", "extra", "wrong"])
def test_replay_requires_exact_case_coverage_before_writing_a_run(client, db, admin, coverage):
    dataset = _create(client, admin, cases=[_case("First"), _case("Second")])
    payload = _replay(dataset)
    if coverage in {"missing", "wrong"}:
        payload["outputs"].pop(dataset["cases"][0]["id"])
    if coverage in {"extra", "wrong"}:
        payload["outputs"]["unknown-case"] = _output()
    response = client.post(
        f"{_ROOT}/datasets/{dataset['id']}/runs", headers=_headers(admin), json=payload,
    )
    assert response.status_code == 422, response.text
    assert db.query(EvalRun).count() == db.query(EvalResult).count() == db.query(EvalMetric).count() == 0


@pytest.mark.parametrize("overrides", [
    {"mode": "live"}, {"model": "current"}, {"prompt_version": "current"}, {"outputs": {}},
])
def test_run_contract_rejects_ambiguous_provenance(client, db, admin, overrides):
    dataset = _create(client, admin)
    response = client.post(
        f"{_ROOT}/datasets/{dataset['id']}/runs", headers=_headers(admin),
        json=_replay(dataset, **overrides),
    )
    assert response.status_code == 422, response.text
    assert db.query(EvalRun).count() == 0


def test_replay_persists_metrics_snapshots_and_unknown_cost(client, db, admin):
    dataset = _create(client, admin, cases=[_case("Known usage"), _case("Unknown usage")])
    payload = _replay(dataset)
    known_id = dataset["cases"][0]["id"]
    payload["outputs"][known_id].update(tokens_input=20, tokens_output=5, cost_usd=0.02, latency_ms=12.5)
    run = _run(client, admin, dataset, payload)
    assert run["status"] == "completed" and run["gate_passed"] is True
    assert run["finished_at"] is not None and len(run["dataset_fingerprint"]) == 64
    assert run["summary"]["metrics"] == _PERFECT
    assert (run["summary"]["case_count"], run["summary"]["passed_count"], run["summary"]["error_count"]) == (2, 2, 0)
    for field in ("cost_usd", "tokens_input", "tokens_output", "latency_ms"):
        assert run["summary"][field] is None
    cases = {case["id"]: case for case in dataset["cases"]}
    for result in run["results"]:
        assert result["metrics"] == _PERFECT
        assert all(0 <= value <= 1 for value in result["metrics"].values())
        assert result["case_snapshot"] == cases[result["case_id"]]
        assert result["retrieved_context"] == cases[result["case_id"]]["retrieved_context"]
        assert result["actual_output"]["text"] == payload["outputs"][result["case_id"]]["text"]
        assert (result["model"], result["prompt_version"]) == ("captured-model-v1", "prompt-v1")
        assert result["status"] == "passed" and result["error_code"] is None
        if result["case_id"] == known_id:
            assert result["latency_ms"] == 12.5 and result["cost_usd"] == 0.02
        else:
            assert result["cost_usd"] is None and result["tokens_input"] is None
            assert result["latency_ms"] is None
    assert db.query(EvalMetric).count() == 10
    assert db.get(EvalRun, run["id"]).created_by == admin["user_id"]
    assert _get(client, admin, f"/runs/{run['id']}") == run
    assert [row["id"] for row in _get(client, admin, "/runs", dataset_id=dataset["id"])] == [run["id"]]
    assert evaluation_service.enforce_run_gate(db, admin["organization_id"], run["id"]).id == run["id"]
    assert _get(client, admin, f"/runs/{run['id']}/gate")["gate_passed"] is True


def test_known_replay_usage_is_summed_without_substituting_unknowns(client, admin):
    dataset = _create(client, admin, cases=[_case("First"), _case("Second")])
    payload = _replay(dataset, outputs={
        case["id"]: _output(tokens_input=10, tokens_output=4, cost_usd=0.005, latency_ms=3)
        for case in dataset["cases"]
    })
    summary = _run(client, admin, dataset, payload)["summary"]
    assert (summary["tokens_input"], summary["tokens_output"], summary["latency_ms"]) == (20, 8, 6)
    assert summary["cost_usd"] == pytest.approx(0.01)


def test_case_edits_do_not_rewrite_historical_snapshots(client, db, admin):
    dataset = _create(client, admin)
    baseline = _run(client, admin, dataset)
    case = db.get(EvalCase, dataset["cases"][0]["id"])
    case.input_json = {"question": "New question"}
    case.expected_output = {"required_phrases": ["new requirement"]}
    case.retrieved_context = [{"id": "new-source", "text": "Changed evidence"}]
    case.critical = False
    db.commit()
    assert _get(client, admin, f"/runs/{baseline['id']}") == baseline
    changed = _get(client, admin, f"/datasets/{dataset['id']}")
    candidate = _run(client, admin, changed)
    assert candidate["dataset_fingerprint"] != baseline["dataset_fingerprint"]
    assert candidate["results"][0]["case_snapshot"]["input_json"] == {"question": "New question"}
    compared = _get(client, admin, "/compare", baseline_id=baseline["id"], candidate_id=candidate["id"])
    assert compared["comparable"] is False and "Dataset snapshots differ" in compared["reasons"]
    assert compared["metric_deltas"] == {} and compared["regressed_case_ids"] == []


def test_comparison_detects_regression_and_gate_rejects_candidate(client, db, admin):
    dataset = _create(client, admin)
    baseline = _run(client, admin, dataset)
    candidate = _run(client, admin, dataset, _replay(
        dataset, model="captured-model-v2", prompt_version="prompt-v2",
        outputs={case["id"]: _output(text="Guaranteed returns", citations=[{"source_id": "invented"}])
                 for case in dataset["cases"]},
    ))
    compared = _get(client, admin, "/compare", baseline_id=baseline["id"], candidate_id=candidate["id"])
    assert candidate["status"] == "completed" and candidate["gate_passed"] is False
    assert compared["comparable"] is True and compared["reasons"] == []
    assert compared["regressed_case_ids"] == [dataset["cases"][0]["id"]]
    assert compared["candidate_gate_passed"] is False
    assert compared["metric_deltas"] == {name: _FAILED[name] - _PERFECT[name] for name in _METRICS}
    with pytest.raises(HTTPException) as failed:
        evaluation_service.enforce_run_gate(db, admin["organization_id"], candidate["id"])
    assert failed.value.status_code == 409
    response = client.get(f"{_ROOT}/runs/{candidate['id']}/gate", headers=_headers(admin))
    assert response.status_code == 409, response.text


@pytest.mark.parametrize(("field", "value", "reason"), [
    ("status", "running", "Both runs must be finished"),
    ("mode", "live", "Execution modes differ"),
    ("thresholds", {"minimum_quality": 0.9}, "Gate thresholds differ"),
    ("scorer_version", "future-scorer", "scorer_version differs"),
    ("context_fingerprint", "changed-context", "context_fingerprint differs"),
])
def test_comparison_refuses_incompatible_runs(client, db, admin, field, value, reason):
    dataset = _create(client, admin)
    baseline = _run(client, admin, dataset)
    candidate = _run(client, admin, dataset)
    row = db.get(EvalRun, candidate["id"])
    if field in {"scorer_version", "context_fingerprint"}:
        row.summary = {**row.summary, field: value}
    elif field == "thresholds":
        row.thresholds = {**row.thresholds, **value}
    else:
        setattr(row, field, value)
    db.commit()
    compared = _get(client, admin, "/compare", baseline_id=baseline["id"], candidate_id=candidate["id"])
    assert compared["comparable"] is False and reason in compared["reasons"]
    assert compared["metric_deltas"] == {} and compared["regressed_case_ids"] == []


def test_comparison_refuses_same_run(client, admin):
    dataset = _create(client, admin)
    run = _run(client, admin, dataset)
    compared = _get(client, admin, "/compare", baseline_id=run["id"], candidate_id=run["id"])
    assert compared["comparable"] is False
    assert "Choose two different runs" in compared["reasons"]


@pytest.mark.parametrize("critical", [True, False])
def test_critical_failure_blocks_gate_even_when_aggregate_thresholds_pass(client, admin, critical):
    dataset = _create(client, admin, cases=[_case("Pass"), _case("Fail", critical=critical)])
    payload = _replay(dataset, thresholds={
        "minimum_quality": 0.5, "minimum_citation_accuracy": 0.5,
        "minimum_factual_coverage": 0.5, "maximum_hallucination_risk": 0.5,
    })
    failed_id = next(case["id"] for case in dataset["cases"] if case["name"] == "Fail")
    payload["outputs"][failed_id] = _output(text="Guaranteed returns", citations=[])
    run = _run(client, admin, dataset, payload)
    assert run["summary"]["metrics"] == {name: 0.5 for name in _METRICS}
    assert run["summary"]["critical_failed"] is critical
    assert run["gate_passed"] is not critical


@pytest.mark.parametrize("mutation", ["running", "failed", "gate_false", "metrics"])
def test_persisted_gate_fails_closed(client, db, admin, mutation):
    dataset = _create(client, admin)
    run = _run(client, admin, dataset)
    row = db.get(EvalRun, run["id"])
    if mutation in {"running", "failed"}:
        row.status = mutation
    elif mutation == "gate_false":
        row.gate_passed = False
    else:
        row.summary = {**row.summary, "metrics": {"quality": 1}}
    db.commit()
    with pytest.raises(HTTPException) as failed:
        evaluation_service.enforce_run_gate(db, admin["organization_id"], run["id"])
    assert failed.value.status_code == 409
    response = client.get(f"{_ROOT}/runs/{run['id']}/gate", headers=_headers(admin))
    assert response.status_code == 409, response.text


@pytest.mark.parametrize("workflow", ["copilot_answer", "multi_agent_research"])
def test_unsupported_live_workflow_persists_failed_results_and_can_replay(client, db, admin, workflow):
    dataset = _create(client, admin, workflow=workflow, cases=[_case("First"), _case("Second")])
    failed = _run(client, admin, dataset, {"mode": "live"})
    assert failed["status"] == "failed" and failed["gate_passed"] is False
    assert failed["finished_at"] is not None and failed["summary"]["error_count"] == 2
    assert failed["summary"]["cost_usd"] is None
    for result in failed["results"]:
        assert result["status"] == "error" and result["error_code"] == "workflow_not_available"
        assert result["actual_output"] is None and result["metrics"] == _FAILED
    recovered = _run(client, admin, dataset)
    assert recovered["gate_passed"] is True
    assert _get(client, admin, f"/runs/{failed['id']}") == failed
    assert db.query(EvalResult).count() == 4 and db.query(EvalMetric).count() == 20


def _seed_deal(db, identity):
    deal = Deal(
        organization_id=identity["organization_id"], name="Cedar offices", address="100 Cedar St",
        city="Austin", state="TX", property_type="office", asking_price=1000000,
        sq_ft=10000, year_built=2000, score=7, risk_level=RiskLevel.high,
    )
    db.add(deal)
    db.flush()
    db.add_all([
        DealAssumptions(organization_id=deal.organization_id, deal_id=deal.id, purchase_price=900000),
        DealOutputs(organization_id=deal.organization_id, deal_id=deal.id, noi=100000, dscr=1.5, cap_rate=0.08),
        Contact(organization_id=deal.organization_id, deal_id=deal.id, name="Owner"),
        Memo(organization_id=deal.organization_id, deal_id=deal.id, title="Original", content="Do not replace", version=3),
    ])
    db.commit()
    return deal


def _live_case(deal, workflow, **overrides):
    expected = {"required_citation_ids": [f"deal:{deal.id}"]}
    if workflow == "score_explanation":
        expected["expected_score"] = 100
    else:
        expected["required_phrases"] = ["Investment Memo", "Cedar offices"]
    return _case(input_json={"deal_id": deal.id}, expected_output=expected, retrieved_context=[], **overrides)


def _product_snapshot(db):
    models = (Deal, DealAssumptions, DealOutputs, Contact, Memo, Signal, OutreachActivity)
    return {
        model.__tablename__: [dict(row) for row in db.execute(
            select(model.__table__).order_by(model.id)
        ).mappings()]
        for model in models
    }


@pytest.mark.parametrize("workflow", ["score_explanation", "opportunity_memo"])
def test_live_product_workflows_do_not_write_deals_memos_or_related_records(client, db, admin, workflow):
    deal = _seed_deal(db, admin)
    dataset = _create(client, admin, workflow=workflow, cases=[_live_case(deal, workflow)])
    before = deepcopy(_product_snapshot(db))
    run = _run(client, admin, dataset, {"mode": "live"})
    db.expire_all()
    assert _product_snapshot(db) == before
    assert (run["model"], run["prompt_version"]) == LIVE_WORKFLOWS[workflow]
    assert run["status"] == "completed" and run["gate_passed"] is True
    result = run["results"][0]
    assert result["status"] == "passed" and result["metrics"] == _PERFECT
    assert result["retrieved_context"][0]["id"] == f"deal:{deal.id}"
    assert result["actual_output"]["citations"][0]["source_id"] == f"deal:{deal.id}"
    assert result["cost_usd"] == run["summary"]["cost_usd"] == 0
    assert result["tokens_input"] == result["tokens_output"] == 0
    assert result["latency_ms"] >= 0
    assert run["summary"]["latency_ms"] == result["latency_ms"]
    if workflow == "score_explanation":
        assert result["actual_output"]["score"] == 100
        assert db.get(Deal, deal.id).score == 7
    else:
        assert "Investment Memo: Cedar offices" in result["actual_output"]["text"]
        assert db.query(Memo).one().version == 3


@pytest.mark.parametrize("workflow", ["score_explanation", "opportunity_memo"])
@pytest.mark.parametrize("hidden", ["other_tenant", "deleted"])
def test_live_workflows_cannot_read_other_tenants_or_deleted_deals(client, db, admin, workflow, hidden):
    owner = _register(client, "b") if hidden == "other_tenant" else admin
    deal = _seed_deal(db, owner)
    deal.name = "Private acquisition marker"
    if hidden == "deleted":
        deal.deleted_at = datetime.now(timezone.utc)
    db.commit()
    dataset = _create(client, admin, workflow=workflow, cases=[_live_case(deal, workflow)])
    run = _run(client, admin, dataset, {"mode": "live"})
    result = run["results"][0]
    assert run["status"] == "failed" and run["gate_passed"] is False
    assert result["error_code"] == "workflow_input_not_found"
    assert result["actual_output"] is None and result["retrieved_context"] == []
    assert "Private acquisition marker" not in str(run)


def test_live_case_database_failure_rolls_back_and_keeps_prior_and_later_results(client, db, admin, monkeypatch):
    deal = _seed_deal(db, admin)
    dataset = _create(client, admin, workflow="score_explanation", cases=[
        _live_case(deal, "score_explanation", name=f"Case {index}") for index in range(3)
    ])
    original = evaluation_service.execute_live
    calls = []

    def fail_second_case(session, org_id, workflow, input_json):
        calls.append(input_json)
        if len(calls) == 2:
            session.execute(text("SELECT provider_secret FROM missing_eval_provider_table"))
        return original(session, org_id, workflow, input_json)

    monkeypatch.setattr(evaluation_service, "execute_live", fail_second_case)
    run = _run(client, admin, dataset, {"mode": "live"})
    assert len(calls) == 3
    assert run["status"] == "failed" and run["gate_passed"] is False
    assert run["finished_at"] is not None
    assert [result["status"] for result in run["results"]] == ["passed", "error", "passed"]
    assert run["results"][1]["error_code"] == "execution_failed"
    assert run["summary"]["passed_count"] == 2 and run["summary"]["error_count"] == 1
    assert run["summary"]["cost_usd"] is None
    assert "provider_secret" not in str(run) and "missing_eval_provider_table" not in str(run)
    assert db.query(EvalResult).count() == 3 and db.query(EvalMetric).count() == 15
    assert _get(client, admin, f"/runs/{run['id']}") == run


@pytest.mark.parametrize("workflow", ["score_explanation", "opportunity_memo"])
@pytest.mark.parametrize("oversize", ["text", "rows"])
def test_oversized_live_context_fails_explicitly_without_partial_output(client, db, admin, workflow, oversize):
    deal = _seed_deal(db, admin)
    if oversize == "text":
        db.add(Signal(
            organization_id=deal.organization_id, deal_id=deal.id, signal_type="news",
            description="private-evidence-" * 700,
        ))
    else:
        db.add_all([
            Contact(organization_id=deal.organization_id, deal_id=deal.id, name=f"Owner {index}")
            for index in range(1000)
        ])
    db.commit()
    dataset = _create(client, admin, workflow=workflow, cases=[_live_case(deal, workflow)])
    before = _product_snapshot(db)
    run = _run(client, admin, dataset, {"mode": "live"})
    assert run["status"] == "failed" and run["gate_passed"] is False
    assert run["finished_at"] is not None
    result = run["results"][0]
    assert result["error_code"] == "context_too_large"
    assert result["actual_output"] is None and result["retrieved_context"] == []
    assert result["metrics"] == _FAILED
    assert "private-evidence" not in str(run)
    db.expire_all()
    assert _product_snapshot(db) == before


def test_capabilities_and_example_seeding_are_explicit_idempotent_and_scoped(client, db, admin):
    capabilities = _get(client, admin, "/capabilities")
    assert set(capabilities["live_workflows"]) == {"score_explanation", "opportunity_memo"}
    assert set(capabilities["replay_workflows"]) == {
        "score_explanation", "opportunity_memo", "copilot_answer", "multi_agent_research",
    }
    assert capabilities["scorer_version"]
    first = client.post(f"{_ROOT}/examples", headers=_headers(admin))
    assert first.status_code == 200, first.text
    second = client.post(f"{_ROOT}/examples", headers=_headers(admin))
    assert second.status_code == 200, second.text
    assert first.json() == second.json() and len(first.json()) == 4
    assert db.query(EvalDataset).count() == db.query(EvalCase).count() == 4
    for item in first.json():
        dataset = _get(client, admin, f"/datasets/{item['id']}")
        outputs = {case["id"]: case["input_json"]["example_output"] for case in dataset["cases"]}
        run = _run(client, admin, dataset, _replay(dataset, outputs=outputs))
        assert run["gate_passed"] is True
        assert run["summary"]["cost_usd"] is None and run["summary"]["latency_ms"] is None
    other = _register(client, "b")
    assert _get(client, other, "/datasets") == []
    seeded = client.post(f"{_ROOT}/examples", headers=_headers(other))
    assert seeded.status_code == 200, seeded.text
    assert {item["id"] for item in seeded.json()}.isdisjoint(item["id"] for item in first.json())
    assert db.query(EvalDataset).count() == 8


@pytest.mark.parametrize("workflow", ["score_explanation", "opportunity_memo"])
def test_live_workflows_scope_each_child_relationship_independently(client, db, admin, workflow):
    other = _register(client, "b")
    deal = _seed_deal(db, admin)
    # Legacy relationships have only a deal FK, so deliberately seed ownership drift.
    for model in (DealAssumptions, DealOutputs, Contact):
        row = db.query(model).filter_by(deal_id=deal.id).one()
        row.organization_id = other["organization_id"]
    db.add_all([
        Signal(organization_id=other["organization_id"], deal_id=deal.id,
               signal_type="news", description="Confidential foreign signal"),
        OutreachActivity(organization_id=other["organization_id"], deal_id=deal.id,
                         activity_type="email", subject="Confidential foreign outreach"),
    ])
    db.commit()
    case = _live_case(deal, workflow)
    if workflow == "score_explanation":
        case["expected_output"]["expected_score"] = 40
    dataset = _create(client, admin, workflow=workflow, cases=[case])
    run = _run(client, admin, dataset, {"mode": "live"})
    assert run["gate_passed"] is True
    result = run["results"][0]
    context = json.loads(result["retrieved_context"][0]["text"])
    assert context["outputs"] is None and context["has_assumptions"] is False
    assert context["contacts_count"] == 0 and context["contact_statuses"] == []
    assert context["signals"] == [] and context["activity_types"] == []
    assert "Confidential foreign" not in str(run)
    if workflow == "score_explanation":
        assert result["actual_output"]["score"] == 40


def test_run_rate_limit_is_per_tenant_and_does_not_create_rejected_run(client, db, admin, monkeypatch):
    monkeypatch.setattr("app.routes.evaluations.AI_LIMIT", 1)
    dataset = _create(client, admin)
    _run(client, admin, dataset)
    response = client.post(
        f"{_ROOT}/datasets/{dataset['id']}/runs", headers=_headers(admin), json=_replay(dataset),
    )
    assert response.status_code == 429, response.text
    assert int(response.headers["Retry-After"]) > 0
    assert db.query(EvalRun).count() == 1
    other = _register(client, "b")
    own_dataset = _create(client, other)
    assert _run(client, other, own_dataset)["gate_passed"] is True
