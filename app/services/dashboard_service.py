from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.models.deal import Deal, DealStatus
from app.models.contact import Contact
from app.models.outreach_activity import OutreachActivity
from app.models.signal import Signal
from app.utils.org_scope import get_org_id, scope_query, active_query


_DEAD_CLOSED = {DealStatus.dead, DealStatus.closed}


def get_kpis(db: Session) -> dict[str, Any]:
    """Return key performance indicators for the dashboard."""
    total_deals = active_query(db.query(func.count(Deal.id)), Deal).scalar() or 0

    active_deals = (
        active_query(db.query(func.count(Deal.id)), Deal)
        .filter(Deal.status.notin_([s.value for s in _DEAD_CLOSED]))
        .scalar()
    ) or 0

    total_pipeline_value = (
        active_query(db.query(func.coalesce(func.sum(Deal.asking_price), 0.0)), Deal)
        .filter(Deal.status.notin_([s.value for s in _DEAD_CLOSED]))
        .scalar()
    ) or 0.0

    avg_score = active_query(db.query(func.avg(Deal.score)), Deal).filter(Deal.score.isnot(None)).scalar()

    rows = (
        active_query(db.query(Deal.status, func.count(Deal.id)), Deal)
        .group_by(Deal.status)
        .all()
    )
    deals_by_status: dict[str, int] = {
        (row[0].value if hasattr(row[0], "value") else str(row[0])): row[1]
        for row in rows
    }

    return {
        "total_deals": total_deals,
        "active_deals": active_deals,
        "total_pipeline_value": float(total_pipeline_value),
        "avg_score": round(avg_score, 2) if avg_score is not None else None,
        "deals_by_status": deals_by_status,
    }


def get_top_opportunities(db: Session, limit: int = 5) -> list[dict[str, Any]]:
    """Top deals by score (highest first)."""
    deals = (
        active_query(db.query(Deal), Deal)
        .filter(Deal.score.isnot(None))
        .order_by(Deal.score.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "deal_id": d.id,
            "name": d.name,
            "property_type": d.property_type,
            "asking_price": d.asking_price,
            "score": d.score,
            "status": d.status.value if hasattr(d.status, "value") else str(d.status),
        }
        for d in deals
    ]


def get_pipeline_snapshot(db: Session) -> list[dict[str, Any]]:
    """Count of deals and total value per status stage."""
    rows = (
        active_query(db.query(
            Deal.status,
            func.count(Deal.id),
            func.coalesce(func.sum(Deal.asking_price), 0.0),
        ), Deal)
        .group_by(Deal.status)
        .all()
    )
    return [
        {
            "stage": row[0].value if hasattr(row[0], "value") else str(row[0]),
            "count": row[1],
            "total_value": float(row[2]),
        }
        for row in rows
    ]


def get_recent_signals(db: Session, limit: int = 10) -> list[dict[str, Any]]:
    """Most recent signals with deal name."""
    rows = (
        scope_query(db.query(Signal, Deal.name), Signal)
        .outerjoin(Deal, Signal.deal_id == Deal.id)
        .order_by(Signal.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": sig.id,
            "deal_id": sig.deal_id,
            "deal_name": deal_name,
            "signal_type": sig.signal_type,
            "source": sig.source,
            "severity": sig.severity,
            "created_at": sig.created_at,
        }
        for sig, deal_name in rows
    ]


def get_ai_insights(db: Session) -> list[dict[str, Any]]:
    """Deterministic insights based on current data."""
    insights: list[dict[str, Any]] = []

    # 1. Deals needing scoring
    unscored = (
        active_query(db.query(func.count(Deal.id)), Deal)
        .filter(Deal.score.is_(None))
        .scalar()
    ) or 0
    if unscored > 0:
        insights.append({
            "insight_type": "needs_scoring",
            "title": "Deals Need Scoring",
            "description": f"{unscored} deal{'s' if unscored != 1 else ''} need scoring",
            "deal_id": None,
            "priority": "high" if unscored > 5 else "medium",
        })

    # 2. Deals with no contacts
    deals_with_contacts_subq = (
        db.query(Contact.deal_id).distinct().subquery()
    )
    no_contacts = (
        active_query(db.query(func.count(Deal.id)), Deal)
        .filter(Deal.id.notin_(db.query(deals_with_contacts_subq.c.deal_id)))
        .scalar()
    ) or 0
    if no_contacts > 0:
        insights.append({
            "insight_type": "no_contacts",
            "title": "Deals Without Contacts",
            "description": f"{no_contacts} deal{'s' if no_contacts != 1 else ''} have no contacts",
            "deal_id": None,
            "priority": "medium",
        })

    # 3. Overdue follow-ups
    now = datetime.now(timezone.utc)
    overdue = (
        scope_query(db.query(func.count(OutreachActivity.id)), OutreachActivity)
        .filter(
            OutreachActivity.follow_up_date < now,
            OutreachActivity.completed == False,  # noqa: E712
        )
        .scalar()
    ) or 0
    if overdue > 0:
        insights.append({
            "insight_type": "overdue_followups",
            "title": "Overdue Follow-ups",
            "description": f"{overdue} follow-up{'s' if overdue != 1 else ''} overdue",
            "deal_id": None,
            "priority": "high",
        })

    # 4. Top risk deal
    top_risk = (
        active_query(db.query(Deal), Deal)
        .filter(Deal.risk_level == "high", Deal.score.isnot(None))
        .order_by(Deal.score.asc())
        .first()
    )
    if top_risk:
        insights.append({
            "insight_type": "top_risk",
            "title": "Top Risk Deal",
            "description": f"Top risk: {top_risk.name}",
            "deal_id": top_risk.id,
            "priority": "high",
        })

    # 5. Pipeline bottleneck
    bottleneck_row = (
        active_query(db.query(Deal.status, func.count(Deal.id).label("cnt")), Deal)
        .group_by(Deal.status)
        .order_by(func.count(Deal.id).desc())
        .first()
    )
    if bottleneck_row:
        stage = bottleneck_row[0]
        stage_str = stage.value if hasattr(stage, "value") else str(stage)
        insights.append({
            "insight_type": "pipeline_bottleneck",
            "title": "Pipeline Bottleneck",
            "description": f"Pipeline bottleneck: {stage_str}",
            "deal_id": None,
            "priority": "low",
        })

    return insights
