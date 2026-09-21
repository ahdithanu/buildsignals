"""Authenticated, workspace-admin evaluation APIs."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.organization_membership import MemberRole
from app.schemas.evaluation import (
    DatasetCreate,
    DatasetDetail,
    DatasetRead,
    RunComparison,
    RunCreate,
    RunDetail,
    RunRead,
)
from app.services import evaluation_service as service
from app.services.eval_scoring import SCORER_VERSION
from app.services.eval_workflows import LIVE_WORKFLOWS
from app.services.rate_limiter import AI_LIMIT, AI_WINDOW, limiter
from app.utils.auth_deps import require_role_strict

router = APIRouter(prefix="/evals", tags=["evaluations"])
admin = require_role_strict(MemberRole.admin)


@router.get("/capabilities")
def capabilities(principal: dict = Depends(admin)):
    return {
        "live_workflows": list(LIVE_WORKFLOWS),
        "replay_workflows": [
            "copilot_answer",
            "opportunity_memo",
            "multi_agent_research",
            "score_explanation",
        ],
        "scorer_version": SCORER_VERSION,
    }


@router.get("/datasets", response_model=list[DatasetRead])
def datasets(principal: dict = Depends(admin), db: Session = Depends(get_db)):
    return service.list_datasets(db, principal["org_id"])


@router.post("/datasets", response_model=DatasetDetail, status_code=201)
def create_dataset(
    payload: DatasetCreate, principal: dict = Depends(admin), db: Session = Depends(get_db)
):
    return service.create_dataset(db, principal["org_id"], principal["user_id"], payload)


@router.post("/examples", response_model=list[DatasetRead])
def examples(principal: dict = Depends(admin), db: Session = Depends(get_db)):
    return service.seed_examples(db, principal["org_id"], principal["user_id"])


@router.get("/datasets/{dataset_id}", response_model=DatasetDetail)
def dataset(dataset_id: str, principal: dict = Depends(admin), db: Session = Depends(get_db)):
    return service.dataset_detail(db, principal["org_id"], dataset_id)


@router.post("/datasets/{dataset_id}/runs", response_model=RunDetail, status_code=201)
def execute(
    dataset_id: str,
    payload: RunCreate,
    principal: dict = Depends(admin),
    db: Session = Depends(get_db),
):
    decision = limiter.check(
        key=f"eval:{principal['org_id']}", limit=AI_LIMIT, window_seconds=AI_WINDOW
    )
    if not decision.allowed:
        raise HTTPException(
            429,
            "Evaluation rate limit exceeded",
            headers={"Retry-After": str(decision.retry_after)},
        )
    return service.run_evaluation(
        db, principal["org_id"], principal["user_id"], dataset_id, payload
    )


@router.get("/runs", response_model=list[RunRead])
def runs(
    dataset_id: str | None = None, principal: dict = Depends(admin), db: Session = Depends(get_db)
):
    return service.list_runs(db, principal["org_id"], dataset_id)


@router.get("/runs/{run_id}", response_model=RunDetail)
def run(run_id: str, principal: dict = Depends(admin), db: Session = Depends(get_db)):
    return service.run_detail(db, principal["org_id"], run_id)


@router.get("/runs/{run_id}/gate", response_model=RunRead)
def gate(run_id: str, principal: dict = Depends(admin), db: Session = Depends(get_db)):
    return service.enforce_run_gate(db, principal["org_id"], run_id)


@router.get("/compare", response_model=RunComparison)
def compare(
    baseline_id: str,
    candidate_id: str,
    principal: dict = Depends(admin),
    db: Session = Depends(get_db),
):
    return service.compare_runs(db, principal["org_id"], baseline_id, candidate_id)
