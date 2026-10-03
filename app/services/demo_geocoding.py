"""Bounded Census address geocoding for the historical demo only."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlencode

from app.models.permit_geocode import PermitGeocode
from app.services.demo_access import DEMO_ORG_ID
from app.services.graph_service import normalize_address

BENCHMARK = "Public_AR_Current"
GEOCODER_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"


def address_hash(permit) -> str:
    key = "|".join((permit.address or "", permit.city or "", permit.state or "", permit.postal_code or ""))
    return hashlib.sha256(key.encode()).hexdigest()


def request_url(permit) -> str:
    if permit.organization_id != DEMO_ORG_ID or not permit.address or not permit.city or permit.state != "OH":
        raise ValueError("Only Ohio addresses in the fixed demo tenant may be geocoded")
    if permit.city.casefold() != "columbus" or not re.fullmatch(r"\d{5}", permit.postal_code or ""):
        raise ValueError("A Columbus city and five-digit ZIP are required")
    return GEOCODER_URL + "?" + urlencode({
        "address": f"{permit.address}, {permit.city}, {permit.state} {permit.postal_code}",
        "benchmark": BENCHMARK, "format": "json",
    })


def validated_match(permit, response: dict) -> dict | None:
    if not isinstance(response, dict):
        return None
    matches = response.get("result", {}).get("addressMatches", [])
    if not isinstance(matches, list) or len(matches) != 1:
        return None
    match = matches[0]
    if not isinstance(match, dict):
        return None
    parts = match.get("addressComponents", {})
    full = match.get("matchedAddress", "")
    coords = match.get("coordinates", {})
    if not isinstance(parts, dict) or not isinstance(full, str) or not isinstance(coords, dict):
        return None
    if (not isinstance(parts.get("city"), str) or not isinstance(parts.get("state"), str)
            or parts["city"].casefold() != "columbus" or parts["state"].upper() != "OH"
            or parts.get("zip") != permit.postal_code):
        return None
    if normalize_address(full.split(",")[0]) != normalize_address(permit.address):
        return None
    lat, lon = coords.get("y"), coords.get("x")
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return None
    if not (39.7 <= lat <= 40.2 and -83.3 <= lon <= -82.7):
        return None
    return {"latitude": lat, "longitude": lon, "matched_address": full}


def save_match(db, permit, response: dict, url: str) -> bool:
    if permit.organization_id != DEMO_ORG_ID or url != request_url(permit):
        raise ValueError("Geocode evidence does not belong to the requested demo permit")
    match = validated_match(permit, response)
    if match is None:
        return False
    response_hash = hashlib.sha256(json.dumps(response, sort_keys=True).encode()).hexdigest()
    row = db.query(PermitGeocode).filter_by(organization_id=DEMO_ORG_ID, permit_id=permit.id).first()
    if row is None:
        row = PermitGeocode(organization_id=DEMO_ORG_ID, permit_id=permit.id)
        db.add(row)
    row.address_hash = address_hash(permit)
    row.latitude = match["latitude"]
    row.longitude = match["longitude"]
    row.matched_address = match["matched_address"]
    row.benchmark = BENCHMARK
    row.source_url = url
    row.response_hash = response_hash
    row.observed_at = datetime.now(timezone.utc)
    return True
