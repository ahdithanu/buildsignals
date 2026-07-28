from __future__ import annotations

from app.services.parcel_geometry import resolve_parcel_boundary_geometry


def test_resolve_parcel_boundary_geometry_from_arcgis_rings():
    attributes = {
        "geometry": {
            "rings": [[
                [-97.7441, 30.2662],
                [-97.7421, 30.2662],
                [-97.7421, 30.2682],
                [-97.7441, 30.2682],
                [-97.7441, 30.2662],
            ]],
        },
    }

    geometry = resolve_parcel_boundary_geometry(attributes)

    assert geometry == {
        "type": "Polygon",
        "coordinates": [[
            [-97.7441, 30.2662],
            [-97.7421, 30.2662],
            [-97.7421, 30.2682],
            [-97.7441, 30.2682],
            [-97.7441, 30.2662],
        ]],
    }


def test_resolve_parcel_boundary_geometry_ignores_point_geometry():
    attributes = {"geometry": {"x": -97.7431, "y": 30.2672}}

    assert resolve_parcel_boundary_geometry(attributes) is None


def test_resolve_parcel_boundary_geometry_from_geojson_polygon():
    attributes = {
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [-97.7441, 30.2662],
                [-97.7421, 30.2662],
                [-97.7421, 30.2682],
                [-97.7441, 30.2682],
                [-97.7441, 30.2662],
            ]],
        },
    }

    geometry = resolve_parcel_boundary_geometry(attributes)

    assert geometry == attributes["geometry"]
