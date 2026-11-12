"""Strict, tenant-scoped SF address estimates, separate from publisher coordinates."""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from sqlalchemy import and_, false, func, literal

from app.models.ingestion import IngestionSource, PermitRecord
from app.models.permit_geocode import PermitGeocode
from app.services.demo_access import DEMO_ORG_ID, demo_read_only
from app.services.demo_geocoding import BENCHMARK, GEOCODER_URL, address_hash
from app.services.graph_service import normalize_address
from app.utils.org_scope import get_org_id

SOURCE_KEY = "san_francisco_ca_building_permits_primary_address"
SOURCE_URL = "https://data.sf.gov/resource/i98e-djp9.json"
LOCATION_METHOD = "census_address_range_estimate"
MAX_AGE_DAYS = 90  # Conservative application policy, not a publisher accuracy guarantee.
LATITUDE_BOUNDS = (37.70, 37.84)
LONGITUDE_BOUNDS = (-122.53, -122.35)


def _scope(permit, source) -> None:
    org = get_org_id()
    if (org == DEMO_ORG_ID or permit.organization_id != org or source is None
            or source.organization_id != org or source.id != permit.source_id
            or source.key != SOURCE_KEY or source.base_url != SOURCE_URL
            or not source.is_active or not permit.is_active):
        raise ValueError("An active, tenant-scoped SF source record is required")
    if (not isinstance(permit.address, str) or not 1 <= len(permit.address) <= 300
            or not permit.address.strip() or (permit.city or "").strip().casefold() != "san francisco"
            or (permit.state or "").strip().upper() != "CA"
            or not re.fullmatch(r"941[0-9]{2}", permit.postal_code or "")):
        raise ValueError("A complete San Francisco address and five-digit ZIP are required")


def request_url(permit, source) -> str:
    _scope(permit, source)
    return GEOCODER_URL + "?" + urlencode({
        "address": f"{permit.address}, {permit.city}, {permit.state} {permit.postal_code}",
        "benchmark": BENCHMARK, "format": "json",
    })


def _valid_coordinates(latitude, longitude) -> bool:
    return (type(latitude) in (int, float) and type(longitude) in (int, float)
            and math.isfinite(latitude) and math.isfinite(longitude)
            and LATITUDE_BOUNDS[0] <= latitude <= LATITUDE_BOUNDS[1]
            and LONGITUDE_BOUNDS[0] <= longitude <= LONGITUDE_BOUNDS[1])


def validated_match(permit, source, response) -> dict | None:
    _scope(permit, source)
    result = response.get("result") if isinstance(response, dict) else None
    matches = result.get("addressMatches") if isinstance(result, dict) else None
    if not isinstance(matches, list) or len(matches) != 1 or not isinstance(matches[0], dict):
        return None
    match = matches[0]
    parts, coords, full = match.get("addressComponents"), match.get("coordinates"), match.get("matchedAddress")
    if not isinstance(parts, dict) or not isinstance(coords, dict) or not isinstance(full, str):
        return None
    if not 1 <= len(full) <= 500:
        return None
    address_parts = [part.strip() for part in full.rsplit(",", 3)]
    if (len(address_parts) != 4 or address_parts[1].casefold() != "san francisco"
            or address_parts[2].upper() != "CA" or address_parts[3] != permit.postal_code
            or normalize_address(address_parts[0]) != normalize_address(permit.address)
            or not isinstance(parts.get("city"), str) or parts["city"].casefold() != "san francisco"
            or parts.get("state") != "CA" or parts.get("zip") != permit.postal_code
            or not _valid_coordinates(coords.get("y"), coords.get("x"))):
        return None
    return {"latitude": coords["y"], "longitude": coords["x"], "matched_address": full}


def is_current_geocode(permit, source, row, *, now=None) -> bool:
    try:
        _scope(permit, source)
    except ValueError:
        return False
    if demo_read_only.get() or permit.latitude is not None or permit.longitude is not None:
        return False
    observed = row.observed_at
    if not isinstance(observed, datetime):
        return False
    observed = observed.replace(tzinfo=timezone.utc) if observed.tzinfo is None else observed
    now = now or datetime.now(timezone.utc)
    return bool(row.organization_id == permit.organization_id and row.permit_id == permit.id
        and row.address_hash == address_hash(permit) and row.benchmark == BENCHMARK
        and row.source_url == GEOCODER_URL and re.fullmatch(r"[a-f0-9]{64}", row.response_hash or "")
        and isinstance(row.matched_address, str) and 1 <= len(row.matched_address.strip()) <= 500
        and now - timedelta(days=MAX_AGE_DAYS) <= observed <= now + timedelta(minutes=5)
        and _valid_coordinates(row.latitude, row.longitude))


def save_match(db, permit, response, url: str) -> bool:
    if demo_read_only.get():
        raise PermissionError("Demo sessions cannot write production geocodes")
    if permit.organization_id != get_org_id() or get_org_id() == DEMO_ORG_ID:
        raise ValueError("Geocode tenant scope does not match")
    with db.no_autoflush:
        source = db.query(IngestionSource).populate_existing().filter_by(
            id=permit.source_id, organization_id=get_org_id()).first()
        if url != request_url(permit, source):
            raise ValueError("Geocode evidence does not match the requested address")
        if permit.latitude is not None or permit.longitude is not None:
            return False
        match = validated_match(permit, source, response)
        if match is None:
            return False
        try:
            response_hash = hashlib.sha256(json.dumps(response, sort_keys=True, allow_nan=False).encode()).hexdigest()
        except (TypeError, ValueError):
            return False
        row = db.query(PermitGeocode).filter_by(organization_id=get_org_id(), permit_id=permit.id).first()
    if row is not None and is_current_geocode(permit, source, row) and row.response_hash == response_hash:
        return True
    if row is None:
        row = PermitGeocode(organization_id=get_org_id(), permit_id=permit.id)
        db.add(row)
    row.address_hash, row.response_hash = address_hash(permit), response_hash
    row.latitude, row.longitude = match["latitude"], match["longitude"]
    row.matched_address, row.benchmark = match["matched_address"], BENCHMARK
    row.source_url = GEOCODER_URL  # Keep address query strings out of stored URLs.
    row.observed_at = datetime.now(timezone.utc)
    return True


def sql_address_hash(db, permit=PermitRecord):
    joined = func.coalesce(permit.address, "")
    for field in (permit.city, permit.state, permit.postal_code):
        joined = joined + literal("|") + func.coalesce(field, "")
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        return func.encode(func.sha256(func.convert_to(joined, "UTF8")), "hex")
    if dialect == "sqlite":
        # SQLite has no built-in SHA256; register only on this local connection.
        connection = db.connection().connection.driver_connection
        connection.create_function("buildsignals_sha256", 1,
            lambda value: hashlib.sha256(value.encode()).hexdigest(), deterministic=True)
        return func.buildsignals_sha256(joined)
    raise ValueError("Derived locations support PostgreSQL and SQLite only")


def derived_geocode_predicate(db, permit=PermitRecord, geocode=PermitGeocode, source=IngestionSource, *, now=None):
    """Filter stored, validated evidence before pagination; never fetch a provider."""
    if demo_read_only.get() or get_org_id() == DEMO_ORG_ID:
        return false()
    now = now or datetime.now(timezone.utc)
    return and_(
        permit.organization_id == get_org_id(), source.organization_id == permit.organization_id,
        source.id == permit.source_id, source.key == SOURCE_KEY, source.base_url == SOURCE_URL,
        source.is_active.is_(True), permit.is_active.is_(True),
        func.lower(func.trim(permit.city)) == "san francisco", func.upper(func.trim(permit.state)) == "CA",
        permit.postal_code.regexp_match(r"^941[0-9]{2}$"), func.length(permit.postal_code) == 5,
        func.length(permit.address).between(1, 300), func.length(func.trim(permit.address)) > 0,
        permit.latitude.is_(None), permit.longitude.is_(None),
        geocode.organization_id == permit.organization_id, geocode.permit_id == permit.id,
        geocode.address_hash == sql_address_hash(db, permit), geocode.benchmark == BENCHMARK,
        geocode.source_url == GEOCODER_URL, geocode.response_hash.regexp_match(r"^[a-f0-9]{64}$"),
        func.length(geocode.response_hash) == 64,
        func.length(func.trim(geocode.matched_address)).between(1, 500),
        geocode.latitude.between(*LATITUDE_BOUNDS), geocode.longitude.between(*LONGITUDE_BOUNDS),
        geocode.observed_at >= now - timedelta(days=MAX_AGE_DAYS),
        geocode.observed_at <= now + timedelta(minutes=5),
    )
