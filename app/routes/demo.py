from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.graph import GraphEntity, GraphRelationship
from app.models.ingestion import PermitRecord
from app.models.parcel import ParcelRecord
from app.utils.auth_deps import get_current_user
from app.utils.org_scope import active_query

router = APIRouter(prefix="/demo", tags=["demo"])


def _require_demo(principal: dict) -> None:
    if not principal.get("is_demo"):
        raise HTTPException(status_code=403, detail="Demo session required")


def _permit_query(db: Session):
    return active_query(db.query(PermitRecord), PermitRecord).filter(PermitRecord.is_active.is_(True))


@router.get("/summary")
def demo_summary(principal: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_demo(principal)
    permits = _permit_query(db)
    parcels = active_query(db.query(ParcelRecord), ParcelRecord).filter(ParcelRecord.is_active.is_(True))
    return {
        "permit_records": permits.count(),
        "graph_entities": active_query(db.query(GraphEntity), GraphEntity).count(),
        "relationships": active_query(db.query(GraphRelationship), GraphRelationship).count(),
        "captured_at": permits.with_entities(func.max(PermitRecord.last_seen_at)).scalar(),
        "parcel_references": permits.filter(func.trim(PermitRecord.parcel_id) != "")
            .with_entities(func.count(func.distinct(PermitRecord.parcel_id))).scalar() or 0,
        "parcel_records": parcels.count(),
        "mapped_permits": permits.filter(
            PermitRecord.latitude.between(-85, 85), PermitRecord.longitude.between(-180, 180),
        ).count(),
        "mapped_parcels": parcels.filter(
            ParcelRecord.latitude.between(-85, 85), ParcelRecord.longitude.between(-180, 180),
        ).count(),
    }


@router.get("/parcel-references")
def demo_parcel_references(
    principal: dict = Depends(get_current_user), db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=25), offset: int = Query(0, ge=0, le=5000),
):
    _require_demo(principal)
    rows = _permit_query(db).filter(func.trim(PermitRecord.parcel_id) != "").with_entities(
        PermitRecord.parcel_id.label("reference"),
        func.count(PermitRecord.id).label("permit_count"),
        func.min(PermitRecord.id).label("sample_id"),
    ).group_by(PermitRecord.parcel_id).order_by(
        func.count(PermitRecord.id).desc(), PermitRecord.parcel_id,
    ).offset(offset).limit(limit).all()
    samples = {row.id: row for row in _permit_query(db).filter(
        PermitRecord.id.in_([item.sample_id for item in rows]),
    ).all()} if rows else {}
    return [{
        "reference": item.reference,
        "permit_count": item.permit_count,
        "sample_permit_id": item.sample_id,
        "sample_address": samples[item.sample_id].address if item.sample_id in samples else None,
    } for item in rows]


def _valid_boundary(boundary: dict | None) -> bool:
    if not boundary or boundary.get("type") != "Polygon":
        return False
    rings = boundary.get("coordinates")
    return bool(isinstance(rings, list) and rings and len(rings) <= 8
        and sum(len(ring) for ring in rings if isinstance(ring, list)) <= 500 and all(
        isinstance(ring, list) and len(ring) >= 4 and all(
            isinstance(point, list) and len(point) >= 2
            and isinstance(point[0], (int, float)) and isinstance(point[1], (int, float))
            and -180 <= point[0] <= 180 and -85 <= point[1] <= 85
            for point in ring
        ) for ring in rings
    ))


@router.get("/map")
def demo_map(principal: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_demo(principal)
    permits = _permit_query(db).filter(
        PermitRecord.latitude.between(-85, 85), PermitRecord.longitude.between(-180, 180),
    ).order_by(PermitRecord.last_seen_at.desc(), PermitRecord.id).limit(100).all()
    parcels = active_query(db.query(ParcelRecord), ParcelRecord).filter(
        ParcelRecord.is_active.is_(True),
        ParcelRecord.latitude.between(-85, 85), ParcelRecord.longitude.between(-180, 180),
    ).order_by(ParcelRecord.last_seen_at.desc(), ParcelRecord.id).limit(100).all()
    return {
        "permits": [{
            "id": row.id, "title": row.address or row.permit_number or row.external_record_id,
            "latitude": row.latitude, "longitude": row.longitude, "kind": "permit",
        } for row in permits],
        "parcels": [{
            "id": row.id, "title": row.address or row.external_parcel_id,
            "latitude": row.latitude, "longitude": row.longitude, "kind": "parcel",
            "boundary": boundary if _valid_boundary(boundary := row.boundary_geometry) else None,
        } for row in parcels],
        "limit_per_layer": 100,
    }
