from __future__ import annotations

from typing import Any


def _normalize_ring(ring: Any) -> list[list[float]] | None:
    if not isinstance(ring, list) or len(ring) < 4:
        return None
    coordinates: list[list[float]] = []
    for pair in ring:
        if not isinstance(pair, (list, tuple)) or len(pair) < 2:
            return None
        try:
            coordinates.append([float(pair[0]), float(pair[1])])
        except (TypeError, ValueError):
            return None
    return coordinates


def _arcgis_rings_to_geojson_polygon(geometry: dict[str, Any]) -> dict[str, Any] | None:
    rings = geometry.get("rings")
    if not isinstance(rings, list) or not rings:
        return None
    normalized_rings: list[list[list[float]]] = []
    for ring in rings:
        normalized = _normalize_ring(ring)
        if normalized is not None:
            normalized_rings.append(normalized)
    if not normalized_rings:
        return None
    return {"type": "Polygon", "coordinates": normalized_rings}


def _geojson_polygon(geometry: dict[str, Any]) -> dict[str, Any] | None:
    geom_type = str(geometry.get("type") or "").lower()
    coordinates = geometry.get("coordinates")
    if geom_type == "polygon" and isinstance(coordinates, list):
        normalized_rings: list[list[list[float]]] = []
        for ring in coordinates:
            normalized = _normalize_ring(ring)
            if normalized is not None:
                normalized_rings.append(normalized)
        if not normalized_rings:
            return None
        return {"type": "Polygon", "coordinates": normalized_rings}
    if geom_type == "multipolygon" and isinstance(coordinates, list):
        first_polygon = coordinates[0]
        if not isinstance(first_polygon, list):
            return None
        normalized_rings: list[list[list[float]]] = []
        for ring in first_polygon:
            normalized = _normalize_ring(ring)
            if normalized is not None:
                normalized_rings.append(normalized)
        if not normalized_rings:
            return None
        return {"type": "Polygon", "coordinates": normalized_rings}
    return None


def resolve_parcel_boundary_geometry(attributes: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return a GeoJSON polygon for map display when ingestion retained boundary geometry."""
    if not isinstance(attributes, dict):
        return None

    geometry = attributes.get("geometry") or attributes.get("_geometry")
    if not isinstance(geometry, dict):
        return None

    if "rings" in geometry:
        return _arcgis_rings_to_geojson_polygon(geometry)

    if "x" in geometry and "y" in geometry:
        return None

    if str(geometry.get("type") or "").lower() == "feature":
        nested = geometry.get("geometry")
        if isinstance(nested, dict):
            return resolve_parcel_boundary_geometry({"geometry": nested})

    geojson = _geojson_polygon(geometry)
    if geojson is not None:
        return geojson

    nested = geometry.get("geometry")
    if isinstance(nested, dict):
        return resolve_parcel_boundary_geometry({"geometry": nested})

    return None
