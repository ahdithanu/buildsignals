from __future__ import annotations

from app.services.parcel_geometry import (
    export_policy_allows_boundary_display,
    resolve_display_boundary_geometry,
    resolve_parcel_boundary_geometry,
)


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


def test_export_policy_allows_nearby_parcel_context():
    assert export_policy_allows_boundary_display(
        "derived_nearby_parcel_context_only_no_raw_delaware_firstmap_resale"
    )
    assert export_policy_allows_boundary_display(
        "derived_parcel_context_no_raw_polygon_source_replacement_export"
    )


def test_export_policy_blocks_centroid_only_sources():
    assert not export_policy_allows_boundary_display(
        "derived_geometry_situs_only_no_raw_source_export"
    )
    assert not export_policy_allows_boundary_display(
        "derived_geometry_parcel_id_only_no_raw_pva_source_export"
    )
    assert not export_policy_allows_boundary_display(None)


def test_resolve_display_boundary_geometry_respects_export_policy():
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

    allowed = resolve_display_boundary_geometry(
        attributes,
        "derived_nearby_parcel_context_only_no_raw_test_resale",
    )
    blocked = resolve_display_boundary_geometry(
        attributes,
        "derived_geometry_situs_only_no_raw_source_export",
    )

    assert allowed is not None
    assert blocked is None
