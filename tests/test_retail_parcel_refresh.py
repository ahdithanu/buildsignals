import pytest

from scripts import retail_parcel_refresh as worker


@pytest.mark.parametrize("key", ["collin_county_tx_parcels_nearby_narrow", "miami_dade_fl_property_appraiser_parcels", "orange_county_fl_property_appraiser_parcels"])
def test_bounded_parcel_source_is_incremental_and_private_fields_are_not_requested(key):
    entry = worker.scoped_entry(key, anchor_id="anchor-1", latitude=25.8, longitude=-80.2, radius_miles=1)
    assert entry.record_type == "parcel"
    assert entry.settings["reconciliation_mode"] == "incremental"
    assert entry.settings["schedule_mode"] == "manual"
    config = entry.settings["connector"]
    assert config["query"]["distance"] == 1
    assert config["query"]["units"] == "esriSRUnit_StatuteMile"
    assert config["query"]["inSR"] == 4326
    assert "*" not in config["out_fields"]
    assert all(not m.canonical_field.startswith(("owner", "last_sale")) for m in entry.field_mappings)
    assert "mapID" not in config["out_fields"]
    assert entry.settings["rights_basis"]


@pytest.mark.parametrize("kwargs", [{"radius_miles": 0}, {"radius_miles": 4}, {"latitude": float("nan")}, {"longitude": 181}])
def test_invalid_scopes_fail_before_requests(kwargs):
    args = dict(anchor_id="anchor-1", latitude=25.8, longitude=-80.2, radius_miles=1)
    args.update(kwargs)
    with pytest.raises(ValueError):
        worker.scoped_entry("miami_dade_fl_property_appraiser_parcels", **args)


def test_held_source_is_not_accepted():
    with pytest.raises(ValueError):
        worker.scoped_entry("maricopa_az_parcels", anchor_id="x", latitude=33.4, longitude=-111.9, radius_miles=1)


def test_njgin_nearby_profile_keeps_native_identity_and_remains_inactive():
    key = "new_jersey_njgin_statewide_parcels_nearby_narrow"
    entry = worker.scoped_entry(key, anchor_id="verified-signal-required",
                               latitude=39.74, longitude=-75.31, radius_miles=1)
    assert entry.is_active is False
    assert entry.settings["parent_source_key"] == key
    assert entry.settings["publisher_freshness"] == "unknown"
    assert entry.settings["connector"]["include_geometry"] is True
    fields = set(entry.settings["connector"]["out_fields"].split(","))
    assert fields == {"OBJECTID", "PIN_NODUP", "PAMS_PIN", "PROP_LOC",
                      "MUN_NAME", "CALC_ACRE"}
    assert entry.settings["enforce_field_allowlist"] is True
    identity = next(m for m in entry.field_mappings if m.canonical_field == "source_record_id")
    assert identity.source_field == "PIN_NODUP" and identity.is_required
    assert not any(m.canonical_field in {"owner_name", "zoning_code", "last_sale_price"}
                   for m in entry.field_mappings)
    assert entry.settings["export_policy"] == "derived_nearby_parcel_context_only_no_raw_polygon_or_source_replacement_export"


def test_each_fixed_scope_has_stable_distinct_identity():
    args = dict(anchor_id="anchor-1", latitude=25.8, longitude=-80.2, radius_miles=1)
    first = worker.scoped_entry("miami_dade_fl_property_appraiser_parcels", **args)
    assert first.key == worker.scoped_entry("miami_dade_fl_property_appraiser_parcels", **args).key
    assert first.key != worker.scoped_entry("miami_dade_fl_property_appraiser_parcels", **{**args, "radius_miles": 2}).key
    assert first.key != worker.scoped_entry("miami_dade_fl_property_appraiser_parcels", **{**args, "latitude": 25.9}).key


def test_quarter_mile_scope_is_inactive_distinct_and_keeps_upper_bounds():
    key = "new_jersey_njgin_statewide_parcels_nearby_narrow"
    args = dict(anchor_id="historical-reference-not-live-approval", latitude=39.92, longitude=-75.03)
    entry = worker.scoped_entry(key, **args, radius_miles=0.25)
    assert not entry.is_active
    assert entry.settings["connector"]["query"]["distance"] == 0.25
    assert entry.key != worker.scoped_entry(key, **args, radius_miles=1).key
    assert worker.MAX_RECORDS == 2000
    for invalid in (0.249, 3.001):
        with pytest.raises(ValueError):
            worker.scoped_entry(key, **args, radius_miles=invalid)
