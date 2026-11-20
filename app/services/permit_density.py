"""Read-only SQL grid over every eligible current tenant permit.

Each attempted resolution performs one aggregate SELECT, including an unmapped
bucket. Only a complete grid is returned, so final totals and cells share one
statement snapshot even when concurrent ingestion changes the inventory.
"""
from datetime import datetime, timezone
from math import ceil

from sqlalchemy import Integer, case, cast, func, or_
from sqlalchemy.orm import Session

from app.models.ingestion import PermitRecord
from app.schemas.permit_density import PermitDensityResponse
from app.services.map_coverage import _filters, _state_expression
from app.services.map_signals import permit_location_query

CELL_DEGREES = (0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 4, 8)
MAX_CELLS = 2048


def get_permit_density(db: Session, *, state: str | None = None) -> PermitDensityResponse:
    if state is not None and not isinstance(state, str):
        raise ValueError("State must be a US state code, DC, or __unknown__")
    state = _filters(state=state, kind="permit", limit=100, offset=0)
    measured_at = datetime.now(timezone.utc)
    with db.no_autoflush:
        query, native, derived = permit_location_query(db)
        projection = {column["name"]: column["expr"] for column in query.column_descriptions}
        if state is not None:
            query = query.filter(_state_expression(PermitRecord) == state)
        inventory = query.with_entities(
            case((or_(native, derived), projection["map_latitude"])).label("latitude"),
            case((or_(native, derived), projection["map_longitude"])).label("longitude"),
            case((native, 1), else_=0).label("source_coordinate"),
        ).subquery("density_inventory")
        for degrees in CELL_DEGREES:
            latitude_index = case(
                (inventory.c.latitude.is_(None), None),
                (inventory.c.latitude + 90 >= 175, ceil(175 / degrees) - 1),
                else_=cast(func.floor((inventory.c.latitude + 90) / degrees), Integer),
            )
            # Clamp upper edges, including near-edge floats rounded up by addition.
            longitude_index = case(
                (inventory.c.longitude.is_(None), None),
                (inventory.c.longitude + 180 >= 360, int(360 / degrees) - 1),
                else_=cast(func.floor((inventory.c.longitude + 180) / degrees), Integer),
            )
            rows = db.query(
                latitude_index.label("latitude_index"), longitude_index.label("longitude_index"),
                func.count().label("count"),
                func.sum(inventory.c.source_coordinate).label("source_coordinate_count"),
            ).select_from(inventory).group_by(latitude_index, longitude_index).order_by(
                latitude_index, longitude_index,
            ).limit(MAX_CELLS + 2).all()
            # Up to 2049 mapped cells plus one unmapped bucket prove overflow.
            mapped_rows = [row for row in rows if row.latitude_index is not None]
            if len(mapped_rows) <= MAX_CELLS:
                break
        else:
            # At 8 degrees the entire eligible world has at most 22 * 45 cells.
            raise RuntimeError("Permit density exceeded the bounded world grid")

    cells = []
    for row in mapped_rows:
        grid_south = round(-90 + row.latitude_index * degrees, 10)
        south = max(-85, grid_south)
        west = round(-180 + row.longitude_index * degrees, 10)
        north = min(85, round(grid_south + degrees, 10))
        east = min(180, round(west + degrees, 10))
        count, source_count = int(row.count), int(row.source_coordinate_count)
        cells.append(dict(
            id=f"permit-density:{degrees:g}:{row.latitude_index}:{row.longitude_index}",
            latitude=(south + north) / 2, longitude=(west + east) / 2,
            count=count, source_coordinate_count=source_count, estimated_count=count - source_count,
            south=south, west=west, north=north, east=east,
        ))
    mapped = sum(cell["count"] for cell in cells)
    source = sum(cell["source_coordinate_count"] for cell in cells)
    unmapped = sum(int(row.count) for row in rows if row.latitude_index is None)
    return PermitDensityResponse(
        measured_at=measured_at, state=state, total_permits=mapped + unmapped,
        mapped_permits=mapped, unmapped_permits=unmapped,
        source_coordinate_count=source, estimated_count=mapped - source,
        cell_degrees=degrees, cells=cells, complete=True,
    )
