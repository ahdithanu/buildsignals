from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.dashboard import (
    KPIResponse,
    TopOpportunity,
    PipelineSnapshot,
    RecentSignal,
    AIInsight,
)
from app.services.dashboard_service import (
    get_kpis,
    get_top_opportunities,
    get_pipeline_snapshot,
    get_recent_signals,
    get_ai_insights,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/kpis", response_model=KPIResponse)
def dashboard_kpis(db: Session = Depends(get_db)):
    return get_kpis(db)


@router.get("/top-opportunities", response_model=list[TopOpportunity])
def dashboard_top_opportunities(
    limit: int = Query(default=5, ge=1, le=50),
    db: Session = Depends(get_db),
):
    return get_top_opportunities(db, limit=limit)


@router.get("/pipeline-snapshot", response_model=list[PipelineSnapshot])
def dashboard_pipeline_snapshot(db: Session = Depends(get_db)):
    return get_pipeline_snapshot(db)


@router.get("/recent-signals", response_model=list[RecentSignal])
def dashboard_recent_signals(
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return get_recent_signals(db, limit=limit)


@router.get("/ai-insights", response_model=list[AIInsight])
def dashboard_ai_insights(db: Session = Depends(get_db)):
    return get_ai_insights(db)
