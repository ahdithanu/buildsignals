from __future__ import annotations

import math
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.parcel import ParcelRecord
from app.utils.org_scope import active_query, get_org_id


EARTH_RADIUS_MILES = 3958.7613


def haversine_miles(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    lat_a, lat_b = math.radians(latitude_a), math.radians(latitude_b)
    delta_lat = lat_b - lat_a
    delta_lon = math.radians(longitude_b - longitude_a)
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MILES * math.asin(min(1.0, math.sqrt(haversine)))


def find_nearby_parcels(
    db: Session,
    *,
    latitude: float,
    longitude: float,
    radius_miles: float,
    minimum_land_area_sq_ft: float | None = None,
    zoning_codes: Iterable[str] = (),
    land_uses: Iterable[str] = (),
    limit: int = 50,
) -> list[tuple[ParcelRecord, float]]:
    if not 0.25 <= radius_miles <= 5:
        raise ValueError("radius_miles must be between 0.25 and 5")
    zoning = {value.casefold() for value in zoning_codes}
    uses = {value.casefold() for value in land_uses}
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        rows = db.execute(text("""
            WITH nearby AS (
              SELECT id, source_id, external_parcel_id, parcel_group_id,
                     ST_Distance(
                       centroid,
                       ST_SetSRID(ST_MakePoint(:longitude, :latitude), 4326)::geography
                     ) / 1609.344 AS distance_miles
              FROM parcel_records
              WHERE organization_id = :organization_id
                AND is_active = TRUE
                AND centroid IS NOT NULL
                AND ST_DWithin(
                  centroid,
                  ST_SetSRID(ST_MakePoint(:longitude, :latitude), 4326)::geography,
                  :radius_meters
                )
            ), grouped AS (
              SELECT *, ROW_NUMBER() OVER (
                PARTITION BY source_id, COALESCE(parcel_group_id, id)
                ORDER BY (external_parcel_id = parcel_group_id) DESC,
                         distance_miles, external_parcel_id, id
              ) AS group_rank
              FROM nearby
            )
            SELECT id, distance_miles
            FROM grouped
            WHERE group_rank = 1
            ORDER BY distance_miles, id
            LIMIT 500
        """), {
            "latitude": latitude,
            "longitude": longitude,
            "organization_id": get_org_id(),
            "radius_meters": radius_miles * 1609.344,
        }).all()
        parcels = active_query(db.query(ParcelRecord), ParcelRecord).filter(
            ParcelRecord.id.in_([row.id for row in rows])
        ).all()
        by_id = {parcel.id: parcel for parcel in parcels}
        candidates = [
            (by_id[row.id], float(row.distance_miles))
            for row in rows if row.id in by_id
        ]
    else:
        latitude_delta = radius_miles / 69.0
        longitude_scale = max(math.cos(math.radians(latitude)), 0.01)
        longitude_delta = radius_miles / (69.172 * longitude_scale)
        parcels = active_query(db.query(ParcelRecord), ParcelRecord).filter(
            ParcelRecord.is_active.is_(True),
            ParcelRecord.latitude.between(latitude - latitude_delta, latitude + latitude_delta),
            ParcelRecord.longitude.between(longitude - longitude_delta, longitude + longitude_delta),
        ).all()
        candidates = []
        for parcel in parcels:
            distance = haversine_miles(
                latitude, longitude, parcel.latitude, parcel.longitude
            )
            if distance <= radius_miles:
                candidates.append((parcel, distance))

    filtered = [
        (parcel, distance)
        for parcel, distance in candidates
        if (
            minimum_land_area_sq_ft is None
            or (
                parcel.land_area_sq_ft is not None
                and parcel.land_area_sq_ft >= minimum_land_area_sq_ft
            )
        )
        and (not zoning or (parcel.zoning_code or "").casefold() in zoning)
        and (not uses or (parcel.land_use or "").casefold() in uses)
    ]
    grouped: dict[tuple[str, str], tuple[ParcelRecord, float]] = {}
    for parcel, distance in filtered:
        group_id = (parcel.source_id, parcel.parcel_group_id or parcel.id)
        existing = grouped.get(group_id)
        preference = (
            parcel.external_parcel_id != parcel.parcel_group_id,
            round(distance, 9), parcel.external_parcel_id, parcel.id,
        )
        if existing is None:
            grouped[group_id] = (parcel, distance)
            continue
        existing_parcel, existing_distance = existing
        existing_preference = (
            existing_parcel.external_parcel_id != existing_parcel.parcel_group_id,
            round(existing_distance, 9), existing_parcel.external_parcel_id,
            existing_parcel.id,
        )
        if preference < existing_preference:
            grouped[group_id] = (parcel, distance)
    filtered = list(grouped.values())
    filtered.sort(key=lambda item: (round(item[1], 9), item[0].external_parcel_id, item[0].id))
    return filtered[:limit]
