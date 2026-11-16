"""Database-aggregated tenant inventory, never a sample of the first map pins.

Group coordinates are arithmetic means of eligible stored/projected points,
not parcel locations or inferred state/city centers. Missing locations remain
in totals, groups and the independently paginated record list.
"""
from datetime import datetime, timezone
from hashlib import sha256

from sqlalchemy import case, func, literal, or_, union_all
from sqlalchemy.orm import Session

from app.models.ingestion import PermitRecord
from app.models.parcel import ParcelRecord
from app.models.planning import PlanningRecord
from app.schemas.map_coverage import MapCoverageResponse, MapRecordsResponse
from app.services.map_signals import (
    current_record_predicate,
    native_coordinate_predicate,
    permit_location_query,
)
from app.utils.org_scope import active_query

UNKNOWN = "__unknown__"
STATE_LABELS = dict(
    AL="Alabama", AK="Alaska", AZ="Arizona", AR="Arkansas", CA="California",
    CO="Colorado", CT="Connecticut", DE="Delaware", DC="District of Columbia",
    FL="Florida", GA="Georgia", HI="Hawaii", ID="Idaho", IL="Illinois", IN="Indiana",
    IA="Iowa", KS="Kansas", KY="Kentucky", LA="Louisiana", ME="Maine", MD="Maryland",
    MA="Massachusetts", MI="Michigan", MN="Minnesota", MS="Mississippi", MO="Missouri",
    MT="Montana", NE="Nebraska", NV="Nevada", NH="New Hampshire", NJ="New Jersey",
    NM="New Mexico", NY="New York", NC="North Carolina", ND="North Dakota", OH="Ohio",
    OK="Oklahoma", OR="Oregon", PA="Pennsylvania", RI="Rhode Island", SC="South Carolina",
    SD="South Dakota", TN="Tennessee", TX="Texas", UT="Utah", VT="Vermont", VA="Virginia",
    WA="Washington", WV="West Virginia", WI="Wisconsin", WY="Wyoming",
)


def _filters(*, state, kind, limit, offset):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Limit must be between 1 and 100")
    if type(offset) is not int or not 0 <= offset <= 100000:
        raise ValueError("Offset must be between 0 and 100000")
    if kind not in {"all", "permit", "planning", "parcel"}:
        raise ValueError("Invalid record kind")
    if state is not None:
        state = state.strip()
        state = UNKNOWN if state.lower() == UNKNOWN else state.upper()
        if state not in STATE_LABELS and state != UNKNOWN:
            raise ValueError("State must be a US state code, DC, or __unknown__")
    return state


def _state_expression(model):
    value = func.upper(func.trim(func.coalesce(model.state, "")))
    return case((value.in_(tuple(STATE_LABELS)), value), else_=UNKNOWN)


def _project(query, model, kind, valid, latitude, longitude, method):
    jurisdiction = func.trim(func.coalesce(model.jurisdiction, ""))
    if kind == "permit":
        title = func.coalesce(func.nullif(func.trim(model.project_name), ""),
                              func.nullif(func.trim(model.permit_number), ""), "Permit")
    elif kind == "planning":
        title = func.coalesce(func.nullif(func.trim(model.title), ""), "Planning record")
    else:
        title = func.coalesce(func.nullif(func.trim(model.address), ""), "Parcel")
    return query.with_entities(
        model.id.label("id"), literal(kind).label("kind"),
        _state_expression(model).label("state"),
        case((jurisdiction == "", UNKNOWN), else_=func.lower(jurisdiction)).label("jurisdiction_key"),
        case((jurisdiction == "", UNKNOWN), else_=jurisdiction).label("jurisdiction"),
        title.label("title"), model.address.label("address"), model.city.label("city"),
        case((valid, latitude), else_=None).label("latitude"),
        case((valid, longitude), else_=None).label("longitude"),
        case((valid, method), else_=None).label("location_method"),
        case((valid, 1), else_=0).label("mapped"),
    ).statement


def _inventory(db):
    permit, native, derived = permit_location_query(db)
    # Reuse the helper's named coordinate projections without loading ORM rows.
    projection = {column["name"]: column["expr"] for column in permit.column_descriptions}
    statements = [_project(
        permit, PermitRecord, "permit", or_(native, derived),
        projection["map_latitude"], projection["map_longitude"], projection["location_method"],
    )]
    for kind, model in (("planning", PlanningRecord), ("parcel", ParcelRecord)):
        query = active_query(db.query(model), model).filter(current_record_predicate(model))
        statements.append(_project(query, model, kind, native_coordinate_predicate(model),
                                   model.latitude, model.longitude, literal("source_coordinate")))
    return union_all(*statements).subquery("coverage_inventory")


def _select_filters(query, inventory, state, kind):
    if state is not None:
        query = query.filter(inventory.c.state == state)
    if kind != "all":
        query = query.filter(inventory.c.kind == kind)
    return query


def _counts(inventory):
    return [
        func.sum(case((inventory.c.kind == kind, 1), else_=0)).label(f"{kind}_count")
        for kind in ("permit", "planning", "parcel")
    ] + [func.sum(inventory.c.mapped).label("mapped_count"),
         func.sum(1 - inventory.c.mapped).label("unmapped_count")]


def _counts_dict(row):
    return {name: int(row[name] or 0) for name in (
        "permit_count", "planning_count", "parcel_count", "mapped_count", "unmapped_count",
    )}


def _group_query(db, inventory, *, state=None, kind="all", jurisdiction=False):
    columns = [inventory.c.state]
    grouped = [inventory.c.state]
    if jurisdiction:
        columns += [inventory.c.jurisdiction_key, func.min(inventory.c.jurisdiction).label("jurisdiction")]
        grouped.append(inventory.c.jurisdiction_key)
    query = db.query(*columns, *_counts(inventory),
                     func.avg(inventory.c.latitude).label("latitude"),
                     func.avg(inventory.c.longitude).label("longitude")).select_from(inventory)
    return _select_filters(query, inventory, state, kind).group_by(*grouped)


def _page_links(total, limit, offset):
    following = offset + limit
    return dict(next_offset=following if following < total and following <= 100000 else None,
                previous_offset=max(0, offset - limit) if offset else None)


def _state_row(row):
    return dict(state=row["state"], label=STATE_LABELS.get(row["state"], "Unknown state"),
                **_counts_dict(row), latitude=row["latitude"], longitude=row["longitude"])


def get_map_coverage(db: Session, *, state=None, kind="all", limit=100, offset=0) -> MapCoverageResponse:
    state = _filters(state=state, kind=kind, limit=limit, offset=offset)
    measured_at = datetime.now(timezone.utc)
    with db.no_autoflush:
        inventory = _inventory(db)
        totals = _select_filters(db.query(*_counts(inventory)).select_from(inventory),
                                inventory, state, kind).one()._mapping
        # SQL normalizes to only 51 state codes plus one unknown bucket.
        states = [_state_row(row._mapping) for row in _group_query(db, inventory)
                  .order_by(inventory.c.state).limit(52).all()]
        query = _group_query(db, inventory, state=state, kind=kind, jurisdiction=state is not None)
        total_groups = db.query(func.count()).select_from(query.subquery()).scalar()
        ordering = [inventory.c.state]
        if state is not None:
            ordering.append(inventory.c.jurisdiction_key)
        rows = query.order_by(*ordering).offset(offset).limit(limit).all()
        groups = []
        for result in rows:
            row = result._mapping
            item = _state_row(row)
            jurisdiction = row["jurisdiction"] if state is not None else None
            key = row["jurisdiction_key"] if state is not None else ""
            identity = f"{row['state']}:{key}"
            item.update(id="coverage-" + sha256(identity.encode()).hexdigest()[:24], jurisdiction=jurisdiction)
            if state is not None:
                item["label"] = "Unknown jurisdiction" if jurisdiction == UNKNOWN else jurisdiction
            groups.append(item)
    return MapCoverageResponse(
        measured_at=measured_at, totals=_counts_dict(totals), states=states, groups=groups,
        grouping="jurisdiction" if state is not None else "state", total_groups=total_groups,
        limit=limit, offset=offset, **_page_links(total_groups, limit, offset),
        truncated=total_groups > len(groups),
    )


def list_map_records(db: Session, *, state=None, kind="all", jurisdiction=None,
                     limit=100, offset=0) -> MapRecordsResponse:
    state = _filters(state=state, kind=kind, limit=limit, offset=offset)
    if jurisdiction is not None:
        if not isinstance(jurisdiction, str) or not 1 <= len(jurisdiction.strip()) <= 255:
            raise ValueError("Jurisdiction must be a nonempty string of at most 255 characters")
        jurisdiction = jurisdiction.strip().lower()
    with db.no_autoflush:
        inventory = _inventory(db)
        query = _select_filters(db.query(inventory), inventory, state, kind)
        if jurisdiction is not None:
            query = query.filter(inventory.c.jurisdiction_key == jurisdiction)
        total = db.query(func.count()).select_from(query.subquery()).scalar()
        columns = [inventory.c[name] for name in (
            "id", "kind", "title", "address", "city", "state", "jurisdiction",
            "latitude", "longitude", "location_method",
        )]
        rows = query.with_entities(*columns).order_by(inventory.c.kind, inventory.c.id).offset(offset).limit(limit).all()
    return MapRecordsResponse(items=[dict(row._mapping) for row in rows], total=total,
                              limit=limit, offset=offset, **_page_links(total, limit, offset))
