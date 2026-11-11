"""Build fixed-scope parcel configurations; optionally verify via public GETs only."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from urllib.parse import urlparse

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.ingestion.catalog import load_catalog  # noqa: E402
from app.services.ingestion.connectors.arcgis import ArcGISFeatureServerConnector  # noqa: E402
from app.services.ingestion.connectors.base import RetryingHttpClient  # noqa: E402
from app.services.ingestion.normalization import (  # noqa: E402
    normalize_parcel,
    prepare_mapped_record,
)

FIELDS = {
    "new_jersey_njgin_statewide_parcels_nearby_narrow": (
        "OBJECTID,PIN_NODUP,PAMS_PIN,PROP_LOC,MUN_NAME,CALC_ACRE", True,
    ),
    "collin_county_tx_parcels_nearby_narrow": (
        "OBJECTID,PROP_ID,propID,geoID,gisPropID,situsConcat,situsConcatShort,"
        "situsCity,situsZip,landSizeSqft", True,
    ),
    "miami_dade_fl_property_appraiser_parcels": (
        "OBJECTID,FOLIO,PARENT_FOLIO,TRUE_SITE_ADDR,TRUE_SITE_CITY,TRUE_SITE_ZIP_CODE,LOT_SIZE",
        True,
    ),
    "orange_county_fl_property_appraiser_parcels": (
        "OBJECTID,PARCEL,PARENT_ID,SITUS,SITUS_CITY,CITY_SITUS,SITUS_ZIP,ZIP_SITUS,"
        "LATITUDE,LONGITUDE,SHAPE.STArea()", False,
    ),
}
CANONICAL = frozenset({
    "source_record_id", "parcel_group_id", "address", "city", "postal_code",
    "latitude", "longitude", "land_area_sq_ft",
})
MAX_RECORDS = 2000
PAGE_SIZE = 250


def scoped_entry(key, *, anchor_id, latitude, longitude, radius_miles):
    if key not in FIELDS:
        raise ValueError("Source is not in the reviewed parcel allowlist")
    if not isinstance(anchor_id, str) or not anchor_id.strip():
        raise ValueError("A nonempty anchor identity is required")
    numbers = []
    for value, lower, upper in ((latitude, -90, 90), (longitude, -180, 180),
                                (radius_miles, 0.25, 3)):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Scope values must be finite numbers")
        value = float(value)
        if not math.isfinite(value) or not lower <= value <= upper:
            raise ValueError("Scope values are outside the permitted bounds")
        numbers.append(value if value else 0.0)
    latitude, longitude, radius_miles = numbers
    scope = dict(source_key=key, anchor_id=anchor_id.strip(), latitude=latitude,
                 longitude=longitude, radius_miles=radius_miles)
    digest = hashlib.sha256(json.dumps(scope, sort_keys=True, separators=(",", ":"))
                            .encode()).hexdigest()
    entry = next(row for row in load_catalog() if row.key == key).model_copy(deep=True)
    if not entry.is_active:
        raise ValueError("Reviewed parcel source must remain active in the catalog")
    rights_basis = entry.settings.get("rights_basis")
    if not isinstance(rights_basis, str) or not rights_basis.strip():
        raise ValueError("Reviewed parcel source requires nonempty rights evidence")
    entry.key = f"{key[:59]}_scope_{digest[:32]}"
    entry.is_active = False
    entry.field_mappings = [m for m in entry.field_mappings
                            if m.is_active and m.canonical_field in CANONICAL]
    out_fields, geometry = FIELDS[key]
    original = entry.settings.get("connector", {})
    entry.settings.update({
        "scope": scope, "scope_sha256": digest, "parent_source_key": key,
        "reconciliation_mode": "incremental", "schedule_mode": "manual",
        "publisher_freshness": "unknown",
        "field_allowlist": out_fields.split(",") + (["geometry"] if geometry else []),
        "canary_required_fields": [m.source_field for m in entry.field_mappings
                                    if m.is_required] + (["geometry"] if geometry else
                                                        ["LATITUDE", "LONGITUDE"]),
        "connector": {
            "page_size": PAGE_SIZE, "where": original["where"],
            "keyset_field": "OBJECTID", "order_by_fields": "OBJECTID ASC",
            "out_fields": out_fields, "include_geometry": geometry,
            "query": {
                "geometry": json.dumps({"x": longitude, "y": latitude,
                                        "spatialReference": {"wkid": 4326}}),
                "geometryType": "esriGeometryPoint", "inSR": 4326, "outSR": 4326,
                "spatialRel": "esriSpatialRelIntersects", "distance": radius_miles,
                "units": "esriSRUnit_StatuteMile",
            },
        },
    })
    return entry


class _BoundedClient:
    def __init__(self, host):
        self.client = RetryingHttpClient(allowed_hosts=frozenset({host}), max_retries=0, timeout=30)

    def get_json(self, url, *, params=None, headers=None):
        body, _ = self.client.get_bytes(url, params=params, headers=headers,
                                        max_bytes=8 * 1024 * 1024)
        return json.loads(body)


def verify_scope(key, *, anchor_id, latitude, longitude, radius_miles,
                 max_records=MAX_RECORDS, http_client=None):
    """Count/reconcile a bounded spatial canary without database or file writes."""
    if type(max_records) is not int or not 1 <= max_records <= MAX_RECORDS:
        raise ValueError("Record budget must be between 1 and 2000")
    entry = scoped_entry(key, anchor_id=anchor_id, latitude=latitude,
                         longitude=longitude, radius_miles=radius_miles)
    config = entry.settings["connector"]
    client = http_client or _BoundedClient(urlparse(entry.base_url).hostname)

    def count():
        payload = client.get_json(entry.base_url, params={
            **config["query"], "where": config["where"], "f": "json",
            "returnCountOnly": "true", "returnGeometry": "false",
        })
        if (not isinstance(payload, dict) or "error" in payload
                or type(payload.get("count")) is not int or payload["count"] < 0):
            raise ValueError("Invalid provider count response")
        return payload["count"]

    before = count()
    if not 1 <= before <= max_records:
        raise ValueError("Scoped provider count is empty or exceeds record budget")
    connector = ArcGISFeatureServerConnector(entry.base_url, http_client=client, **config)
    checkpoint = None
    seen = 0
    identities = set()
    cursors = set()
    allowed = set(entry.settings["field_allowlist"])
    for _ in range(math.ceil(max_records / PAGE_SIZE) + 1):
        connector.page_size = min(PAGE_SIZE, max_records - seen) if seen < max_records else 1
        page = connector.fetch(checkpoint)
        if len(page.records) > connector.page_size or seen + len(page.records) > max_records:
            raise ValueError("Provider exceeded the bounded record budget")
        for record in page.records:
            if set(record) - allowed:
                raise ValueError("Provider returned fields outside the privacy allowlist")
            if any(isinstance(value, (dict, list, tuple))
                   for field, value in record.items() if field != "geometry"):
                raise ValueError("Unexpected nested attribute payload")
            geometry = record.get("geometry")
            if geometry is not None and (
                not isinstance(geometry, dict)
                or set(geometry) - {"x", "y", "rings", "spatialReference"}
            ):
                raise ValueError("Unexpected geometry payload")
            if config["include_geometry"]:
                reference = (geometry or {}).get("spatialReference") or page.metadata.get("spatial_reference")
                if not isinstance(reference, dict) or reference.get("latestWkid", reference.get("wkid")) != 4326:
                    raise ValueError("Geometry must explicitly use WGS84")
                if set(reference) - {"wkid", "latestWkid"}:
                    raise ValueError("Unexpected spatial reference payload")
            cursor = record.get("OBJECTID")
            if type(cursor) is not int or cursor in cursors or (cursors and cursor <= max(cursors)):
                raise ValueError("Provider keyset identity is invalid or repeated")
            cursors.add(cursor)
            prepared, mappings = prepare_mapped_record(record, entry.field_mappings)
            normalized = normalize_parcel(prepared, mappings, defaults=entry.settings["defaults"])
            if normalized.values.get("latitude") is None or normalized.values.get("longitude") is None:
                raise ValueError("Parcel is missing required coordinates")
            identities.add(normalized.source_record_id)
            seen += 1
        if not page.has_more:
            break
        if page.checkpoint is None or page.checkpoint == checkpoint:
            raise ValueError("Provider did not advance its checkpoint")
        checkpoint = page.checkpoint
    else:
        raise ValueError("Provider did not exhaust within the page budget")
    after = count()
    if before != seen or seen != after:
        raise ValueError("Provider counts did not reconcile")
    return {"scope_key": entry.key, "source_key": key, "scope_sha256": entry.settings["scope_sha256"],
            "provider_before": before, "records_valid": seen, "provider_after": after,
            "distinct_parcels": len(identities), "duplicate_parcel_rows": seen - len(identities),
            "publisher_freshness": "unknown", "read_only": True,
            "production_anchor_verified": False, "production_qualified": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-key", choices=sorted(FIELDS), required=True)
    parser.add_argument("--anchor-id", required=True)
    parser.add_argument("--latitude", type=float, required=True)
    parser.add_argument("--longitude", type=float, required=True)
    parser.add_argument("--radius-miles", type=float, required=True)
    parser.add_argument("--max-records", type=int, default=MAX_RECORDS)
    parser.add_argument("--verify", action="store_true", help="Perform bounded public GETs only")
    args = vars(parser.parse_args(argv))
    key = args.pop("source_key")
    live = args.pop("verify")
    budget = args.pop("max_records")
    try:
        if type(budget) is not int or not 1 <= budget <= MAX_RECORDS:
            raise ValueError("Invalid record budget")
        result = (verify_scope(key, **args, max_records=budget) if live
                  else scoped_entry(key, **args).model_dump(mode="json"))
    except Exception:
        print(json.dumps({"ok": False, "error": "Parcel scope validation or verification failed"}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
