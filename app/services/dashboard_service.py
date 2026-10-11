from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.contact import Contact
from app.models.deal import Deal, DealStatus
from app.models.outreach_activity import OutreachActivity
from app.models.signal import Signal
from app.utils.org_scope import active_query, scope_query

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
    now = datetime.now(timezone.utc)

    def _sample_records(query, *, record_type: str, limit: int = 25) -> list[dict[str, Any]]:
        return [{"record_type": record_type, "id": row.id} for row in query.limit(limit).all()]

    def _evidence(record_type: str, *, count: int, filter_: str, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{
            "record_type": record_type,
            "count": count,
            "filter": filter_,
            "sample_records": records,
        }]

    generated = now

    # 1. Deals needing scoring
    unscored_query = active_query(db.query(Deal), Deal).filter(Deal.score.is_(None))
    unscored = unscored_query.with_entities(func.count(Deal.id)).scalar() or 0
    if unscored > 0:
        insights.append({
            "insight_type": "needs_scoring",
            "title": "Deals Need Scoring",
            "description": f"{unscored} deal{'s' if unscored != 1 else ''} need scoring",
            "deal_id": None,
            "priority": "high" if unscored > 5 else "medium",
            "generated_at": generated,
            "time_window": {"as_of": generated.isoformat()},
            "source_records": _evidence(
                "deal",
                count=unscored,
                filter_="active deals where score is null",
                records=_sample_records(unscored_query.order_by(Deal.created_at.desc(), Deal.id), record_type="deal"),
            ),
        })

    # 2. Deals with no contacts
    deals_with_contacts_subq = (
        db.query(Contact.deal_id).distinct().subquery()
    )
    no_contacts_query = active_query(db.query(Deal), Deal).filter(
        Deal.id.notin_(db.query(deals_with_contacts_subq.c.deal_id))
    )
    no_contacts = no_contacts_query.with_entities(func.count(Deal.id)).scalar() or 0
    if no_contacts > 0:
        insights.append({
            "insight_type": "no_contacts",
            "title": "Deals Without Contacts",
            "description": f"{no_contacts} deal{'s' if no_contacts != 1 else ''} have no contacts",
            "deal_id": None,
            "priority": "medium",
            "generated_at": generated,
            "time_window": {"as_of": generated.isoformat()},
            "source_records": _evidence(
                "deal",
                count=no_contacts,
                filter_="active deals without linked contacts",
                records=_sample_records(no_contacts_query.order_by(Deal.created_at.desc(), Deal.id), record_type="deal"),
            ),
        })

    # 3. Overdue follow-ups
    overdue_query = scope_query(db.query(OutreachActivity), OutreachActivity).filter(
        OutreachActivity.follow_up_date < now,
        OutreachActivity.completed == False,  # noqa: E712
    )
    overdue = overdue_query.with_entities(func.count(OutreachActivity.id)).scalar() or 0
    if overdue > 0:
        insights.append({
            "insight_type": "overdue_followups",
            "title": "Overdue Follow-ups",
            "description": f"{overdue} follow-up{'s' if overdue != 1 else ''} overdue",
            "deal_id": None,
            "priority": "high",
            "generated_at": generated,
            "time_window": {"end": generated.isoformat()},
            "source_records": _evidence(
                "outreach_activity",
                count=overdue,
                filter_="incomplete outreach activities with follow_up_date before generated_at",
                records=_sample_records(overdue_query.order_by(OutreachActivity.follow_up_date, OutreachActivity.id), record_type="outreach_activity"),
            ),
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
            "generated_at": generated,
            "time_window": {"as_of": generated.isoformat()},
            "source_records": [{"record_type": "deal", "id": top_risk.id, "filter": "active high-risk scored deal with lowest score"}],
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
        bottleneck_query = active_query(db.query(Deal), Deal).filter(Deal.status == stage)
        insights.append({
            "insight_type": "pipeline_bottleneck",
            "title": "Pipeline Bottleneck",
            "description": f"Pipeline bottleneck: {stage_str}",
            "deal_id": None,
            "priority": "low",
            "generated_at": generated,
            "time_window": {"as_of": generated.isoformat()},
            "source_records": _evidence(
                "deal",
                count=bottleneck_row[1],
                filter_=f"active deals in status {stage_str}",
                records=_sample_records(bottleneck_query.order_by(Deal.created_at.desc(), Deal.id), record_type="deal"),
            ),
        })

    return insights
