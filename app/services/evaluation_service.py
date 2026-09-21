"""Tenant-scoped, immutable eval snapshots and bounded synchronous orchestration."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from time import perf_counter

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.evaluation import EvalCase, EvalDataset, EvalMetric, EvalResult, EvalRun
from app.schemas.evaluation import (
    CaseRead,
    DatasetCreate,
    DatasetDetail,
    DatasetRead,
    EvalOutput,
    Evidence,
    ExpectedOutput,
    ResultRead,
    RunComparison,
    RunCreate,
    RunDetail,
    RunRead,
    Thresholds,
)
from app.services.audit_service import log_change
from app.services.eval_examples import example_datasets
from app.services.eval_scoring import SCORER_VERSION, result_passes, score_output
from app.services.eval_workflows import LIVE_WORKFLOWS, EvalExecutionError, execute_live

logger = logging.getLogger(__name__)


def _hash(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _dataset(db: Session, org_id: str, dataset_id: str) -> EvalDataset:
    row = db.query(EvalDataset).filter_by(organization_id=org_id, id=dataset_id).first()
    if row is None:
        raise HTTPException(404, "Evaluation dataset not found")
    return row


def list_datasets(db: Session, org_id: str) -> list[DatasetRead]:
    return [
        DatasetRead.model_validate(row)
        for row in db.query(EvalDataset)
        .filter_by(organization_id=org_id)
        .order_by(EvalDataset.created_at.desc(), EvalDataset.id)
        .limit(100)
    ]


def dataset_detail(db: Session, org_id: str, dataset_id: str) -> DatasetDetail:
    dataset = _dataset(db, org_id, dataset_id)
    cases = (
        db.query(EvalCase)
        .filter_by(organization_id=org_id, dataset_id=dataset.id)
        .order_by(EvalCase.created_at, EvalCase.id)
        .all()
    )
    return DatasetDetail(
        **DatasetRead.model_validate(dataset).model_dump(),
        cases=[CaseRead.model_validate(case) for case in cases],
    )


def create_dataset(db: Session, org_id: str, user_id: str, payload: DatasetCreate) -> DatasetDetail:
    dataset = EvalDataset(
        organization_id=org_id, created_by=user_id, **payload.model_dump(exclude={"cases"})
    )
    try:
        db.add(dataset)
        db.flush()
        for case in payload.cases:
            db.add(
                EvalCase(
                    organization_id=org_id, dataset_id=dataset.id, **case.model_dump(mode="json")
                )
            )
        log_change(
            db,
            "eval_dataset",
            dataset.id,
            "create",
            actor_id=user_id,
            organization_id=org_id,
            new_values={"workflow": dataset.workflow, "case_count": len(payload.cases)},
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "A dataset with that name already exists") from None
    return dataset_detail(db, org_id, dataset.id)


def seed_examples(db: Session, org_id: str, user_id: str) -> list[DatasetRead]:
    result = []
    for payload in example_datasets():
        existing = (
            db.query(EvalDataset).filter_by(organization_id=org_id, name=payload.name).first()
        )
        if existing:
            result.append(DatasetRead.model_validate(existing))
        else:
            result.append(DatasetRead.model_validate(create_dataset(db, org_id, user_id, payload)))
    return result


def _run(db: Session, org_id: str, run_id: str) -> EvalRun:
    row = db.query(EvalRun).filter_by(organization_id=org_id, id=run_id).first()
    if row is None:
        raise HTTPException(404, "Evaluation run not found")
    return row


def list_runs(db: Session, org_id: str, dataset_id: str | None = None) -> list[RunRead]:
    query = db.query(EvalRun).filter_by(organization_id=org_id)
    if dataset_id:
        _dataset(db, org_id, dataset_id)
        query = query.filter_by(dataset_id=dataset_id)
    return [
        RunRead.model_validate(row)
        for row in query.order_by(EvalRun.started_at.desc(), EvalRun.id).limit(100)
    ]


def run_detail(db: Session, org_id: str, run_id: str) -> RunDetail:
    run = _run(db, org_id, run_id)
    rows = (
        db.query(EvalResult)
        .filter_by(organization_id=org_id, run_id=run.id)
        .order_by(EvalResult.created_at, EvalResult.id)
        .all()
    )
    result_ids = [row.id for row in rows]
    metric_rows = (
        db.query(EvalMetric)
        .filter(EvalMetric.organization_id == org_id, EvalMetric.result_id.in_(result_ids))
        .all()
    )
    metrics: dict[str, dict[str, float]] = {}
    for metric in metric_rows:
        metrics.setdefault(metric.result_id, {})[metric.name] = metric.value
    results = []
    for row in rows:
        data = {key: getattr(row, key) for key in ResultRead.model_fields if key != "metrics"}
        results.append(ResultRead(**data, metrics=metrics.get(row.id, {})))
    return RunDetail(**RunRead.model_validate(run).model_dump(), results=results)


def _zero_metrics():
    return {
        "quality": 0.0,
        "citation_accuracy": 0.0,
        "hallucination_risk": 1.0,
        "factual_coverage": 0.0,
        "rule_compliance": 0.0,
    }


def run_evaluation(
    db: Session, org_id: str, user_id: str, dataset_id: str, payload: RunCreate
) -> RunDetail:
    dataset = dataset_detail(db, org_id, dataset_id)
    if not dataset.cases or len(dataset.cases) > 25:
        raise HTTPException(422, "Datasets require 1 to 25 cases per bounded run")
    case_ids = {case.id for case in dataset.cases}
    if payload.mode == "replay" and set(payload.outputs) != case_ids:
        raise HTTPException(422, "Replay must supply exactly one output for each dataset case")
    model, prompt_version = (
        (payload.model, payload.prompt_version)
        if payload.mode == "replay"
        else LIVE_WORKFLOWS.get(dataset.workflow, ("unavailable", "unavailable"))
    )
    snapshots = [case.model_dump(mode="json") for case in dataset.cases]
    run = EvalRun(
        organization_id=org_id,
        dataset_id=dataset.id,
        created_by=user_id,
        mode=payload.mode,
        model=model,
        prompt_version=prompt_version,
        status="running",
        dataset_fingerprint=_hash({"workflow": dataset.workflow, "cases": snapshots}),
        thresholds=payload.thresholds.model_dump(),
        summary={"scorer_version": SCORER_VERSION},
        gate_passed=False,
    )
    db.add(run)
    db.flush()
    run_id = run.id
    log_change(
        db,
        "eval_run",
        run_id,
        "start",
        actor_id=user_id,
        organization_id=org_id,
        new_values={"dataset_id": dataset.id, "mode": payload.mode},
    )
    db.commit()
    for case in dataset.cases:
        started = perf_counter()
        context = case.retrieved_context
        output = None
        error_code = None
        try:
            if payload.mode == "live":
                output, context = execute_live(db, org_id, dataset.workflow, case.input_json)
            else:
                output = EvalOutput.model_validate(payload.outputs[case.id])
            metrics = score_output(
                output, ExpectedOutput.model_validate(case.expected_output), context
            )
            status = "passed" if result_passes(metrics, payload.thresholds) else "failed"
        except Exception as error:
            db.rollback()
            metrics = _zero_metrics()
            status = "error"
            output = None
            error_code = error.code if isinstance(error, EvalExecutionError) else "execution_failed"
            logger.warning(
                "eval_case_failed run_id=%s case_id=%s code=%s", run_id, case.id, error_code
            )
        latency = (perf_counter() - started) * 1000
        # Replay evaluation overhead is not the captured model's latency.
        if payload.mode == "replay":
            latency = output.latency_ms if output else None
        result = EvalResult(
            organization_id=org_id,
            run_id=run_id,
            case_id=case.id,
            case_snapshot=case.model_dump(mode="json"),
            actual_output=output.model_dump(mode="json") if output else None,
            retrieved_context=[
                Evidence.model_validate(item).model_dump(mode="json") for item in context
            ],
            status=status,
            error_code=error_code,
            model=model,
            prompt_version=prompt_version,
            latency_ms=latency,
            tokens_input=output.tokens_input if output else None,
            tokens_output=output.tokens_output if output else None,
            cost_usd=output.cost_usd if output else None,
        )
        db.add(result)
        db.flush()
        for name, value in metrics.items():
            db.add(EvalMetric(organization_id=org_id, result_id=result.id, name=name, value=value))
        db.commit()
    detail = run_detail(db, org_id, run_id)
    averages = {
        name: float(sum(Decimal(str(result.metrics[name])) for result in detail.results) / len(detail.results))
        for name in _zero_metrics()
    }
    critical_failed = any(
        result.case_snapshot["critical"] and result.status != "passed" for result in detail.results
    )
    errors = sum(result.status == "error" for result in detail.results)
    summary = {
        "scorer_version": SCORER_VERSION,
        "metrics": averages,
        "case_count": len(detail.results),
        "passed_count": sum(result.status == "passed" for result in detail.results),
        "error_count": errors,
        "critical_failed": critical_failed,
        "context_fingerprint": _hash(
            [
                {"case_id": result.case_id, "context": result.retrieved_context}
                for result in sorted(detail.results, key=lambda result: result.case_id)
            ]
        ),
    }
    for field in ("tokens_input", "tokens_output", "cost_usd", "latency_ms"):
        values = [getattr(result, field) for result in detail.results]
        summary[field] = sum(values) if all(value is not None for value in values) else None
    run = _run(db, org_id, run_id)
    run.summary = summary
    run.status = "failed" if errors else "completed"
    run.gate_passed = (
        not errors and not critical_failed and result_passes(averages, payload.thresholds)
    )
    run.finished_at = datetime.now(timezone.utc)
    log_change(
        db,
        "eval_run",
        run_id,
        "complete",
        actor_id=user_id,
        organization_id=org_id,
        new_values={"gate_passed": run.gate_passed, "status": run.status},
    )
    db.commit()
    logger.info(
        "eval_run_completed run_id=%s cases=%s gate_passed=%s",
        run_id,
        len(detail.results),
        run.gate_passed,
    )
    return run_detail(db, org_id, run_id)


def compare_runs(db: Session, org_id: str, baseline_id: str, candidate_id: str) -> RunComparison:
    baseline = run_detail(db, org_id, baseline_id)
    candidate = run_detail(db, org_id, candidate_id)
    reasons = []
    if baseline.id == candidate.id:
        reasons.append("Choose two different runs")
    if baseline.status == "running" or candidate.status == "running":
        reasons.append("Both runs must be finished")
    if baseline.dataset_fingerprint != candidate.dataset_fingerprint:
        reasons.append("Dataset snapshots differ")
    if baseline.mode != candidate.mode:
        reasons.append("Execution modes differ")
    if baseline.thresholds != candidate.thresholds:
        reasons.append("Gate thresholds differ")
    for field in ("scorer_version", "context_fingerprint"):
        if baseline.summary.get(field) != candidate.summary.get(field):
            reasons.append(f"{field} differs")
    before = baseline.summary.get("metrics", {})
    after = candidate.summary.get("metrics", {})
    deltas = (
        {name: after[name] - before[name] for name in before if name in after}
        if not reasons
        else {}
    )
    previous = {result.case_id: result for result in baseline.results}
    regressed = (
        [
            result.case_id
            for result in candidate.results
            if result.case_id in previous
            and previous[result.case_id].status == "passed"
            and result.status != "passed"
        ]
        if not reasons
        else []
    )
    return RunComparison(
        baseline_id=baseline_id,
        candidate_id=candidate_id,
        comparable=not reasons,
        reasons=reasons,
        metric_deltas=deltas,
        regressed_case_ids=regressed,
        candidate_gate_passed=candidate.gate_passed,
        baseline_gate_passed=baseline.gate_passed,
    )


def enforce_run_gate(db: Session, org_id: str, run_id: str) -> RunRead:
    run = RunRead.model_validate(_run(db, org_id, run_id))
    if run.status != "completed" or not run.gate_passed:
        raise HTTPException(409, "Evaluation regression gate failed or run is incomplete")
    # Re-evaluate the persisted summary so changing thresholds in a client cannot bypass this gate.
    if not result_passes(run.summary.get("metrics", {}), Thresholds.model_validate(run.thresholds)):
        raise HTTPException(409, "Evaluation regression gate failed")
    return run
