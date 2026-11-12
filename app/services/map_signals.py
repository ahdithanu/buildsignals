"""Bounded geographic source records independent of saved parcel searches."""
from sqlalchemy import and_, case, false, literal, or_
from sqlalchemy.orm import Session

from app import config
from app.models.ingestion import IngestionSource, PermitRecord
from app.models.permit_geocode import PermitGeocode
from app.models.planning import PlanningRecord
from app.utils.org_scope import active_query


def native_coordinate_predicate(model):
    return and_(model.latitude.between(-85, 85), model.longitude.between(-180, 180))


def permit_location_query(db: Session):
    """Share map eligibility and location projection with inventory counts."""
    query = active_query(db.query(PermitRecord), PermitRecord).filter(
        PermitRecord.is_active.is_(True),
    )
    native = native_coordinate_predicate(PermitRecord)
    derived = false()
    latitude, longitude = PermitRecord.latitude, PermitRecord.longitude
    method = literal("source_coordinate")
    if config.SF_DERIVED_LOCATIONS_ENABLED:
        from app.services.sf_geocoding import derived_geocode_predicate

        query = query.outerjoin(PermitGeocode, and_(
            PermitGeocode.permit_id == PermitRecord.id,
            PermitGeocode.organization_id == PermitRecord.organization_id,
        )).outerjoin(IngestionSource, and_(
            IngestionSource.id == PermitRecord.source_id,
            IngestionSource.organization_id == PermitRecord.organization_id,
        ))
        derived = derived_geocode_predicate(db)
        latitude = case((native, PermitRecord.latitude), else_=PermitGeocode.latitude)
        longitude = case((native, PermitRecord.longitude), else_=PermitGeocode.longitude)
        method = case(
            (native, "source_coordinate"), else_="census_address_range_estimate",
        )
    return query.add_columns(
        latitude.label("map_latitude"), longitude.label("map_longitude"),
        method.label("location_method"),
    ), native, derived


def list_map_signals(
    db: Session,
    *,
    limit: int = 100,
    offset: int = 0,
    state: str | None = None,
) -> dict:
    if not 1 <= limit <= 100:
        raise ValueError("Limit must be between 1 and 100")
    if offset < 0:
        raise ValueError("Offset must be greater than or equal to 0")
    items, truncated = [], []
    for kind, model in (("permit", PermitRecord), ("planning", PlanningRecord)):
        if kind == "permit":
            query, native, derived = permit_location_query(db)
            query = query.filter(or_(native, derived))
        else:
            query = active_query(db.query(model), model).filter(
                native_coordinate_predicate(model),
            ).add_columns(
                model.latitude.label("map_latitude"), model.longitude.label("map_longitude"),
                literal("source_coordinate").label("location_method"),
            )
        if state:
            query = query.filter(model.state.ilike(state.strip()))
        rows = query.order_by(model.updated_at.desc(), model.id).offset(offset).limit(limit + 1).all()
        if len(rows) > limit:
            truncated.append(kind)
        for row, latitude, longitude, location_method in rows[:limit]:
            items.append({
                "id": row.id, "kind": kind,
                "title": (row.project_name or row.permit_number or row.external_record_id)
                if kind == "permit" else row.title,
                "latitude": latitude, "longitude": longitude,
                "location_method": location_method,
                "address": row.address, "city": row.city, "state": row.state,
                "stage": row.approval_stage if kind == "permit" else row.stage,
                "source_id": row.source_id, "raw_record_id": row.latest_raw_record_id,
                "source_url": row.source_url, "updated_at": row.updated_at,
            })
    return {
        "items": items,
        "limit_per_layer": limit,
        "offset_per_layer": offset,
        "next_offset": offset + limit if truncated else None,
        "previous_offset": max(0, offset - limit) if offset else None,
        "truncated_layers": truncated,
    }
