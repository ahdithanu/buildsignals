"""Bounded geographic source records independent of saved parcel searches."""
from sqlalchemy.orm import Session

from app.models.ingestion import PermitRecord
from app.models.planning import PlanningRecord
from app.utils.org_scope import active_query


def list_map_signals(db: Session, *, limit: int = 100, state: str | None = None) -> dict:
    if not 1 <= limit <= 100:
        raise ValueError("Limit must be between 1 and 100")
    items, truncated = [], []
    for kind, model in (("permit", PermitRecord), ("planning", PlanningRecord)):
        query = active_query(db.query(model), model).filter(
            model.latitude.between(-85, 85), model.longitude.between(-180, 180),
        )
        if kind == "permit":
            query = query.filter(model.is_active.is_(True))
        if state:
            query = query.filter(model.state.ilike(state.strip()))
        rows = query.order_by(model.updated_at.desc(), model.id).limit(limit + 1).all()
        if len(rows) > limit:
            truncated.append(kind)
        for row in rows[:limit]:
            items.append({
                "id": row.id, "kind": kind,
                "title": (row.project_name or row.permit_number or row.external_record_id)
                if kind == "permit" else row.title,
                "latitude": row.latitude, "longitude": row.longitude,
                "address": row.address, "city": row.city, "state": row.state,
                "stage": row.approval_stage if kind == "permit" else row.stage,
                "source_id": row.source_id, "raw_record_id": row.latest_raw_record_id,
                "source_url": row.source_url, "updated_at": row.updated_at,
            })
    return {"items": items, "limit_per_layer": limit, "truncated_layers": truncated}
