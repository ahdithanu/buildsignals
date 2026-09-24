from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.graph import GraphEntity, GraphEntityLink, GraphRelationship
from app.schemas.graph import GraphEntityResponse, GraphRelationshipResponse
from app.models.ingestion import PermitRecord
from app.models.parcel import ParcelRecord
from app.models.permit_geocode import PermitGeocode
from app.services.demo_geocoding import address_hash
from app.utils.auth_deps import get_current_user
from app.utils.org_scope import active_query

router = APIRouter(prefix="/demo", tags=["demo"])


def _require_demo(principal: dict) -> None:
    if not principal.get("is_demo"):
        raise HTTPException(status_code=403, detail="Demo session required")


def _permit_query(db: Session):
    return active_query(db.query(PermitRecord), PermitRecord).filter(PermitRecord.is_active.is_(True))


def _current_geocodes(db: Session):
    rows = active_query(db.query(PermitGeocode, PermitRecord), PermitGeocode).join(
        PermitRecord,
        (PermitRecord.id == PermitGeocode.permit_id)
        & (PermitRecord.organization_id == PermitGeocode.organization_id),
    ).filter(PermitRecord.is_active.is_(True)).all()
    return [(geocode, permit) for geocode, permit in rows
            if permit.latitude is None and permit.longitude is None
            and geocode.address_hash == address_hash(permit)]


@router.get("/summary")
def demo_summary(principal: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_demo(principal)
    permits = _permit_query(db)
    parcels = active_query(db.query(ParcelRecord), ParcelRecord).filter(ParcelRecord.is_active.is_(True))
    derived = _current_geocodes(db)
    source_locations = permits.filter(
        PermitRecord.latitude.between(-85, 85), PermitRecord.longitude.between(-180, 180),
    ).with_entities(PermitRecord.latitude, PermitRecord.longitude).all()
    mapped_locations = {(row.latitude, row.longitude) for row in source_locations}
    mapped_locations.update((geocode.latitude, geocode.longitude) for geocode, _ in derived)
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
        ).count() + len(derived),
        "derived_geocoded_permits": len(derived),
        "mapped_filing_locations": len(mapped_locations),
        "mapped_parcels": parcels.filter(
            ParcelRecord.latitude.between(-85, 85), ParcelRecord.longitude.between(-180, 180),
        ).count(),
    }


@router.get("/activity")
def demo_activity(principal: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_demo(principal)
    rows = _permit_query(db).with_entities(
        PermitRecord.filed_at, PermitRecord.issued_at, PermitRecord.approval_stage,
    ).limit(5000).all()
    months: dict[str, dict[str, int]] = {}
    stages: dict[str, int] = {}
    for filed_at, issued_at, stage in rows:
        stages[stage or "unknown"] = stages.get(stage or "unknown", 0) + 1
        for field, value in (("filed", filed_at), ("issued", issued_at)):
            if value:
                month = value.strftime("%Y-%m")
                bucket = months.setdefault(month, {"filed": 0, "issued": 0})
                bucket[field] += 1
    return {"months": [{"month": month, **counts} for month, counts in sorted(months.items())],
            "stages": stages, "records_considered": len(rows), "limit": 5000}


@router.get("/graph-neighbors")
def demo_graph_neighbors(
    entity_id: str = Query(min_length=36, max_length=36),
    exclude_entity_id: str | None = Query(None, min_length=36, max_length=36),
    principal: dict = Depends(get_current_user), db: Session = Depends(get_db),
):
    _require_demo(principal)
    entity = active_query(db.query(GraphEntity), GraphEntity).filter(GraphEntity.id == entity_id).first()
    if not entity or entity.entity_type.value not in {"company", "property", "parcel"}:
        raise HTTPException(status_code=404, detail="Graph entity not available")
    relationships = active_query(db.query(GraphRelationship), GraphRelationship).options(
        joinedload(GraphRelationship.evidence),
    ).filter(
        GraphRelationship.is_current.is_(True),
        or_(GraphRelationship.source_entity_id == entity_id, GraphRelationship.target_entity_id == entity_id),
    ).order_by(GraphRelationship.last_verified_at.desc(), GraphRelationship.id).limit(12).all()
    other_ids = [r.target_entity_id if r.source_entity_id == entity_id else r.source_entity_id for r in relationships]
    entities = {row.id: row for row in active_query(db.query(GraphEntity), GraphEntity).filter(
        GraphEntity.id.in_(other_ids), GraphEntity.entity_type == "permit",
    ).all()}
    links = {row.entity_id: row.record_id for row in active_query(db.query(GraphEntityLink), GraphEntityLink).filter(
        GraphEntityLink.entity_id.in_(entities), GraphEntityLink.record_type == "permit",
    ).all()}
    return {"entity": GraphEntityResponse.model_validate(entity), "neighbors": [{
        "entity": GraphEntityResponse.model_validate(entities[other_id]),
        "relationship": GraphRelationshipResponse.model_validate(relationship),
        "permit_id": links.get(other_id),
    } for relationship, other_id in zip(relationships, other_ids)
        if other_id in entities and other_id != exclude_entity_id and links.get(other_id)]}


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


@router.get("/parcel-filings")
def demo_parcel_filings(
    reference: str = Query(min_length=1, max_length=255),
    principal: dict = Depends(get_current_user), db: Session = Depends(get_db),
):
    _require_demo(principal)
    rows = _permit_query(db).filter(PermitRecord.parcel_id == reference).order_by(
        PermitRecord.filed_at.desc(), PermitRecord.id,
    ).limit(25).all()
    addresses = _permit_query(db).filter(PermitRecord.parcel_id == reference).with_entities(
        func.count(func.distinct(PermitRecord.address)), func.count(PermitRecord.id),
    ).first()
    return {
        "reference": reference,
        "total_filings": addresses[1] if addresses else 0,
        "distinct_reported_addresses": addresses[0] if addresses else 0,
        "limit": 25,
        "filings": [{
            "id": row.id, "permit_number": row.permit_number or row.application_number or row.external_record_id,
            "address": row.address, "description": row.description, "status": row.status,
            "approval_stage": row.approval_stage, "filed_at": row.filed_at,
            "source_url": row.source_url,
        } for row in rows],
    }


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
    derived = _current_geocodes(db)[:100]
    parcels = active_query(db.query(ParcelRecord), ParcelRecord).filter(
        ParcelRecord.is_active.is_(True),
        ParcelRecord.latitude.between(-85, 85), ParcelRecord.longitude.between(-180, 180),
    ).order_by(ParcelRecord.last_seen_at.desc(), ParcelRecord.id).limit(100).all()
    return {
        "permits": [{
            "id": row.id, "title": row.address or row.permit_number or row.external_record_id,
            "latitude": row.latitude, "longitude": row.longitude, "kind": "permit",
            "location_method": "source_coordinate", "source_url": row.source_url,
            "filing_number": row.permit_number or row.application_number or row.external_record_id,
            "status": row.status,
        } for row in permits] + [{
            "id": permit.id, "title": permit.address or permit.external_record_id,
            "latitude": geocode.latitude, "longitude": geocode.longitude, "kind": "permit",
            "location_method": "census_address_range_estimate", "source_url": geocode.source_url,
            "matched_address": geocode.matched_address,
            "filing_number": permit.permit_number or permit.application_number or permit.external_record_id,
            "status": permit.status,
        } for geocode, permit in derived[:max(0, 100 - len(permits))]],
        "parcels": [{
            "id": row.id, "title": row.address or row.external_parcel_id,
            "latitude": row.latitude, "longitude": row.longitude, "kind": "parcel",
            "boundary": boundary if _valid_boundary(boundary := row.boundary_geometry) else None,
            "location_method": "source_coordinate", "source_url": row.source.base_url,
            "external_parcel_id": row.external_parcel_id,
        } for row in parcels],
        "limit_per_layer": 100,
    }
