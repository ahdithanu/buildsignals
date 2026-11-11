"""Opt-in NJGIN municipal qualification; aggregate output, no database or activation."""
from __future__ import annotations

import argparse
import json
import math
import socket
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError

from app.schemas.ingestion import FieldMappingCreate
from app.services.ingestion.connectors.arcgis import ArcGISConnector
from app.services.ingestion.connectors.base import RetryingHttpClient
from app.services.ingestion.normalization import normalize_parcel, prepare_mapped_record

LAYER = "https://maps.nj.gov/arcgis/rest/services/Framework/Cadastral/MapServer/0"
CATALOG_KEY = "new_jersey_njgin_statewide_parcels_nearby_narrow"
MARKETS = {"0817": "Swedesboro Borough", "0802": "Deptford Township",
           "0409": "Cherry Hill Township"}
REQUIRED_TYPES = {"OBJECTID": "esriFieldTypeOID", "PIN_NODUP": "esriFieldTypeString",
                  "PCL_MUN": "esriFieldTypeString"}
OPTIONAL_FIELDS = ("PAMS_PIN", "PCL_GUID", "PCLLASTUPD", "PCL_PBDATE")
DATE_FIELDS = ("PCL_PBDATE", "PCLLASTUPD")
METADATA_FLAGS = ("supportsQueryWithDistance", "supportsQueryWithHistoricMoment",
                  "supportsReturningGeometryCentroid")
MAX_BYTES = 1_000_000
MAX_ROWS = 3
MAX_REQUESTS = 7
CENTROID_MAPPINGS = tuple(
    FieldMappingCreate(source_field="geometry", canonical_field=field,
                       transform="arcgis_polygon_centroid", transform_options={"axis": axis})
    for field, axis in (("longitude", "x"), ("latitude", "y"))
)


class _Failure(ValueError):
    """A local, fixed diagnostic code, never publisher content."""


class _BoundedClient:
    def __init__(self, client):
        self.client = client
        self.requests = 0

    def get_json(self, url, *, params=None, headers=None):
        if url not in {LAYER, LAYER + "/query"}:
            raise _Failure("endpoint_scope")
        if self.requests >= MAX_REQUESTS:
            raise _Failure("request_budget")
        params = dict(params or {})
        if params.get("returnCentroid") == "true":
            # The shared connector otherwise turns polygon return on for centroids.
            params["returnGeometry"] = "false"
        self.requests += 1
        body, _ = self.client.get_bytes(url, params=params, headers=headers, max_bytes=MAX_BYTES)
        if len(body) > MAX_BYTES:
            raise _Failure("response_byte_budget")
        try:
            payload = json.loads(body)
        except (ValueError, UnicodeError):
            raise _Failure("invalid_json") from None
        if not isinstance(payload, dict):
            raise _Failure("invalid_response")
        if "error" in payload:
            raise _Failure("arcgis_error")
        if "outFields" in params:
            features = payload.get("features")
            if not isinstance(features, list) or len(features) > MAX_ROWS:
                raise _Failure("sample_record_scope")
            geometry_field = "centroid" if params.get("returnCentroid") == "true" else "geometry"
            for feature in features:
                if not isinstance(feature, dict) or set(feature) - {"attributes", geometry_field}:
                    raise _Failure("sample_geometry_scope")
                attributes = feature.get("attributes")
                if (not isinstance(attributes, dict)
                        or set(attributes) - set(params["outFields"].split(","))):
                    raise _Failure("sample_field_scope")
        return payload


def _municipalities(values):
    if (not isinstance(values, (tuple, list)) or not 1 <= len(values) <= 3
            or any(not isinstance(code, str) or code not in MARKETS for code in values)
            or len(set(values)) != len(values)):
        raise ValueError("Select distinct requested municipality codes only")
    return tuple(values)


def _metadata_flags(meta):
    capabilities = meta.get("advancedQueryCapabilities")
    if not isinstance(capabilities, dict):
        capabilities = {}
    return {name: capabilities.get(name) if type(capabilities.get(name)) is bool else None
            for name in METADATA_FLAGS}


def _schema(meta):
    raw_fields = meta.get("fields")
    if (not isinstance(raw_fields, list)
            or any(not isinstance(field, dict) or not isinstance(field.get("name"), str)
                   for field in raw_fields)):
        raise _Failure("invalid_metadata")
    fields = {field["name"]: field for field in raw_fields}
    capabilities = meta.get("advancedQueryCapabilities") or {}
    if not isinstance(capabilities, dict):
        raise _Failure("invalid_metadata")
    missing = sorted(set(REQUIRED_TYPES) - set(fields))
    mismatched = sorted(name for name, kind in REQUIRED_TYPES.items()
                        if name in fields and fields[name].get("type") != kind)
    valid = (not missing and not mismatched
             and fields["PCL_MUN"].get("length") == 4
             and meta.get("geometryType") == "esriGeometryPolygon")
    return {
        "required_fields_missing": missing,
        "required_field_type_mismatches": mismatched,
        "municipality_field": "PCL_MUN",
        "municipality_string_length_verified": fields.get("PCL_MUN", {}).get("length") == 4,
        "missing_optional_fields": sorted(set(OPTIONAL_FIELDS) - set(fields)),
        "legacy_optional_fields_missing": [] if "PCL_GUID" in fields else ["PCL_GUID"],
        "required_schema_valid": valid,
        "supports_centroid": capabilities.get("supportsReturningGeometryCentroid") is True,
        "supports_order_by": capabilities.get("supportsOrderBy") is True,
    }, tuple(field for field in DATE_FIELDS
             if fields.get(field, {}).get("type") == "esriFieldTypeDate")


def _date(value):
    if type(value) not in {int, float} or not math.isfinite(value) or value <= 0:
        return None
    try:
        return datetime.fromtimestamp(value / 1000, timezone.utc).date().isoformat()
    except (ValueError, OverflowError, OSError):
        return None


def _local_centroid(geometry, spatial_reference):
    if (not isinstance(geometry, dict)
            or set(geometry) - {"rings", "spatialReference"}):
        raise _Failure("invalid_polygon")
    sr = geometry.get("spatialReference", spatial_reference)
    rings = geometry.get("rings")
    if not isinstance(sr, dict) or sr.get("wkid") != 4326 or not isinstance(rings, list) or not rings:
        raise _Failure("invalid_polygon")
    for ring in rings:
        if not isinstance(ring, list) or len(ring) < 3:
            raise _Failure("invalid_polygon")
        for point in ring:
            if (not isinstance(point, list) or len(point) != 2
                    or any(type(value) not in {int, float} or not math.isfinite(value)
                           for value in point)
                    or not -180 <= point[0] <= 180 or not -90 <= point[1] <= 90):
                raise _Failure("invalid_polygon")
        if len({tuple(point) for point in ring}) < 3:
            raise _Failure("invalid_polygon")
        pairs = list(zip(ring, ring[1:] + ring[:1]))
        origin_x, origin_y = ring[0]
        twice_area = math.fsum(
            (a[0] - origin_x) * (b[1] - origin_y)
            - (b[0] - origin_x) * (a[1] - origin_y) for a, b in pairs)
        shared_twice_area = sum(a[0] * b[1] - b[0] * a[1] for a, b in pairs)
        # Match the shared transform's floor so its degenerate averaging cannot pass.
        if abs(twice_area) <= 1e-12 or abs(shared_twice_area) <= 1e-12:
            raise _Failure("invalid_polygon")
    prepared, mapping = prepare_mapped_record({"geometry": geometry}, CENTROID_MAPPINGS)
    coordinates = {canonical: prepared[field] for field, canonical in mapping.items()}
    return {"x": coordinates["longitude"], "y": coordinates["latitude"],
            "spatialReference": {"wkid": 4326}}


def _sample(rows, *, code, count, spatial_reference, date_fields, geometry_mode):
    if len(rows) != min(count, MAX_ROWS):
        raise _Failure("sample_record_scope")
    ids = set()
    for row in rows:
        pin = row.get("PIN_NODUP")
        if not isinstance(pin, str) or not pin.strip() or pin.strip() == "XXXNLL":
            raise _Failure("invalid_identity")
        if row.get("PCL_MUN") != code:
            raise _Failure("municipality_mismatch")
        if type(row.get("OBJECTID")) is not int:
            raise _Failure("invalid_transport_id")
        centroid = (_local_centroid(row.get("geometry"), spatial_reference)
                    if geometry_mode == "local_polygon_centroid" else row.get("centroid"))
        if not isinstance(centroid, dict) or set(centroid) - {"x", "y", "spatialReference"}:
            raise _Failure("invalid_centroid")
        sr = centroid.get("spatialReference", spatial_reference)
        x, y = centroid.get("x"), centroid.get("y")
        if (not isinstance(sr, dict) or sr.get("wkid") != 4326
                or type(x) not in {int, float} or type(y) not in {int, float}
                or not math.isfinite(x) or not math.isfinite(y)
                or not -180 <= x <= 180 or not -90 <= y <= 90):
            raise _Failure("invalid_centroid")
        normalized = normalize_parcel(
            {"PIN_NODUP": pin, "x": x, "y": y},
            {"PIN_NODUP": "source_record_id", "x": "longitude", "y": "latitude"},
        )
        ids.add(normalized.source_record_id)
    if len(ids) != len(rows):
        raise _Failure("duplicate_identity")
    dates = {}
    for field in date_fields:
        values = [value for row in rows if (value := _date(row.get(field))) is not None]
        dates[field] = {"valid": len(values), "min": min(values) if values else None,
                        "max": max(values) if values else None}
    return {"sample_rows": len(rows), "sample_unique_ids": len(ids),
            "sample_valid_wgs84_centroids": len(rows), "sample_dates": dates,
            "sample_is_freshness_census": False}


def _failure_reason(error):
    if isinstance(error, _Failure):
        return str(error)
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        if isinstance(error, socket.gaierror):
            return "dns_resolution_failed"
        if isinstance(error, HTTPError):
            return "http_" + str(error.code) if type(error.code) is int else "http_error"
        if isinstance(error, TimeoutError):
            return "request_timeout"
        error = error.reason if isinstance(error, URLError) else error.__cause__
        if not isinstance(error, BaseException):
            break
    return "transport_or_response_error"


def qualify(*, live=False, municipalities=tuple(MARKETS), http_client=None):
    codes = _municipalities(municipalities)
    report = {"qualification_only": True, "is_active": False,
              "catalog_key": CATALOG_KEY, "identity_field": "PIN_NODUP",
              "rights_scope": "existing_narrow_derived_nearby_context_only",
              "network_requests": 0, "technical_qualification_passed": False,
              "network_requests_unit": "logical_get_bytes_operations",
              "max_logical_operations": MAX_REQUESTS, "wire_request_count": None,
              "http_client_injected": http_client is not None,
              "default_transport_settings": {
                  "max_retries": 0, "timeout_seconds": 20,
                  "max_same_host_redirect_responses": 6, "per_ip_failover": True,
              },
              "metadata_observed": False,
              "metadata_flags": dict.fromkeys(METADATA_FLAGS),
              "catalog_contract_verified": False, "blockers": [],
              "markets": {code: {"municipality": MARKETS[code]} for code in codes}}
    if not live:
        return report
    client = _BoundedClient(http_client if http_client is not None else RetryingHttpClient(
        timeout=20, max_retries=0, allowed_hosts=frozenset({"maps.nj.gov"})))
    phase = "metadata"
    try:
        meta = client.get_json(LAYER, params={"f": "json"})
        report["metadata_observed"] = True
        report["metadata_flags"] = _metadata_flags(meta)
        schema, date_fields = _schema(meta)
        report["schema"] = schema
        if not schema["required_schema_valid"]:
            raise _Failure("schema_mismatch")
        geometry_mode = "server_centroid" if schema["supports_centroid"] else "local_polygon_centroid"
        report["geometry_mode"] = geometry_mode
        report["centroid_method"] = ("server_centroid" if schema["supports_centroid"] else
                                     "existing_arcgis_polygon_centroid_first_ring")
        sample_blocker = "ordering_not_supported" if not schema["supports_order_by"] else None
        if sample_blocker:
            report["blockers"].append(sample_blocker)
        for code in codes:
            result = report["markets"][code]
            where = f"PCL_MUN = '{code}' AND PIN_NODUP IS NOT NULL AND PIN_NODUP <> 'XXXNLL'"
            phase = f"{code}_count"
            count = client.get_json(LAYER + "/query", params={
                "f": "json", "where": where, "returnCountOnly": "true",
                "returnGeometry": "false",
            }).get("count")
            if type(count) is not int or count < 0:
                raise _Failure("invalid_count")
            result["provider_count"] = count
            if count == 0 or sample_blocker:
                result["sample_skipped"] = "empty_scope" if count == 0 else sample_blocker
                if count == 0:
                    report["blockers"].append(f"{code}_empty_scope")
                continue
            phase = f"{code}_sample"
            page = ArcGISConnector(
                LAYER, page_size=MAX_ROWS, where=where,
                out_fields=",".join((*REQUIRED_TYPES, *date_fields)),
                order_by_fields="OBJECTID ASC", include_geometry=not schema["supports_centroid"],
                include_centroid=schema["supports_centroid"], query={"outSR": 4326}, http_client=client,
            ).fetch()
            result.update(_sample(page.records, code=code, count=count,
                                  spatial_reference=page.metadata.get("spatial_reference"),
                                  date_fields=date_fields, geometry_mode=geometry_mode))
        report["technical_qualification_passed"] = not report["blockers"]
    except Exception as error:
        report.update(failed=True, failure_reason=_failure_reason(error), failure_phase=phase)
    report["network_requests"] = client.requests
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--municipality", action="append", choices=tuple(MARKETS))
    args = parser.parse_args(argv)
    try:
        report = qualify(live=args.live, municipalities=args.municipality or tuple(MARKETS))
    except ValueError:
        parser.error("Select distinct requested municipality codes only")
    print(json.dumps(report, sort_keys=True))
    return int(bool(report.get("failed") or report["blockers"]))


if __name__ == "__main__":
    raise SystemExit(main())
