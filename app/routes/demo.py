from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.graph import GraphEntity, GraphRelationship
from app.models.ingestion import PermitRecord
from app.utils.auth_deps import get_current_user
from app.utils.org_scope import active_query

router = APIRouter(prefix="/demo", tags=["demo"])


@router.get("/summary")
def demo_summary(principal: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    if not principal.get("is_demo"):
        raise HTTPException(status_code=403, detail="Demo session required")
    return {
        "permit_records": active_query(db.query(PermitRecord), PermitRecord).count(),
        "graph_entities": active_query(db.query(GraphEntity), GraphEntity).count(),
        "relationships": active_query(db.query(GraphRelationship), GraphRelationship).count(),
        "captured_at": active_query(db.query(func.max(PermitRecord.last_seen_at)), PermitRecord).scalar(),
    }
