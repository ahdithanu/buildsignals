from __future__ import annotations

import json
import re
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models.ingestion import IngestionSource, SourceFieldMapping
from app.schemas.ingestion import FieldMappingCreate, IngestionSourceCreate
from app.schemas.ingestion_candidate import IngestionSourceCandidate
from app.services.ingestion.catalog import (
    catalog_source_for_candidate,
    load_candidate_catalog,
    load_catalog,
    summarize_coverage,
    sync_catalog,
)
from app.services.ingestion.health import validate_candidate_source_canary
from app.services.ingestion.normalization import (
    missing_required_source_fields,
    normalize_parcel,
    normalize_permit,
    normalize_planning_record,
    prepare_mapped_record,
)
from app.services.ingestion.service import _normalization_hash, execute_source_run


def test_production_permit_sources_declare_freshness_contracts():
    entries = [entry for entry in load_catalog() if entry.record_type == "permit"]

    assert entries
    assert all(entry.settings["freshness_sla_hours"] > 0 for entry in entries)
    assert all(
        entry.settings["collection_sla_hours"]
        >= entry.settings["collection_interval_minutes"] / 60
        for entry in entries
    )
    for entry in entries:
        freshness_field = entry.settings.get("freshness_field")
        if freshness_field:
            assert entry.settings["freshness_semantics"] in {
                "record_updated_at",
                "dataset_refreshed_at",
                "filing_event_at",
            }
    by_key = {entry.key: entry for entry in entries}
    assert by_key["buffalo_ny_planning_zoning_approvals"].settings[
        "freshness_semantics"
    ] == "filing_event_at"


def test_applicant_mappings_declare_conservative_value_semantics():
    applicant_mappings = {
        (entry.key, mapping.source_field): mapping.value_semantics
        for entry in load_catalog()
        for mapping in entry.field_mappings
        if mapping.canonical_field == "applicant_name"
    }

    assert len(applicant_mappings) == 26
    assert set(applicant_mappings.values()) <= {
        "unknown", "business_dba", "legal_entity", "person"
    }
    assert applicant_mappings[
        ("new_york_ny_legacy_job_applications", "applicant_s_last_name")
    ] == "person"
    assert applicant_mappings[
        ("texas_comptroller_sales_tax_locations", "__applicant_name")
    ] == "legal_entity"
    assert applicant_mappings[
        ("washington_dc_basic_business_licenses_retail_openings", "ENTITYNAME")
    ] == "legal_entity"
    assert applicant_mappings[
        ("new_york_state_sla_pending_licenses", "legalname")
    ] == "legal_entity"
    assert applicant_mappings[
        ("new_york_ny_dob_now_job_applications", "applicant_business_name")
    ] == "unknown"
    assert applicant_mappings[
        ("san_marcos_tx_planning_application_notices", "__applicant_name")
    ] == "unknown"
    assert applicant_mappings[
        ("columbus_oh_site_engineering_applications", "APPLICANT_BUS_NAME")
    ] == "legal_entity"
    assert applicant_mappings[
        ("columbus_oh_commercial_building_permits", "APPLICANT_BUS_NAME")
    ] == "legal_entity"


def test_field_semantic_change_invalidates_normalization_hash():
    mapping = SimpleNamespace(
        source_field="applicant",
        canonical_field="applicant_name",
        value_semantics="unknown",
        transform=None,
        transform_options=None,
        default_value=None,
        is_required=False,
        is_active=True,
    )
    source = SimpleNamespace(
        record_type="permit",
        jurisdiction="Austin, TX",
        settings={},
        field_mappings=[mapping],
    )

    before = _normalization_hash(source)
    mapping.value_semantics = "legal_entity"

    assert _normalization_hash(source) != before


def test_catalog_loads_first_live_source_cohort():
    entries = load_catalog()

    assert {entry.key for entry in entries} == {
        "austin_tx_issued_construction_permits",
        "seattle_wa_issued_building_permits",
        "seattle_wa_land_use_permits",
        "seattle_wa_street_use_public_notices",
        "washington_ecology_sepa_register",
        "pierce_county_wa_pals_permits",
        "bellingham_wa_nonres_building_permits",
        "chicago_il_building_permits",
        "new_york_ny_dob_now_approved_permits",
        "austin_tx_plan_review_cases",
        "new_york_ny_dob_now_job_applications",
        "austin_tx_site_plan_cases",
        "new_york_ny_legacy_job_applications",
        "new_orleans_la_permits_blds",
        "east_baton_rouge_la_building_permits",
        "san_francisco_ca_building_permits_primary_address",
        "san_francisco_ca_planning_department_non_project_records",
        "marin_county_ca_commercial_building_permits",
        "san_jose_ca_planning_permit_applications",
        "boulder_co_construction_permits",
        "denver_co_commercial_construction_permits",
        "denver_co_residential_construction_permits",
        "denver_co_demolition_permits",
        "somerville_ma_building_permit_applications",
        "san_diego_ca_development_permit_approvals_2026",
        "cleveland_oh_building_permit_applications",
        "cincinnati_oh_building_permits",
        "portland_or_development_and_building_applications",
        "pittsburgh_pa_issued_building_permits",
        "milwaukee_wi_commercial_permit_work",
        "minneapolis_mn_commercial_construction_permits",
        "st_louis_mo_commercial_occupancy_applications",
        "louisville_jefferson_ky_active_construction_permits",
        "montgomery_county_md_commercial_permits",
        "maryland_imap_sdat_parcel_points",
        "henderson_nv_commercial_development_permits",
        "vermont_act250_large_development_context",
        "montgomery_al_commercial_construction_permits",
        "fayetteville_ar_permit_lifecycle_narrow",
        "fort_worth_tx_civic_commercial_permits",
        "texas_comptroller_sales_tax_locations",
        "charleston_sc_active_commercial_permits",
        "charleston_sc_trc_development_plans",
        "provo_ut_building_permit_applications",
        "provo_ut_planning_applications",
        "maine_dep_land_applications_and_permits",
        "bismarck_nd_development_activities",
        "lincoln_ne_development_applications",
        "delaware_dnrec_stormwater_noi",
        "delaware_firstmap_statewide_parcels_narrow",
        "delaware_dnrec_septic_permits_narrow",
        "virginia_vgin_statewide_parcels_narrow",
        "fairfax_county_va_development_tracker_site_records",
        "norfolk_va_permits_and_inspections_permit_records",
        "norfolk_va_conditional_use_permits",
        "virginia_beach_va_building_permit_applications",
        "lynchburg_va_development_projects_locations",
        "washington_dc_dob_building_permits_2026",
        "washington_dc_basic_business_licenses_retail_openings",
        "washington_dc_owner_parcels_nearby",
        "massachusetts_massgis_l3_property_tax_parcels",
        "cook_county_il_assessor_parcels_current_year_nearby",
        "sacramento_ca_commercial_building_permits_applied_current_year",
        "nashville_tn_planning_development_applications",
        "boston_ma_article_80_development_projects",
        "cary_nc_development_applications",
        "cary_nc_building_permit_applications",
        "raleigh_nc_development_plans",
        "charlotte_nc_rezoning_petitions",
        "new_hanover_nc_commercial_site_plans",
        "madison_wi_current_planning_projects",
        "orlando_fl_permit_applications",
        "mesa_az_commercial_permit_submittals",
        "tempe_az_building_permits_commercial_context",
        "florida_dep_erp_applications_commercial_context",
        "miami_dade_fl_wasd_unincorporated_permits_narrow",
        "greensboro_nc_building_permits_commercial",
        "wake_county_nc_building_permits_commercial",
        "buffalo_ny_planning_zoning_approvals",
        "new_york_ny_pluto_parcels",
        "san_diego_ca_sangis_parcel_spine",
        "louisville_jefferson_ky_lojic_parcels_narrow",
        "vermont_vcgi_statewide_parcels_narrow",
        "rhode_island_statewide_tax_parcels_narrow",
        "new_hampshire_dra_granit_parcel_mosaic_narrow",
        "montgomery_al_parcels_nearby_narrow",
        "arkansas_statewide_parcels_nearby_narrow",
        "collin_county_tx_parcels_nearby_narrow",
        "tennessee_comptroller_impact_parcels_nearby_narrow",
        "greenville_county_sc_parcels_narrow",
        "sedgwick_county_ks_parcels_nearby_narrow",
        "utah_county_ut_parcels_nearby_narrow",
        "sioux_falls_sd_parcels_nearby_narrow",
        "cass_county_nd_parcels_nearby_narrow",
        "maine_geolibrary_organized_towns_parcels_nearby_narrow",
        "indianapolis_marion_county_in_parcels",
        "hennepin_mn_county_parcels",
        "st_louis_mo_city_parcels",
        "allegheny_county_pa_parcels_nearby_narrow",
        "allegheny_county_pa_property_assessments",
        "denver_co_assessor_parcels",
        "colorado_statewide_public_parcels_nearby_narrow",
        "new_jersey_njgin_statewide_parcels_nearby_narrow",
        "florida_fdor_statewide_cadastral_parcels",
        "miami_dade_fl_property_appraiser_parcels",
        "orange_county_fl_property_appraiser_parcels",
        "hillsborough_county_fl_property_appraiser_parcels",
        "duval_county_fl_property_appraiser_parcels",
        "broward_county_fl_dor_parcel_centroids",
        "polk_county_fl_property_appraiser_parcels",
        "wake_county_nc_parcels",
        "los_angeles_ca_building_permits_submitted",
        "new_york_ny_dohmh_restaurant_permit_applicants",
        "hartford_ct_building_permits_lifecycle",
        "new_york_state_sla_pending_licenses",
        "detroit_mi_bseed_building_permits",
        "detroit_mi_bseed_building_plan_reviews",
        "washington_state_lcb_local_authority_letters",
            "everett_wa_planning_application_notices",
            "bend_or_planning_applications",
            "bend_or_permit_applications_point",
            "bend_or_permit_applications_line",
            "taylor_tx_development_notices",
            "san_marcos_tx_planning_application_notices",
            "savannah_ga_commercial_building_permits",
            "columbus_oh_site_engineering_applications",
            "columbus_oh_commercial_building_permits",
            "tacoma_wa_commercial_permit_lifecycle",
            "arlington_tx_commercial_permit_applications",
            "arlington_tx_commercial_issued_permits",
            "dallas_tx_legistar_planning_agendas",
        }
    for entry in entries:
        source_fields = [mapping.source_field for mapping in entry.field_mappings]
        assert len(source_fields) == len(set(source_fields))
        assert any(
            mapping.canonical_field == "source_record_id" and mapping.is_required
            for mapping in entry.field_mappings
        )
        assert entry.settings["signal_stage"] in {
            "pre_approval_and_approved",
            "pre_approval",
            "approved_only",
            "parcel_context",
        }


def test_allegheny_property_assessments_are_admitted_as_cc0_parcel_context():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "allegheny_county_pa_property_assessments"
    )

    assert entry.adapter == "csv"
    assert entry.record_type == "parcel"
    assert entry.base_url == "https://tools.wprdc.org/downstream/65855e14-549e-4992-b5be-d629afc676fa"
    assert entry.settings["official_landing_page"] == "https://data.wprdc.org/dataset/property-assessments"
    assert entry.settings["license"] == "Creative Commons CCZero"
    assert entry.settings["signal_stage"] == "parcel_context"
    assert entry.settings["reconciliation_mode"] == "monthly_full_snapshot"
    assert any(
        mapping.canonical_field == "source_record_id" and mapping.source_field == "PARID"
        for mapping in entry.field_mappings
    )
    assert any(
        mapping.canonical_field == "total_assessed_value" and mapping.source_field == "COUNTYTOTAL"
        for mapping in entry.field_mappings
    )
    assert any(
        mapping.canonical_field == "observed_at" and mapping.source_field == "ASOFDATE"
        for mapping in entry.field_mappings
    )


def test_candidate_catalog_tracks_retry_and_hold_sources_without_production_overlap():
    entries = load_candidate_catalog()

    assert {entry.key for entry in entries} == {
        "orlando_fl_planning_applications",
        "atlanta_ga_building_permit_tracker",
        "phoenix_az_plan_review_and_permits",
        "huntsville_al_issued_building_permits",
        "birmingham_al_digital_plan_room",
        "mobile_al_build_mobile_portal",
        "evansville_in_building_commission_permits",
        "anchorage_ak_bsd_permit_lookup",
        "juneau_ak_civic_access_permits",
        "honolulu_hi_building_permits_2005_2025",
        "boise_id_development_tracker",
        "cedar_rapids_ia_building_permits",
        "biloxi_ms_development_review_agendas",
        "bozeman_mt_active_planning_projects",
        "bernalillo_county_nm_accela_permits",
        "tulsa_ok_development_plans",
        "charleston_wv_energov_permits",
        "cheyenne_wy_opengov_permits",
        "madison_wi_legistar_plan_commission",
        "arapahoe_county_co_legistar_planning",
        "mesquite_tx_planning_zoning_agendas",
        "maricopa_county_az_planning_zoning_agendas",
        "jacksonville_fl_planning_commission_agendas",
        "hillsborough_county_fl_legistar_land_use",
        "port_st_lucie_fl_legistar_planning",
        "san_jose_ca_planning_director_hearings",
        "san_jose_ca_large_energy_projects",
    }
    by_key = {entry.key: entry for entry in entries}

    assert "savannah_ga_commercial_building_permits" not in by_key
    assert "detroit_mi_bseed_building_plan_reviews" not in by_key
    assert "san_marcos_tx_planning_application_notices" not in by_key
    assert "taylor_tx_development_notices" not in by_key
    assert not {key for key in by_key if key.startswith("bend_or_")}

    orlando = by_key["orlando_fl_planning_applications"]
    assert orlando.status == "legal_hold"
    assert orlando.base_url.endswith("/bhxy-4rji.json")
    assert "public opening announcements" in orlando.early_warning_value
    assert orlando.next_audit_on.isoformat() == "2026-08-15"
    assert orlando.can_run_canary is False

    atlanta = by_key["atlanta_ga_building_permit_tracker"]
    assert atlanta.status == "legal_hold"
    assert atlanta.base_url.endswith("/Building_Permit_Tracker/FeatureServer/2/query")
    assert atlanta.official_landing_page == "https://gis.atlantaga.gov/"
    assert "pre-approval statuses" in atlanta.blocker_summary
    assert atlanta.can_run_canary is False

    phoenix = by_key["phoenix_az_plan_review_and_permits"]
    assert phoenix.status == "legal_hold"
    assert phoenix.base_url.endswith("/Public/Planning_Permit/MapServer")
    assert "blank license metadata" in phoenix.blocker_summary
    assert phoenix.can_run_canary is False

    huntsville = by_key["huntsville_al_issued_building_permits"]
    assert huntsville.status == "legal_hold"
    assert huntsville.base_url.endswith("/Licenses/BuildingPermits/MapServer/0/query")
    assert "Issued-permit confirmation layer" in huntsville.early_warning_value
    assert huntsville.can_run_canary is False

    birmingham = by_key["birmingham_al_digital_plan_room"]
    assert birmingham.status == "legal_hold"
    assert birmingham.adapter == "portal"
    assert "Digital plan-room workflow" in birmingham.early_warning_value
    assert birmingham.can_run_canary is False

    mobile = by_key["mobile_al_build_mobile_portal"]
    assert mobile.status == "legal_hold"
    assert mobile.adapter == "portal"
    assert "Mobile portal coverage" in mobile.early_warning_value
    assert mobile.can_run_canary is False

    evansville = by_key["evansville_in_building_commission_permits"]
    assert evansville.status == "legal_hold"
    assert evansville.base_url.endswith("/BC/BUILDING_COMMISSION_PERMITS/MapServer/0/query")
    assert "application status" in evansville.blocker_summary
    assert evansville.can_run_canary is False

    nationwide_holds = {
        "anchorage_ak_bsd_permit_lookup",
        "honolulu_hi_building_permits_2005_2025",
        "boise_id_development_tracker",
        "cedar_rapids_ia_building_permits",
        "biloxi_ms_development_review_agendas",
        "bozeman_mt_active_planning_projects",
        "bernalillo_county_nm_accela_permits",
        "tulsa_ok_development_plans",
        "charleston_wv_energov_permits",
        "cheyenne_wy_opengov_permits",
    }
    assert all(by_key[key].can_run_canary is False for key in nationwide_holds)


def test_savannah_production_source_preserves_distinct_minimized_lifecycle_rows():
    source = next(
        entry
        for entry in load_catalog()
        if entry.key == "savannah_ga_commercial_building_permits"
    )
    base_record = {
        "PIN": "20005 02003",
        "PermitNumber": "26-03951-BC",
        "PermitType": "Building Commercial Permit",
        "WorkClass": "New",
        "PermitStatus": "In Review",
        "District": "Hitch Village/Fred Wessels Homes",
        "IssuedDate": None,
        "FinalizedDate": None,
        "Address": "620 EAST BAY ST",
        "Description": "FOUNDATION PERMIT - HOTEL WITH BASEMENT",
        "Permit_Value": 450000,
    }
    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in source.field_mappings]

    normalized = []
    for object_id in (104549, 104550):
        prepared, field_mapping = prepare_mapped_record(
            {**base_record, "OBJECTID": object_id}, mappings
        )
        normalized.append(
            normalize_permit(
                prepared,
                field_mapping,
                defaults=source.settings["defaults"],
            )
        )

    assert normalized[0].source_record_id == (
        "26-03951-BC|620 EAST BAY ST|104549"
    )
    assert normalized[1].source_record_id == (
        "26-03951-BC|620 EAST BAY ST|104550"
    )
    assert normalized[0].values["permit_number"] == "26-03951-BC"
    assert normalized[0].values["approval_stage"] == "pre_approval"
    assert normalized[0].values["parcel_id"] == "20005 02003"
    assert source.settings["reconciliation_mode"] == "weekly_full_snapshot"
    assert source.settings["connector"]["include_geometry"] is False
    assert "ApplicantName" not in source.settings["field_allowlist"]
    assert "ApplicantName" in source.settings["suppressed_fields"]


def test_candidate_catalog_closes_the_fifty_state_research_gap():
    coverage = summarize_coverage()

    assert coverage.researched_state_count == 50
    assert coverage.unresearched_state_count == 0
    assert coverage.unresearched_states == []
    assert coverage.covered_state_count == 40
    assert coverage.missing_state_count == 10
    assert coverage.candidate_only_state_count == 10
    assert set(coverage.candidate_only_states) == {
        "AK", "HI", "IA", "ID", "MS", "MT", "NM", "OK", "WV", "WY",
    }
    assert set(coverage.missing_states) == set(coverage.candidate_only_states)


def test_candidate_catalog_can_include_promoted_history():
    entries = load_candidate_catalog(include_promoted=True)
    by_key = {entry.key: entry for entry in entries}

    assert {
        "bend_or_permit_applications_line",
        "bend_or_permit_applications_point",
        "bend_or_planning_applications",
        "taylor_tx_development_notices",
        "san_marcos_tx_planning_application_notices",
        "savannah_ga_commercial_building_permits",
    } <= set(by_key)
    for key in (
        "bend_or_permit_applications_line",
        "bend_or_permit_applications_point",
        "bend_or_planning_applications",
        "taylor_tx_development_notices",
        "san_marcos_tx_planning_application_notices",
        "savannah_ga_commercial_building_permits",
    ):
        production = catalog_source_for_candidate(by_key[key])
        assert production is not None
        assert production.settings["candidate_key"] == key


def test_catalog_candidate_match_rejects_missing_provenance_and_identity_drift():
    candidate = load_candidate_catalog(include_promoted=True)[0]
    assert catalog_source_for_candidate(candidate, []) is None
    base = IngestionSourceCreate(
        key=candidate.key,
        name=candidate.name,
        adapter=candidate.adapter,
        record_type=candidate.record_type,
        jurisdiction=candidate.jurisdiction,
        base_url=candidate.base_url,
        settings={},
        field_mappings=[],
    )

    with pytest.raises(ValueError, match="missing candidate provenance"):
        catalog_source_for_candidate(candidate, [base])

    unapproved = base.model_copy(
        update={"settings": {"candidate_key": candidate.key}}
    )
    with pytest.raises(ValueError, match="not approved for production"):
        catalog_source_for_candidate(candidate, [unapproved])

    drifted = base.model_copy(
        update={
            "adapter": "csv" if candidate.adapter != "csv" else "socrata",
            "settings": {
                "candidate_key": candidate.key,
                "candidate_status": "approved_for_production",
            },
        }
    )
    with pytest.raises(ValueError, match="drifted from its candidate"):
        catalog_source_for_candidate(candidate, [drifted])


def test_summarize_coverage_ignores_database_only_sources():
    database_only = SimpleNamespace(
        key="runtime_only_unreviewed_source",
        is_active=True,
    )

    coverage = summarize_coverage(live_sources=[database_only])

    assert coverage.live_source_count == 0
    assert coverage.candidate_count == len(
        load_candidate_catalog(include_promoted=True)
    )
    assert coverage.covered_state_count == 0
    assert coverage.missing_state_count == 50
    assert coverage.researched_state_count == 50
    assert coverage.unresearched_state_count == 0


def test_summarize_coverage_requires_active_database_source():
    candidate = next(
        entry
        for entry in load_candidate_catalog(include_promoted=True)
        if entry.key.startswith("bend_or_")
    )
    catalog_source = catalog_source_for_candidate(candidate)
    assert catalog_source is not None
    inactive = SimpleNamespace(key=catalog_source.key, is_active=False)
    active = SimpleNamespace(
        key=catalog_source.key,
        name=catalog_source.name,
        jurisdiction=catalog_source.jurisdiction,
        settings=catalog_source.settings,
        is_active=True,
    )

    inactive_coverage = summarize_coverage(live_sources=[inactive])
    active_coverage = summarize_coverage(live_sources=[active])

    assert inactive_coverage.live_source_count == 0
    assert inactive_coverage.candidate_count == len(
        load_candidate_catalog(include_promoted=True)
    )
    assert active_coverage.live_source_count == 1
    assert active_coverage.candidate_count == inactive_coverage.candidate_count - 1


def test_summarize_coverage_groups_live_sources_by_signal_stage():
    coverage = summarize_coverage()

    assert coverage.live_source_count > 0
    assert "approved_only" in coverage.live_signal_sources_by_stage
    assert "pre_approval_and_approved" in coverage.live_signal_sources_by_stage
    assert any(
        source.source_key == "texas_comptroller_sales_tax_locations"
        for source in coverage.live_signal_sources_by_stage["approved_only"]
    )
    assert any(
        source.source_key == "seattle_wa_issued_building_permits"
        for source in coverage.live_signal_sources_by_stage["pre_approval_and_approved"]
    )

def test_candidate_catalog_rejects_production_key_overlap(tmp_path):
    payload = [
        {
            "key": "austin_tx_plan_review_cases",
            "name": "Overlap",
            "adapter": "socrata",
            "record_type": "permit",
            "jurisdiction": "Austin, TX",
            "base_url": "https://example.test/overlap.json",
            "official_landing_page": "https://example.test/overlap",
            "license": "Public Domain",
            "status": "queued",
            "blocker_summary": "Test blocker",
            "early_warning_value": "Test value",
            "candidate_source_fields": ["id"],
            "last_checked_on": "2026-07-18",
            "next_audit_on": "2026-07-25",
            "notes": "Test note",
        }
    ]
    path = tmp_path / "candidate_catalog.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="already exist in production catalog"):
        load_candidate_catalog(path)


def test_candidate_catalog_rejects_reverse_audit_dates(tmp_path):
    payload = [
        IngestionSourceCandidate(
            key="candidate_dates_invalid",
            name="Candidate Dates Invalid",
            adapter="socrata",
            record_type="permit",
            jurisdiction="Test",
            base_url="https://example.test/candidate-dates.json",
            official_landing_page="https://example.test/candidate-dates",
            license="Public Domain",
            status="queued",
            blocker_summary="Awaiting audit",
            early_warning_value="Test early warning value",
            candidate_source_fields=["id"],
            last_checked_on="2026-07-18",
            next_audit_on="2026-07-17",
            notes="Test note",
        ).model_dump(mode="json")
    ]
    path = tmp_path / "candidate_catalog.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="next_audit_on cannot be earlier"):
        load_candidate_catalog(path)


def test_candidate_catalog_rejects_retry_candidates_without_probe_config(tmp_path):
    payload = [
        {
            "key": "candidate_retry_missing_probe",
            "name": "Candidate Retry Missing Probe",
            "adapter": "socrata",
            "record_type": "permit",
            "jurisdiction": "Test",
            "base_url": "https://example.test/candidate-retry.json",
            "official_landing_page": "https://example.test/candidate-retry",
            "license": "Public Domain",
            "status": "operational_retry",
            "blocker_summary": "Awaiting retry",
            "early_warning_value": "Test value",
            "candidate_source_fields": ["id"],
            "last_checked_on": "2026-07-18",
            "next_audit_on": "2026-07-25",
            "notes": "Test note"
        }
    ]
    path = tmp_path / "candidate_catalog.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="operational_retry candidates require"):
        load_candidate_catalog(path)


def test_candidate_retry_canary_uses_probe_config(monkeypatch):
    candidate = IngestionSourceCandidate(
        key="candidate_retry",
        name="Candidate Retry",
        adapter="socrata",
        record_type="permit",
        jurisdiction="Test",
        base_url="https://example.test/retry.json",
        official_landing_page="https://example.test/retry",
        license="Public Domain",
        status="operational_retry",
        blocker_summary="Awaiting retry",
        early_warning_value="Test value",
        candidate_source_fields=["license", "application_date"],
        probe_settings={
            "connector": {"page_size": 5},
            "defaults": {"state": "TX", "approval_stage": "pre_approval"},
        },
        probe_field_mappings=[
            {
                "source_field": "license",
                "canonical_field": "source_record_id",
                "is_required": True,
            },
            {
                "source_field": "application_date",
                "canonical_field": "filed_at",
            },
        ],
        last_checked_on="2026-07-18",
        next_audit_on="2026-07-25",
        notes="Test note",
    )
    monkeypatch.setattr(
        "app.services.ingestion.health.build_connector",
        lambda _adapter, _config: SimpleNamespace(
            fetch_page=lambda: SimpleNamespace(
                source="test",
                records=(
                    {"license": "ABC-1", "application_date": "2026-07-18T00:00:00"},
                ),
                checkpoint={"offset": 1},
                has_more=False,
            )
        ),
    )

    result = validate_candidate_source_canary(candidate, sample_size=1)

    assert result.candidate_key == "candidate_retry"
    assert result.ok is True
    assert result.records_valid == 1
    assert result.approval_stages == {"pre_approval": 1}


def test_opening_signal_sources_declare_stage_date_and_raw_export_limits(tmp_path):
    valid_payload = [{
        "key": "opening_signal",
        "name": "Opening Signal",
        "adapter": "socrata",
        "record_type": "permit",
        "jurisdiction": "Test",
        "base_url": "https://example.test/resource/openings.json",
        "settings": {
            "official_landing_page": "https://example.test/openings",
            "license": "Public Domain",
                "reconciliation_mode": "daily_recent_snapshot",
                "collection_interval_minutes": 1440,
                "collection_sla_hours": 24,
                "retry_interval_minutes": 360,
                "schedule_mode": "automatic",
                "signal_stage": "approved_only",
            "retailer_opening_signal": True,
            "opening_signal_date_field": "first_sale_date",
            "export_policy": "derived_retailer_opening_context_only_no_raw_export",
            "connector": {
                "query": {
                    "$select": "id,first_sale_date"
                }
            },
        },
        "field_mappings": [
            {"source_field": "id", "canonical_field": "source_record_id", "is_required": True}
        ],
    }]
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(valid_payload), encoding="utf-8")

    assert load_catalog(path)[0].key == "opening_signal"

    preapproval_payload = json.loads(json.dumps(valid_payload))
    preapproval_payload[0]["settings"]["signal_stage"] = "pre_approval_and_approved"
    path.write_text(json.dumps(preapproval_payload), encoding="utf-8")
    assert load_catalog(path)[0].key == "opening_signal"

    invalid_payload = json.loads(json.dumps(valid_payload))
    invalid_payload[0]["settings"]["signal_stage"] = "parcel_context"
    path.write_text(json.dumps(invalid_payload), encoding="utf-8")
    with pytest.raises(ValueError, match="approved_only or pre_approval_and_approved"):
        load_catalog(path)

    invalid_payload = json.loads(json.dumps(valid_payload))
    invalid_payload[0]["settings"].pop("opening_signal_date_field")
    path.write_text(json.dumps(invalid_payload), encoding="utf-8")
    with pytest.raises(ValueError, match="requires opening_signal_date_field"):
        load_catalog(path)

    invalid_payload = json.loads(json.dumps(valid_payload))
    invalid_payload[0]["settings"]["export_policy"] = "derived_context_only"
    path.write_text(json.dumps(invalid_payload), encoding="utf-8")
    with pytest.raises(ValueError, match="opening-context export policy"):
        load_catalog(path)


def test_opening_signal_date_field_must_be_selected(tmp_path):
    payload = [{
        "key": "opening_signal_missing_date",
        "name": "Opening Signal Missing Date",
        "adapter": "socrata",
        "record_type": "permit",
        "jurisdiction": "Test",
        "base_url": "https://example.test/resource/openings-missing-date.json",
        "settings": {
            "official_landing_page": "https://example.test/openings",
            "license": "Public Domain",
                "reconciliation_mode": "daily_recent_snapshot",
                "collection_interval_minutes": 1440,
                "collection_sla_hours": 24,
                "retry_interval_minutes": 360,
                "schedule_mode": "automatic",
                "signal_stage": "approved_only",
            "retailer_opening_signal": True,
            "opening_signal_date_field": "first_sale_date",
            "export_policy": "derived_retailer_opening_context_only_no_raw_export",
            "connector": {
                "query": {
                    "$select": "id,trade_name"
                }
            },
        },
        "field_mappings": [
            {"source_field": "id", "canonical_field": "source_record_id", "is_required": True}
        ],
    }]
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="opening_signal_date_field field"):
        load_catalog(path)


def test_austin_site_plan_cases_are_recent_actionable_and_party_enriched():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "austin_tx_site_plan_cases"
    )
    selected_fields = {
        field.strip()
        for field in entry.settings["connector"]["query"]["$select"].split(",")
    }
    suppressed = set(entry.settings["suppressed_fields"])
    where = entry.settings["connector"]["query"]["$where"]

    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert entry.settings["connector"]["keyset_fields"] == ["folderrsn"]
    assert "application_start_date >= '2024-01-01T00:00:00'" in where
    assert "Intake Pending" in where
    assert "Approved and Released" in where
    assert "Withdrawn" not in where
    assert "applicant_organization_name" in selected_fields
    assert "owner_organization_name" in selected_fields
    assert "applicant_phone1" not in selected_fields
    assert "owner_phone1" not in selected_fields
    assert suppressed.isdisjoint(selected_fields)
    assert selected_fields <= set(entry.settings["field_allowlist"])
    assert entry.settings["canary_stage_probes"][0]["expected_stage"] == "pre_approval"

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    record = {
        "folderrsn": "13739788",
        "permit_number": "SP-2026-1000C",
        "case_type": "Site Plan",
        "sub_type": "Site Plan Administrative",
        "work": "Consolidated",
        "case_name": "TACO BELL EAST AUSTIN",
        "description_of_work": "The applicant is proposing a restaurant with associated improvements.",
        "proposed_land_use": "Commercial",
        "status": "Intake Pending",
        "status_date": "2026-07-17T14:27:31.000",
        "street_number": "2607",
        "street_direction": "S",
        "street_name": "1ST",
        "street_type": "ST",
        "unit": "100",
        "city": "Austin",
        "zip_code": "78704",
        "tcad_id": "0404020155",
        "propertyrsn": "567873",
        "applicant_fullname": "Christian Ornelas",
        "applicant_organization_name": "GarzaEMC",
        "owner_fullname": "Jane Owner",
        "owner_organization_name": "East Austin Retail LLC",
        "latitude": "30.242",
        "longitude": "-97.755",
        "application_start_date": "2026-07-17T13:44:40.000",
        "approval_date": None,
        "final_date": None,
        "link": "https://abc.austintexas.gov/web/permit/public-search-other?t_detail=1&t_selected_folderrsn=13739788",
    }
    prepared, field_mapping = prepare_mapped_record(record, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.source_record_id == "13739788"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["project_name"] == "TACO BELL EAST AUSTIN"
    assert normalized.values["address"] == "2607 S 1ST ST 100"
    assert normalized.values["applicant_name"] == "GarzaEMC"
    assert normalized.values["owner_name"] == "East Austin Retail LLC"
    assert normalized.values["parcel_id"] == "0404020155"
    assert normalized.values["source_url"].endswith("13739788")
    assert "applicant_phone1" not in normalized.values


def test_catalog_rejects_sources_without_reviewed_license_metadata(tmp_path):
    payload = load_catalog()[0].model_dump(mode="json")
    payload["settings"].pop("license")
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps([payload]))

    with pytest.raises(ValueError, match="missing reviewed metadata.*license"):
        load_catalog(catalog_path)


def test_catalog_rejects_duplicate_base_urls(tmp_path):
    first = load_catalog()[0].model_dump(mode="json")
    duplicate = {**first, "key": "duplicate_official_endpoint"}
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps([first, duplicate]))

    with pytest.raises(ValueError, match="Duplicate ingestion catalog base URLs"):
        load_catalog(catalog_path)


def test_geometry_only_parcel_spines_do_not_fetch_or_map_suppressed_fields():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "san_diego_ca_sangis_parcel_spine"
    )
    suppressed = set(entry.settings["suppressed_fields"])
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }
    mapped_fields = {mapping.source_field for mapping in entry.field_mappings}

    assert entry.settings["export_policy"] == "derived_geometry_situs_only_no_raw_source_export"
    assert suppressed.isdisjoint(out_fields)
    assert suppressed.isdisjoint(mapped_fields)
    assert "owner_name" not in {mapping.canonical_field for mapping in entry.field_mappings}
    assert "total_assessed_value" not in {mapping.canonical_field for mapping in entry.field_mappings}
    assert "last_sale_date" not in {mapping.canonical_field for mapping in entry.field_mappings}


def test_catalog_rejects_suppressed_fields_in_connector_or_mapping(tmp_path):
    payload = next(
        entry for entry in load_catalog()
        if entry.key == "san_diego_ca_sangis_parcel_spine"
    ).model_dump(mode="json")
    payload["settings"]["connector"]["out_fields"] += ",own_name1"
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps([payload]))

    with pytest.raises(ValueError, match="fetches suppressed fields.*own_name1"):
        load_catalog(catalog_path)

    payload["settings"]["connector"]["out_fields"] = payload["settings"]["connector"][
        "out_fields"
    ].replace(",own_name1", "")
    payload["field_mappings"].append(
        {
            "source_field": "own_name1",
            "canonical_field": "owner_name",
            "transform": None,
            "transform_options": None,
            "default_value": None,
            "is_required": False,
            "is_active": True,
        }
    )
    catalog_path.write_text(json.dumps([payload]))

    with pytest.raises(ValueError, match="maps suppressed fields.*own_name1"):
        load_catalog(catalog_path)


def test_catalog_rejects_wildcard_fetch_with_suppressed_fields(tmp_path):
    payload = next(
        entry for entry in load_catalog()
        if entry.key == "san_diego_ca_sangis_parcel_spine"
    ).model_dump(mode="json")
    payload["settings"]["connector"]["out_fields"] = "*"
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps([payload]))

    with pytest.raises(ValueError, match="cannot fetch '\\*'"):
        load_catalog(catalog_path)


def test_catalog_rejects_fetched_fields_outside_allowlist(tmp_path):
    payload = next(
        entry for entry in load_catalog()
        if entry.key == "mesa_az_commercial_permit_submittals"
    ).model_dump(mode="json")
    payload["settings"]["connector"]["query"]["$select"] += ",assigned_by_name"
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps([payload]))

    with pytest.raises(ValueError, match="outside field_allowlist.*assigned_by_name"):
        load_catalog(catalog_path)


def test_catalog_rejects_allowlisted_suppressed_fields(tmp_path):
    payload = next(
        entry for entry in load_catalog()
        if entry.key == "tempe_az_building_permits_commercial_context"
    ).model_dump(mode="json")
    payload["settings"]["field_allowlist"].append("ContractorPhone")
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps([payload]))

    with pytest.raises(ValueError, match="allowlists suppressed fields.*contractorphone"):
        load_catalog(catalog_path)


def test_catalog_rejects_canary_fields_outside_allowlist(tmp_path):
    payload = next(
        entry for entry in load_catalog()
        if entry.key == "new_jersey_njgin_statewide_parcels_nearby_narrow"
    ).model_dump(mode="json")
    payload["settings"]["canary_required_fields"].append("OWNER_NAME")
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps([payload]))

    with pytest.raises(ValueError, match="canary fields outside field_allowlist.*owner_name"):
        load_catalog(catalog_path)


def test_addressless_parcel_sources_declare_derived_context_policy():
    for entry in load_catalog():
        if entry.record_type != "parcel":
            continue
        canonical_fields = {
            mapping.canonical_field
            for mapping in entry.field_mappings
            if mapping.is_active
        }
        if "address" in canonical_fields:
            continue

        export_policy = str(entry.settings.get("export_policy", ""))
        assert export_policy.startswith(("derived_geometry_", "derived_nearby_")), entry.key


def test_catalog_rejects_freshness_candidate_without_hold(tmp_path):
    payload = next(
        entry for entry in load_catalog()
        if entry.key == "los_angeles_ca_building_permits_submitted"
    ).model_dump(mode="json")
    payload["settings"].pop("freshness_enforcement_hold")
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps([payload]))

    with pytest.raises(ValueError, match="freshness_field_candidate.*freshness_enforcement_hold"):
        load_catalog(catalog_path)


def test_catalog_rejects_freshness_candidate_not_selected(tmp_path):
    payload = next(
        entry for entry in load_catalog()
        if entry.key == "los_angeles_ca_building_permits_submitted"
    ).model_dump(mode="json")
    payload["settings"]["connector"]["query"]["$select"] = payload["settings"]["connector"][
        "query"
    ]["$select"].replace(",refresh_time", "")
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps([payload]))

    with pytest.raises(ValueError, match="freshness_field_candidate.*not selected"):
        load_catalog(catalog_path)


def test_catalog_rejects_enforced_freshness_field_not_selected(tmp_path):
    payload = next(
        entry for entry in load_catalog()
        if entry.key == "los_angeles_ca_building_permits_submitted"
    ).model_dump(mode="json")
    payload["settings"].pop("freshness_field_candidate")
    payload["settings"].pop("freshness_enforcement_hold")
    payload["settings"]["freshness_field"] = "refresh_time"
    payload["settings"]["freshness_sla_hours"] = 96
    payload["settings"]["connector"]["query"]["$select"] = payload["settings"]["connector"][
        "query"
    ]["$select"].replace(",refresh_time", "")
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps([payload]))

    with pytest.raises(ValueError, match="freshness_field.*not selected"):
        load_catalog(catalog_path)


def test_catalog_rejects_candidate_and_enforced_freshness_field_together(tmp_path):
    payload = next(
        entry for entry in load_catalog()
        if entry.key == "los_angeles_ca_building_permits_submitted"
    ).model_dump(mode="json")
    payload["settings"]["freshness_field"] = "refresh_time"
    payload["settings"]["freshness_sla_hours"] = 96
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps([payload]))

    with pytest.raises(ValueError, match="cannot declare both freshness_field"):
        load_catalog(catalog_path)


def test_catalog_rejects_freshness_probe_without_enforced_field(tmp_path):
    payload = next(
        entry for entry in load_catalog()
        if entry.key == "san_jose_ca_planning_permit_applications"
    ).model_dump(mode="json")
    payload["settings"].pop("freshness_field")
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps([payload]))

    with pytest.raises(ValueError, match="canary_freshness_probe requires freshness_field"):
        load_catalog(catalog_path)


def test_catalog_rejects_malformed_freshness_probe(tmp_path):
    payload = next(
        entry for entry in load_catalog()
        if entry.key == "san_jose_ca_planning_permit_applications"
    ).model_dump(mode="json")
    payload["settings"]["canary_freshness_probe"]["sample_size"] = 101
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps([payload]))

    with pytest.raises(ValueError, match="canary_freshness_probe sample_size"):
        load_catalog(catalog_path)

    payload["settings"]["canary_freshness_probe"]["sample_size"] = 5
    payload["settings"]["canary_freshness_probe"]["connector"] = {}
    catalog_path.write_text(json.dumps([payload]))

    with pytest.raises(ValueError, match="canary_freshness_probe requires a connector"):
        load_catalog(catalog_path)


def test_seattle_land_use_permits_are_preapproval_development_context():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "seattle_wa_land_use_permits"
    )
    canonical_fields = {mapping.canonical_field for mapping in entry.field_mappings}
    suppressed = set(entry.settings["suppressed_fields"])
    allowlist = set(entry.settings["field_allowlist"])
    selected_fields = {
        field.strip()
        for field in entry.settings["connector"]["query"]["$select"].split(",")
    }
    mapped_fields = {mapping.source_field for mapping in entry.field_mappings}

    assert entry.adapter == "socrata"
    assert entry.record_type == "permit"
    assert entry.settings["license"] == "Public Domain"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert entry.settings["connector"]["order_by"] == "applieddate DESC, :id ASC"
    assert "permitclassmapped IN" in entry.settings["connector"]["query"]["$where"]
    assert "statuscurrent NOT IN" in entry.settings["connector"]["query"]["$where"]
    assert "applieddate >= '2024-01-01'" in entry.settings["connector"]["query"]["$where"]
    assert "raw source replacement exports" in entry.settings["rights_basis"]
    assert suppressed.isdisjoint(allowlist)
    assert suppressed.isdisjoint(selected_fields)
    assert suppressed.isdisjoint(mapped_fields)
    assert "source_record_id" in canonical_fields
    assert "approval_stage" in canonical_fields
    assert "project_name" not in canonical_fields

    prepared, field_mapping = prepare_mapped_record(
        {
            ":id": "row-2dta_qmr9~zi65",
            "permitnum": "3044186-LU",
            "permitclass": "Industrial",
            "permitclassmapped": "Non-Residential",
            "permittypemapped": "Master Use Permit",
            "permittypedesc": None,
            "description": (
                "Land Use Application to allow a 9-story Business Support "
                "Services (Data Center) building. Parking for 264 vehicles proposed."
            ),
            "housingunits": None,
            "housingunitsremoved": None,
            "housingunitsadded": None,
            "estprojectcost": "220000000.0000",
            "applieddate": "2026-06-05",
            "issueddate": None,
            "expiresdate": None,
            "decisiondate": None,
            "statuscurrent": "Reviews In Process",
            "originaladdress1": "3625 1ST AVE S",
            "originalcity": "SEATTLE",
            "originalstate": "WA",
            "originalzip": "98134",
            "contractorcompanyname": None,
            "link": {
                "url": "https://services.seattle.gov/portal/customize/LinkToRecord.aspx?altId=3044186-LU"
            },
            "latitude": "47.57035461",
            "longitude": "-122.33579131",
            "location1": {
                "latitude": "47.57035461",
                "longitude": "-122.33579131",
            },
        },
        entry.field_mappings,
    )
    normalized = normalize_permit(
        prepared,
        field_mapping,
        defaults=entry.settings["defaults"],
    )

    assert normalized.source_record_id == "row-2dta_qmr9~zi65"
    assert normalized.values["permit_number"] == "3044186-LU"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert "project_name" not in normalized.values
    assert normalized.values["valuation"] == Decimal("220000000.0000")
    assert normalized.values["source_url"].endswith("3044186-LU")
    assert float(normalized.values["latitude"]) == pytest.approx(47.57035461)
    assert float(normalized.values["longitude"]) == pytest.approx(-122.33579131)


def test_seattle_street_use_notices_are_preapproval_public_comment_context():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "seattle_wa_street_use_public_notices"
    )
    canonical_fields = {mapping.canonical_field for mapping in entry.field_mappings}

    assert entry.adapter == "socrata"
    assert entry.record_type == "permit"
    assert entry.settings["license"] == "Public Domain"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert entry.settings["export_policy"] == (
        "derived_street_use_notice_context_only_no_raw_seattle_sdot_source_resale"
    )
    assert set(entry.settings["canary_required_fields"]) == {
        "application_number",
        "application_type",
        "address",
    }
    assert "approval_stage" in canonical_fields
    assert "project_name" in canonical_fields
    assert "latitude" in canonical_fields
    assert "longitude" in canonical_fields

    prepared, field_mapping = prepare_mapped_record(
        {
            "address": "5311 Ballard Ave NW",
            "city": "SEATTLE",
            "state": "WA",
            "zip_code": "98107",
            "business": "Radiator Whisky",
            "application_type": "Curb Space Cafe",
            "size": "12 ft x 10 ft",
            "application_number": "SUPSM0009602",
            "start_of_public_comment_period": "2026-07-08T00:00:00.000",
            "end_of_public_comment_period": "2026-07-22T00:00:00.000",
            "location": {
                "type": "Point",
                "coordinates": [-122.38356, 47.6667],
            },
        },
        entry.field_mappings,
    )
    normalized = normalize_permit(
        prepared,
        field_mapping,
        defaults=entry.settings["defaults"],
    )

    assert normalized.source_record_id == "SUPSM0009602"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert float(normalized.values["longitude"]) == pytest.approx(-122.38356)
    assert float(normalized.values["latitude"]) == pytest.approx(47.6667)


def test_washington_sepa_register_suppresses_contact_and_raw_document_fields():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "washington_ecology_sepa_register"
    )
    canonical_fields = {mapping.canonical_field for mapping in entry.field_mappings}
    suppressed = set(entry.settings["suppressed_fields"])
    allowlist = set(entry.settings["field_allowlist"])
    mapped_fields = {mapping.source_field for mapping in entry.field_mappings}

    assert entry.adapter == "socrata"
    assert entry.record_type == "permit"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert entry.settings["attribution_required"] is True
    assert entry.settings["export_policy"] == (
        "derived_sepa_register_context_only_no_raw_ecology_document_resale"
    )
    assert "no formal license" in entry.settings["license"]
    assert "document bodies" in entry.settings["rights_basis"]
    assert suppressed.isdisjoint(allowlist)
    assert suppressed.isdisjoint(mapped_fields)
    assert "leadagencycontactemail" not in mapped_fields
    assert "applicantcontactinfo" not in mapped_fields
    assert "applicant_name" in canonical_fields
    assert "parcel_id" in canonical_fields
    assert "source_url" in canonical_fields


def test_nyc_dob_now_job_applications_are_fresh_filtered_and_business_name_only():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "new_york_ny_dob_now_job_applications"
    )
    selected_fields = {
        field.strip()
        for field in entry.settings["connector"]["query"]["$select"].split(",")
    }
    suppressed = set(entry.settings["suppressed_fields"])
    mapped_fields = {mapping.source_field for mapping in entry.field_mappings}

    assert entry.adapter == "socrata"
    assert entry.record_type == "permit"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert entry.settings["freshness_field"] == "current_status_date"
    assert entry.settings["canary_freshness_probe"]["connector"]["order_by"] == "current_status_date DESC"
    assert "Plan Examiner Review" in entry.settings["connector"]["query"]["$where"]
    assert "filing_date >= '2024-01-01T00:00:00'" in entry.settings["connector"]["query"]["$where"]
    assert entry.settings["canary_stage_probes"][0]["expected_stage"] == "pre_approval"
    assert entry.settings["canary_stage_probes"][1]["expected_stage"] == "approved"
    assert suppressed.isdisjoint(selected_fields)
    assert suppressed.isdisjoint(mapped_fields)
    assert selected_fields <= set(entry.settings["field_allowlist"])

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    filing = {
        ":id": "row-test-tmobile",
        "job_filing_number": "M01000000-I1",
        "filing_status": "Plan Examiner Review",
        "house_no": "418",
        "street_name": "EAST 14 STREET",
        "borough": "Manhattan",
        "postcode": "10009",
        "block": "00440",
        "lot": "0001",
        "bin": "1000001",
        "bbl": "1004400001",
        "commmunity_board": "103",
        "work_on_floor": "1",
        "job_type": "Alteration",
        "filing_review_type": "Standard Plan Examination",
        "building_type": "Mixed",
        "job_description": "Install accessory business sign for T-Mobile authorized retailer.",
        "applicant_business_name": "Sign Engineer LLC",
        "owner_s_business_name": "Retail Property Owner LLC",
        "initial_cost": "18000",
        "total_construction_floor_area": "400",
        "proposed_dwelling_units": "0",
        "latitude": "40.731",
        "longitude": "-73.989",
        "filing_date": "2026-07-01T00:00:00.000",
        "current_status_date": "2026-07-17T04:32:49.000",
        "approved_date": None,
    }
    prepared, field_mapping = prepare_mapped_record(filing, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.source_record_id == "row-test-tmobile"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["description"].startswith("Install accessory business sign")
    assert normalized.values["address"] == "418 EAST 14 STREET"
    assert normalized.values["owner_name"] == "Retail Property Owner LLC"
    assert normalized.values["applicant_name"] == "Sign Engineer LLC"


def test_san_francisco_planning_non_project_records_preserve_entitlement_chain_context():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "san_francisco_ca_planning_department_non_project_records"
    )
    selected_fields = {
        field.strip()
        for field in entry.settings["connector"]["query"]["$select"].split(",")
    }
    suppressed = set(entry.settings["suppressed_fields"])

    assert entry.adapter == "socrata"
    assert entry.record_type == "permit"
    assert entry.settings["license"] == "Public Domain U.S. Government"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert "record_type IN ('CUA','DRM','PRL','VAR','ZAD','PCA','COA','SHD')" in entry.settings["connector"]["query"]["$where"]
    assert "Closed - Withdrawn" in entry.settings["connector"]["query"]["$where"]
    assert "applicant" not in selected_fields
    assert "assigned_to_planner" not in selected_fields
    assert suppressed.isdisjoint(selected_fields)
    assert selected_fields <= set(entry.settings["field_allowlist"])
    assert entry.settings["canary_stage_probes"][0]["expected_stage"] == "pre_approval"
    assert entry.settings["canary_stage_probes"][1]["expected_stage"] == "approved"

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    submitted = {
        "record_id": "2026-006230CUA",
        "parent_id": "2026-006230PRJ",
        "record_type": "CUA",
        "record_status": "Submitted",
        "open_date": "2026-07-14T00:00:00.000",
        "close_date": None,
        "project_name": "3995 24TH STREET",
        "description": "A Conditional Use authorization is sought to extend the hours of operation for an existing Starbucks.",
        "project_address": "3995 24TH ST 94114",
        "block": "6508",
        "lot": "025",
        "building_permits": None,
        "applicant_org": "Greenbergfarrow",
        "pim_link": {"url": "https://sfplanninggis.org/pim?search=2026-006230CUA"},
    }
    prepared, field_mapping = prepare_mapped_record(submitted, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.source_record_id == "2026-006230CUA"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["application_number"] == "2026-006230CUA"
    assert normalized.values["permit_number"] == "2026-006230CUA"
    assert normalized.values["permit_type"] == "Planning entitlement / review record"
    assert normalized.values["permit_subtype"] == "CUA"
    assert normalized.values["project_name"] == "3995 24TH STREET"
    assert "existing Starbucks" in normalized.values["description"]
    assert normalized.values["address"] == "3995 24TH ST 94114"
    assert normalized.values["parcel_id"] == "6508-025"
    assert normalized.values["applicant_name"] == "Greenbergfarrow"
    assert normalized.values["filed_at"].isoformat() == "2026-07-14T00:00:00+00:00"
    assert normalized.values["source_url"].endswith("2026-006230CUA")
    assert "applicant" not in normalized.values
    assert "parent_id" in normalized.unmapped

    approved = {
        **submitted,
        "record_id": "2026-004314COA",
        "record_type": "COA",
        "record_status": "Closed - Approved",
        "close_date": "2026-07-09T00:00:00.000",
    }
    prepared, field_mapping = prepare_mapped_record(approved, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.values["approval_stage"] == "approved"
    assert normalized.values["approved_at"].isoformat() == "2026-07-09T00:00:00+00:00"


def test_marin_county_commercial_building_permits_preserve_received_to_issued_lifecycle():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "marin_county_ca_commercial_building_permits"
    )
    selected_fields = {
        field.strip()
        for field in entry.settings["connector"]["query"]["$select"].split(",")
    }
    suppressed = set(entry.settings["suppressed_fields"])

    assert entry.adapter == "socrata"
    assert entry.record_type == "permit"
    assert entry.settings["license"] == "Open Data Commons Open Database License"
    assert entry.settings["attribution_required"] is True
    assert entry.settings["share_alike_review_required"] is True
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert "type_permit = 'COMMERCIAL'" in entry.settings["connector"]["query"]["$where"]
    assert "issued_date IS NULL" in entry.settings["canary_stage_probes"][0]["connector"]["query"]["$where"]
    assert "issued_date >= '2026-01-01T00:00:00'" in entry.settings["canary_stage_probes"][1]["connector"]["query"]["$where"]
    assert "contractor_address" not in selected_fields
    assert "contractor_license" not in selected_fields
    assert suppressed.isdisjoint(selected_fields)
    assert selected_fields <= set(entry.settings["field_allowlist"])

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    received = {
        "unique_id": "OM_94301",
        "permit_tracking_id": "94301",
        "permit_number": "",
        "received_date": "2026-06-15T00:00:00.000",
        "issued_date": None,
        "address": "3422 STATE ROUTE 1, STINSON BEACH, CA 94970",
        "parcel_number": "195-193-35",
        "zipcode": "94970",
        "city_town": "STINSON BEACH",
        "city_town_inferred": "STINSON BEACH",
        "type_permit": "COMMERCIAL",
        "permit_work_class": "New; OtherTransportation; ",
        "fee_code_title": "All Commercial Uses - New construction; Electrical Permits",
        "description": "(N) Two-Story Fire Station, Driveway, Accessible Parking Stalls, Ev Stalls",
        "contractor": None,
        "construction_value": "9205000",
        "latitude": "37.8984955",
        "longitude": "-122.6398061",
    }
    prepared, field_mapping = prepare_mapped_record(received, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.source_record_id == "OM_94301"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["application_number"] == "94301"
    assert normalized.values["permit_number"] == "94301"
    assert normalized.values["permit_type"] == "COMMERCIAL"
    assert normalized.values["work_class"] == "New; OtherTransportation;"
    assert normalized.values["proposed_use"] == "All Commercial Uses - New construction; Electrical Permits"
    assert "Two-Story Fire Station" in normalized.values["description"]
    assert normalized.values["address"] == "3422 STATE ROUTE 1, STINSON BEACH, CA 94970"
    assert normalized.values["city"] == "STINSON BEACH"
    assert normalized.values["postal_code"] == "94970"
    assert normalized.values["parcel_id"] == "195-193-35"
    assert normalized.values["valuation"] == Decimal("9205000")
    assert normalized.values["latitude"] == Decimal("37.8984955")
    assert normalized.values["longitude"] == Decimal("-122.6398061")
    assert normalized.values["filed_at"].isoformat() == "2026-06-15T00:00:00+00:00"
    assert "contractor_address" not in normalized.values

    issued = {
        **received,
        "unique_id": "IN_B47478_47478",
        "permit_tracking_id": "B47478",
        "permit_number": "B47478",
        "issued_date": "2026-07-17T09:23:09.000",
        "contractor": "GORDON DRAKE",
    }
    prepared, field_mapping = prepare_mapped_record(issued, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.values["approval_stage"] == "approved"
    assert normalized.values["permit_number"] == "B47478"
    assert normalized.values["contractor_name"] == "GORDON DRAKE"
    assert normalized.values["issued_at"].isoformat() == "2026-07-17T09:23:09+00:00"


def test_san_jose_planning_permit_applications_preserve_review_lifecycle():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "san_jose_ca_planning_permit_applications"
    )
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }
    suppressed = set(entry.settings["suppressed_fields"])

    assert entry.adapter == "arcgis"
    assert entry.record_type == "permit"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    assert entry.settings["connector"]["include_geometry"] is True
    assert entry.settings["freshness_field"] == "LASTUPDATE"
    assert entry.settings["freshness_sla_hours"] == 720
    assert entry.settings["canary_freshness_probe"]["connector"]["order_by_fields"] == "LASTUPDATE DESC"
    assert entry.settings["canary_freshness_probe"]["connector"]["keyset_field"] is None
    assert "Under Review" in entry.settings["connector"]["where"]
    assert "Approved/Certified" in entry.settings["canary_stage_probes"][1]["connector"]["where"]
    assert "PROJECTMANAGER" not in out_fields
    assert "ISSUEUSER" not in out_fields
    assert "LASTEDITOR" not in out_fields
    assert "NOTES" not in out_fields
    assert suppressed.isdisjoint(out_fields)
    assert out_fields <= set(entry.settings["field_allowlist"])

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    review = {
        "OBJECTID": 246744,
        "FOLDERRSN": "1968004",
        "FOLDERNUM": "671531",
        "FOLDERDESC": "Japantown Corp Yard mixed-use building with office space and residential units",
        "FOLDERNAME": "ER22-112",
        "ADDRESS": "653 7TH ST",
        "APN": "24939044",
        "APPLICANT": "Sean McEachern (Shea Properties)",
        "OWNERNAME": "Shea Properties",
        "WORKDESC": "Addendum",
        "SUBDESC": "Private Project, NEPA not applicable",
        "INDATE": 1651223219000,
        "ISSUEDATE": 1783468800000,
        "FINALDATE": None,
        "REFERENCENUM": "ER22-112",
        "ZONING": "",
        "LASTUPDATE": 1783594737000,
        "ENTERPRISEID": "PLN-PMPL-0000246747",
        "GlobalID": "{155B248D-5349-4CA1-97BE-784A9533AF4B}",
        "PERMITSTATUS": "Under Review",
        "PERMITISSUE": "ISSUED",
        "PERMITTYPE": "Environmental Review ",
        "FOLDERYR": "22",
        "geometry": {"x": -121.89330186193912, "y": 37.350830461721635},
    }
    prepared, field_mapping = prepare_mapped_record(review, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.source_record_id == "1968004"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["application_number"] == "ER22-112"
    assert normalized.values["permit_type"] == "Environmental Review"
    assert normalized.values["work_class"] == "Addendum"
    assert normalized.values["review_type"] == "Private Project, NEPA not applicable"
    assert normalized.values["project_name"] == "ER22-112"
    assert normalized.values["address"] == "653 7TH ST"
    assert normalized.values["parcel_id"] == "24939044"
    assert normalized.values["applicant_name"] == "Sean McEachern (Shea Properties)"
    assert normalized.values["owner_name"] == "Shea Properties"
    assert normalized.values["latitude"] == Decimal("37.350830461721635")
    assert normalized.values["longitude"] == Decimal("-121.89330186193912")
    assert normalized.values["filed_at"].isoformat() == "2022-04-29T09:06:59+00:00"
    assert normalized.values["status_updated_at"].isoformat() == "2026-07-09T10:58:57+00:00"

    approved = {
        **review,
        "FOLDERRSN": "2000001",
        "PERMITSTATUS": "Approved",
        "FINALDATE": 1783641600000,
    }
    prepared, field_mapping = prepare_mapped_record(approved, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.values["approval_stage"] == "approved"
    assert normalized.values["completed_at"].isoformat() == "2026-07-10T00:00:00+00:00"


def test_pierce_county_pals_permits_preserve_lifecycle_and_suppress_raw_fields():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "pierce_county_wa_pals_permits"
    )
    canonical_fields = {mapping.canonical_field for mapping in entry.field_mappings}
    suppressed = set(entry.settings["suppressed_fields"])
    allowlist = set(entry.settings["field_allowlist"])
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }
    mapped_fields = {mapping.source_field for mapping in entry.field_mappings}

    assert entry.adapter == "arcgis"
    assert entry.record_type == "permit"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert entry.settings["attribution_required"] is True
    assert entry.settings["export_policy"] == (
        "derived_pierce_county_permit_context_only_no_raw_pals_resale"
    )
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    assert entry.settings["connector"]["include_geometry"] is True
    assert "applicationNumber" in entry.settings["connector"]["out_fields"]
    assert "applicationStatus" in entry.settings["connector"]["out_fields"]
    assert suppressed.isdisjoint(allowlist)
    assert suppressed.isdisjoint(out_fields)
    assert suppressed.isdisjoint(mapped_fields)
    assert "powerCompany" not in entry.settings["connector"]["out_fields"]
    assert "approval_stage" in canonical_fields
    assert "parcel_id" in canonical_fields
    assert "source_url" in canonical_fields

    prepared, field_mapping = prepare_mapped_record(
        {
            "OBJECTID": 618063,
            "applicationNumber": 987744,
            "applicationType": "Residential Fire Sprinkler System",
            "applicationStatus": "Accepted",
            "parcelNumber": "0220072023",
            "workType": "Tenant Improvement",
            "buildingType": "Commercial",
            "projectValue": 125000,
            "applicationDate": 1769213242000,
            "workDescription": "Review for commercial tenant improvement",
            "siteAddress": "28926 31st AV E",
            "projectName": "Retail Pad",
            "urlOnlinePermits": "https://pals.piercecountywa.gov/palsonline/#/permitSearch/permit/departmentStatus?applPermitId=987744",
            "geometry": {"x": -122.60184784163869, "y": 47.241701901638855},
        },
        entry.field_mappings,
    )
    normalized = normalize_permit(
        prepared,
        field_mapping,
        defaults=entry.settings["defaults"],
    )

    assert normalized.source_record_id == "987744"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["project_name"] == "Retail Pad"
    assert float(normalized.values["longitude"]) == pytest.approx(-122.6018478)
    assert float(normalized.values["latitude"]) == pytest.approx(47.2417019)

    approved_prepared, approved_mapping = prepare_mapped_record(
        {
            "OBJECTID": 618064,
            "applicationNumber": 987745,
            "applicationType": "Commercial Building",
            "applicationStatus": "Issued",
            "applicationDate": 1769213242000,
            "approvalDate": 1769676431000,
            "issuedDate": 1769676490000,
            "siteAddress": "100 Market St",
            "workDescription": "Commercial shell permit",
        },
        entry.field_mappings,
    )
    assert normalize_permit(
        approved_prepared,
        approved_mapping,
        defaults=entry.settings["defaults"],
    ).values["approval_stage"] == "approved"


def test_bellingham_nonres_building_permits_preserve_application_stage_context():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "bellingham_wa_nonres_building_permits"
    )
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }
    suppressed = set(entry.settings["suppressed_fields"])

    assert entry.adapter == "arcgis"
    assert entry.record_type == "permit"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert entry.settings["connector"]["include_geometry"] is True
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    assert "New Construction Applied not yet Issued (in last year)" in (
        entry.settings["connector"]["where"]
    )
    assert entry.settings["canary_stage_probes"][0]["expected_stage"] == "pre_approval"
    assert entry.settings["canary_stage_probes"][1]["expected_stage"] == "approved"
    assert "OWNER_NAME" not in out_fields
    assert "APPLICANT_NAME" not in out_fields
    assert "CONTRACTOR_NAME" not in out_fields
    assert "FEES_CHARGED" not in out_fields
    assert suppressed.isdisjoint(out_fields)
    assert out_fields <= set(entry.settings["field_allowlist"])
    assert set(entry.settings["canary_required_fields"]) <= set(entry.settings["field_allowlist"])

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    applied = {
        "OBJECTID": 178399906,
        "PERMIT_NO": "BLD2025-0814",
        "PERMIT_CATEGORY": "BUILDING",
        "PERMIT_CLASS": "NONRESIDENTIAL",
        "APPLIED": 1757894400000,
        "APPROVED": None,
        "ISSUED": None,
        "FINALED": None,
        "EXPIRED": 1789689600000,
        "PARENT_PROJECT_NO": None,
        "PARENT_PERMIT_NO": None,
        "PermitType": "BUILDING NONRESIDENTIAL",
        "PermitSubType": "ADDITION",
        "STATUS": "REQUEST FOR INFO",
        "SITE_ADDR": "200 E CHESTNUT ST",
        "DESCRIPTION": "2 STORY OFFICE & KITCHEN ADDITION TO (E) RESTAURANT: FIAMMA",
        "JOBVALUE": 540321.42,
        "EXIST_FLOOR_AREA": None,
        "NEW_FLOOR_AREA": 2362,
        "TOTAL_FLOOR_AREA": 4962,
        "NUM_STORIES": None,
        "SCOPEOFWORK": None,
        "SITE_APN": "380330163051",
        "SITE_ALTERNATE_ID": None,
        "GEO_STATUS": "ACTIVE",
        "GIS_OBJECT_ID": 12345,
        "Occupancy_Class_1": None,
        "Floor_Area_1": None,
        "Occupancy_Class_2": None,
        "Floor_Area_2": None,
        "Neighborhood": "DOWNTOWN",
        "Zoning_Description": "Downtown District Urban Village",
        "Query_Result": "New Construction Applied not yet Issued (in last year)",
        "geometry": {"x": -122.47955604935133, "y": 48.74774419347438},
    }
    prepared, field_mapping = prepare_mapped_record(applied, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.source_record_id == "BLD2025-0814"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["permit_number"] == "BLD2025-0814"
    assert normalized.values["application_number"] == "BLD2025-0814"
    assert normalized.values["project_name"].startswith("200 E CHESTNUT ST")
    assert normalized.values["status"] == "REQUEST FOR INFO"
    assert normalized.values["permit_type"] == "BUILDING NONRESIDENTIAL"
    assert normalized.values["permit_subtype"] == "ADDITION"
    assert normalized.values["work_class"] == "NONRESIDENTIAL"
    assert normalized.values["parcel_id"] == "380330163051"
    assert normalized.values["filed_at"].isoformat() == "2025-09-15T00:00:00+00:00"
    assert normalized.values["expires_at"].isoformat() == "2026-09-18T00:00:00+00:00"
    assert normalized.values["valuation"] == Decimal("540321.42")
    assert normalized.values["square_feet"] == 2362
    assert normalized.values["longitude"].quantize(Decimal("0.000001")) == Decimal("-122.479556")
    assert normalized.values["latitude"].quantize(Decimal("0.000001")) == Decimal("48.747744")
    assert "OWNER_NAME" not in normalized.values
    assert "APPLICANT_NAME" not in normalized.values

    issued = {
        **applied,
        "OBJECTID": 178432051,
        "PERMIT_NO": "BLD2025-1094",
        "APPLIED": 1766016000000,
        "APPROVED": 1769990400000,
        "ISSUED": 1769990400000,
        "EXPIRED": 1833062400000,
        "STATUS": "ISSUED",
        "SITE_ADDR": "516 E HOLLY ST",
        "DESCRIPTION": "REMODEL & SMALL ADDITION TO (E) LOAN CENTER-WECU",
        "SITE_APN": "380330315006",
        "Query_Result": "New Construction Issued not yet Finaled ",
    }
    prepared, field_mapping = prepare_mapped_record(issued, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.values["approval_stage"] == "approved"
    assert normalized.values["approved_at"].isoformat() == "2026-02-02T00:00:00+00:00"
    assert normalized.values["issued_at"].isoformat() == "2026-02-02T00:00:00+00:00"


def test_delaware_dnrec_stormwater_noi_preserves_pre_approval_signal():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "delaware_dnrec_stormwater_noi"
    )
    canonical_fields = {mapping.canonical_field for mapping in entry.field_mappings}

    assert entry.adapter == "socrata"
    assert entry.record_type == "permit"
    assert entry.settings["license"] == "Public Domain"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert "planned construction activities" in entry.settings["rights_basis"]
    assert "owneroperator" in entry.settings["field_allowlist"]
    assert "owner_name" in canonical_fields

    prepared, field_mapping = prepare_mapped_record(
        {
            "permitnumber": "6744",
            "projectname": "203 HANSE CT",
            "owneroperator": "MGI LEASING INC",
            "project_location": "203 HANSEN CT",
            "datereceived": "2022-06-07T10:22:00.000",
            "projecttype": "Industrial",
            "delegateagency": "City Of Newark",
            "permitstatuscode": "Active",
            "latitude": "39.66",
            "longitude": "-75.78",
            "estimatedarea": "1.30",
            "constructcounty": "New Castle",
        },
        entry.field_mappings,
    )
    normalized = normalize_permit(
        prepared,
        field_mapping,
        defaults=entry.settings["defaults"],
    )

    assert normalized.source_record_id == "6744"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["project_name"] == "203 HANSE CT"
    assert normalized.values["owner_name"] == "MGI LEASING INC"
    assert float(normalized.values["latitude"]) == pytest.approx(39.66)
    assert float(normalized.values["longitude"]) == pytest.approx(-75.78)


def test_delaware_firstmap_parcels_are_narrow_geometry_context_only():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "delaware_firstmap_statewide_parcels_narrow"
    )
    suppressed = set(entry.settings["suppressed_fields"])
    allowlist = set(entry.settings["field_allowlist"])
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }
    mapped_fields = {mapping.source_field for mapping in entry.field_mappings}

    assert entry.adapter == "arcgis"
    assert entry.record_type == "parcel"
    assert entry.settings["license"] == "Public Domain"
    assert entry.settings["signal_stage"] == "parcel_context"
    assert entry.settings["connector"]["include_geometry"] is True
    assert entry.settings["connector"]["include_centroid"] is True
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    assert entry.settings["export_policy"] == (
        "derived_nearby_parcel_context_only_no_raw_delaware_firstmap_resale"
    )
    assert suppressed.isdisjoint(allowlist)
    assert suppressed.isdisjoint(out_fields)
    assert suppressed.isdisjoint(mapped_fields)
    assert "OWNER" not in out_fields
    assert "SALE_PRICE" not in mapped_fields

    prepared, field_mapping = prepare_mapped_record(
        {
            "OBJECTID": 17810643,
            "PIN": "0600500019",
            "ACRES": 0.29410104,
            "COUNTY": "New Castle",
            "UPDATED": 1782864000000,
            "centroid": {"x": -75.52104459228563, "y": 39.835052931073655},
            "geometry": {
                "rings": [[
                    [-75.52092528443355, 39.83522338557626],
                    [-75.52081899307417, 39.834910673876756],
                    [-75.52127695600264, 39.83496886694226],
                    [-75.52116505466434, 39.83526917634252],
                    [-75.52092528443355, 39.83522338557626],
                ]]
            },
        },
        entry.field_mappings,
    )
    normalized = normalize_parcel(
        prepared,
        field_mapping,
        defaults=entry.settings["defaults"],
    )

    assert normalized.source_record_id == "0600500019"
    assert normalized.values["parcel_group_id"] == "0600500019"
    assert normalized.values["county"] == "New Castle"
    assert normalized.values["state"] == "DE"
    assert float(normalized.values["latitude"]) == pytest.approx(39.8350529)
    assert float(normalized.values["longitude"]) == pytest.approx(-75.5210446)
    assert float(normalized.values["land_area_sq_ft"]) == pytest.approx(12811.44, rel=0.01)


def test_delaware_dnrec_septic_permits_are_narrow_site_readiness_context():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "delaware_dnrec_septic_permits_narrow"
    )
    suppressed = set(entry.settings["suppressed_fields"])
    allowlist = set(entry.settings["field_allowlist"])
    mapped_fields = {mapping.source_field for mapping in entry.field_mappings}

    assert entry.adapter == "socrata"
    assert entry.record_type == "permit"
    assert entry.settings["license"] == "Public Domain"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert "site-readiness context" in entry.settings["rights_basis"]
    assert suppressed.isdisjoint(allowlist)
    assert suppressed.isdisjoint(mapped_fields)
    assert "ownername" not in mapped_fields
    assert "designerlicensenumber" not in mapped_fields
    assert "contractor" in mapped_fields

    prepared, field_mapping = prepare_mapped_record(
        {
            "permitnumber": "283246",
            "taxparcelnumbers": "ED-00-056.00-01-29.05.000",
            "county": "Kent",
            "septicsystemtype": "Elevated Mound",
            "septicsystemsubtype": "Standard",
            "ownername": "Cmh Homes Inc",
            "designer": "Carbaugh, PE, Brian",
            "permitstatus": "Application Received",
            "constructiontype": "Replacement",
            "septicpropusecode": "4-bedroom",
            "flowrate": "480",
            "proposedsize": "1110",
            "minimumsize": "1104",
            "appreceiveddate": "2026-07-16T00:00:00.000",
            "pretreattype": "Septic Tank",
            "url_for_permit_details": "https://den.dnrec.delaware.gov/Detail/PermitDetail.aspx?id=60848750&Panel=ViewAll",
        },
        entry.field_mappings,
    )
    normalized = normalize_permit(
        prepared,
        field_mapping,
        defaults=entry.settings["defaults"],
    )

    assert normalized.source_record_id == "283246"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["parcel_id"] == "ED-00-056.00-01-29.05.000"
    assert normalized.values["jurisdiction"] == "Kent"
    assert normalized.values.get("owner_name") is None


def test_virginia_vgin_parcels_are_narrow_proximity_context_only():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "virginia_vgin_statewide_parcels_narrow"
    )
    suppressed = set(entry.settings["suppressed_fields"])
    allowlist = set(entry.settings["field_allowlist"])
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }
    mapped_fields = {mapping.source_field for mapping in entry.field_mappings}

    assert entry.adapter == "arcgis"
    assert entry.record_type == "parcel"
    assert entry.settings["signal_stage"] == "parcel_context"
    assert entry.settings["connector"]["include_geometry"] is True
    assert entry.settings["connector"]["include_centroid"] is True
    assert entry.settings["export_policy"] == (
        "derived_nearby_parcel_context_only_no_raw_vgin_parcel_resale"
    )
    assert suppressed.isdisjoint(allowlist)
    assert suppressed.isdisjoint(out_fields)
    assert suppressed.isdisjoint(mapped_fields)
    assert "Owner1" not in out_fields
    assert "M_Address" not in out_fields

    prepared, field_mapping = prepare_mapped_record(
        {
            "OBJECTID": 1,
            "VGIN_QPID": 5110500000734,
            "FIPS": "51105",
            "LOCALITY": "Lee County",
            "PARCELID": None,
            "PTM_ID": None,
            "LASTUPDATE": 1540958400000,
            "GPIN": None,
            "PIN": None,
            "Address": None,
            "City": None,
            "State": None,
            "Zip": None,
            "VGIN_Locality_Name": "Lee County",
            "centroid": {"x": -83.5801701470685, "y": 36.59760114118398},
            "geometry": {
                "rings": [[
                    [-83.57996717120515, 36.59760745451736],
                    [-83.5802353808084, 36.597584941783424],
                    [-83.58030788919194, 36.59761102725115],
                    [-83.57996717120515, 36.59760745451736],
                ]]
            },
        },
        entry.field_mappings,
    )
    normalized = normalize_parcel(
        prepared,
        field_mapping,
        defaults=entry.settings["defaults"],
    )

    assert normalized.source_record_id == "5110500000734"
    assert normalized.values["county"] == "Lee County"
    assert normalized.values["state"] == "VA"
    assert float(normalized.values["latitude"]) == pytest.approx(36.5976011)
    assert float(normalized.values["longitude"]) == pytest.approx(-83.5801701)


def test_fairfax_development_tracker_suppresses_internal_fields_and_maps_lifecycle():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "fairfax_county_va_development_tracker_site_records"
    )
    suppressed = set(entry.settings["suppressed_fields"])
    allowlist = set(entry.settings["field_allowlist"])
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }
    mapped_fields = {mapping.source_field for mapping in entry.field_mappings}

    assert entry.adapter == "arcgis"
    assert entry.record_type == "permit"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert entry.settings["connector"]["include_centroid"] is True
    assert entry.settings["export_policy"] == (
        "derived_fairfax_development_context_only_no_raw_plus_resale"
    )
    assert suppressed.isdisjoint(allowlist)
    assert suppressed.isdisjoint(out_fields)
    assert suppressed.isdisjoint(mapped_fields)
    assert "INSPECTOR_ASSIGNED" not in out_fields
    assert "last_edited_user" not in out_fields

    prepared, field_mapping = prepare_mapped_record(
        {
            "OBJECTID": 148,
            "GlobalID": "{6EC1FFE9-2DBF-49CD-8DB5-807FE39BE54D}",
            "RECORDID": "006553-CON-001-1",
            "APPTYPEALIAS": "Conservation Plan",
            "PROJECT_NAME": "MAYMONT SEC 2 LOT 31 [DR]",
            "PARCEL_ID": "0193 22  0031",
            "SUPERVISOR_DISTRICT": "HUNTER MILL",
            "RECORD_STATUS": "Application Accepted",
            "RECORD_STATUS_DATE": 1459814400000,
            "SUBMITTED_DATE": 1458864000000,
            "ACCEPTED_DATE": 1458864000000,
            "APPROVED_DATE": None,
            "PROJECT_STATUS": "Review",
            "ADDRESS_1": "9834 CORSINI CT",
            "CITY": "VIENNA",
            "STATE": "VA",
            "ZIP_CODE": "22182",
            "MAR_ADDRESS": "9834 CORSINI CT, VIENNA, VA, 22182",
            "PUBLIC_VIEW": "Yes",
            "LINK_URL": "https://plus.fairfaxcounty.gov/CitizenAccess/urlrouting.ashx?type=1000&Module=Site&capID1=16WW3&capID2=00000&capID3=00NLE&agencyCode=FFX&FromACA=Y",
            "CLOSED_DATE": None,
            "APPROVED_PLAN_LINK": None,
            "VALID_PARCEL_ID": "Yes",
            "DATA_CENTER": "NO",
            "TOTAL_DWELLING_UNITS": None,
            "centroid": {"x": -77.28366293357432, "y": 38.95785383971839},
        },
        entry.field_mappings,
    )
    normalized = normalize_permit(
        prepared,
        field_mapping,
        defaults=entry.settings["defaults"],
    )

    assert normalized.source_record_id == "006553-CON-001-1"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["project_name"] == "MAYMONT SEC 2 LOT 31 [DR]"
    assert normalized.values["parcel_id"] == "0193 22 0031"
    assert float(normalized.values["latitude"]) == pytest.approx(38.9578538)
    assert float(normalized.values["longitude"]) == pytest.approx(-77.2836629)

    approved_prepared, approved_mapping = prepare_mapped_record(
        {
            "OBJECTID": 149,
            "RECORDID": "006553-CON-001-2",
            "APPTYPEALIAS": "Conservation Plan",
            "PROJECT_NAME": "Approved Site",
            "PARCEL_ID": "0193 22  0032",
            "RECORD_STATUS": "Approved",
            "RECORD_STATUS_DATE": 1459814400000,
            "SUBMITTED_DATE": 1458864000000,
            "APPROVED_DATE": 1459814400000,
            "PROJECT_STATUS": "Inspection",
            "MAR_ADDRESS": "9836 CORSINI CT, VIENNA, VA, 22182",
            "LINK_URL": "https://plus.fairfaxcounty.gov/example",
            "centroid": {"x": -77.283, "y": 38.957},
        },
        entry.field_mappings,
    )
    assert normalize_permit(
        approved_prepared,
        approved_mapping,
        defaults=entry.settings["defaults"],
    ).values["approval_stage"] == "approved"


def test_norfolk_permit_records_use_distinct_permit_slice_and_preserve_pending_status():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "norfolk_va_permits_and_inspections_permit_records"
    )
    suppressed = set(entry.settings["suppressed_fields"])
    allowlist = set(entry.settings["field_allowlist"])
    select_clause = entry.settings["connector"]["query"]["$select"]
    mapped_fields = {mapping.source_field for mapping in entry.field_mappings}

    assert entry.adapter == "socrata"
    assert entry.record_type == "permit"
    assert entry.settings["license"] == "Public Domain"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert select_clause.startswith("DISTINCT ftpuser")
    assert "inspection_number" not in select_clause
    assert suppressed.isdisjoint(allowlist)
    assert suppressed.isdisjoint(mapped_fields)
    assert "inspection_status" not in mapped_fields

    prepared, field_mapping = prepare_mapped_record(
        {
            "ftpuser": "ZP26-01595",
            "permit_address": "244 GRANBY STREET",
            "permit_application_date": "2026-06-22T00:00:00.000",
            "permit_type": "Zoning",
            "permit_status": "Pending",
            "permit_use_class": "Commercial",
            "permit_work_type": "New",
            "permit_description": "",
            "permit_structure": "Business License Review",
            "permit_use_type": "Commercial",
            "permit_use_group": "R-3",
            "geocoded_column": {
                "type": "Point",
                "coordinates": [-76.29069435, 36.84918635],
            },
            "parcel_gpin": "1427963242",
        },
        entry.field_mappings,
    )
    normalized = normalize_permit(
        prepared,
        field_mapping,
        defaults=entry.settings["defaults"],
    )

    assert normalized.source_record_id == "ZP26-01595"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["occupancy_type"] == "Commercial"
    assert normalized.values["proposed_use"] == "Commercial"
    assert normalized.values["parcel_id"] == "1427963242"
    assert float(normalized.values["latitude"]) == pytest.approx(36.84918635)
    assert float(normalized.values["longitude"]) == pytest.approx(-76.29069435)


def test_norfolk_conditional_use_permits_are_effective_planning_context():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "norfolk_va_conditional_use_permits"
    )
    suppressed = set(entry.settings["suppressed_fields"])
    allowlist = set(entry.settings["field_allowlist"])
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }
    mapped_fields = {mapping.source_field for mapping in entry.field_mappings}

    assert entry.adapter == "arcgis"
    assert entry.record_type == "permit"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert "not a complete pending application queue" in entry.settings["rights_basis"]
    assert suppressed.isdisjoint(allowlist)
    assert suppressed.isdisjoint(out_fields)
    assert suppressed.isdisjoint(mapped_fields)
    assert "NOTES" not in out_fields
    assert "last_edited_user" not in out_fields

    prepared, field_mapping = prepare_mapped_record(
        {
            "OBJECTID": 4158,
            "CPCITEM": None,
            "ORDINANCE": None,
            "APPLICANT": "APPLEBEES NEIGHBORHOOD GRILL & BAR",
            "ADDRESS": "5750 E VIRGINIA BEACH BOULEVARD",
            "LINK": "https://gisshare.norfolk.gov/planning/pdf/.pdf",
            "TYPE": "Extended Hours, ABC On-Premises",
            "EFFECTIVE_DATE": 1783987200000,
            "EXPIRATION_DATE": None,
            "ENTERTAINMENT_TYPE": "No Entertainment",
            "LATEST_CLOSING_HOUR": "2:00 am",
            "geometry": {"x": -76.20777486519532, "y": 36.856192122365805},
        },
        entry.field_mappings,
    )
    normalized = normalize_permit(
        prepared,
        field_mapping,
        defaults=entry.settings["defaults"],
    )

    assert normalized.source_record_id == "4158"
    assert normalized.values["approval_stage"] == "approved"
    assert normalized.values["applicant_name"] == "APPLEBEES NEIGHBORHOOD GRILL & BAR"
    assert normalized.values["project_name"] == "APPLEBEES NEIGHBORHOOD GRILL & BAR"
    assert normalized.values["permit_type"] == "Extended Hours, ABC On-Premises"
    assert float(normalized.values["latitude"]) == pytest.approx(36.8561921)
    assert float(normalized.values["longitude"]) == pytest.approx(-76.2077749)


def test_virginia_beach_permits_use_status_not_issue_date_for_lifecycle():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "virginia_beach_va_building_permit_applications"
    )
    suppressed = set(entry.settings["suppressed_fields"])
    allowlist = set(entry.settings["field_allowlist"])
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }
    mapped_fields = {mapping.source_field for mapping in entry.field_mappings}

    assert entry.adapter == "arcgis"
    assert entry.record_type == "permit"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert "required modified-source disclaimer" in entry.settings["rights_basis"]
    assert suppressed.isdisjoint(allowlist)
    assert suppressed.isdisjoint(out_fields)
    assert suppressed.isdisjoint(mapped_fields)
    assert "CreatedBy" not in out_fields

    prepared, field_mapping = prepare_mapped_record(
        {
            "OBJECTID": 95892,
            "PermitNumber": "2026-BDCA-11397",
            "PermitType": "Building",
            "ConstructionType": "Commercial",
            "WorkType": "Addition and or Alteration",
            "ApplicationDate": "2026/04/29",
            "IssueDate": "2026/04/29",
            "FinalDate": None,
            "Status": "Pending Revisions",
            "WorkDesc": "ONE STORY COMMERCIAL STORAGE",
            "GPIN": "24162870810000",
            "StreetAddress": "1330 CREDLE RD",
            "AddressUnit": "",
            "City": "Virginia Beach",
            "State": "VA",
            "Zip": "23454",
        },
        entry.field_mappings,
    )
    normalized = normalize_permit(
        prepared,
        field_mapping,
        defaults=entry.settings["defaults"],
    )

    assert normalized.source_record_id == "2026-BDCA-11397"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["permit_subtype"] == "Commercial"
    assert normalized.values["parcel_id"] == "24162870810000"
    assert normalized.values["address"] == "1330 CREDLE RD"

    approved_prepared, approved_mapping = prepare_mapped_record(
        {
            "OBJECTID": 101755,
            "PermitNumber": "2026-GASC-18304",
            "PermitType": "Gas",
            "ConstructionType": "Commercial",
            "ApplicationDate": "2026/07/10",
            "IssueDate": "2026/07/10",
            "FinalDate": None,
            "Status": "Active",
            "WorkDesc": "Repair leak on gas line",
            "GPIN": "14965464480000",
            "StreetAddress": "833 SEAHAWK CIR",
            "City": "Virginia Beach",
            "State": "VA",
            "Zip": "23452",
        },
        entry.field_mappings,
    )
    assert normalize_permit(
        approved_prepared,
        approved_mapping,
        defaults=entry.settings["defaults"],
    ).values["approval_stage"] == "approved"


def test_lynchburg_development_projects_are_geocoded_pre_approval_context():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "lynchburg_va_development_projects_locations"
    )
    suppressed = set(entry.settings["suppressed_fields"])
    allowlist = set(entry.settings["field_allowlist"])
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }
    mapped_fields = {mapping.source_field for mapping in entry.field_mappings}

    assert entry.adapter == "arcgis"
    assert entry.record_type == "permit"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert "not inclusive because of join conflicts" in entry.settings["rights_basis"]
    assert entry.settings["connector"]["include_geometry"] is True
    assert suppressed.isdisjoint(allowlist)
    assert suppressed.isdisjoint(out_fields)
    assert suppressed.isdisjoint(mapped_fields)
    assert "Contact" not in out_fields
    assert "Owner_TRAKiT" not in out_fields

    prepared, field_mapping = prepare_mapped_record(
        {
            "OBJECTID": 11500,
            "Parcel_ID": "24605004",
            "LRSN": 24605004,
            "Address": "2735 WARDS RD",
            "RecordNo": "SPR2607-0001",
            "Name": "Wards Road Car Wash",
            "Type": "SITE PLAN",
            "SubType": "ADMIN REVIEW",
            "StartDate": 1783468800000,
            "EndDate": None,
            "Status": "AWAITING PAYMENT",
            "Neighborhood": "WARDS RD COMMERCIAL CORRIDOR",
            "geometry": {"x": -79.18130211895715, "y": 37.36033955899184},
        },
        entry.field_mappings,
    )
    normalized = normalize_permit(
        prepared,
        field_mapping,
        defaults=entry.settings["defaults"],
    )

    assert normalized.source_record_id == "SPR2607-0001"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["project_name"] == "Wards Road Car Wash"
    assert normalized.values["parcel_id"] == "24605004"
    assert float(normalized.values["latitude"]) == pytest.approx(37.3603396)
    assert float(normalized.values["longitude"]) == pytest.approx(-79.1813021)

    approved_prepared, approved_mapping = prepare_mapped_record(
        {
            "OBJECTID": 6881,
            "Parcel_ID": "02105042",
            "Address": "1456 RIVERMONT AVE",
            "RecordNo": "HPC2607-0003",
            "Name": "Paint, Gutters, Roof, Fence",
            "Type": "HISTORIC PRESERVE",
            "SubType": "ADMIN REVIEW",
            "StartDate": 1783209600000,
            "EndDate": None,
            "Status": "APPROVED",
            "Neighborhood": "MIDDLE RIVERMONT",
            "geometry": {"x": -79.15481260383768, "y": 37.431499200906586},
        },
        entry.field_mappings,
    )
    assert normalize_permit(
        approved_prepared,
        approved_mapping,
        defaults=entry.settings["defaults"],
    ).values["approval_stage"] == "approved"


def test_cary_development_applications_preserve_early_retail_context():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "cary_nc_development_applications"
    )
    suppressed = set(entry.settings["suppressed_fields"])
    allowlist = set(entry.settings["field_allowlist"])
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }
    mapped_fields = {mapping.source_field for mapping in entry.field_mappings}

    assert entry.adapter == "arcgis"
    assert entry.record_type == "permit"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert entry.settings["license"] == "CC0 1.0 Universal"
    assert "under review" in entry.settings["rights_basis"]
    assert entry.settings["connector"]["include_geometry"] is True
    assert suppressed.isdisjoint(allowlist)
    assert suppressed.isdisjoint(out_fields)
    assert suppressed.isdisjoint(mapped_fields)
    assert "SalesforceID" not in out_fields
    assert "GlobalID" not in out_fields

    prepared, field_mapping = prepare_mapped_record(
        {
            "OBJECTID": 40163,
            "ApplicationName": "7001 Weston Pkwy - Multi-Family and Retail",
            "ApplicationNumber": "26-DP-10884",
            "ApplicationDate": 1781568000000,
            "ActionDate": None,
            "Status": "In Review",
            "SummaryDescription": "Convert existing office bldg to 248 multi-family units & 3,100sf of retail",
            "IDTApplicationURL": "https://townofcary.geocivix.com/secure/project/?projectid=2206697",
            "FinalActionDocumentURL": None,
            "UseGroup": "Mixed - Commercial/Residential",
            "UseCategory": "Retail Sales & Service",
            "UseType": "Retail store",
            "ReviewType": "New plan",
            "PlanTier": "Tier 1",
            "TotalSqFt": 3100,
            "geometry": {
                "rings": [[
                    [-78.8120, 35.8300],
                    [-78.8110, 35.8300],
                    [-78.8110, 35.8310],
                    [-78.8120, 35.8310],
                    [-78.8120, 35.8300],
                ]]
            },
        },
        entry.field_mappings,
    )
    normalized = normalize_permit(
        prepared,
        field_mapping,
        defaults=entry.settings["defaults"],
    )

    assert normalized.source_record_id == "26-DP-10884"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["project_name"] == "7001 Weston Pkwy - Multi-Family and Retail"
    assert normalized.values["proposed_use"] == "Mixed - Commercial/Residential | Retail Sales & Service | Retail store"
    assert normalized.values["square_feet"] == 3100
    assert normalized.values["source_url"] == "https://townofcary.geocivix.com/secure/project/?projectid=2206697"
    assert float(normalized.values["latitude"]) == pytest.approx(35.8305)
    assert float(normalized.values["longitude"]) == pytest.approx(-78.8115)

    approved_prepared, approved_mapping = prepare_mapped_record(
        {
            "OBJECTID": 40166,
            "ApplicationName": "Atticus Improvements - Impervious Surface Revisions",
            "ApplicationNumber": "26-DP-6731-A",
            "ApplicationDate": 1781740800000,
            "ActionDate": 1782172800000,
            "Status": "Approved",
            "SummaryDescription": "Impervious area corrections",
            "ReviewType": "Project Modification",
            "PlanTier": "Tier 3",
            "TotalSqFt": 0,
        },
        entry.field_mappings,
    )
    assert normalize_permit(
        approved_prepared,
        approved_mapping,
        defaults=entry.settings["defaults"],
    ).values["approval_stage"] == "approved"


def test_cary_building_permit_applications_preserve_non_residential_preapproval():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "cary_nc_building_permit_applications"
    )
    suppressed = set(entry.settings["suppressed_fields"])
    allowlist = set(entry.settings["field_allowlist"])
    mapped_fields = {mapping.source_field for mapping in entry.field_mappings}

    assert entry.adapter == "opendatasoft"
    assert entry.record_type == "permit"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert entry.settings["license"] == "CC0 1.0 Universal"
    assert entry.settings["connector"]["query"] == {
        "where": "permitclassmapped = 'Non-Residential'"
    }
    assert "applications rather than individual permits" in entry.settings["rights_basis"]
    assert suppressed.isdisjoint(allowlist)
    assert suppressed.isdisjoint(mapped_fields)
    assert "contractorphone" not in mapped_fields
    assert "owneraddress1" not in mapped_fields

    prepared, field_mapping = prepare_mapped_record(
        {
            "permitnum": "26-00010569",
            "description": "INTERIOR ALTERATION",
            "statuscurrent": "IN PLAN CHECK (PC)",
            "statuscurrentmapped": "In Review",
            "applieddate": "2026-07-23",
            "issuedate": None,
            "completeddate": None,
            "statusdate": "2026-07-23",
            "originaladdress1": "3550 NW CARY PKWY 100",
            "originalcity": "CARY",
            "originalstate": "NC",
            "originalzip": "27513",
            "pin": "754357261",
            "permitclassmapped": "Non-Residential",
            "workclassmapped": "Existing",
            "permittypemapped": "Building",
            "permittypedesc": "INTERIOR ALTERATION (B105)",
            "projectcost": 200000,
            "totalsqft": 6000,
            "contractorcompanyname": None,
            "ownername": "JCG PTNR LLC",
            "latitude": 35.797443,
            "longitude": -78.818693,
            "_record_url": "https://data.townofcary.org/api/v2/catalog/datasets/permit-applications/records/example",
        },
        entry.field_mappings,
    )
    normalized = normalize_permit(
        prepared,
        field_mapping,
        defaults=entry.settings["defaults"],
    )

    assert normalized.source_record_id == "26-00010569"
    assert normalized.values["application_number"] == "26-00010569"
    assert normalized.values["permit_number"] == "26-00010569"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["description"] == "INTERIOR ALTERATION"
    assert normalized.values["owner_name"] == "JCG PTNR LLC"
    assert normalized.values["parcel_id"] == "754357261"
    assert normalized.values["valuation"] == 200000
    assert normalized.values["square_feet"] == 6000

    issued_prepared, issued_mapping = prepare_mapped_record(
        {
            "permitnum": "26-00006728",
            "description": "INT ALTERATIONS FOR AN EXISTING TENANT",
            "statuscurrent": "CERTICATE OF COMPLIANCE (CC)",
            "statuscurrentmapped": "Occupancy",
            "applieddate": "2026-02-09",
            "issuedate": "2026-04-14",
            "completeddate": "2026-07-16",
            "statusdate": "2026-07-16",
            "originaladdress1": "107 WOODWINDS INDUSTRIAL CT",
            "permitclassmapped": "Non-Residential",
        },
        entry.field_mappings,
    )
    assert normalize_permit(
        issued_prepared,
        issued_mapping,
        defaults=entry.settings["defaults"],
    ).values["approval_stage"] == "approved"


def test_miami_dade_wasd_permits_preserve_applied_retail_processes():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "miami_dade_fl_wasd_unincorporated_permits_narrow"
    )
    suppressed = set(entry.settings["suppressed_fields"])
    allowlist = set(entry.settings["field_allowlist"])
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }
    mapped_fields = {mapping.source_field for mapping in entry.field_mappings}

    assert entry.adapter == "arcgis"
    assert entry.record_type == "permit"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert "Florida AGO 2003-42" in entry.settings["rights_basis"]
    assert "PROJDESC LIKE '%RETAIL%'" in entry.settings["connector"]["where"]
    assert entry.settings["connector"]["page_size"] == 100
    assert entry.settings["connector"]["include_geometry"] is True
    assert suppressed.isdisjoint(allowlist)
    assert suppressed.isdisjoint(out_fields)
    assert suppressed.isdisjoint(mapped_fields)
    assert "MUNICURL" not in out_fields
    assert "GlobalID" not in out_fields

    prepared, field_mapping = prepare_mapped_record(
        {
            "OBJECTID": 429514,
            "ID": 567648,
            "EFFECTIVE": "Active",
            "MUNICID": "30",
            "PROJNAME": "BAL HARBOUR SHOPS LLC                             ",
            "PROJDESC": "RETAIL SALES                                      ",
            "PROJZIP": "          ",
            "BLDPRCNO": "M2026017062      ",
            "BLDPRCSTAT": "APPLIED     ",
            "BLDPRCISDT": 1780272000000,
            "BLDPRCSTDT": None,
            "BLDPRMNO": "                 ",
            "BLDPRMSTAT": "            ",
            "BLDPRMIDT": None,
            "BLDPRMSTDT": 1780272000000,
            "COTYPE": "     ",
            "CODATE": None,
            "EEOSNO": None,
            "WSCNO": None,
            "DEALLOCTYP": "Incomplete",
            "INSERTDATE": 1780887607000,
            "UPDATEDATE": None,
            "geometry": {"x": -80.12545032073432, "y": 25.88816880157457},
        },
        entry.field_mappings,
    )
    normalized = normalize_permit(
        prepared,
        field_mapping,
        defaults=entry.settings["defaults"],
    )

    assert normalized.source_record_id == "M2026017062"
    assert normalized.values["application_number"] == "M2026017062"
    assert "permit_number" not in normalized.values
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["project_name"] == "BAL HARBOUR SHOPS LLC"
    assert normalized.values["description"] == "RETAIL SALES"
    assert normalized.values["proposed_use"] == "RETAIL SALES"
    assert normalized.values["owner_name"] == "BAL HARBOUR SHOPS LLC"
    assert float(normalized.values["latitude"]) == pytest.approx(25.8881688)
    assert float(normalized.values["longitude"]) == pytest.approx(-80.1254503)

    issued_prepared, issued_mapping = prepare_mapped_record(
        {
            "OBJECTID": 424034,
            "EFFECTIVE": "Active",
            "PROJNAME": "MIAMI DADE COUNTY",
            "PROJDESC": "GOVERNMENT FACILITIES",
            "BLDPRCNO": "N2015171447",
            "BLDPRCSTAT": "APPLIED",
            "BLDPRCISDT": 1440460800000,
            "BLDPRMNO": "2014062937",
            "BLDPRMSTAT": "ACTIVE",
            "BLDPRMIDT": 1410307200000,
            "BLDPRMSTDT": 1447632000000,
        },
        entry.field_mappings,
    )
    issued = normalize_permit(
        issued_prepared,
        issued_mapping,
        defaults=entry.settings["defaults"],
    )
    assert issued.values["approval_stage"] == "approved"
    assert issued.values["permit_number"] == "2014062937"


def test_florida_dep_erp_preserves_commercial_pending_context():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "florida_dep_erp_applications_commercial_context"
    )
    suppressed = set(entry.settings["suppressed_fields"])
    allowlist = set(entry.settings["field_allowlist"])
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }
    mapped_fields = {mapping.source_field for mapping in entry.field_mappings}

    assert entry.adapter == "arcgis"
    assert entry.record_type == "permit"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert "does not replace municipal building-permit feeds" in entry.settings["rights_basis"]
    assert "PROJ_NAME LIKE '%RESTAURANT%'" in entry.settings["connector"]["where"]
    assert entry.settings["connector"]["order_by_fields"] == "OBJECTID DESC"
    approval_stage_mapping = next(
        mapping for mapping in entry.field_mappings
        if mapping.source_field == "__approval_stage"
    )
    assert "Issue: Pending Final Action" in approval_stage_mapping.transform_options["cases"][0]["values"]
    assert suppressed.isdisjoint(allowlist)
    assert suppressed.isdisjoint(out_fields)
    assert suppressed.isdisjoint(mapped_fields)
    assert "APP_NAME" not in out_fields
    assert "PROCESSOR" not in out_fields

    prepared, field_mapping = prepare_mapped_record(
        {
            "OBJECTID": 802664,
            "TEMP_ID": 802664,
            "APP_NO": "0418997-003-EI",
            "SITE_ID": "418997",
            "PROJ_NO": "003",
            "PROJ_NAME": "SHACK MOORING EXPANSION",
            "SITE_NAME": "THE SHACK RESTAURANT",
            "COMPANY": "KIT INVESTMENT OF FLORIDA, LLC",
            "ADDRESS": "4845 DIXIE HWY NE",
            "CITY": "PALM BAY",
            "ZIP5": 32905,
            "PER_TYPE": "EI",
            "PER_SUB": "E29",
            "PER_DESC": "<10 ac project area, <1 ac works, <10 boat slips",
            "RCVD_DATE": 1783382400000,
            "AGENCY_ACT": "Pending",
            "ACT_DATE": None,
            "EXPIR_DATE": None,
            "COMP_DATE": None,
            "PROJ_DESC": None,
            "DOCUMENTS": "https://prodenv.dep.state.fl.us/DepNexus/public/electronic-documents/ERP_418997/gis-facility!search",
            "REPORTS": "https://prodapps.dep.state.fl.us/pa/summarypending/PaDataNexus/printDetail?site_id=0418997&program1=ERP",
            "geometry": {"x": -80.6091205, "y": 28.0331524},
        },
        entry.field_mappings,
    )
    normalized = normalize_permit(
        prepared,
        field_mapping,
        defaults=entry.settings["defaults"],
    )

    assert normalized.source_record_id == "0418997-003-EI"
    assert normalized.values["application_number"] == "0418997-003-EI"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["project_name"] == "SHACK MOORING EXPANSION"
    assert normalized.values["applicant_name"] == "KIT INVESTMENT OF FLORIDA, LLC"
    assert normalized.values["source_url"].startswith("https://prodenv.dep.state.fl.us/")
    assert float(normalized.values["latitude"]) == pytest.approx(28.0331524)
    assert float(normalized.values["longitude"]) == pytest.approx(-80.6091205)

    effective_prepared, effective_mapping = prepare_mapped_record(
        {
            "OBJECTID": 803346,
            "APP_NO": "0473715-001-EG",
            "SITE_ID": "473715",
            "PROJ_NAME": "PHILCO- GUAVA DRIVE WAREHOUSE",
            "SITE_NAME": "Philco- Guava Drive Warehouse",
            "COMPANY": "ANDERSON-DIXON LLC",
            "ADDRESS": "2611 GUAVA DR",
            "CITY": "EDGEWATER",
            "PER_TYPE": "EG",
            "PER_SUB": "E10",
            "PER_DESC": "Water - ERP ESSA General Permit 10/2",
            "RCVD_DATE": 1783987200000,
            "AGENCY_ACT": "Effective",
            "ACT_DATE": 1783987200000,
            "geometry": {"x": -80.90031, "y": 28.96903},
        },
        entry.field_mappings,
    )
    assert normalize_permit(
        effective_prepared,
        effective_mapping,
        defaults=entry.settings["defaults"],
    ).values["approval_stage"] == "approved"


def test_washington_dc_dob_building_permits_preserve_pre_issuance_construction():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "washington_dc_dob_building_permits_2026"
    )

    suppressed = set(entry.settings["suppressed_fields"])
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }
    mapped_fields = {mapping.source_field for mapping in entry.field_mappings}

    assert entry.adapter == "arcgis"
    assert entry.record_type == "permit"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    assert entry.settings["connector"]["include_geometry"] is True
    assert "PERMIT_TYPE_NAME = 'CONSTRUCTION'" in entry.settings["connector"]["where"]
    assert "HOME OCCUPATION" not in entry.settings["connector"]["where"]
    assert entry.settings["canary_stage_probes"][0]["expected_stage"] == "pre_approval"
    assert "READY FOR ISSUANCE" in entry.settings["canary_stage_probes"][0]["connector"]["where"]
    assert suppressed.isdisjoint(out_fields)
    assert suppressed.isdisjoint(mapped_fields)

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    application = {
        "OBJECTID": 1119328466,
        "PERMIT_ID": "B2605595",
        "ISSUE_DATE": None,
        "PERMIT_TYPE_NAME": "CONSTRUCTION",
        "PERMIT_SUBTYPE_NAME": "ALTERATION AND REPAIR",
        "PERMIT_CATEGORY_NAME": "NA",
        "APPLICATION_STATUS_NAME": "READY FOR ISSUANCE",
        "FULL_ADDRESS": "1100 L ST NW, WASHINGTON, DC 20005",
        "DESC_OF_WORK": "Level 2 alteration of tenant office space.",
        "SSL": "0316    0032",
        "ZONING": "D-4-R",
        "PERMIT_APPLICANT": "CHRIS VU",
        "OWNER_NAME": "12TH & L STREETS LTD PARTNERSHIP",
        "LASTMODIFIEDDATE": 1784214258000,
        "geometry": {"x": -77.02754935813694, "y": 38.90355769255569},
    }
    prepared, field_mapping = prepare_mapped_record(application, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.source_record_id == "B2605595"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["parcel_id"] == "0316 0032"
    assert normalized.values["owner_name"] == "12TH & L STREETS LTD PARTNERSHIP"
    assert normalized.values["applicant_name"] == "CHRIS VU"
    assert normalized.values["latitude"] == Decimal("38.90355769255569")
    assert normalized.values["longitude"] == Decimal("-77.02754935813694")

    issued = {
        **application,
        "APPLICATION_STATUS_NAME": "PERMIT ISSUED",
        "ISSUE_DATE": 1784088000000,
    }
    prepared, field_mapping = prepare_mapped_record(issued, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])
    assert normalized.values["approval_stage"] == "approved"
    assert normalized.values["issued_at"].isoformat() == "2026-07-15T04:00:00+00:00"

    ready_with_issue_date = {
        **application,
        "APPLICATION_STATUS_NAME": "READY FOR ISSUANCE",
        "ISSUE_DATE": 1784088000000,
    }
    prepared, field_mapping = prepare_mapped_record(ready_with_issue_date, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])
    assert normalized.values["approval_stage"] == "pre_approval"


def test_washington_dc_basic_business_licenses_are_retail_opening_context():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "washington_dc_basic_business_licenses_retail_openings"
    )
    suppressed = set(entry.settings["suppressed_fields"])
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }
    mapped_fields = {mapping.source_field for mapping in entry.field_mappings}
    canonical_fields = {mapping.canonical_field for mapping in entry.field_mappings}

    assert entry.adapter == "arcgis"
    assert entry.record_type == "permit"
    assert entry.settings["signal_stage"] == "approved_only"
    assert entry.settings["retailer_opening_signal"] is True
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    assert "LICENSESTATUS = 'Active'" in entry.settings["connector"]["where"]
    assert "PREMISEINDC = 'Y'" in entry.settings["connector"]["where"]
    assert "Restaurant" in entry.settings["connector"]["where"]
    assert "BUSINESSOWNERFIRSTNAME" not in out_fields
    assert "AGENTENTITY" not in out_fields
    assert "BILLINGADDRESS" not in out_fields
    assert suppressed.isdisjoint(out_fields)
    assert suppressed.isdisjoint(mapped_fields)
    assert "owner_name" not in canonical_fields

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    license_row = {
        "OBJECTID": 13057241,
        "CUSTOMERNUMBER": "931326000183",
        "LICENSESTATUS": "Active",
        "LICENSETYPE": "Business License",
        "LICENSESUBTYPE": "Public Health Food Establish",
        "LICENSESTATUSDATE": 1782878400000,
        "LICENSESTARTDATE": 1782878400000,
        "LICENSEENDDATE": 1848628800000,
        "INITIALISSUEDATE": 1782878400000,
        "PRIMARYACTIVITY": "Restaurant",
        "BUSINESSACTIVITY": "Caterers",
        "PREMISEADDRESS": "1501 K ST NW, WASHINGTON, DC, 20005",
        "PREMISEINDC": "Y",
        "ENTITYNAME": "Maman 1501 K Street LLC",
        "ENTITYTRADENAME": "Maman",
        "ENTITYTYPE": "Limited Liability Company (LLC)",
        "DATAREFRESHEDON": 1784260800000,
        "SSL": "0198    0041,0198    0846",
        "LATITUDE": 38.9029524,
        "LONGITUDE": -77.03511817,
    }
    prepared, field_mapping = prepare_mapped_record(license_row, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.source_record_id == "931326000183:13057241"
    assert normalized.values["approval_stage"] == "approved"
    assert normalized.values["permit_number"] == "931326000183"
    assert normalized.values["project_name"] == "Maman"
    assert normalized.values["applicant_name"] == "Maman 1501 K Street LLC"
    assert normalized.values["parcel_id"] == "0198 0041,0198 0846"
    assert normalized.values["latitude"] == Decimal("38.9029524")
    assert normalized.values["longitude"] == Decimal("-77.03511817")
    assert normalized.values["approved_at"].isoformat() == "2026-07-01T04:00:00+00:00"
    assert normalized.values["status_updated_at"].isoformat() == "2026-07-17T04:00:00+00:00"


def test_new_york_sla_pending_licenses_are_preopening_context():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "new_york_state_sla_pending_licenses"
    )
    selected_fields = {
        field.strip()
        for field in entry.settings["connector"]["query"]["$select"].split(",")
    }
    suppressed = set(entry.settings["suppressed_fields"])

    assert entry.adapter == "socrata"
    assert entry.record_type == "permit"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert entry.settings["retailer_opening_signal"] is True
    assert entry.settings["opening_signal_date_field"] == "received_date"
    assert "license unspecified" in entry.settings["license"]
    assert entry.settings["freshness_field"] == "received_date"
    assert entry.settings["connector"]["keyset_fields"] == ["application_id"]
    assert entry.settings["canary_freshness_probe"]["connector"]["order_by"] == "received_date DESC"
    assert entry.settings["canary_freshness_probe"]["connector"]["keyset_fields"] is None
    assert "Conditionally Approved" in entry.settings["connector"]["query"]["$where"]
    assert entry.settings["canary_stage_probes"][0]["expected_stage"] == "pre_approval"
    assert entry.settings["canary_stage_probes"][1]["expected_stage"] == "approved"
    assert suppressed.isdisjoint(selected_fields)
    assert selected_fields <= set(entry.settings["field_allowlist"])

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    pending = {
        "application_id": "NA-0340-26-120427",
        "premises_county": "Nassau",
        "type": "1",
        "class": "340",
        "description": "Restaurant",
        "legalname": "Chipotle Mexican Grill of Colorado LLC",
        "dba": "Chipotle Mexican Grill",
        "actual_address_of_premises": "85 Henry St",
        "additional_address_information": None,
        "city": "Freeport",
        "state_name": "New York",
        "zip_code": "11520",
        "received_date": "2026-07-17T15:37:00.000",
        "status": "Under Review",
        "aka_address": None,
        "georeference": {
            "type": "Point",
            "coordinates": [-73.5792, 40.65521],
        },
    }
    prepared, field_mapping = prepare_mapped_record(pending, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.source_record_id == "NA-0340-26-120427"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["project_name"] == "Chipotle Mexican Grill"
    assert normalized.values["applicant_name"] == "Chipotle Mexican Grill of Colorado LLC"
    assert normalized.values["proposed_use"] == "Restaurant"
    assert normalized.values["longitude"] == Decimal("-73.5792")
    assert normalized.values["latitude"] == Decimal("40.65521")

    conditional = {**pending, "status": "Conditionally Approved"}
    prepared, field_mapping = prepare_mapped_record(conditional, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.values["approval_stage"] == "approved"


def test_washington_dc_owner_parcels_capture_phase_two_acquisition_context():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "washington_dc_owner_parcels_nearby"
    )
    suppressed = set(entry.settings["suppressed_fields"])
    allowlist = set(entry.settings["field_allowlist"])
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }
    mapped_fields = {mapping.source_field for mapping in entry.field_mappings}

    assert entry.adapter == "arcgis"
    assert entry.record_type == "parcel"
    assert entry.settings["signal_stage"] == "parcel_context"
    assert entry.settings["refresh_frequency"] == "daily"
    assert entry.settings["connector"]["include_centroid"] is True
    assert entry.settings["connector"].get("include_geometry") is None
    assert "raw polygon export" in entry.settings["rights_basis"]
    assert "MORTGAGECO" not in out_fields
    assert "ANNUALTAX" not in out_fields
    assert suppressed.isdisjoint(allowlist)
    assert suppressed.isdisjoint(out_fields)
    assert suppressed.isdisjoint(mapped_fields)

    prepared, field_mapping = prepare_mapped_record(
        {
            "OBJECTID": 7335931,
            "SSL": "PAR 01550037",
            "PREMISEADD": "2935 MILLS AVE NE WASHINGTON DC 20018",
            "OWNERNAME": "TERRY, LISA",
            "ADDRESS1": "351 TENNESSEE AVE NE",
            "ADDRESS2": None,
            "CITYSTZIP": "WASHINGTON DC 20002-6445",
            "PROPTYPE": "Residential-Single Family (Det",
            "USECODE": "012",
            "LANDAREA": 8250,
            "NEWLAND": 371420,
            "NEWIMPR": 681380,
            "NEWTOTAL": 1052800,
            "SALEPRICE": 0,
            "SALEDATE": 1129780800000,
            "VACLNDUSE": "Vacant",
            "EXTRACTDAT": 1775448000000,
            "LAST_EDITED_DATE": 1773080339000,
            "centroid": {"x": -76.97335965437271, "y": 38.928317904070155},
        },
        entry.field_mappings,
    )
    normalized = normalize_parcel(
        prepared,
        field_mapping,
        defaults=entry.settings["defaults"],
    )

    assert normalized.source_record_id == "PAR 01550037"
    assert normalized.values["parcel_group_id"] == "PAR 01550037"
    assert normalized.values["address"] == "2935 MILLS AVE NE WASHINGTON DC 20018"
    assert normalized.values["owner_name"] == "TERRY, LISA"
    assert normalized.values["owner_mailing_address"] == "351 TENNESSEE AVE NE, WASHINGTON DC 20002-6445"
    assert normalized.values["land_area_sq_ft"] == 8250
    assert normalized.values["land_value"] == 371420
    assert normalized.values["improvement_value"] == 681380
    assert normalized.values["total_assessed_value"] == 1052800
    assert normalized.values["last_sale_date"].year == 2005
    assert normalized.values["last_sale_price"] == 0
    assert normalized.values["vacancy_indicator"] == "Vacant"
    assert normalized.values["land_use"] == "Residential-Single Family (Det | 012"
    assert float(normalized.values["latitude"]) == pytest.approx(38.928317904070155)
    assert float(normalized.values["longitude"]) == pytest.approx(-76.97335965437271)


def test_massachusetts_massgis_parcels_use_centroids_and_suppress_raw_exports():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "massachusetts_massgis_l3_property_tax_parcels"
    )

    suppressed = set(entry.settings["suppressed_fields"])
    allowlist = set(entry.settings["field_allowlist"])
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }
    mapped_fields = {mapping.source_field for mapping in entry.field_mappings}

    assert entry.adapter == "arcgis"
    assert entry.record_type == "parcel"
    assert entry.settings["signal_stage"] == "parcel_context"
    assert entry.settings["connector"]["include_centroid"] is True
    assert entry.settings["connector"].get("include_geometry") is None
    assert "raw polygon source-replacement export" in entry.settings["rights_basis"]
    assert "OWN_ADDR" not in out_fields
    assert "LS_BOOK" not in out_fields
    assert suppressed.isdisjoint(allowlist)
    assert suppressed.isdisjoint(out_fields)
    assert suppressed.isdisjoint(mapped_fields)

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    parcel = {
        "OBJECTID": 1,
        "TOWN_ID": 80,
        "MAP_PAR_ID": "119_193_000_000",
        "POLY_TYPE": "FEE",
        "USE_CODE": "1010",
        "SITE_ADDR": "96 WEST MAIN ST",
        "CITY": "DUDLEY",
        "ZIP": "01571",
        "OWNER1": "EKBERG, DONNA MARIE",
        "BLDG_VAL": 238200,
        "LAND_VAL": 77700,
        "TOTAL_VAL": 322100,
        "FY": 2026,
        "LS_DATE": "19860211",
        "LS_PRICE": 0,
        "ZONING": "B15",
        "BLD_AREA": 2402,
        "GlobalID": "9b040210-f40d-449e-8520-b84fe5ad20de",
        "centroid": {"x": -71.89992893203083, "y": 42.04488415648192},
    }
    prepared, field_mapping = prepare_mapped_record(parcel, mappings)
    normalized = normalize_parcel(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.source_record_id == "9b040210-f40d-449e-8520-b84fe5ad20de"
    assert normalized.values["parcel_group_id"] == "80:119_193_000_000"
    assert normalized.values["address"] == "96 WEST MAIN ST"
    assert normalized.values["owner_name"] == "EKBERG, DONNA MARIE"
    assert normalized.values["land_use"] == "1010 | FEE | 2026"
    assert normalized.values["last_sale_date"].isoformat() == "1986-02-11T00:00:00+00:00"
    assert normalized.values["latitude"] == Decimal("42.04488415648192")
    assert normalized.values["longitude"] == Decimal("-71.89992893203083")


def test_cook_county_assessor_parcels_admit_current_year_context_spine_only():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "cook_county_il_assessor_parcels_current_year_nearby"
    )
    suppressed = set(entry.settings["suppressed_fields"])
    allowlist = set(entry.settings["field_allowlist"])
    selected_fields = {
        field.strip()
        for field in entry.settings["connector"]["query"]["$select"].split(",")
    }
    mapped_fields = {mapping.source_field for mapping in entry.field_mappings}

    assert entry.adapter == "socrata"
    assert entry.record_type == "parcel"
    assert entry.settings["signal_stage"] == "parcel_context"
    assert entry.settings["refresh_frequency"] == "bi-weekly"
    assert entry.settings["export_policy"] == (
        "derived_geometry_context_only_no_raw_assessor_source_resale"
    )
    assert entry.settings["connector"]["keyset_fields"] == ["row_id"]
    assert "address, owner, value, and deed enrichment" in entry.settings["rights_basis"].casefold()
    assert "lat IS NOT NULL" in entry.settings["connector"]["query"]["$where"]
    assert "lon IS NOT NULL" in entry.settings["connector"]["query"]["$where"]
    assert suppressed.isdisjoint(allowlist)
    assert suppressed.isdisjoint(selected_fields)
    assert suppressed.isdisjoint(mapped_fields)
    assert selected_fields <= allowlist
    assert "owner_name" not in {mapping.canonical_field for mapping in entry.field_mappings}
    assert "total_assessed_value" not in {mapping.canonical_field for mapping in entry.field_mappings}

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    parcel = {
        "pin": "17032270241105",
        "pin10": "1703227024",
        "row_id": "170322702411052026",
        "year": "2026.0",
        "class": "299",
        "township_name": "North Chicago",
        "zip_code": "60611",
        "lat": "41.897883532",
        "lon": "-87.6206525272",
        "cook_municipality_name": "CITY OF CHICAGO",
        "chicago_community_area_name": "NEAR NORTH SIDE",
        "chicago_industrial_corridor_name": "",
        "econ_qualified_opportunity_zone_num": "17031081403",
        "tax_tif_district_name": "",
    }
    prepared, field_mapping = prepare_mapped_record(parcel, mappings)
    normalized = normalize_parcel(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.source_record_id == "170322702411052026"
    assert normalized.values["parcel_group_id"] == "1703227024"
    assert normalized.values["postal_code"] == "60611"
    assert normalized.values["land_use"] == (
        "299 | North Chicago | CITY OF CHICAGO | NEAR NORTH SIDE | 17031081403"
    )
    assert normalized.values["latitude"] == Decimal("41.897883532")
    assert normalized.values["longitude"] == Decimal("-87.6206525272")


def test_los_angeles_submitted_building_permits_preserve_pre_issuance_retail_context():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "los_angeles_ca_building_permits_submitted"
    )
    selected_fields = {
        field.strip()
        for field in entry.settings["connector"]["query"]["$select"].split(",")
    }
    suppressed = set(entry.settings["suppressed_fields"])

    assert entry.adapter == "socrata"
    assert entry.record_type == "permit"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert entry.settings["refresh_frequency"] == "daily"
    assert entry.settings["freshness_field_candidate"] == "refresh_time"
    assert "2026-07-12" in entry.settings["freshness_enforcement_hold"]
    assert "freshness_field" not in entry.settings
    assert entry.settings["connector"]["order_by"] == "submitted_date DESC, permit_nbr ASC"
    assert "permit_sub_type = 'Commercial'" in entry.settings["connector"]["query"]["$where"]
    assert "Ready to Issue" in entry.settings["connector"]["query"]["$where"]
    assert "raw source-replacement resale" in entry.settings["rights_basis"]
    assert suppressed.isdisjoint(selected_fields)
    assert selected_fields <= set(entry.settings["field_allowlist"])

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    submitted = {
        "permit_nbr": "26016-10000-15835",
        "primary_address": "6081 W CENTER DR 202B-202C",
        "zip_code": "90045",
        "apn": "4104001035",
        "zone": "C2-1",
        "permit_type": "Bldg-Alter/Repair",
        "permit_sub_type": "Commercial",
        "use_desc": "Retail",
        "submitted_date": "2026-07-10T00:00:00.000",
        "issue_date": None,
        "status_desc": "Submitted",
        "status_date": "2026-07-10T00:00:00.000",
        "valuation": "50000",
        "square_footage": "2400",
        "business_unit": "Regular Plan Check",
        "work_desc": "CHANGE OF USE FROM RETAIL TO GYM IN PREPARATION OF FUTURE TENANT",
        "lat": "33.97811",
        "lon": "-118.39245",
        "refresh_time": "2026-07-12T00:00:00.000",
    }
    prepared, field_mapping = prepare_mapped_record(submitted, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.source_record_id == "26016-10000-15835"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["status"] == "Submitted"
    assert normalized.values["permit_number"] == "26016-10000-15835"
    assert normalized.values["parcel_id"] == "4104001035"
    assert normalized.values["project_name"] == "6081 W CENTER DR 202B-202C - Retail"
    assert normalized.values["valuation"] == Decimal("50000")
    assert normalized.values["square_feet"] == 2400
    assert normalized.values["latitude"] == Decimal("33.97811")
    assert normalized.values["longitude"] == Decimal("-118.39245")

    issued = {
        **submitted,
        "permit_nbr": "26016-10000-15835-ISSUED",
        "status_desc": "Issued",
        "issue_date": "2026-07-15T00:00:00.000",
    }
    prepared, field_mapping = prepare_mapped_record(issued, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.values["approval_stage"] == "approved"
    assert normalized.values["status"] == "Issued"
    assert normalized.values["issued_at"].isoformat() == "2026-07-15T00:00:00+00:00"


def test_nyc_dohmh_restaurant_permit_applicants_preserve_pre_inspection_chain_signals():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "new_york_ny_dohmh_restaurant_permit_applicants"
    )
    selected_fields = {
        field.strip()
        for field in entry.settings["connector"]["query"]["$select"].split(",")
    }
    suppressed = set(entry.settings["suppressed_fields"])

    assert entry.adapter == "socrata"
    assert entry.record_type == "permit"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert entry.settings["defaults"]["approval_stage"] == "pre_approval"
    assert "inspection_date = '1900-01-01T00:00:00'" in entry.settings["connector"]["query"]["$where"]
    assert "phone" not in selected_fields
    assert "grade" not in selected_fields
    assert suppressed.isdisjoint(selected_fields)
    assert selected_fields <= set(entry.settings["field_allowlist"])
    assert "before inspection/grade activity" in entry.settings["rights_basis"]

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    applicant = {
        ":id": "row-gw3u_ck4n-7u9i",
        "camis": "50182600",
        "dba": "BROOKLYN DUMPLING SHOP",
        "boro": "Manhattan",
        "building": "235",
        "street": "WEST   46 STREET",
        "zipcode": "10036",
        "cuisine_description": "Chinese",
        "inspection_date": "1900-01-01T00:00:00.000",
        "action": None,
        "inspection_type": None,
        "record_date": "2026-07-17T06:00:15.000",
        "bin": "1024737",
        "bbl": "1010180006",
        "latitude": "40.759124635911",
        "longitude": "-73.986348218206",
    }
    prepared, field_mapping = prepare_mapped_record(applicant, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.source_record_id == "row-gw3u_ck4n-7u9i"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["application_number"] == "50182600"
    assert normalized.values["permit_number"] == "50182600"
    assert normalized.values["project_name"] == "BROOKLYN DUMPLING SHOP"
    assert normalized.values["description"] == "BROOKLYN DUMPLING SHOP | Chinese | Manhattan"
    assert normalized.values["address"] == "235 WEST 46 STREET"
    assert normalized.values["parcel_id"] == "1010180006"
    assert normalized.values["filed_at"].isoformat() == "2026-07-17T06:00:15+00:00"
    assert normalized.values["latitude"] == Decimal("40.759124635911")
    assert normalized.values["longitude"] == Decimal("-73.986348218206")


def test_boston_article_80_projects_preserve_pre_approval_development_review():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "boston_ma_article_80_development_projects"
    )
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }
    suppressed = set(entry.settings["suppressed_fields"])

    assert entry.adapter == "arcgis"
    assert entry.record_type == "permit"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert entry.settings["connector"]["keyset_field"] == "objectid"
    assert "Under Review" in entry.settings["connector"]["where"]
    assert "NOT LIKE '%TEST%'" in entry.settings["connector"]["where"]
    assert entry.settings["canary_stage_probes"][0]["expected_stage"] == "pre_approval"
    assert suppressed.isdisjoint(out_fields)
    assert out_fields <= set(entry.settings["field_allowlist"])

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    project = {
        "objectid": 348999,
        "project_id": 5027,
        "project__project_name": "408 South Huntington Avenue",
        "project_status": "Under Review",
        "project__record_type": "Large Project",
        "project_street_number": "408",
        "project_street_name": "South Huntington",
        "project_street_suffix": "Avenue",
        "project_zip_code": "02130",
        "neighborhood": "Jamaica Plain",
        "last_filed_date": "2026-07-16",
        "last_board_approved_date": None,
        "coo_permit_date": None,
        "project_uses": "Residential",
        "gross_square_footage": 92500,
        "total_development_cost": 42000000,
        "description": "Demolition of existing 1-story commercial building and new 5-story multifamily building.",
        "website_url": "https://www.bostonplans.org/projects/development-projects/408-south-huntington-avenue",
        "latitude": 42.3301,
        "longitude": -71.1112,
    }
    prepared, field_mapping = prepare_mapped_record(project, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.source_record_id == "5027"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["application_number"] == "5027"
    assert normalized.values["project_name"] == "408 South Huntington Avenue"
    assert normalized.values["address"] == "408 South Huntington Avenue"
    assert normalized.values["status"] == "Under Review"
    assert normalized.values["filed_at"].isoformat() == "2026-07-16T00:00:00+00:00"
    assert normalized.values["valuation"] == Decimal("42000000")
    assert normalized.values["square_feet"] == 92500

    approved = {
        **project,
        "project_id": 4272,
        "project_status": "Board Approved",
        "last_board_approved_date": "2026-07-18",
    }
    prepared, field_mapping = prepare_mapped_record(approved, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.values["approval_stage"] == "approved"
    assert normalized.values["approved_at"].isoformat() == "2026-07-18T00:00:00+00:00"


def test_sacramento_commercial_applied_current_year_preserves_pre_approval_context():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "sacramento_ca_commercial_building_permits_applied_current_year"
    )
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }
    suppressed = set(entry.settings["suppressed_fields"])

    assert entry.adapter == "arcgis"
    assert entry.record_type == "permit"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    assert "Type = 'Commercial'" in entry.settings["connector"]["where"]
    assert entry.settings["canary_stage_probes"][0]["expected_stage"] == "pre_approval"
    assert "Ready-to-Issue" in entry.settings["canary_stage_probes"][0]["connector"]["where"]
    assert suppressed.isdisjoint(out_fields)
    assert out_fields <= set(entry.settings["field_allowlist"])

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    applied = {
        "OBJECTID": 10900,
        "Type": "Commercial",
        "Sub_Type": "Remodel",
        "Category": "Retail Store",
        "Application": "COM-2613499",
        "Rpt_Status": "Applied",
        "Status_Date": "06/26/2026",
        "Current_Status": "Applied",
        "Parcel_No": "00601050090000",
        "Address": "1020 12TH ST 110",
        "Site_Location": None,
        "ZIP": "95814",
        "Project_Sq_Ft": 650,
        "Valuation": 50000,
        "Activity_Code": "B1 ALTER/REPAIR",
        "Contractor": None,
        "Work_Desc": "EPC - EXPEDITED - Accessibility restroom upgrade to existing nonconforming condition.",
        "Project_Name": "Remodel Cafe, unleased",
    }
    prepared, field_mapping = prepare_mapped_record(applied, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.source_record_id == "COM-2613499"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["application_number"] == "COM-2613499"
    assert normalized.values["permit_number"] == "COM-2613499"
    assert normalized.values["proposed_use"] == "Retail Store"
    assert normalized.values["work_class"] == "B1 ALTER/REPAIR"
    assert normalized.values["project_name"] == "Remodel Cafe, unleased"
    assert normalized.values["address"] == "1020 12TH ST 110"
    assert normalized.values["parcel_id"] == "00601050090000"
    assert normalized.values["filed_at"].isoformat() == "2026-06-26T00:00:00+00:00"
    assert normalized.values["valuation"] == Decimal("50000")
    assert normalized.values["square_feet"] == 650

    approved = {
        **applied,
        "Application": "COM-2613500",
        "Current_Status": "Finaled",
    }
    prepared, field_mapping = prepare_mapped_record(approved, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.values["approval_stage"] == "approved"


def test_nashville_planning_development_applications_preserve_pending_review_context():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "nashville_tn_planning_development_applications"
    )
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }
    suppressed = set(entry.settings["suppressed_fields"])

    assert entry.adapter == "arcgis"
    assert entry.record_type == "permit"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert entry.settings["connector"]["include_geometry"] is True
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    assert "PSTAT IN ('New','Pending','Active','Complete')" in entry.settings["connector"]["where"]
    assert entry.settings["canary_stage_probes"][0]["expected_stage"] == "pre_approval"
    assert "APP_EMAIL" not in out_fields
    assert "APP_PHONE_BUS" not in out_fields
    assert suppressed.isdisjoint(out_fields)
    assert out_fields <= set(entry.settings["field_allowlist"])

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    pending = {
        "OBJECTID": 576,
        "PERTYPE": "Specific Plan Amendment",
        "DATE_ACCEPTED": 1784118581000,
        "MPCNUM": "2008SP-013-001",
        "BILLNUM": "",
        "PROJECT_DESC": "BUCHANAN POINT SP",
        "LOCATION_DESC": "555 MCCRORY CREEK RD 37214",
        "MPC_DATE": 1787806800000,
        "READ3_DATE": None,
        "READ3": None,
        "CD": "15 (Jeff Gregg)",
        "CAPTION": "A request to amend a Specific Plan to permit industrial and commercial uses.",
        "PSTAT": "New",
        "READ2_DATE": None,
        "MPC_ACTION_DESC": None,
        "READ2": None,
        "READ1_DATE": None,
        "READ1": None,
        "Parcels": "Map 096, Parcel(s) 020-023, 025, 026",
        "Acreage": "188.53",
        "ExistingZoning": "R10; SP",
        "NewZoning": None,
        "CommunityPlan": "14, Donelson - Hermitage - Old Hickory",
        "geometry": {"x": -86.65229090644056, "y": 36.147133559952785},
    }
    prepared, field_mapping = prepare_mapped_record(pending, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.source_record_id == "2008SP-013-001"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["application_number"] == "2008SP-013-001"
    assert normalized.values["permit_number"] == "2008SP-013-001"
    assert normalized.values["permit_subtype"] == "Specific Plan Amendment"
    assert normalized.values["project_name"] == "BUCHANAN POINT SP"
    assert normalized.values["address"] == "555 MCCRORY CREEK RD 37214"
    assert normalized.values["parcel_id"] == "Map 096, Parcel(s) 020-023, 025, 026"
    assert normalized.values["status"] == "New"
    assert normalized.values["filed_at"].isoformat() == "2026-07-15T12:29:41+00:00"
    assert normalized.values["latitude"] == Decimal("36.147133559952785")
    assert normalized.values["longitude"] == Decimal("-86.65229090644056")
    assert "CommunityPlan" in normalized.unmapped
    assert "APP_EMAIL" not in normalized.values

    approved = {
        **pending,
        "MPCNUM": "2026SP-001-001",
        "PSTAT": "Complete",
        "MPC_ACTION_DESC": "Approved by MPC",
        "READ3": "PASS3RD",
        "READ3_DATE": 1784361600000,
    }
    prepared, field_mapping = prepare_mapped_record(approved, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.values["approval_stage"] == "approved"
    assert normalized.values["approved_at"].isoformat() == "2026-07-18T08:00:00+00:00"


def test_raleigh_development_plans_preserve_preapproval_retail_chain_context():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "raleigh_nc_development_plans"
    )
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }
    suppressed = set(entry.settings["suppressed_fields"])

    assert entry.adapter == "arcgis"
    assert entry.record_type == "permit"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert entry.settings["connector"]["include_geometry"] is True
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    assert "status IN ('Submitted - Online','In Review','Approved')" in entry.settings["connector"]["where"]
    assert entry.settings["canary_stage_probes"][0]["expected_stage"] == "pre_approval"
    assert "Submitted - Online" in entry.settings["canary_stage_probes"][0]["connector"]["where"]
    assert "GlobalID" not in out_fields
    assert suppressed.isdisjoint(out_fields)
    assert out_fields <= set(entry.settings["field_allowlist"])

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    preapproval = {
        "OBJECTID": 54325,
        "submitted": 1783958796523,
        "approved": None,
        "updated": 1784211052207,
        "plan_type": "DSLC - Preliminary Subdivision",
        "status": "In Review",
        "acreage": 8.93,
        "major_street": "9800 Falls Of Neuse Rd",
        "developer": "Blew & Associates, P.A.",
        "plan_name": "DSLC - 7 BREW OF RALEIGH",
        "lots_req": 2,
        "sq_ft_req": None,
        "units_req": None,
        "zoning": "",
        "plan_number": "SUB-0040-2026",
        "geometry": {"x": -78.6001225135742, "y": 35.90674353926273},
    }
    prepared, field_mapping = prepare_mapped_record(preapproval, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.source_record_id == "SUB-0040-2026"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["application_number"] == "SUB-0040-2026"
    assert normalized.values["permit_number"] == "SUB-0040-2026"
    assert normalized.values["project_name"] == "DSLC - 7 BREW OF RALEIGH"
    assert normalized.values["developer_name"] == "Blew & Associates, P.A."
    assert normalized.values["address"] == "9800 Falls Of Neuse Rd"
    assert normalized.values["status"] == "In Review"
    assert normalized.values["permit_type"] == "Development plan"
    assert normalized.values["permit_subtype"] == "DSLC - Preliminary Subdivision"
    assert normalized.values["proposed_use"] == "DSLC - Preliminary Subdivision"
    assert normalized.values["filed_at"].isoformat() == "2026-07-13T16:06:36.523000+00:00"
    assert normalized.values["status_updated_at"].isoformat() == "2026-07-16T14:10:52.207000+00:00"
    assert normalized.values["latitude"] == Decimal("35.90674353926273")
    assert normalized.values["longitude"] == Decimal("-78.6001225135742")
    assert "acreage" in normalized.unmapped
    assert "GlobalID" not in normalized.values

    approved = {
        **preapproval,
        "plan_number": "ASR-0099-2026",
        "status": "Approved",
        "approved": 1784361600000,
    }
    prepared, field_mapping = prepare_mapped_record(approved, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.values["approval_stage"] == "approved"
    assert normalized.values["approved_at"].isoformat() == "2026-07-18T08:00:00+00:00"


def test_charlotte_rezoning_petitions_preserve_preapproval_chain_context():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "charlotte_nc_rezoning_petitions"
    )
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }
    suppressed = set(entry.settings["suppressed_fields"])

    assert entry.adapter == "arcgis"
    assert entry.record_type == "permit"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert entry.settings["export_policy"] == "derived_centroid_and_case_context_only_no_raw_geometry_export"
    assert entry.settings["connector"]["include_geometry"] is True
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    assert "Received >= TIMESTAMP '2024-01-01 00:00:00'" in entry.settings["connector"]["where"]
    assert entry.settings["canary_stage_probes"][0]["expected_stage"] == "pre_approval"
    assert "Status = 'Pen'" in entry.settings["canary_stage_probes"][0]["connector"]["where"]
    assert len(entry.settings["canary_stage_probes"]) == 1
    assert "created_user" not in out_fields
    assert "RezoneStaff" not in out_fields
    assert suppressed.isdisjoint(out_fields)
    assert out_fields <= set(entry.settings["field_allowlist"])

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    petition = {
        "OBJECTID": 27499,
        "Petition": "2026-034",
        "Petitioner": "Sam's Mart, LLC",
        "ExistZone": "N1-A",
        "ReqZone": "ML-1(CD)",
        "Type": "CD",
        "SPA": None,
        "Acres": 7.51,
        "Received": 1778817600000,
        "Approved": None,
        "Status": "Pen",
        "Hyperlink": "https://www.charlottenc.gov/Growth-and-Development/Planning-and-Development/Rezoning/2026/2026-034",
        "Propluse": None,
        "geometry": {
            "rings": [
                [
                    [-80.6502351037746, 35.24593744600604],
                    [-80.65017659217126, 35.24561394432064],
                    [-80.64967129682668, 35.24574101457934],
                    [-80.64973882972543, 35.24607107177273],
                    [-80.6502351037746, 35.24593744600604],
                ]
            ]
        },
    }
    prepared, field_mapping = prepare_mapped_record(petition, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.source_record_id == "2026-034"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["application_number"] == "2026-034"
    assert normalized.values["permit_number"] == "2026-034"
    assert normalized.values["project_name"] == "2026-034 - Sam's Mart, LLC"
    assert normalized.values["developer_name"] == "Sam's Mart, LLC"
    assert normalized.values["applicant_name"] == "Sam's Mart, LLC"
    assert normalized.values["status"] == "Pen"
    assert normalized.values["permit_type"] == "Rezoning petition"
    assert normalized.values["permit_subtype"] == "CD"
    assert normalized.values["proposed_use"] == "ML-1(CD)"
    assert normalized.values["square_feet"] == 327135
    assert normalized.values["filed_at"].isoformat() == "2026-05-15T04:00:00+00:00"
    assert normalized.values["source_url"].endswith("/2026-034")
    assert normalized.values["latitude"].quantize(Decimal("0.000001")) == Decimal("35.245865")
    assert normalized.values["longitude"].quantize(Decimal("0.000001")) == Decimal("-80.650009")
    assert "created_user" not in normalized.values

    approved = {
        **petition,
        "Petition": "2026-099",
        "Approved": 1784361600000,
        "Status": "App",
    }
    prepared, field_mapping = prepare_mapped_record(approved, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.values["approval_stage"] == "approved"
    assert normalized.values["approved_at"].isoformat() == "2026-07-18T08:00:00+00:00"


def test_madison_current_planning_projects_preserve_preapproval_chain_context():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "madison_wi_current_planning_projects"
    )
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }
    suppressed = set(entry.settings["suppressed_fields"])

    assert entry.adapter == "arcgis"
    assert entry.record_type == "permit"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert entry.settings["export_policy"] == "derived_project_context_only_no_raw_geometry_export"
    assert entry.settings["connector"]["include_geometry"] is True
    assert entry.settings["connector"]["keyset_field"] == "ESRI_OID"
    assert "Web_Planning_Project = 'Y'" in entry.settings["connector"]["where"]
    assert "DATES_SubmittedDate >= DATE '2025-01-01'" in entry.settings["connector"]["where"]
    assert entry.settings["canary_stage_probes"][0]["expected_stage"] == "pre_approval"
    assert entry.settings["canary_stage_probes"][1]["expected_stage"] == "approved"
    assert "CONTACT_RespParty_Email" not in out_fields
    assert "APO_OWNER_Mail_Address" not in out_fields
    assert suppressed.isdisjoint(out_fields)
    assert out_fields <= set(entry.settings["field_allowlist"])

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    project = {
        "ESRI_OID": 9912,
        "ID": "155772",
        "RECORD_RecordID": "LNDUSE-2026-00032",
        "PROJECT_ProjectAlias": "1001 Wisconsin Pl",
        "RECORD_Status": "Application Under Review",
        "DATES_SubmittedDate": 1783036800000,
        "DATES_Circulated": 1784073600000,
        "Project_Description": "Edgewater Hotel restaurant and bar expansion",
        "Requests": "Conditional Use",
        "MeetingDates": "Plan Commission: August 2026",
        "APO_ADDRESS_PARTIAL_LINE": "1001 WISCONSIN PL",
        "CONTACT_RespParty_OrgName": "The Edgewater Hospitality Co",
        "APO_OWNER_Full_Name": "EDGEWATER HOTEL COMPANY LLC",
        "APO_PARCEL_NUMBER": "070914442010",
        "ProjectURL": "https://www.cityofmadison.com/dpced/planning/development/current-development-proposals/1001-wisconsin-pl/155772/",
        "ASI_LU_PInf_LndUseLegURL": "https://madison.legistar.com/LegislationDetail.aspx?ID=155772",
        "ASI_LU_PInf_ReZonLegURL": None,
        "ASI_LU_PInf_UDCLegURL": None,
        "geometry": {"x": -89.38691, "y": 43.07942},
    }
    prepared, field_mapping = prepare_mapped_record(project, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.source_record_id == "LNDUSE-2026-00032"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["application_number"] == "LNDUSE-2026-00032"
    assert normalized.values["permit_number"] == "LNDUSE-2026-00032"
    assert normalized.values["project_name"] == "1001 Wisconsin Pl"
    assert normalized.values["developer_name"] == "The Edgewater Hospitality Co"
    assert normalized.values["owner_name"] == "EDGEWATER HOTEL COMPANY LLC"
    assert normalized.values["parcel_id"] == "070914442010"
    assert normalized.values["address"] == "1001 WISCONSIN PL"
    assert normalized.values["permit_type"] == "Planning project"
    assert normalized.values["permit_subtype"] == "Conditional Use"
    assert normalized.values["filed_at"].isoformat() == "2026-07-03T00:00:00+00:00"
    assert normalized.values["status_updated_at"].isoformat() == "2026-07-15T00:00:00+00:00"
    assert normalized.values["source_url"].startswith("https://www.cityofmadison.com/")
    assert normalized.values["latitude"] == Decimal("43.07942")
    assert normalized.values["longitude"] == Decimal("-89.38691")
    assert "CONTACT_RespParty_Email" not in normalized.values

    approved = {
        **project,
        "RECORD_RecordID": "LNDUSE-2026-00077",
        "RECORD_Status": "Final Approval Granted",
    }
    prepared, field_mapping = prepare_mapped_record(approved, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.values["approval_stage"] == "approved"


def test_east_baton_rouge_building_permits_are_approved_commercial_confirmation():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "east_baton_rouge_la_building_permits"
    )
    selected_fields = {
        field.strip()
        for field in entry.settings["connector"]["query"]["$select"].split(",")
    }
    suppressed = set(entry.settings["suppressed_fields"])

    assert entry.adapter == "socrata"
    assert entry.record_type == "permit"
    assert entry.settings["signal_stage"] == "approved_only"
    assert entry.settings["defaults"]["approval_stage"] == "approved"
    assert "designation = 'Commercial'" in entry.settings["connector"]["query"]["$where"]
    assert "issueddate >= '2024-01-01T00:00:00'" in entry.settings["connector"]["query"]["$where"]
    assert "contractoraddress" not in selected_fields
    assert "permitfee" not in selected_fields
    assert suppressed.isdisjoint(selected_fields)
    assert selected_fields <= set(entry.settings["field_allowlist"])

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    permit = {
        "permitid": "9340123",
        "permitnumber": "182979",
        "permittype": "Existing Bldg - Remodel Only (C)",
        "designation": "Commercial",
        "projectdescription": "Renovation to convert 976sf office space into Parent Resource Center for University View Academy.",
        "squarefootage": "976",
        "projectvalue": "250000",
        "creationdate": "2026-06-10T00:00:00.000",
        "issueddate": "2026-07-17T00:00:00.000",
        "address": "3112 VALLEY CREEK DR BATON ROUGE LA 70808",
        "streetaddress": "3112 VALLEY CREEK DR",
        "city1": "BATON ROUGE",
        "state1": "LA",
        "zip": "70808",
        "parishname": "East Baton Rouge",
        "ownername": "Barry Harris",
        "applicantname": "Michael Jackson",
        "contractorname": "CONTOUR DEVELOPMENT GROUP LLC - Michael Jevon Jackson",
        "lat": "30.402",
        "long": "-91.106",
    }
    prepared, field_mapping = prepare_mapped_record(permit, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.source_record_id == "9340123"
    assert normalized.values["approval_stage"] == "approved"
    assert normalized.values["application_number"] == "182979"
    assert normalized.values["permit_number"] == "182979"
    assert normalized.values["permit_type"] == "Existing Bldg - Remodel Only (C)"
    assert normalized.values["occupancy_type"] == "Commercial"
    assert normalized.values["address"] == "3112 VALLEY CREEK DR"
    assert normalized.values["owner_name"] == "Barry Harris"
    assert normalized.values["applicant_name"] == "Michael Jackson"
    assert normalized.values["contractor_name"] == "CONTOUR DEVELOPMENT GROUP LLC - Michael Jevon Jackson"
    assert normalized.values["valuation"] == Decimal("250000")
    assert normalized.values["square_feet"] == 976
    assert normalized.values["filed_at"].isoformat() == "2026-06-10T00:00:00+00:00"
    assert normalized.values["issued_at"].isoformat() == "2026-07-17T00:00:00+00:00"
    assert "contractoraddress" not in normalized.values


def test_texas_comptroller_sales_tax_locations_are_approved_retailer_opening_context():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "texas_comptroller_sales_tax_locations"
    )
    selected_fields = {
        field.strip()
        for field in entry.settings["connector"]["query"]["$select"].split(",")
    }
    suppressed = set(entry.settings["suppressed_fields"])

    assert entry.adapter == "socrata"
    assert entry.record_type == "permit"
    assert entry.settings["signal_stage"] == "approved_only"
    assert entry.settings["defaults"]["permit_type"] == "Sales tax permit"
    assert entry.settings["defaults"]["approval_stage"] == "approved"
    assert "loc_state = 'TX'" in entry.settings["connector"]["query"]["$where"]
    assert "out_of_business_date IS NULL" in entry.settings["connector"]["query"]["$where"]
    assert "tp_address" not in selected_fields
    assert "unique_taid" not in selected_fields
    assert suppressed.isdisjoint(selected_fields)
    assert selected_fields <= set(entry.settings["field_allowlist"])

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    outlet = {
        "tp_number": "17418232123",
        "tp_name": "STARBUCKS CORPORATION",
        "org_type": "CORPORATION",
        "loc_number": "9812",
        "loc_name": "STARBUCKS",
        "address_number": "1000",
        "address_text": "MAIN ST STE 120",
        "permit_date": "2026-07-09T00:00:00.000",
        "juris_city": "HOUSTON",
        "loc_city": "HOUSTON",
        "loc_state": "TX",
        "loc_zip": "77002",
        "loc_county": "101",
        "naics": "722515",
        "first_sale_date": "2026-08-01T00:00:00.000",
        "out_of_business_date": None,
    }
    prepared, field_mapping = prepare_mapped_record(outlet, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.source_record_id == "17418232123:9812"
    assert normalized.values["approval_stage"] == "approved"
    assert normalized.values["application_number"] == "17418232123:9812"
    assert normalized.values["permit_number"] == "17418232123:9812"
    assert normalized.values["permit_type"] == "Sales tax permit"
    assert normalized.values["permit_subtype"] == "722515"
    assert normalized.values["project_name"] == "STARBUCKS"
    assert normalized.values["owner_name"] == "STARBUCKS CORPORATION"
    assert normalized.values["applicant_name"] == "STARBUCKS CORPORATION"
    assert normalized.values["address"] == "1000 MAIN ST STE 120"
    assert normalized.values["city"] == "HOUSTON"
    assert normalized.values["state"] == "TX"
    assert normalized.values["postal_code"] == "77002"
    assert normalized.values["filed_at"].isoformat() == "2026-07-09T00:00:00+00:00"
    assert normalized.values["issued_at"].isoformat() == "2026-07-09T00:00:00+00:00"
    assert normalized.unmapped["first_sale_date"] == "2026-08-01T00:00:00.000"
    assert "tp_address" not in normalized.values


def test_orlando_permit_applications_preserve_preapproval_chain_context():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "orlando_fl_permit_applications"
    )
    selected_fields = {
        field.strip()
        for field in entry.settings["connector"]["query"]["$select"].split(",")
    }
    suppressed = set(entry.settings["suppressed_fields"])

    assert entry.adapter == "socrata"
    assert entry.record_type == "permit"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert "plan_review_type = 'Commercial'" in entry.settings["connector"]["query"]["$where"]
    assert "No Address" in entry.settings["connector"]["query"]["$where"]
    assert entry.settings["canary_stage_probes"][0]["expected_stage"] == "pre_approval"
    assert "issue_permit_date IS NULL" in entry.settings["canary_stage_probes"][0]["connector"]["query"]["$where"]
    assert entry.settings["canary_stage_probes"][1]["expected_stage"] == "approved"
    assert "issue_permit_date IS NOT NULL" in entry.settings["canary_stage_probes"][1]["connector"]["query"]["$where"]
    assert "contractor_phone_number" not in selected_fields
    assert "property_owner_name" not in selected_fields
    assert suppressed.isdisjoint(selected_fields)
    assert selected_fields <= set(entry.settings["field_allowlist"])

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    preapproval = {
        "permit_number": "BLD2026-15486",
        "application_type": "Building Permit",
        "worktype": "Alteration",
        "plan_review_type": "Commercial",
        "application_status": "Open",
        "processed_date": "2026-06-25T00:00:00.000",
        "under_review_date": "2026-06-26T00:00:00.000",
        "pending_issuance_date": None,
        "issue_permit_date": None,
        "final_date": None,
        "coo_date": None,
        "coc_date": None,
        "permit_address": "1500 E COLONIAL DR",
        "project_name": "PUBLIX 0662",
        "contractor_name": "HGR CONSTRUCTION INC",
        "estimated_cost": "1000000",
        "square_footage": "27462",
        "parcel_number": "292225153601070",
        "neighborhood": "Colonialtown South",
        "geocoded_column": {"type": "Point", "coordinates": [-81.3569, 28.5538]},
    }
    prepared, field_mapping = prepare_mapped_record(preapproval, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.source_record_id == "BLD2026-15486"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["application_number"] == "BLD2026-15486"
    assert normalized.values["permit_number"] == "BLD2026-15486"
    assert normalized.values["project_name"] == "PUBLIX 0662"
    assert normalized.values["contractor_name"] == "HGR CONSTRUCTION INC"
    assert normalized.values["address"] == "1500 E COLONIAL DR"
    assert normalized.values["parcel_id"] == "292225153601070"
    assert normalized.values["status"] == "Open"
    assert normalized.values["permit_type"] == "Building Permit"
    assert normalized.values["permit_subtype"] == "Alteration"
    assert normalized.values["review_type"] == "Commercial"
    assert normalized.values["valuation"] == Decimal("1000000")
    assert normalized.values["square_feet"] == 27462
    assert normalized.values["filed_at"].isoformat() == "2026-06-25T00:00:00+00:00"
    assert normalized.values["status_updated_at"].isoformat() == "2026-06-26T00:00:00+00:00"
    assert normalized.values["longitude"] == Decimal("-81.3569")
    assert normalized.values["latitude"] == Decimal("28.5538")
    assert "contractor_phone_number" not in normalized.values

    issued = {
        **preapproval,
        "permit_number": "BLD2026-15487",
        "issue_permit_date": "2026-07-18T00:00:00.000",
    }
    prepared, field_mapping = prepare_mapped_record(issued, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.values["approval_stage"] == "approved"
    assert normalized.values["issued_at"].isoformat() == "2026-07-18T00:00:00+00:00"


def test_mesa_commercial_submittals_preserve_preapproval_chain_context():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "mesa_az_commercial_permit_submittals"
    )
    selected_fields = {
        field.strip()
        for field in entry.settings["connector"]["query"]["$select"].split(",")
    }
    suppressed = set(entry.settings["suppressed_fields"])

    assert entry.adapter == "socrata"
    assert entry.record_type == "permit"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert "record_type = 'Commercial'" in entry.settings["connector"]["query"]["$where"]
    assert "record_status NOT IN" in entry.settings["connector"]["query"]["$where"]
    assert "latitiude" in selected_fields
    assert "assigned_by_name" not in selected_fields
    assert "action_by_name" not in selected_fields
    assert suppressed.isdisjoint(selected_fields)
    assert selected_fields <= set(entry.settings["field_allowlist"])
    assert entry.settings["canary_stage_probes"][0]["expected_stage"] == "pre_approval"
    assert entry.settings["canary_stage_probes"][1]["expected_stage"] == "approved"

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    submittal = {
        "row_number": "88613",
        "record_id": "PMT26-11010",
        "record_type": "Commercial",
        "type_of_submittal": "Sub",
        "record_open_date": "2026-06-12T00:00:00.000",
        "record_status": "In Review",
        "record_status_date": "2026-07-16T00:00:00.000",
        "task": "Application Submittal",
        "description": "Dutch Bros #11114",
        "status": "Accepted - Plan Review Req",
        "status_date": "2026-07-16T00:00:00.000",
        "distribution_date": "2026-07-16T00:00:00.000",
        "submittal_date": "2026-07-16T10:26:38.000",
        "permit_address": "3703 S POWER RD",
        "street_address": "3703 S POWER RD",
        "longitude": "-111.686999",
        "latitiude": "33.348592",
    }
    prepared, field_mapping = prepare_mapped_record(submittal, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.source_record_id == "88613"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["application_number"] == "PMT26-11010"
    assert normalized.values["permit_number"] == "PMT26-11010"
    assert normalized.values["project_name"] == "Dutch Bros #11114"
    assert normalized.values["description"] == "Dutch Bros #11114 | Application Submittal | Accepted - Plan Review Req"
    assert normalized.values["address"] == "3703 S POWER RD"
    assert normalized.values["status"] == "In Review"
    assert normalized.values["review_type"] == "Accepted - Plan Review Req"
    assert normalized.values["permit_type"] == "Commercial"
    assert normalized.values["permit_subtype"] == "Sub"
    assert normalized.values["filed_at"].isoformat() == "2026-06-12T00:00:00+00:00"
    assert normalized.values["status_updated_at"].isoformat() == "2026-07-16T10:26:38+00:00"
    assert normalized.values["latitude"] == Decimal("33.348592")
    assert normalized.values["longitude"] == Decimal("-111.686999")
    assert "assigned_by_name" not in normalized.values

    completed = {
        **submittal,
        "row_number": "86745",
        "record_id": "PMT26-04754",
        "record_status": "C of C Issued",
        "record_status_date": "2026-05-27T00:00:00.000",
    }
    prepared, field_mapping = prepare_mapped_record(completed, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.values["approval_stage"] == "approved"
    assert normalized.values["approved_at"].isoformat() == "2026-05-27T00:00:00+00:00"


def test_tempe_building_permits_preserve_commercial_preapproval_context():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "tempe_az_building_permits_commercial_context"
    )
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }
    suppressed = set(entry.settings["suppressed_fields"])

    assert entry.adapter == "arcgis"
    assert entry.record_type == "permit"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert entry.settings["license"] == "CC BY 4.0"
    assert "StatusDateDtm >= TIMESTAMP '2024-01-01 00:00:00'" in entry.settings["connector"]["where"]
    assert "PermitTypeDesc NOT IN" in entry.settings["connector"]["where"]
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    assert entry.settings["canary_stage_probes"][0]["expected_stage"] == "pre_approval"
    assert entry.settings["canary_stage_probes"][1]["expected_stage"] == "approved"
    assert "ContractorPhone" not in out_fields
    assert "ContractorEmail" not in out_fields
    assert suppressed.isdisjoint(out_fields)
    assert out_fields <= set(entry.settings["field_allowlist"])

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    preapproval = {
        "OBJECTID": 7759174,
        "PermitNum": "DR250023",
        "Description": "CONSTRUCT NEW ONE-STORY RESTAURANT BUILDING, KIOSKS, RESTROOMS W/ASSOCIATED SEATING AREAS",
        "AppliedDateDtm": None,
        "IssuedDateDtm": 1779926400000,
        "CompletedDateDtm": None,
        "Type": "",
        "StatusCurrent": "Ready for Issuance",
        "OriginalAddress1": "70 E RIO SALADO PKWY",
        "OriginalCity": "TEMPE",
        "PermitClass": "DR - Drainage",
        "PermitType": "Engineering,Drainage,NA,NA",
        "PermitTypeDesc": "Drainage Permit",
        "StatusDateDtm": 1779926400000,
        "TotalSqFt": 0,
        "EstProjectCost": 0,
        "HousingUnits": 0,
        "ContractorCompanyName": None,
        "ContractorLicNum": None,
        "ProjectName": "Hayden Ferry Lakeside Plaza",
        "Zone": "MU-4",
        "Latitude": 33.43007254,
        "Longitude": -111.93848293,
    }
    prepared, field_mapping = prepare_mapped_record(preapproval, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.source_record_id == "7759174"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["application_number"] == "DR250023"
    assert normalized.values["permit_number"] == "DR250023"
    assert normalized.values["project_name"] == "Hayden Ferry Lakeside Plaza"
    assert normalized.values["address"] == "70 E RIO SALADO PKWY"
    assert normalized.values["city"] == "TEMPE"
    assert normalized.values["status"] == "Ready for Issuance"
    assert normalized.values["permit_type"] == "Drainage Permit"
    assert normalized.values["review_type"] == "DR - Drainage"
    assert normalized.unmapped["Zone"] == "MU-4"
    assert normalized.values["status_updated_at"].isoformat() == "2026-05-28T00:00:00+00:00"
    assert "RESTAURANT BUILDING" in normalized.values["description"]
    assert normalized.values["latitude"] == Decimal("33.43007254")
    assert normalized.values["longitude"] == Decimal("-111.93848293")
    assert "ContractorPhone" not in normalized.values

    approved = {
        **preapproval,
        "OBJECTID": 7775074,
        "PermitNum": "BP252673",
        "Description": "TI - SUITE 103 - GRAY SHELL - LANDLORD IMPROVEMENTS",
        "AppliedDateDtm": 1765929600000,
        "IssuedDateDtm": 1771459200000,
        "CompletedDateDtm": 1772409600000,
        "Type": "Tenant Improvement",
        "StatusCurrent": "Final",
        "OriginalAddress1": "15 S MCCLINTOCK DR",
        "PermitClass": "437 - Additions and Alterations - Non-Residential",
        "PermitType": "Building,Permit,Permit,NA",
        "PermitTypeDesc": "Building Permit",
        "StatusDateDtm": 1772612598000,
        "TotalSqFt": 12000,
        "EstProjectCost": 80000,
        "ProjectName": "PAD 'B' - SUITE 103 @ TEMPE MARKETPLACE",
        "Zone": None,
    }
    prepared, field_mapping = prepare_mapped_record(approved, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.values["approval_stage"] == "approved"
    assert normalized.values["filed_at"].isoformat() == "2025-12-17T00:00:00+00:00"
    assert normalized.values["issued_at"].isoformat() == "2026-02-19T00:00:00+00:00"
    assert normalized.values["completed_at"].isoformat() == "2026-03-02T00:00:00+00:00"
    assert normalized.values["valuation"] == Decimal("80000")
    assert normalized.values["square_feet"] == 12000


def test_greensboro_building_permits_preserve_commercial_preapproval_context():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "greensboro_nc_building_permits_commercial"
    )
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }
    suppressed = set(entry.settings["suppressed_fields"])

    assert entry.adapter == "arcgis"
    assert entry.record_type == "permit"
    assert entry.settings["license"] == "City of Greensboro Open Data public domain policy"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    assert entry.settings["connector"]["include_geometry"] is True
    assert "BP_COMM_RESID_MULT = 'C'" in entry.settings["connector"]["where"]
    assert "CancelDate IS NULL" in entry.settings["connector"]["where"]
    assert "ContractorPhone" not in out_fields
    assert "OwnerAddress" not in out_fields
    assert suppressed.isdisjoint(out_fields)
    assert out_fields <= set(entry.settings["field_allowlist"])
    assert entry.settings["canary_stage_probes"][0]["expected_stage"] == "pre_approval"
    assert entry.settings["canary_stage_probes"][1]["expected_stage"] == "approved"

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    preapproval = {
        "OBJECTID": 59003,
        "PermitNum": 202612947,
        "PlanReviewNum": "2026-2088",
        "BP_ENTRY_DATE": 1783701780000,
        "IssuedDate": None,
        "StatusCurrent": "Active                                                      ",
        "ApplicationType": "Int/Ext Alterations",
        "Description": "Mezzanine - Mech/Elec/Fire sprinkler system to renovate for office space.",
        "OccupancyDesc": "Business",
        "TypeConstructionDesc": "V-A Any material - protected",
        "Contractor": "PLAN REVIEW",
        "OwnerName": "CHICKASHA I LLC",
        "FullAddress": "4490 CHICKASHA DR",
        "TotalCost": 46256,
        "BuildingSqFt": 687,
        "Zoning": "CD-HI",
        "BP_COMM_RESID_MULT": "C",
        "CancelDate": None,
        "FinalCO": None,
        "FinalCODate": None,
        "AdSakey": 312227,
        "geometry": {"x": -79.7124855455585, "y": 36.192195221879075},
    }
    prepared, field_mapping = prepare_mapped_record(preapproval, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.source_record_id == "202612947"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["application_number"] == "2026-2088"
    assert normalized.values["permit_number"] == "202612947"
    assert normalized.values["project_name"] == (
        "4490 CHICKASHA DR - Business - Int/Ext Alterations"
    )
    assert normalized.values["status"] == "Active"
    assert normalized.values["permit_type"] == "Int/Ext Alterations"
    assert normalized.values["proposed_use"] == "Business"
    assert normalized.values["owner_name"] == "CHICKASHA I LLC"
    assert normalized.values["contractor_name"] == "PLAN REVIEW"
    assert normalized.values["parcel_id"] == "312227"
    assert normalized.values["filed_at"].isoformat() == "2026-07-10T16:43:00+00:00"
    assert normalized.values["valuation"] == Decimal("46256")
    assert normalized.values["square_feet"] == 687
    assert normalized.values["longitude"].quantize(Decimal("0.000001")) == Decimal("-79.712486")
    assert normalized.values["latitude"].quantize(Decimal("0.000001")) == Decimal("36.192195")
    assert "ContractorPhone" not in normalized.values

    approved = {
        **preapproval,
        "OBJECTID": 58456,
        "PermitNum": 202518171,
        "PlanReviewNum": "2025-0763",
        "BP_ENTRY_DATE": 1759241160000,
        "IssuedDate": 1759241280000,
        "StatusCurrent": "Final Inspection Made                                       ",
        "Description": "Alterations related to laboratory rearrangement and office spaces.",
        "FinalCO": "Y",
        "FinalCODate": 1773396600000,
        "TotalCost": 0,
        "BuildingSqFt": 6500,
    }
    prepared, field_mapping = prepare_mapped_record(approved, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.values["approval_stage"] == "approved"
    assert normalized.values["issued_at"].isoformat() == "2025-09-30T14:08:00+00:00"
    assert normalized.values["completed_at"].isoformat() == "2026-03-13T10:10:00+00:00"


def test_wake_county_building_permits_preserve_retail_preapproval_context():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "wake_county_nc_building_permits_commercial"
    )
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }
    suppressed = set(entry.settings["suppressed_fields"])

    assert entry.adapter == "arcgis"
    assert entry.record_type == "permit"
    assert entry.settings["license"] == "CC BY 4.0"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    assert "PERMIT_TYPE = 'Commercial Building'" in entry.settings["connector"]["where"]
    assert "PERMIT_STATUS NOT IN" in entry.settings["connector"]["where"]
    assert "MAILING_ADDRESS" not in out_fields
    assert "MAILING_CITY" not in out_fields
    assert suppressed.isdisjoint(out_fields)
    assert out_fields <= set(entry.settings["field_allowlist"])
    assert entry.settings["canary_stage_probes"][0]["expected_stage"] == "pre_approval"
    assert entry.settings["canary_stage_probes"][1]["expected_stage"] == "approved"

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    preapproval = {
        "OBJECTID": 267568,
        "PERMIT_NUMBER": "CBPR-175796-2026",
        "PERMIT_STATUS": "In Review",
        "APPLICATION_DATE": 1784073600000,
        "ISSUE_DATE": None,
        "FINALED_DATE": None,
        "EXPIRATION_DATE": None,
        "DESCRIPTION": (
            "SHOPS AT MIDWAY - NO TRADES - LEVEL 2 - Michaels-#6725 Application "
            "to remove the Area of Rescue Station"
        ),
        "PERMIT_TYPE": "Commercial Building",
        "WORK_CLASS": "Building Renovation or Repair",
        "PROPOSED_USE": "327C   RETAIL STORE",
        "SQUARE_FEET": 200.0,
        "VALUATION": 1500.0,
        "CONTRACTOR": None,
        "PIN": "1744652987",
        "DISTRICT": "Knightdale",
        "LINK": "https://energovcitizenaccess.tylertech.com/WakeCountyNC/SelfService#/permit/687e7fb5-abe9-4290-bafa-4dec15442958",
        "X": -78.50727644,
        "Y": 35.79843032,
    }
    prepared, field_mapping = prepare_mapped_record(preapproval, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.source_record_id == "CBPR-175796-2026"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["application_number"] == "CBPR-175796-2026"
    assert normalized.values["permit_number"] == "CBPR-175796-2026"
    assert normalized.values["project_name"].startswith("SHOPS AT MIDWAY")
    assert normalized.values["status"] == "In Review"
    assert normalized.values["permit_type"] == "Commercial Building"
    assert normalized.values["permit_subtype"] == "Building Renovation or Repair"
    assert normalized.values["proposed_use"] == "327C RETAIL STORE"
    assert normalized.values["parcel_id"] == "1744652987"
    assert normalized.values["city"] == "Knightdale"
    assert normalized.values["filed_at"].isoformat() == "2026-07-15T00:00:00+00:00"
    assert normalized.values["valuation"] == Decimal("1500")
    assert normalized.values["square_feet"] == 200
    assert normalized.values["longitude"] == Decimal("-78.50727644")
    assert normalized.values["latitude"] == Decimal("35.79843032")
    assert normalized.values["source_url"].startswith(
        "https://energovcitizenaccess.tylertech.com/WakeCountyNC/"
    )
    assert "MAILING_ADDRESS" not in normalized.values

    approved = {
        **preapproval,
        "OBJECTID": 267471,
        "PERMIT_NUMBER": "CBPR-175583-2026",
        "PERMIT_STATUS": "Complete",
        "ISSUE_DATE": 1783900800000,
        "FINALED_DATE": 1784160000000,
        "DESCRIPTION": "ABC License Renewal - Grand Street Pizza",
        "PROPOSED_USE": "327B   RESTURANT/BAR/EATING",
        "SQUARE_FEET": 0.0,
        "VALUATION": 1.0,
    }
    prepared, field_mapping = prepare_mapped_record(approved, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.values["approval_stage"] == "approved"
    assert normalized.values["issued_at"].isoformat() == "2026-07-13T00:00:00+00:00"
    assert normalized.values["completed_at"].isoformat() == "2026-07-16T00:00:00+00:00"


def test_new_hanover_commercial_site_plans_preserve_preapproval_context():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "new_hanover_nc_commercial_site_plans"
    )
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }
    suppressed = set(entry.settings["suppressed_fields"])

    assert entry.adapter == "arcgis"
    assert entry.record_type == "permit"
    assert entry.settings["license"] == (
        "New Hanover County public GIS REST services; derived planning context only"
    )
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert entry.settings["export_policy"] == (
        "derived_site_plan_context_only_no_raw_geometry_export"
    )
    assert entry.settings["connector"]["include_geometry"] is True
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    assert "PLAN_STATUS IN ('In Review','Approved','Approved with Conditions')" in (
        entry.settings["connector"]["where"]
    )
    assert "PLAN_TYPE LIKE '%Commercial%'" in entry.settings["connector"]["where"]
    assert "ASSIGNED_TO" not in out_fields
    assert "OWNER_STREET" not in out_fields
    assert "TOTAL_FEE_AMOUNT" not in out_fields
    assert suppressed.isdisjoint(out_fields)
    assert out_fields <= set(entry.settings["field_allowlist"])
    assert set(entry.settings["canary_required_fields"]) <= set(entry.settings["field_allowlist"])
    assert entry.settings["canary_stage_probes"][0]["expected_stage"] == "pre_approval"
    assert entry.settings["canary_stage_probes"][1]["expected_stage"] == "approved"

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    preapproval = {
        "OBJECTID": 2165610,
        "PLPLANID": "041e8ed2-7ba6-40ae-8353-1afe71b707b8",
        "PLAN_NUMBER": "SITECN-26-000030",
        "PLAN_TYPE": "NHC Commercial Site",
        "WORK_CLASS": "New",
        "PLAN_STATUS": "In Review",
        "APPLY_DATE": 1784206678000,
        "COMPLETE_DATE": None,
        "EXPIRE_DATE": 1815742678000,
        "APPROVAL_EXPIRE_DATE": None,
        "PROJECT": None,
        "DESCRIPTION": (
            "Addition of a secondary driveway to an existing gas station site. "
            "The project will impact existing site design and circulation."
        ),
        "Applicant": "Bluewater Engineering, PLLC",
        "OWNER": "MM FOWLER INC",
        "GENERAL_CONTRACTOR": None,
        "SQUARE_FEET": None,
        "VALUATION": None,
        "MAIN_ZONE": "B-2",
        "PID": "R07918-005-015-000",
        "Lat": 34.1072261,
        "Lon": -77.8990533,
        "GlobalID": "{041E8ED2-7BA6-40AE-8353-1AFE71B707B8}",
        "geometry": {"x": -77.8990533, "y": 34.1072261},
    }
    prepared, field_mapping = prepare_mapped_record(preapproval, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.source_record_id == "041e8ed2-7ba6-40ae-8353-1afe71b707b8"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["application_number"] == "SITECN-26-000030"
    assert normalized.values["permit_number"] == "SITECN-26-000030"
    assert normalized.values["project_name"].startswith("Addition of a secondary driveway")
    assert normalized.values["status"] == "In Review"
    assert normalized.values["permit_type"] == "Commercial site plan"
    assert normalized.values["permit_subtype"] == "NHC Commercial Site"
    assert normalized.values["work_class"] == "New"
    assert normalized.values["proposed_use"] == "NHC Commercial Site | B-2"
    assert normalized.values["applicant_name"] == "Bluewater Engineering, PLLC"
    assert normalized.values["owner_name"] == "MM FOWLER INC"
    assert normalized.values["parcel_id"] == "R07918-005-015-000"
    assert normalized.values["filed_at"].isoformat() == "2026-07-16T12:57:58+00:00"
    assert normalized.values["expires_at"].isoformat() == "2027-07-16T12:57:58+00:00"
    assert normalized.values["latitude"] == Decimal("34.1072261")
    assert normalized.values["longitude"] == Decimal("-77.8990533")
    assert "ASSIGNED_TO" not in normalized.values
    assert "OWNER_STREET" not in normalized.values

    approved = {
        **preapproval,
        "PLPLANID": "d6cd33bf-b748-4de9-9b82-9c42a9d8617f",
        "PLAN_NUMBER": "SITEAPP-24-000022",
        "PLAN_STATUS": "Approved",
        "COMPLETE_DATE": 1784361600000,
        "PROJECT": "US 421 Business Park",
        "DESCRIPTION": "Site Plan - Major Application for industrial flex buildings.",
        "Applicant": "WSP",
        "OWNER": "CAROLINA POWER & LIGHT CO",
        "PID": "R02300-002-001-000",
        "Lat": 34.30303153,
        "Lon": -77.99894898,
        "geometry": {"x": -77.99894898, "y": 34.30303153},
    }
    prepared, field_mapping = prepare_mapped_record(approved, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.values["approval_stage"] == "approved"
    assert normalized.values["approved_at"].isoformat() == "2026-07-18T08:00:00+00:00"
    assert normalized.values["project_name"] == "US 421 Business Park"


def test_buffalo_planning_zoning_approvals_preserve_conditional_context():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "buffalo_ny_planning_zoning_approvals"
    )
    selected_fields = {
        field.strip()
        for field in entry.settings["connector"]["query"]["$select"].split(",")
    }

    assert entry.adapter == "socrata"
    assert entry.record_type == "permit"
    assert entry.settings["license"] == "Public Domain U.S. Government"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert entry.settings["freshness_field"] == "resultdttm"
    assert "Denied" not in entry.settings["connector"]["query"]["$where"]
    assert "AppCond" in entry.settings["connector"]["query"]["$where"]
    assert "Approved" in entry.settings["connector"]["query"]["$where"]
    assert "{utc_today_plus_7}" in entry.settings["connector"]["query"]["$where"]
    assert selected_fields <= set(entry.settings["field_allowlist"])
    assert set(entry.settings["suppressed_fields"]).isdisjoint(selected_fields)
    assert entry.settings["canary_stage_probes"][0]["expected_stage"] == "pre_approval"
    assert entry.settings["canary_stage_probes"][1]["expected_stage"] == "approved"
    assert (
        "{utc_today_plus_7}"
        in entry.settings["canary_stage_probes"][0]["connector"]["query"]["$where"]
    )
    assert (
        "{utc_today_plus_7}"
        in entry.settings["canary_stage_probes"][1]["connector"]["query"]["$where"]
    )

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    conditional = {
        "uniqueid": "9456581237700004035000",
        "apbldgreviewkey": "9689278-4035000",
        "reviewtype": "ZONING",
        "result": "AppCond",
        "resultdttm": "2026-07-17T00:00:00.000",
        "apno": "USE26-9689278",
        "apbldgkey": "9689278",
        "aptype": "USE",
        "address": "309 GERMANIA",
        "city": "Buffalo",
        "state": "NY",
        "zip": "14220",
        "prclid": "1237700004035000",
        "latitude": "42.848",
        "longitude": "-78.837",
        "neighborhood": "Hopkins-Tifft",
    }
    prepared, field_mapping = prepare_mapped_record(conditional, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.source_record_id == "9456581237700004035000"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["application_number"] == "USE26-9689278"
    assert normalized.values["permit_number"] == "USE26-9689278"
    assert normalized.values["review_type"] == "ZONING"
    assert normalized.values["permit_subtype"] == "USE"
    assert normalized.values["status"] == "AppCond"
    assert normalized.values["project_name"] == "309 GERMANIA - ZONING"
    assert normalized.values["description"] == "ZONING | AppCond | Hopkins-Tifft"
    assert normalized.values["parcel_id"] == "1237700004035000"
    assert normalized.values["approved_at"].isoformat() == "2026-07-17T00:00:00+00:00"
    assert normalized.values["latitude"] == Decimal("42.848")
    assert normalized.values["longitude"] == Decimal("-78.837")

    approved = {
        **conditional,
        "uniqueid": "9456581237700004035001",
        "result": "Approved",
    }
    prepared, field_mapping = prepare_mapped_record(approved, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.values["approval_stage"] == "approved"


def test_colorado_statewide_public_parcels_are_derived_proximity_context():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "colorado_statewide_public_parcels_nearby_narrow"
    )
    suppressed = set(entry.settings["suppressed_fields"])
    allowlist = set(entry.settings["field_allowlist"])
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }
    mapped_fields = {mapping.source_field for mapping in entry.field_mappings}

    assert entry.adapter == "arcgis"
    assert entry.record_type == "parcel"
    assert entry.settings["signal_stage"] == "parcel_context"
    assert entry.settings["reconciliation_mode"] == "guarded_full_snapshot"
    assert "raw resale prohibition" in entry.settings["license"]
    assert "Resale" not in entry.settings["connector"]["out_fields"]
    assert "owner" not in out_fields
    assert "legalDesc" not in out_fields
    assert "salePrice" not in out_fields
    assert "apprValTot" not in out_fields
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    assert entry.settings["connector"]["include_geometry"] is True
    assert "parcel_id IS NOT NULL" in entry.settings["connector"]["where"]
    assert suppressed.isdisjoint(allowlist)
    assert suppressed.isdisjoint(out_fields)
    assert suppressed.isdisjoint(mapped_fields)

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    record = {
        "OBJECTID": 1,
        "countyName": "Adams",
        "countyFips": "001",
        "parcel_id": "0171901104005",
        "account": None,
        "situsAdd": "11844 STEELE ST",
        "sitAddCty": "THORNTON",
        "sitAddZip": "80233",
        "landAcres": 0.17,
        "zoningCode": None,
        "zoningDesc": "Residential Low",
        "landUseCde": None,
        "landUseDsc": "Residential",
        "dateReceived": "4/23/2026",
        "URL": None,
        "geometry": {
            "rings": [[
                [-104.949092, 39.912106],
                [-104.949097, 39.9123],
                [-104.948703, 39.912299],
                [-104.948704, 39.912111],
                [-104.949092, 39.912106],
            ]]
        },
    }
    prepared, field_mapping = prepare_mapped_record(record, mappings)
    normalized = normalize_parcel(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.source_record_id == "001:0171901104005"
    assert normalized.values["parcel_group_id"] == "0171901104005"
    assert normalized.values["address"] == "11844 STEELE ST"
    assert normalized.values["city"] == "THORNTON"
    assert normalized.values["postal_code"] == "80233"
    assert normalized.values["land_area_sq_ft"] == Decimal("7405.20")
    assert normalized.values["land_use"] == "Residential"
    assert normalized.values["zoning_code"] == "Residential Low"
    assert normalized.values["observed_at"].isoformat() == "2026-04-23T00:00:00+00:00"
    assert normalized.values["latitude"].quantize(Decimal("0.000001")) == Decimal("39.912127")
    assert normalized.values["longitude"].quantize(Decimal("0.000001")) == Decimal("-104.948698")
    assert "owner" not in normalized.values
    assert "last_sale_price" not in normalized.values


def test_new_jersey_njgin_parcels_are_derived_proximity_context():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "new_jersey_njgin_statewide_parcels_nearby_narrow"
    )
    suppressed = set(entry.settings["suppressed_fields"])
    allowlist = set(entry.settings["field_allowlist"])
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }
    mapped_fields = {mapping.source_field for mapping in entry.field_mappings}

    assert entry.adapter == "arcgis"
    assert entry.record_type == "parcel"
    assert entry.settings["signal_stage"] == "parcel_context"
    assert entry.settings["reconciliation_mode"] == "guarded_full_snapshot"
    assert "owner redaction" in entry.settings["license"]
    assert "PIN_NODUP <> 'XXXNLL'" in entry.settings["connector"]["where"]
    assert "OWNER_NAME" not in out_fields
    assert "SALE_PRICE" not in out_fields
    assert "DEED_BOOK" not in out_fields
    assert "NET_VALUE" not in out_fields
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    assert entry.settings["connector"]["include_geometry"] is True
    assert suppressed.isdisjoint(allowlist)
    assert suppressed.isdisjoint(out_fields)
    assert suppressed.isdisjoint(mapped_fields)

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    record = {
        "OBJECTID": 1,
        "PAMS_PIN": "0703_14_6",
        "PIN_NODUP": "0703_14_6",
        "PCL_MUN": "0703",
        "PCLBLOCK": "14",
        "PCLLOT": "6",
        "PCLQCODE": " ",
        "COUNTY": "ESSEX",
        "MUN_NAME": "CALDWELL BORO TWP",
        "PROP_CLASS": "2",
        "PROP_LOC": "35 HILLSIDE AVE",
        "ST_ADDRESS": "35 HILLSIDE AVE",
        "CITY_STATE": "CALDWELL, NJ",
        "ZIP5": "07006",
        "LAND_DESC": "75X200",
        "CALC_ACRE": 0.3444,
        "PCLLASTUPD": None,
        "PCL_PBDATE": 1695168000000,
        "PCL_GUID": "94ed7180-5f09-4889-82fc-c05db53e80de",
        "geometry": {
            "rings": [[
                [-74.268775, 40.840395],
                [-74.268967, 40.84025],
                [-74.269479, 40.840638],
                [-74.269284, 40.840785],
                [-74.268775, 40.840395],
            ]]
        },
    }
    prepared, field_mapping = prepare_mapped_record(record, mappings)
    normalized = normalize_parcel(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.source_record_id == "0703_14_6"
    assert normalized.values["parcel_group_id"] == "0703_14_6"
    assert normalized.values["address"] == "35 HILLSIDE AVE"
    assert normalized.values["city"] == "CALDWELL BORO TWP"
    assert normalized.values["county"] == "ESSEX"
    assert normalized.values["postal_code"] == "07006"
    assert normalized.values["land_area_sq_ft"] == Decimal("15002.064")
    assert normalized.values["land_use"] == "2 | 75X200"
    assert normalized.values["zoning_code"] == "0703"
    assert normalized.values["observed_at"].isoformat() == "2023-09-20T00:00:00+00:00"
    assert normalized.values["latitude"].quantize(Decimal("0.000001")) == Decimal("40.840479")
    assert normalized.values["longitude"].quantize(Decimal("0.000001")) == Decimal("-74.269058")
    assert "owner_name" not in normalized.values
    assert "last_sale_price" not in normalized.values


def test_florida_fdor_statewide_cadastral_parcels_are_statewide_proximity_spine():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "florida_fdor_statewide_cadastral_parcels"
    )
    suppressed = set(entry.settings["suppressed_fields"])
    allowlist = set(entry.settings["field_allowlist"])
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }
    mapped_fields = {mapping.source_field for mapping in entry.field_mappings}

    assert entry.adapter == "arcgis"
    assert entry.record_type == "parcel"
    assert entry.settings["signal_stage"] == "parcel_context"
    assert entry.settings["refresh_frequency"] == "annual_with_midyear_maintenance"
    assert entry.settings["connector"]["include_centroid"] is True
    assert "STATE_PAR_ IS NOT NULL" in entry.settings["connector"]["where"]
    assert "not title, zoning, or complete sale-history evidence" in entry.settings["rights_basis"]
    assert "S_LEGAL" not in out_fields
    assert "CLERK_NO1" not in out_fields
    assert "FIDU_NAME" not in out_fields
    assert suppressed.isdisjoint(allowlist)
    assert suppressed.isdisjoint(out_fields)
    assert suppressed.isdisjoint(mapped_fields)

    prepared, field_mapping = prepare_mapped_record(
        {
            "OBJECTID": 2,
            "CO_NO": 11,
            "PARCEL_ID": "03206-000-000",
            "PARCELNO": "03206-000-000",
            "STATE_PAR_": "C11-000-000-9790-7",
            "ASMNT_YR": 2025,
            "DOR_UC": "059",
            "PA_UC": "00",
            "JV": 500000,
            "AV_SD": 5000,
            "AV_NSD": 5000,
            "LND_VAL": 5000,
            "LND_SQFOOT": 1089000,
            "TOT_LVG_AR": 0,
            "SALE_PRC1": 0,
            "QUAL_CD1": None,
            "VI_CD1": None,
            "OWN_NAME": "EMP1 LLC",
            "OWN_ADDR1": "7045 NW 22ND ST SUITE B",
            "OWN_ADDR2": " ",
            "OWN_CITY": "GAINESVILLE",
            "OWN_STATE_": "FL",
            "OWN_ZIPCD": 32653,
            "PHY_ADDR1": "12628 NW 150TH AVE",
            "PHY_ADDR2": " ",
            "PHY_CITY": "ALACHUA",
            "PHY_ZIPCD": 32615,
            "ALT_KEY": "13497",
            "PUBLIC_LND": " ",
            "centroid": {"x": -82.48237396858843, "y": 29.794941524135016},
        },
        entry.field_mappings,
    )
    normalized = normalize_parcel(
        prepared,
        field_mapping,
        defaults=entry.settings["defaults"],
    )

    assert normalized.source_record_id == "C11-000-000-9790-7"
    assert normalized.values["parcel_group_id"] == "C11-000-000-9790-7"
    assert normalized.values["county"] == "11"
    assert normalized.values["address"] == "12628 NW 150TH AVE"
    assert normalized.values["city"] == "ALACHUA"
    assert normalized.values["owner_name"] == "EMP1 LLC"
    assert normalized.values["owner_mailing_address"] == "7045 NW 22ND ST SUITE B GAINESVILLE FL 32653"
    assert normalized.values["land_area_sq_ft"] == 1089000
    assert normalized.values["land_value"] == 5000
    assert normalized.values["improvement_value"] == Decimal("495000")
    assert normalized.values["total_assessed_value"] == 500000
    assert normalized.values["last_sale_price"] == 0
    assert normalized.values["land_use"] == "059 | 00"
    assert float(normalized.values["latitude"]) == pytest.approx(29.794941524135016)
    assert float(normalized.values["longitude"]) == pytest.approx(-82.48237396858843)


def test_marion_county_parcel_source_excludes_sale_evidence():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "indianapolis_marion_county_in_parcels"
    )
    canonical_fields = {mapping.canonical_field for mapping in entry.field_mappings}

    assert "owner_name" in canonical_fields
    assert "total_assessed_value" in canonical_fields
    assert "last_sale_date" not in canonical_fields
    assert "last_sale_price" not in canonical_fields


def test_hennepin_county_parcel_source_uses_geometry_and_public_record_evidence():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "hennepin_mn_county_parcels"
    )
    canonical_fields = {mapping.canonical_field for mapping in entry.field_mappings}

    assert entry.adapter == "arcgis"
    assert entry.settings["signal_stage"] == "parcel_context"
    assert entry.settings["attribution_required"] is True
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    assert entry.settings["connector"]["include_geometry"] is True
    assert entry.settings["connector"]["page_size"] == 200
    assert "PID" in entry.settings["connector"]["out_fields"]
    assert "OWNER_NM" in entry.settings["connector"]["out_fields"]
    assert "owner_name" in canonical_fields
    assert "total_assessed_value" in canonical_fields
    assert "last_sale_date" in canonical_fields
    assert "last_sale_price" in canonical_fields


def test_st_louis_city_parcel_source_uses_city_open_data_only():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "st_louis_mo_city_parcels"
    )
    canonical_fields = {mapping.canonical_field for mapping in entry.field_mappings}

    assert entry.adapter == "arcgis"
    assert entry.settings["signal_stage"] == "parcel_context"
    assert entry.settings["attribution_required"] is True
    assert "owner-name reverse search" in entry.settings["rights_basis"]
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    assert entry.settings["connector"]["include_geometry"] is True
    assert entry.settings["connector"]["page_size"] == 200
    assert "ParcelId" in entry.settings["connector"]["out_fields"]
    assert "OwnerName" in entry.settings["connector"]["out_fields"]
    assert "owner_name" in canonical_fields
    assert "total_assessed_value" in canonical_fields
    assert "last_sale_date" in canonical_fields


def test_allegheny_county_parcels_are_derived_geometry_context():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "allegheny_county_pa_parcels_nearby_narrow"
    )
    suppressed = set(entry.settings["suppressed_fields"])
    allowlist = set(entry.settings["field_allowlist"])
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }
    mapped_fields = {mapping.source_field for mapping in entry.field_mappings}
    canonical_fields = {mapping.canonical_field for mapping in entry.field_mappings}

    assert entry.adapter == "arcgis"
    assert entry.record_type == "parcel"
    assert entry.settings["signal_stage"] == "parcel_context"
    assert entry.settings["reconciliation_mode"] == "guarded_full_snapshot"
    assert "public domain" in entry.settings["license"].casefold()
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    assert entry.settings["connector"]["include_geometry"] is True
    assert "PIN IS NOT NULL" in entry.settings["connector"]["where"]
    assert "PIN" in out_fields
    assert "NOTES" not in out_fields
    assert "MODIFIEDBY" not in out_fields
    assert "COMMENTS" not in out_fields
    assert "owner_name" not in canonical_fields
    assert "last_sale_price" not in canonical_fields
    assert suppressed.isdisjoint(allowlist)
    assert suppressed.isdisjoint(out_fields)
    assert suppressed.isdisjoint(mapped_fields)

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    record = {
        "OBJECTID": 4888406,
        "PIN": "0102P00193000000",
        "MAPBLOCKLOT": "102-P-193",
        "MUNICODE": 941,
        "CALCACREAGE": 0.07,
        "MODIFIEDON": "5/16/2013 8:35:32 AM",
        "GlobalID": "{6A619D35-B15C-42D9-9577-C38FB6D8AC00}",
        "geometry": {
            "rings": [[
                [-80.094944, 40.39552],
                [-80.095035, 40.395504],
                [-80.095056, 40.39586],
                [-80.094965, 40.395863],
                [-80.094944, 40.39552],
            ]]
        },
    }
    prepared, field_mapping = prepare_mapped_record(record, mappings)
    normalized = normalize_parcel(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.source_record_id == "0102P00193000000"
    assert normalized.values["parcel_group_id"] == "102-P-193"
    assert normalized.values["county"] == "Allegheny"
    assert normalized.values["state"] == "PA"
    assert normalized.values["land_area_sq_ft"] == Decimal("3049.20")
    assert normalized.values["zoning_code"] == "941"
    assert normalized.values["observed_at"].isoformat() == "2013-05-16T08:35:32+00:00"
    assert normalized.values["latitude"].quantize(Decimal("0.000001")) == Decimal("40.395694")
    assert normalized.values["longitude"].quantize(Decimal("0.000001")) == Decimal("-80.095016")


def test_louisville_lojic_parcel_source_is_geometry_only():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "louisville_jefferson_ky_lojic_parcels_narrow"
    )
    canonical_fields = {mapping.canonical_field for mapping in entry.field_mappings}

    assert entry.adapter == "arcgis"
    assert entry.settings["signal_stage"] == "parcel_context"
    assert entry.settings["export_policy"] == "derived_geometry_parcel_id_only_no_raw_pva_source_export"
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    assert entry.settings["connector"]["include_geometry"] is True
    assert entry.settings["connector"]["page_size"] == 200
    assert "LRSN" in entry.settings["connector"]["out_fields"]
    assert "OWNER" not in entry.settings["connector"]["out_fields"]
    assert "owner_name" not in canonical_fields
    assert "total_assessed_value" not in canonical_fields
    assert "last_sale_date" not in canonical_fields


def test_vermont_vcgi_parcel_source_is_value_added_context_only():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "vermont_vcgi_statewide_parcels_narrow"
    )
    canonical_fields = {mapping.canonical_field for mapping in entry.field_mappings}
    suppressed = set(entry.settings["suppressed_fields"])
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }
    mapped_fields = {mapping.source_field for mapping in entry.field_mappings}

    assert entry.adapter == "arcgis"
    assert entry.settings["signal_stage"] == "parcel_context"
    assert entry.settings["attribution_required"] is True
    assert entry.settings["export_policy"] == (
        "derived_nearby_parcel_context_only_no_raw_vcgi_source_resale"
    )
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    assert entry.settings["connector"]["include_geometry"] is True
    assert entry.settings["connector"]["where"] == (
        "PROPTYPE = 'PARCEL' AND SPAN IS NOT NULL AND SPAN <> ''"
    )
    assert "OWNER1" in entry.settings["connector"]["out_fields"]
    assert "REAL_FLV" in entry.settings["connector"]["out_fields"]
    assert suppressed.isdisjoint(out_fields)
    assert suppressed.isdisjoint(mapped_fields)
    assert "owner_name" in canonical_fields
    assert "total_assessed_value" in canonical_fields
    assert "last_sale_date" not in canonical_fields
    assert "last_sale_price" not in canonical_fields


def test_rhode_island_parcel_source_is_proximity_only():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "rhode_island_statewide_tax_parcels_narrow"
    )
    canonical_fields = {mapping.canonical_field for mapping in entry.field_mappings}
    suppressed = set(entry.settings["suppressed_fields"])
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }

    assert entry.adapter == "arcgis"
    assert entry.settings["signal_stage"] == "parcel_context"
    assert entry.settings["export_policy"] == (
        "derived_nearby_parcel_context_only_no_raw_ri_tax_parcel_resale"
    )
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    assert entry.settings["connector"]["include_geometry"] is True
    assert "TownCode" in entry.settings["connector"]["where"]
    assert "PlatLot" in entry.settings["connector"]["where"]
    assert "OWNER" not in entry.settings["connector"]["out_fields"]
    assert "SALE_PRICE" not in entry.settings["connector"]["out_fields"]
    assert suppressed.isdisjoint(out_fields)
    assert "owner_name" not in canonical_fields
    assert "total_assessed_value" not in canonical_fields
    assert "last_sale_date" not in canonical_fields
    assert "last_sale_price" not in canonical_fields


def test_new_hampshire_parcel_source_is_derived_context_only():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "new_hampshire_dra_granit_parcel_mosaic_narrow"
    )
    canonical_fields = {mapping.canonical_field for mapping in entry.field_mappings}
    suppressed = set(entry.settings["suppressed_fields"])
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }

    assert entry.adapter == "arcgis"
    assert entry.settings["signal_stage"] == "parcel_context"
    assert entry.settings["export_policy"] == (
        "derived_nearby_parcel_context_only_no_raw_nh_parcel_mosaic_resale"
    )
    assert entry.settings["connector"]["keyset_field"] == "objectid"
    assert entry.settings["connector"]["include_geometry"] is True
    assert entry.settings["connector"]["include_centroid"] is True
    assert "nh_gis_id" in entry.settings["connector"]["where"]
    assert "OWNER" not in entry.settings["connector"]["out_fields"]
    assert "SALE_PRICE" not in entry.settings["connector"]["out_fields"]
    assert suppressed.isdisjoint(out_fields)
    assert "owner_name" not in canonical_fields
    assert "total_assessed_value" not in canonical_fields
    assert "last_sale_date" not in canonical_fields
    assert "last_sale_price" not in canonical_fields


def test_vermont_act250_source_is_narrow_large_development_context():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "vermont_act250_large_development_context"
    )
    canonical_fields = {mapping.canonical_field for mapping in entry.field_mappings}

    assert entry.adapter == "arcgis"
    assert entry.record_type == "permit"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert entry.settings["export_policy"] == (
        "derived_large_development_context_only_no_raw_vcgi_source_resale"
    )
    assert "not canonical municipal permit coverage" in entry.settings["rights_basis"]
    assert entry.settings["connector"]["keyset_field"] == "ProjectID"
    assert entry.settings["connector"]["include_geometry"] is False
    assert "ProjectID" in entry.settings["connector"]["out_fields"]
    assert "LINK" in entry.settings["connector"]["out_fields"]
    assert "approval_stage" in canonical_fields
    assert "source_url" in canonical_fields


def test_montgomery_al_permit_source_is_approved_commercial_context_only():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "montgomery_al_commercial_construction_permits"
    )

    assert entry.adapter == "arcgis"
    assert entry.record_type == "permit"
    assert entry.settings["signal_stage"] == "approved_only"
    assert entry.settings["defaults"]["approval_stage"] == "approved"
    assert entry.settings["export_policy"] == (
        "derived_commercial_permit_context_only_no_raw_montgomery_al_source_resale"
    )
    assert entry.settings["record_filters"] == [{"field": "UseType", "value": "Commercial"}]
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    assert "UseType = 'Commercial'" in entry.settings["connector"]["where"]
    assert "IssuedDate IS NOT NULL" in entry.settings["connector"]["where"]


def test_montgomery_al_parcel_source_excludes_owner_value_and_sale():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "montgomery_al_parcels_nearby_narrow"
    )
    canonical_fields = {mapping.canonical_field for mapping in entry.field_mappings}
    suppressed = set(entry.settings["suppressed_fields"])
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }

    assert entry.adapter == "arcgis"
    assert entry.settings["signal_stage"] == "parcel_context"
    assert entry.settings["export_policy"] == (
        "derived_nearby_parcel_context_only_no_raw_alabama_local_parcel_resale"
    )
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    assert entry.settings["connector"]["include_geometry"] is True
    assert entry.settings["connector"]["include_centroid"] is True
    assert suppressed.isdisjoint(out_fields)
    assert "OwnerName" not in entry.settings["connector"]["out_fields"]
    assert "TotalValue" not in entry.settings["connector"]["out_fields"]
    assert "owner_name" not in canonical_fields
    assert "total_assessed_value" not in canonical_fields
    assert "last_sale_date" not in canonical_fields
    assert "last_sale_price" not in canonical_fields


def test_fayetteville_ar_permit_source_preserves_lifecycle_context():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "fayetteville_ar_permit_lifecycle_narrow"
    )
    canonical_fields = {mapping.canonical_field for mapping in entry.field_mappings}

    assert entry.adapter == "arcgis"
    assert entry.record_type == "permit"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert entry.settings["export_policy"] == (
        "derived_permit_context_only_no_raw_fayetteville_ar_source_resale"
    )
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    assert "Commercial Building Permit" in entry.settings["connector"]["where"]
    assert "Sign Permit" in entry.settings["connector"]["where"]
    assert "approval_stage" in canonical_fields
    assert "source_url" in canonical_fields

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    prepared, field_mapping = prepare_mapped_record(
        {
            "OBJECTID": 1,
            "PERMITNUMBER": "COMM-1",
            "PM_TYPE": "Commercial Building Permit",
            "PM_STATUS": "In Review",
            "DESCRIPTION": "Retail tenant finish",
            "ISSUEDATE": None,
        },
        mappings,
    )
    assert normalize_permit(prepared, field_mapping).values["approval_stage"] == "pre_approval"

    approved_prepared, approved_mapping = prepare_mapped_record(
        {
            "OBJECTID": 2,
            "PERMITNUMBER": "COMM-2",
            "PM_TYPE": "Commercial Building Permit",
            "PM_STATUS": "Issued",
            "DESCRIPTION": "Retail tenant finish",
            "ISSUEDATE": "2026-07-01",
        },
        mappings,
    )
    assert normalize_permit(approved_prepared, approved_mapping).values["approval_stage"] == "approved"


def test_arkansas_parcel_source_excludes_owner_value_and_legal_fields():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "arkansas_statewide_parcels_nearby_narrow"
    )
    canonical_fields = {mapping.canonical_field for mapping in entry.field_mappings}
    suppressed = set(entry.settings["suppressed_fields"])
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }

    assert entry.adapter == "arcgis"
    assert entry.settings["signal_stage"] == "parcel_context"
    assert entry.settings["export_policy"] == (
        "derived_nearby_parcel_context_only_no_raw_arkansas_cadastral_resale"
    )
    assert entry.settings["connector"]["keyset_field"] == "objectid"
    assert entry.settings["connector"]["include_geometry"] is True
    assert "parcelid" in entry.settings["connector"]["where"]
    assert suppressed.isdisjoint(out_fields)
    assert "ownername" not in entry.settings["connector"]["out_fields"]
    assert "parcellgl" not in entry.settings["connector"]["out_fields"]
    assert "totalvalue" not in entry.settings["connector"]["out_fields"]
    assert "owner_name" not in canonical_fields
    assert "total_assessed_value" not in canonical_fields
    assert "last_sale_date" not in canonical_fields
    assert "last_sale_price" not in canonical_fields


def test_fort_worth_tx_permit_source_preserves_preapproval_lifecycle():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "fort_worth_tx_civic_commercial_permits"
    )
    canonical_fields = {mapping.canonical_field for mapping in entry.field_mappings}

    assert entry.adapter == "arcgis"
    assert entry.record_type == "permit"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert entry.settings["export_policy"] == (
        "derived_permit_context_only_no_raw_fort_worth_tx_source_resale"
    )
    assert entry.settings["connector"]["keyset_field"] == "CAPID"
    assert "Commercial Building Permit" in entry.settings["connector"]["where"]
    assert "approval_stage" in canonical_fields

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    prepared, field_mapping = prepare_mapped_record(
        {
            "CAPID": 100,
            "Permit_No": "PB26-1",
            "Permit_Type": "Commercial Building Permit",
            "Current_Status": "Plan Review",
        },
        mappings,
    )
    assert normalize_permit(prepared, field_mapping).values["approval_stage"] == "pre_approval"

    issued, issued_mapping = prepare_mapped_record(
        {
            "CAPID": 101,
            "Permit_No": "PB26-2",
            "Permit_Type": "Commercial Building Permit",
            "Current_Status": "Issued",
        },
        mappings,
    )
    assert normalize_permit(issued, issued_mapping).values["approval_stage"] == "approved"


def test_collin_county_parcel_source_excludes_owner_value_and_deed_fields():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "collin_county_tx_parcels_nearby_narrow"
    )
    canonical_fields = {mapping.canonical_field for mapping in entry.field_mappings}
    suppressed = set(entry.settings["suppressed_fields"])
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }

    assert entry.adapter == "arcgis"
    assert entry.settings["signal_stage"] == "parcel_context"
    assert entry.settings["export_policy"] == (
        "derived_nearby_parcel_context_only_no_raw_collin_cad_resale"
    )
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    assert entry.settings["connector"]["where"] == "PROP_ID > 0"
    assert suppressed.isdisjoint(out_fields)
    assert "ownerName" not in entry.settings["connector"]["out_fields"]
    assert "currValMarket" not in entry.settings["connector"]["out_fields"]
    assert "deedNum" not in entry.settings["connector"]["out_fields"]
    assert "owner_name" not in canonical_fields
    assert "total_assessed_value" not in canonical_fields
    assert "last_sale_date" not in canonical_fields
    assert "last_sale_price" not in canonical_fields


def test_tennessee_comptroller_parcel_source_is_limited_derived_context():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "tennessee_comptroller_impact_parcels_nearby_narrow"
    )
    canonical_fields = {mapping.canonical_field for mapping in entry.field_mappings}
    suppressed = set(entry.settings["suppressed_fields"])
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }

    assert entry.adapter == "arcgis"
    assert entry.settings["signal_stage"] == "parcel_context"
    assert entry.settings["export_policy"] == (
        "derived_nearby_parcel_context_only_no_raw_tennessee_comptroller_resale"
    )
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    assert entry.settings["connector"]["include_geometry"] is True
    assert "Davidson" in entry.settings["coverage_limitations"][0]
    assert "Shelby" in entry.settings["coverage_limitations"][0]
    assert suppressed.isdisjoint(out_fields)
    assert "owner_name" not in canonical_fields
    assert "total_assessed_value" not in canonical_fields
    assert "last_sale_date" not in canonical_fields
    assert "last_sale_price" not in canonical_fields


def test_charleston_active_commercial_permits_include_preapproval_and_approved():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "charleston_sc_active_commercial_permits"
    )
    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]

    assert entry.adapter == "arcgis"
    assert entry.record_type == "permit"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert entry.settings["export_policy"] == (
        "derived_permit_context_only_no_raw_charleston_sc_source_resale"
    )
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    assert "Building Commercial" in entry.settings["connector"]["where"]
    assert "Sign" in entry.settings["connector"]["where"]
    assert entry.settings["connector"]["include_geometry"] is False

    filed_record = {
        "OBJECTID": 1,
        "PERMIT_NUMBER": "BC2026-001",
        "PERMIT_TYPE": "Building Commercial",
        "WORK_CLASS": "Alteration",
        "PERMIT_STATUS": "Under Review",
        "APPLICATION_DATE": 1771516168000,
        "ISSUE_DATE": None,
        "PERMIT_ADDRESS_LINE1": "100 KING ST",
    }
    issued_record = filed_record | {
        "OBJECTID": 2,
        "PERMIT_NUMBER": "BC2026-002",
        "PERMIT_STATUS": "Issued",
        "ISSUE_DATE": 1771775368000,
    }

    filed, filed_mapping = prepare_mapped_record(filed_record, mappings)
    issued, issued_mapping = prepare_mapped_record(issued_record, mappings)
    filed_normalized = normalize_permit(filed, filed_mapping, defaults=entry.settings["defaults"])
    issued_normalized = normalize_permit(issued, issued_mapping, defaults=entry.settings["defaults"])

    assert filed_normalized.values["approval_stage"] == "pre_approval"
    assert issued_normalized.values["approval_stage"] == "approved"


def test_charleston_trc_development_plans_include_site_plan_preapproval():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "charleston_sc_trc_development_plans"
    )
    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]

    assert entry.adapter == "arcgis"
    assert entry.record_type == "permit"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert entry.settings["export_policy"] == (
        "derived_development_plan_context_only_no_raw_charleston_sc_source_resale"
    )
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    assert entry.settings["connector"]["where"] == "1=1"
    assert "PLAN_STATUS" in entry.settings["connector"]["out_fields"]
    assert "TRC_PLAN_NUMBER" in entry.settings["connector"]["out_fields"]

    review_record = {
        "OBJECTID": 11,
        "TRC_PLAN_NUMBER": "TRC-SP-2026-001",
        "PLAN_TYPE": "TRC - Site Plan",
        "WORK_CLASS": "TRC - Site Plan",
        "PLAN_STATUS": "Needs Review",
        "MAIN_ADDRESS_LINE1": "2057 WAMBAW CREEK RD",
    }
    approved_record = review_record | {
        "OBJECTID": 12,
        "TRC_PLAN_NUMBER": "TRC-SP-2026-002",
        "PLAN_STATUS": "Approved with Conditions",
    }

    review, review_mapping = prepare_mapped_record(review_record, mappings)
    approved, approved_mapping = prepare_mapped_record(approved_record, mappings)
    review_normalized = normalize_permit(
        review, review_mapping, defaults=entry.settings["defaults"]
    )
    approved_normalized = normalize_permit(
        approved, approved_mapping, defaults=entry.settings["defaults"]
    )

    assert review_normalized.values["approval_stage"] == "pre_approval"
    assert approved_normalized.values["approval_stage"] == "approved"


def test_provo_building_permits_include_pending_and_issued_lifecycle():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "provo_ut_building_permit_applications"
    )
    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]

    assert entry.adapter == "arcgis"
    assert entry.record_type == "permit"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert entry.settings["export_policy"] == (
        "derived_permit_context_only_no_raw_provo_source_resale"
    )
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    assert entry.settings["connector"]["include_geometry"] is True

    pending_record = {
        "OBJECTID": 100,
        "xxClient_BP_Applications_View_PermitNumber": "PRBD20260001",
        "xxClient_BP_Applications_View_Status": "In Plan Check",
        "xxClient_BP_Applications_View_dateIssued": None,
        "xxClient_BP_Applications_View_streetAddress": "100 W CENTER ST, Provo, UT",
    }
    issued_record = pending_record | {
        "OBJECTID": 101,
        "xxClient_BP_Applications_View_PermitNumber": "PRBD20260002",
        "xxClient_BP_Applications_View_Status": "Permit(s) Issued",
        "xxClient_BP_Applications_View_dateIssued": 1783468800000,
    }

    pending, pending_mapping = prepare_mapped_record(pending_record, mappings)
    issued, issued_mapping = prepare_mapped_record(issued_record, mappings)
    pending_normalized = normalize_permit(
        pending, pending_mapping, defaults=entry.settings["defaults"]
    )
    issued_normalized = normalize_permit(
        issued, issued_mapping, defaults=entry.settings["defaults"]
    )

    assert pending_normalized.values["approval_stage"] == "pre_approval"
    assert issued_normalized.values["approval_stage"] == "approved"


def test_provo_planning_applications_include_site_plan_preapproval():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "provo_ut_planning_applications"
    )
    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]

    assert entry.adapter == "arcgis"
    assert entry.record_type == "permit"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert entry.settings["export_policy"] == (
        "derived_planning_context_only_no_raw_provo_source_resale"
    )
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    assert entry.settings["connector"]["include_geometry"] is True

    review_record = {
        "OBJECTID": 200,
        "xxClient_Planning_Application_View_PermitNumber": "PLMPPA20260001",
        "xxClient_Planning_Application_View_StatusDescription": "Complete Application",
        "xxClient_Planning_Application_View_PAName": "Retail pad site plan",
        "xxClient_Planning_Application_View_Address": "200 N UNIVERSITY AVE",
    }
    approved_record = review_record | {
        "OBJECTID": 201,
        "xxClient_Planning_Application_View_PermitNumber": "PLMPPA20260002",
        "xxClient_Planning_Application_View_StatusDescription": "Approved",
    }

    review, review_mapping = prepare_mapped_record(review_record, mappings)
    approved, approved_mapping = prepare_mapped_record(approved_record, mappings)
    review_normalized = normalize_permit(
        review, review_mapping, defaults=entry.settings["defaults"]
    )
    approved_normalized = normalize_permit(
        approved, approved_mapping, defaults=entry.settings["defaults"]
    )

    assert review_normalized.values["approval_stage"] == "pre_approval"
    assert approved_normalized.values["approval_stage"] == "approved"


def test_maine_dep_land_applications_are_narrow_development_context():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "maine_dep_land_applications_and_permits"
    )
    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]

    assert entry.adapter == "arcgis"
    assert entry.record_type == "permit"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert entry.settings["export_policy"] == (
        "derived_development_context_only_no_raw_maine_dep_source_resale"
    )
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    assert entry.settings["connector"]["include_geometry"] is False

    in_process_record = {
        "OBJECTID": 1,
        "GIS_OBJECTID": "8029913068277532001",
        "ATS_NUMBER": "L-2026-001",
        "LICENSE_NUMBER": None,
        "STATUS": "In Process",
        "RECEIVED_DATE": "2026-07-01",
        "CONCLUSION_DATE": None,
        "PROJECT_DESCRIPTION": "Stormwater permit for retail site work",
    }
    completed_record = in_process_record | {
        "OBJECTID": 2,
        "GIS_OBJECTID": "8029913068277532002",
        "ATS_NUMBER": "L-2026-002",
        "LICENSE_NUMBER": "L-2026-002",
        "STATUS": "Completed",
        "CONCLUSION_DATE": "2026-07-10",
    }

    in_process, in_process_mapping = prepare_mapped_record(in_process_record, mappings)
    completed, completed_mapping = prepare_mapped_record(completed_record, mappings)
    in_process_normalized = normalize_permit(
        in_process, in_process_mapping, defaults=entry.settings["defaults"]
    )
    completed_normalized = normalize_permit(
        completed, completed_mapping, defaults=entry.settings["defaults"]
    )

    assert in_process_normalized.values["approval_stage"] == "pre_approval"
    assert completed_normalized.values["approval_stage"] == "approved"


def test_greenville_county_parcel_source_excludes_owner_value_sale_and_tax_fields():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "greenville_county_sc_parcels_narrow"
    )
    canonical_fields = {mapping.canonical_field for mapping in entry.field_mappings}
    suppressed = set(entry.settings["suppressed_fields"])
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }

    assert entry.adapter == "arcgis"
    assert entry.settings["signal_stage"] == "parcel_context"
    assert entry.settings["export_policy"] == (
        "derived_nearby_parcel_context_only_no_raw_greenville_county_sc_resale"
    )
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    assert entry.settings["connector"]["include_geometry"] is True
    assert suppressed.isdisjoint(out_fields)
    assert "OWNAM1" not in entry.settings["connector"]["out_fields"]
    assert "FAIRMKTVAL" not in entry.settings["connector"]["out_fields"]
    assert "SLPRICE" not in entry.settings["connector"]["out_fields"]
    assert "owner_name" not in canonical_fields
    assert "total_assessed_value" not in canonical_fields
    assert "last_sale_date" not in canonical_fields
    assert "last_sale_price" not in canonical_fields


def test_sedgwick_county_parcel_source_excludes_owner_address_value_and_sale_fields():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "sedgwick_county_ks_parcels_nearby_narrow"
    )
    canonical_fields = {mapping.canonical_field for mapping in entry.field_mappings}
    suppressed = set(entry.settings["suppressed_fields"])
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }

    assert entry.adapter == "arcgis"
    assert entry.settings["signal_stage"] == "parcel_context"
    assert entry.settings["export_policy"] == (
        "derived_nearby_parcel_context_only_no_raw_sedgwick_resale"
    )
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    assert entry.settings["connector"]["include_geometry"] is True
    assert "AIN" in entry.settings["connector"]["out_fields"]
    assert "PIN" in entry.settings["connector"]["out_fields"]
    assert suppressed.isdisjoint(out_fields)
    assert "OWNER" not in entry.settings["connector"]["out_fields"]
    assert "ADDRESS" not in entry.settings["connector"]["out_fields"]
    assert "SALE_PRICE" not in entry.settings["connector"]["out_fields"]
    assert "owner_name" not in canonical_fields
    assert "address" not in canonical_fields
    assert "total_assessed_value" not in canonical_fields
    assert "last_sale_date" not in canonical_fields
    assert "last_sale_price" not in canonical_fields


def test_utah_county_parcel_source_excludes_owner_sale_and_paid_extract_fields():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "utah_county_ut_parcels_nearby_narrow"
    )
    canonical_fields = {mapping.canonical_field for mapping in entry.field_mappings}
    suppressed = set(entry.settings["suppressed_fields"])
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }

    assert entry.adapter == "arcgis"
    assert entry.settings["signal_stage"] == "parcel_context"
    assert entry.settings["export_policy"] == (
        "derived_nearby_parcel_context_only_no_owner_or_raw_assessor_resale"
    )
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    assert entry.settings["connector"]["include_geometry"] is True
    assert "PARCEL_ID" in entry.settings["connector"]["out_fields"]
    assert "PARCEL_ADD" in entry.settings["connector"]["out_fields"]
    assert suppressed.isdisjoint(out_fields)
    assert "OWNERNAME" not in entry.settings["connector"]["out_fields"]
    assert "SALE_PRICE" not in entry.settings["connector"]["out_fields"]
    assert "owner_name" not in canonical_fields
    assert "total_assessed_value" not in canonical_fields
    assert "last_sale_date" not in canonical_fields
    assert "last_sale_price" not in canonical_fields


def test_maine_geolibrary_parcel_source_excludes_owner_table_and_raw_exports():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "maine_geolibrary_organized_towns_parcels_nearby_narrow"
    )
    canonical_fields = {mapping.canonical_field for mapping in entry.field_mappings}
    suppressed = set(entry.settings["suppressed_fields"])
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }

    assert entry.adapter == "arcgis"
    assert entry.settings["signal_stage"] == "parcel_context"
    assert entry.settings["export_policy"] == (
        "derived_nearby_parcel_context_only_no_owner_or_raw_assessor_resale"
    )
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    assert entry.settings["connector"]["include_geometry"] is True
    assert "STATE_ID" in entry.settings["connector"]["out_fields"]
    assert "PROP_LOC" in entry.settings["connector"]["out_fields"]
    assert suppressed.isdisjoint(out_fields)
    assert "OWNER" not in entry.settings["connector"]["out_fields"]
    assert "Shape__Area" not in entry.settings["connector"]["out_fields"]
    assert "owner_name" not in canonical_fields
    assert "total_assessed_value" not in canonical_fields
    assert "last_sale_date" not in canonical_fields
    assert "last_sale_price" not in canonical_fields


def test_bismarck_development_activities_preserve_preapproval_and_exclude_internal_fields():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "bismarck_nd_development_activities"
    )
    canonical_fields = {mapping.canonical_field for mapping in entry.field_mappings}
    suppressed = set(entry.settings["suppressed_fields"])
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }

    assert entry.adapter == "arcgis"
    assert entry.record_type == "permit"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert entry.settings["export_policy"] == (
        "derived_development_context_only_no_raw_bismarck_planning_activity_resale"
    )
    assert entry.settings["connector"]["keyset_field"] == "ObjectId"
    assert entry.settings["connector"]["include_geometry"] is True
    assert "PROJECT_NO" in entry.settings["connector"]["out_fields"]
    assert "STATUS" in entry.settings["connector"]["out_fields"]
    assert "APPLIED" in entry.settings["connector"]["out_fields"]
    assert "APPROVED" in entry.settings["connector"]["out_fields"]
    assert suppressed.isdisjoint(out_fields)
    assert "FEES_CHARGED" not in entry.settings["connector"]["out_fields"]
    assert "SITE_DESCRIPTION" not in entry.settings["connector"]["out_fields"]
    assert "Shape__Area" not in entry.settings["connector"]["out_fields"]
    assert "approval_stage" in canonical_fields
    assert "applicant_name" in canonical_fields
    assert "developer_name" in canonical_fields
    assert "parcel_id" in canonical_fields


def test_lincoln_development_applications_preserve_preapproval_and_exclude_raw_shape_fields():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "lincoln_ne_development_applications"
    )
    canonical_fields = {mapping.canonical_field for mapping in entry.field_mappings}
    suppressed = set(entry.settings["suppressed_fields"])
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }

    assert entry.adapter == "arcgis"
    assert entry.record_type == "permit"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert entry.settings["export_policy"] == (
        "derived_development_context_only_no_raw_lincoln_lancaster_pats_resale"
    )
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    assert entry.settings["connector"]["include_geometry"] is True
    assert "APPNUM" in entry.settings["connector"]["out_fields"]
    assert "STATUS" in entry.settings["connector"]["out_fields"]
    assert "SUBMITTAL_DATE" in entry.settings["connector"]["out_fields"]
    assert "EFFECTIVE_DATE" in entry.settings["connector"]["out_fields"]
    assert suppressed.isdisjoint(out_fields)
    assert "Shape.STArea()" not in entry.settings["connector"]["out_fields"]
    assert "Shape.STLength()" not in entry.settings["connector"]["out_fields"]
    assert "approval_stage" in canonical_fields
    assert "application_number" in canonical_fields
    assert "project_name" in canonical_fields
    assert "latitude" in canonical_fields
    assert "longitude" in canonical_fields

    prepared, field_mapping = prepare_mapped_record(
        {
            "OBJECTID": 5001,
            "APPNUM": "CZ26001",
            "SUBTYPE": "Change of Zone",
            "STATUS": "Staff Review",
            "SUBMITTAL_DATE": 1784073600000,
            "DESCRIPTION": "Rezoning and site plan for a national retailer",
            "PROJECT_NAME": "Highway Retail Center",
            "geometry": {
                "rings": [[
                    [-96.7051, 40.8129],
                    [-96.7031, 40.8129],
                    [-96.7031, 40.8141],
                    [-96.7051, 40.8141],
                    [-96.7051, 40.8129],
                ]]
            },
            "HYPERLINK": "https://lincoln.ne.gov/pats/example",
        },
        entry.field_mappings,
    )
    normalized = normalize_permit(
        prepared,
        field_mapping,
        defaults=entry.settings["defaults"],
    )

    assert normalized.source_record_id == "CZ26001"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["project_name"] == "Highway Retail Center"
    assert float(normalized.values["latitude"]) == pytest.approx(40.8135)
    assert float(normalized.values["longitude"]) == pytest.approx(-96.7041)


def test_sioux_falls_parcel_source_excludes_sale_legal_and_raw_exports():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "sioux_falls_sd_parcels_nearby_narrow"
    )
    canonical_fields = {mapping.canonical_field for mapping in entry.field_mappings}
    suppressed = set(entry.settings["suppressed_fields"])
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }

    assert entry.adapter == "arcgis"
    assert entry.settings["signal_stage"] == "parcel_context"
    assert entry.settings["attribution_required"] is True
    assert entry.settings["export_policy"] == (
        "derived_nearby_parcel_context_only_no_raw_sioux_falls_parcel_resale"
    )
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    assert entry.settings["connector"]["include_geometry"] is True
    assert "TAG" in entry.settings["connector"]["out_fields"]
    assert "ADDRESS" in entry.settings["connector"]["out_fields"]
    assert "OWNNAME1" in entry.settings["connector"]["out_fields"]
    assert suppressed.isdisjoint(out_fields)
    assert "LEGAL" not in entry.settings["connector"]["out_fields"]
    assert "SALE_PRICE" not in entry.settings["connector"]["out_fields"]
    assert "Shape.STArea()" not in entry.settings["connector"]["out_fields"]
    assert "owner_name" in canonical_fields
    assert "owner_mailing_address" in canonical_fields
    assert "total_assessed_value" not in canonical_fields
    assert "last_sale_date" not in canonical_fields
    assert "last_sale_price" not in canonical_fields


def test_cass_county_nd_parcel_source_excludes_owner_legal_sale_and_value_fields():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "cass_county_nd_parcels_nearby_narrow"
    )
    canonical_fields = {mapping.canonical_field for mapping in entry.field_mappings}
    suppressed = set(entry.settings["suppressed_fields"])
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }

    assert entry.adapter == "arcgis"
    assert entry.settings["signal_stage"] == "parcel_context"
    assert entry.settings["attribution_required"] is True
    assert entry.settings["export_policy"] == (
        "derived_nearby_parcel_context_only_no_raw_cass_county_nd_resale"
    )
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    assert entry.settings["connector"]["include_geometry"] is True
    assert "GISPIN" in entry.settings["connector"]["out_fields"]
    assert "PropertyAddress" in entry.settings["connector"]["out_fields"]
    assert "ACRES" in entry.settings["connector"]["out_fields"]
    assert suppressed.isdisjoint(out_fields)
    assert "MailName" not in entry.settings["connector"]["out_fields"]
    assert "LGDESC" not in entry.settings["connector"]["out_fields"]
    assert "ASSESSED_VALUE" not in entry.settings["connector"]["out_fields"]
    assert "SALE_PRICE" not in entry.settings["connector"]["out_fields"]
    assert "owner_name" not in canonical_fields
    assert "owner_mailing_address" not in canonical_fields
    assert "total_assessed_value" not in canonical_fields
    assert "last_sale_date" not in canonical_fields
    assert "last_sale_price" not in canonical_fields


def test_catalog_sync_is_idempotent_and_preserves_source_ids(db):
    entries = load_catalog()

    first = sync_catalog(db, entries)
    db.commit()
    source_ids = {source.key: source.id for source in db.query(IngestionSource).all()}
    mapping_count = db.query(SourceFieldMapping).count()

    second = sync_catalog(db, entries)
    db.commit()

    assert first.created == len(entries)
    assert second.unchanged == len(entries)
    assert {source.key: source.id for source in db.query(IngestionSource).all()} == source_ids
    assert db.query(SourceFieldMapping).count() == mapping_count


def test_catalog_sync_preserves_tenant_source_pause(db):
    entry = load_catalog()[0]
    sync_catalog(db, [entry])
    db.commit()
    source = db.query(IngestionSource).one()
    source.is_active = False
    db.commit()

    result = sync_catalog(db, [entry])
    db.commit()

    assert result.unchanged == 1
    assert db.query(IngestionSource).one().is_active is False


def test_catalog_sync_can_reactivate_a_catalog_disabled_source(db):
    active_entry = load_catalog()[0]
    inactive_entry = active_entry.model_copy(update={"is_active": False})
    sync_catalog(db, [inactive_entry])
    db.commit()
    assert db.query(IngestionSource).one().is_active is False

    result = sync_catalog(db, [active_entry])
    db.commit()

    assert result.updated == 1
    assert db.query(IngestionSource).one().is_active is True


def test_promoted_washington_sources_bootstrap_from_production_catalog(db):
    keys = {
        "washington_state_lcb_local_authority_letters",
        "everett_wa_planning_application_notices",
    }
    entries = [entry for entry in load_catalog() if entry.key in keys]

    first = sync_catalog(db, entries)
    db.commit()
    sources = {
        source.key: source
        for source in db.query(IngestionSource).filter(IngestionSource.key.in_(keys)).all()
    }

    assert first.created == 2
    assert set(sources) == keys
    assert sources["washington_state_lcb_local_authority_letters"].settings["connector"]["page_size"] == 500
    assert sources["washington_state_lcb_local_authority_letters"].settings[
        "reconciliation_mode"
    ] == "daily_rolling_window_incremental"
    assert sources["everett_wa_planning_application_notices"].settings["connector"]["page_size"] == 100
    assert {
        mapping.canonical_field
        for mapping in sources["washington_state_lcb_local_authority_letters"].field_mappings
    } >= {"source_record_id", "permit_number", "project_name", "latitude", "longitude"}
    assert "linked_document_body" in sources[
        "everett_wa_planning_application_notices"
    ].settings["suppressed_fields"]

    second = sync_catalog(db, entries)
    db.commit()
    assert second.unchanged == 2


def test_taylor_development_notices_promote_minimized_preapproval_evidence():
    entry = next(
        source
        for source in load_catalog()
        if source.key == "taylor_tx_development_notices"
    )
    record = {
        "guid": "https://www.taylortx.gov/CivicAlerts.aspx?aid=2079/639217198500000000",
        "title": "Notice of Public Hearings - PZ 2026-2715 - Employment Center Plan - Project Mustang",
        "link": "https://www.taylortx.gov/CivicAlerts.aspx?aid=2079",
        "published_at": "Fri, 07 Aug 2026 16:17:30 -0600",
        "description": "",
    }
    mappings = [
        SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings
    ]
    prepared, field_mapping = prepare_mapped_record(record, mappings)
    normalized = normalize_permit(
        prepared,
        field_mapping,
        defaults=entry.settings["defaults"],
    )

    assert normalized.source_record_id == record["guid"]
    assert normalized.values["application_number"] == "PZ 2026-2715"
    assert normalized.values["project_name"] == record["title"]
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["source_url"] == record["link"]
    assert entry.settings["candidate_status"] == "approved_for_production"
    assert entry.settings["promotion_rights_approved"] is True
    assert entry.settings["field_allowlist"] == [
        "guid",
        "title",
        "link",
        "published_at",
        "description",
    ]
    assert {
        "applicant_contact",
        "planner_contact",
        "linked_document_body",
        "enclosure",
        "raw_source_export",
    } <= set(entry.settings["suppressed_fields"])


@pytest.mark.parametrize(
    ("task_status", "expected_stage"),
    [
        ("Routed for Electronic Review", "pre_approval"),
        ("Plans Approved", "approved"),
    ],
)
def test_detroit_plan_reviews_promote_minimized_lifecycle_evidence(
    task_status, expected_stage
):
    entry = next(
        source
        for source in load_catalog()
        if source.key == "detroit_mi_bseed_building_plan_reviews"
    )
    record = {
        "ObjectId": 91382,
        "record_id": "BLD2026-01024",
        "address": "1200 WOODWARD AVE",
        "submitted_date": 1786752000000,
        "task": "Building Plan Review",
        "task_status": task_status,
        "task_status_date": 1786752000000,
        "work_description": "INTERIOR TENANT BUILDOUT",
        "parcel_id": "01000123.",
        "longitude": -83.0458,
        "latitude": 42.3314,
    }
    mappings = [
        SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings
    ]
    prepared, field_mapping = prepare_mapped_record(record, mappings)
    normalized = normalize_permit(
        prepared,
        field_mapping,
        defaults=entry.settings["defaults"],
    )

    assert normalized.source_record_id == "BLD2026-01024"
    assert normalized.values["approval_stage"] == expected_stage
    assert normalized.values["parcel_id"] == "01000123."
    assert entry.settings["candidate_status"] == "approved_for_production"
    assert entry.settings["promotion_rights_approved"] is True
    assert entry.settings["promotion_data_minimization_approved"] is True
    assert entry.settings["connector"]["include_geometry"] is False
    assert entry.settings["connector"]["out_fields"] == ",".join(
        entry.settings["field_allowlist"]
    )
    assert {
        "applicant_name",
        "owner_name",
        "contractor_name",
        "architect_name",
        "engineer_name",
        "reviewer_name",
        "task_id",
        "plan_file",
        "attachment",
        "document_body",
        "raw_geometry",
        "raw_source_export",
    } <= set(entry.settings["suppressed_fields"])


def test_san_marcos_notices_promote_contact_suppressed_preapproval_evidence():
    entry = next(
        source
        for source in load_catalog()
        if source.key == "san_marcos_tx_planning_application_notices"
    )
    record = {
        "article_id": "2617",
        "title": "ZC-26-07 (Wonder World Medical CM to BP)",
        "link": "https://www.sanmarcostx.gov/m/newsflash/Home/Detail/2617",
        "published_at": "August 11, 2026",
        "description": (
            "A Zoning Change Application from Commercial to Business Park was "
            "submitted by the Drenner Group on behalf of SM Hwy 123 Landholdings, LLC."
        ),
    }
    mappings = [
        SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings
    ]
    prepared, field_mapping = prepare_mapped_record(record, mappings)
    normalized = normalize_permit(
        prepared,
        field_mapping,
        defaults=entry.settings["defaults"],
    )

    assert normalized.source_record_id == "2617"
    assert normalized.values["application_number"] == "ZC-26-07"
    assert normalized.values["project_name"] == record["title"]
    assert normalized.values["description"] == record["description"]
    assert normalized.values["applicant_name"] == "Drenner Group"
    assert normalized.values["owner_name"] == "SM Hwy 123 Landholdings, LLC"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["source_url"] == record["link"]
    assert entry.adapter == "civicplus_newsflash"
    assert entry.settings["candidate_status"] == "approved_for_production"
    assert entry.settings["promotion_rights_approved"] is True
    assert entry.settings["promotion_data_minimization_approved"] is True
    assert entry.settings["field_allowlist"] == [
        "article_id",
        "title",
        "link",
        "published_at",
        "description",
    ]
    assert entry.settings["connector"]["category_id"] == 30
    assert entry.settings["connector"]["max_description_chars"] == 2000
    mapping_by_canonical = {
        mapping.canonical_field: mapping for mapping in entry.field_mappings
    }
    assert mapping_by_canonical["applicant_name"].value_semantics == "unknown"
    assert mapping_by_canonical["owner_name"].value_semantics == "unknown"
    assert {
        "email_address",
        "phone_number",
        "linked_detail_body",
        "linked_document_body",
        "attachment",
        "raw_source_export",
    } <= set(entry.settings["suppressed_fields"])


@pytest.mark.parametrize(
    ("description", "applicant", "owner"),
    [
        (
            "A Zoning Change Application has beensubmitted by the Drenner Group, "
            "onbehalf of SM Hwy 123 Landholdings, LLC, for approximately 4.64 acres.",
            "Drenner Group",
            "SM Hwy 123 Landholdings, LLC",
        ),
        (
            "A request was submitted by Shane Glosson, TWWG, LLC, on behalf of "
            "Sinai Pentecostal Church for approximately 14.72 acres.",
            "Shane Glosson, TWWG, LLC",
            "Sinai Pentecostal Church",
        ),
        (
            "A request has been submitted by Quiddity Engineering, LLC, on behalf "
            "of HEB, LP, to modify standards within the district.",
            "Quiddity Engineering, LLC",
            "HEB, LP",
        ),
    ],
)
def test_san_marcos_party_extraction_stops_at_project_narrative(
    description, applicant, owner
):
    entry = next(
        source
        for source in load_catalog()
        if source.key == "san_marcos_tx_planning_application_notices"
    )
    mappings = [
        SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings
    ]
    record = {
        "article_id": "test-party",
        "title": "ZC-26-99 Test",
        "link": "https://www.sanmarcostx.gov/m/newsflash/Home/Detail/test-party",
        "published_at": "August 14, 2026",
        "description": description,
    }

    prepared, field_mapping = prepare_mapped_record(record, mappings)
    normalized = normalize_permit(
        prepared, field_mapping, defaults=entry.settings["defaults"]
    )

    assert normalized.values["applicant_name"] == applicant
    assert normalized.values["owner_name"] == owner


def test_catalog_sync_updates_mutable_fields_and_rejects_adapter_change(db):
    original = load_catalog()[0]
    sync_catalog(db, [original])
    db.commit()
    source_id = db.query(IngestionSource).one().id

    changed_payload = original.model_dump()
    changed_payload["name"] = "Austin permits (official)"
    changed = IngestionSourceCreate.model_validate(changed_payload)
    result = sync_catalog(db, [changed])
    db.commit()

    assert result.updated == 1
    assert db.query(IngestionSource).one().id == source_id
    assert db.query(IngestionSource).one().name == "Austin permits (official)"

    invalid_payload = changed.model_dump()
    invalid_payload["adapter"] = "arcgis"
    with pytest.raises(ValueError, match="cannot change adapter"):
        sync_catalog(db, [IngestionSourceCreate.model_validate(invalid_payload)])


def test_declarative_transforms_cover_live_source_shapes():
    mappings = [
        FieldMappingCreate(
            source_field="street_number",
            canonical_field="address",
            transform="join_fields",
            transform_options={"fields": ["street_number", "direction", "street"], "separator": " "},
        ),
        FieldMappingCreate(
            source_field="link",
            canonical_field="source_url",
            transform="object_path",
            transform_options={"path": ["url"]},
        ),
        FieldMappingCreate(
            source_field="owner_business",
            canonical_field="owner_name",
            transform="first_nonempty",
            transform_options={"fields": ["owner_business", "owner_person"]},
        ),
        FieldMappingCreate(
            source_field="__approval_stage",
            canonical_field="approval_stage",
            transform="presence_map",
            transform_options={
                "field": "issued_at",
                "present": "approved",
                "absent": "pre_approval",
            },
        ),
        FieldMappingCreate(source_field="id", canonical_field="source_record_id"),
    ]
    record = {
        "id": "42",
        "street_number": "100",
        "direction": "N",
        "street": "State St",
        "link": {"url": "https://example.test/42"},
        "owner_business": "",
        "owner_person": "Jane Owner",
    }

    prepared, field_mapping = prepare_mapped_record(record, mappings)
    normalized = normalize_permit(prepared, field_mapping)

    assert normalized.values["address"] == "100 N State St"
    assert normalized.values["source_url"] == "https://example.test/42"
    assert normalized.values["owner_name"] == "Jane Owner"
    assert normalized.values["approval_stage"] == "pre_approval"


def test_unix_milliseconds_transform_normalizes_arcgis_dates():
    mappings = [
        FieldMappingCreate(source_field="id", canonical_field="source_record_id"),
        FieldMappingCreate(
            source_field="applied",
            canonical_field="filed_at",
            transform="unix_milliseconds",
        ),
    ]
    prepared, field_mapping = prepare_mapped_record(
        {"id": "arc-1", "applied": 1784073600000},
        mappings,
    )

    normalized = normalize_permit(prepared, field_mapping)

    assert normalized.values["filed_at"].isoformat() == "2026-07-15T00:00:00+00:00"


def test_unix_milliseconds_transform_can_quarantine_future_dates():
    mappings = [
        FieldMappingCreate(source_field="id", canonical_field="source_record_id"),
        FieldMappingCreate(
            source_field="issued",
            canonical_field="issued_at",
            transform="unix_milliseconds",
            transform_options={"max_future_hours": 48},
        ),
    ]
    prepared, field_mapping = prepare_mapped_record(
        {"id": "arc-future", "issued": 4102444800000},
        mappings,
    )

    normalized = normalize_permit(prepared, field_mapping)

    assert "issued_at" not in normalized.values


def test_date_transform_can_quarantine_future_dates():
    mappings = [
        FieldMappingCreate(source_field="id", canonical_field="source_record_id"),
        FieldMappingCreate(
            source_field="filed",
            canonical_field="filed_at",
            transform="date",
            transform_options={"max_future_hours": 48},
        ),
    ]
    prepared, field_mapping = prepare_mapped_record(
        {"id": "future-date", "filed": "2100-01-01"},
        mappings,
    )

    normalized = normalize_permit(prepared, field_mapping)

    assert "filed_at" not in normalized.values


def test_yyyymm_transform_normalizes_month_dates():
    mappings = [
        FieldMappingCreate(source_field="id", canonical_field="source_record_id"),
        FieldMappingCreate(
            source_field="sale_month",
            canonical_field="last_sale_date",
            transform="yyyymm",
        ),
    ]
    prepared, field_mapping = prepare_mapped_record(
        {"id": "parcel-1", "sale_month": "202406"},
        mappings,
    )
    normalized = normalize_parcel(prepared, field_mapping)

    assert normalized.values["last_sale_date"].isoformat() == "2024-06-01T00:00:00+00:00"

    blank_prepared, blank_mapping = prepare_mapped_record(
        {"id": "parcel-2", "sale_month": " "},
        mappings,
    )
    blank_normalized = normalize_parcel(blank_prepared, blank_mapping)
    assert "last_sale_date" not in blank_normalized.values


def test_permit_text_fields_coerce_numeric_identifiers_to_strings():
    mappings = [
        FieldMappingCreate(source_field="id", canonical_field="source_record_id"),
        FieldMappingCreate(source_field="id", canonical_field="application_number"),
    ]
    prepared, field_mapping = prepare_mapped_record({"id": 13669}, mappings)
    normalized = normalize_permit(prepared, field_mapping)

    assert normalized.source_record_id == "13669"
    assert normalized.values["application_number"] == "13669"


def test_parcel_date_fields_accept_numeric_yyyymmdd_values():
    mappings = [
        FieldMappingCreate(source_field="id", canonical_field="source_record_id"),
        FieldMappingCreate(source_field="sale_date", canonical_field="last_sale_date"),
    ]
    prepared, field_mapping = prepare_mapped_record(
        {"id": "parcel-1", "sale_date": 20240430},
        mappings,
    )

    normalized = normalize_parcel(prepared, field_mapping)

    assert normalized.values["last_sale_date"].isoformat() == "2024-04-30T00:00:00+00:00"


def test_parcel_date_fields_accept_epoch_milliseconds():
    mappings = [
        FieldMappingCreate(source_field="id", canonical_field="source_record_id"),
        FieldMappingCreate(source_field="sale_date", canonical_field="last_sale_date"),
    ]
    prepared, field_mapping = prepare_mapped_record(
        {"id": "parcel-1", "sale_date": 1734307200000},
        mappings,
    )

    normalized = normalize_parcel(prepared, field_mapping)

    assert normalized.values["last_sale_date"].isoformat() == "2024-12-16T00:00:00+00:00"

    prepared, field_mapping = prepare_mapped_record(
        {"id": "parcel-2", "sale_date": 31536000000},
        mappings,
    )

    old_sale = normalize_parcel(prepared, field_mapping)

    assert old_sale.values["last_sale_date"].isoformat() == "1971-01-01T00:00:00+00:00"


def test_parcel_date_fields_skip_zero_placeholders():
    mappings = [
        FieldMappingCreate(source_field="id", canonical_field="source_record_id"),
        FieldMappingCreate(source_field="sale_date", canonical_field="last_sale_date"),
    ]
    prepared, field_mapping = prepare_mapped_record(
        {"id": "parcel-1", "sale_date": 0},
        mappings,
    )

    normalized = normalize_parcel(prepared, field_mapping)

    assert "last_sale_date" not in normalized.values


def test_parcel_numeric_fields_skip_unknown_placeholders():
    mappings = [
        FieldMappingCreate(source_field="id", canonical_field="source_record_id"),
        FieldMappingCreate(source_field="land_value", canonical_field="land_value"),
        FieldMappingCreate(
            source_field="acreage",
            canonical_field="land_area_sq_ft",
            transform="multiply",
            transform_options={"factor": 43560},
        ),
        FieldMappingCreate(
            source_field="edited",
            canonical_field="observed_at",
            transform="unix_milliseconds",
        ),
    ]
    prepared, field_mapping = prepare_mapped_record(
        {
            "id": "parcel-1",
            "land_value": "UNKNOWN",
            "acreage": "UNKNOWN",
            "edited": "UNKNOWN",
        },
        mappings,
    )

    normalized = normalize_parcel(prepared, field_mapping)

    assert normalized.source_record_id == "parcel-1"
    assert "land_value" not in normalized.values
    assert "land_area_sq_ft" not in normalized.values
    assert "observed_at" not in normalized.values


def test_parcel_transforms_preserve_identity_and_derived_values():
    mappings = [
        FieldMappingCreate(
            source_field="bbl", canonical_field="source_record_id",
            transform="zero_pad", transform_options={"width": 10},
        ),
        FieldMappingCreate(
            source_field="__improvement", canonical_field="improvement_value",
            transform="subtract_fields", transform_options={"fields": ["total", "land"]},
        ),
        FieldMappingCreate(
            source_field="__assessed", canonical_field="total_assessed_value",
            transform="sum_fields", transform_options={"fields": ["school", "non_school"]},
        ),
    ]
    prepared, field_mapping = prepare_mapped_record(
        {
            "bbl": "100010010.0", "total": "750000", "land": "250000",
            "school": "325000", "non_school": "300000",
        },
        mappings,
    )

    normalized = normalize_parcel(prepared, field_mapping)

    assert normalized.source_record_id == "0100010010"
    assert normalized.values["improvement_value"] == 500000
    assert normalized.values["total_assessed_value"] == 625000


def test_arcgis_polygon_centroid_transform_derives_wgs84_point():
    mappings = [
        FieldMappingCreate(
            source_field="geometry",
            canonical_field="longitude",
            transform="arcgis_polygon_centroid",
            transform_options={"axis": "x"},
        ),
        FieldMappingCreate(
            source_field="geometry",
            canonical_field="latitude",
            transform="arcgis_polygon_centroid",
            transform_options={"axis": "y"},
        ),
    ]
    prepared, field_mapping = prepare_mapped_record(
        {
            "geometry": {
                "rings": [[
                    [-117.0, 32.0],
                    [-116.0, 32.0],
                    [-116.0, 33.0],
                    [-117.0, 33.0],
                    [-117.0, 32.0],
                ]]
            }
        },
        mappings,
    )

    normalized = normalize_parcel({"id": "parcel-1", **prepared}, {
        "id": "source_record_id",
        **field_mapping,
    })

    assert normalized.values["longitude"] == -116.5
    assert normalized.values["latitude"] == 32.5


def test_conditional_map_can_select_source_fields_for_physical_grouping():
    mapping = FieldMappingCreate(
        source_field="__physical_group",
        canonical_field="parcel_group_id",
        transform="conditional_map",
        transform_options={
            "cases": [
                {
                    "field": "use_code",
                    "operator": "in",
                    "values": ["004"],
                    "value_fields": ["address", "city", "postal_code"],
                }
            ],
            "default_field": "parcel_id",
            "separator": "|",
        },
    )

    condo, condo_mapping = prepare_mapped_record(
        {
            "parcel_id": "unit-12",
            "use_code": "004",
            "address": "100 Ocean Dr",
            "city": "Fort Lauderdale",
            "postal_code": "33301",
        },
        [mapping],
    )
    commercial, commercial_mapping = prepare_mapped_record(
        {"parcel_id": "store-1", "use_code": "011", "address": "200 Main St"},
        [mapping],
    )

    condo_key = next(key for key, value in condo_mapping.items() if value == "parcel_group_id")
    commercial_key = next(
        key for key, value in commercial_mapping.items() if value == "parcel_group_id"
    )
    assert condo[condo_key] == "100 Ocean Dr|Fort Lauderdale|33301"
    assert commercial[commercial_key] == "store-1"


def test_required_transformed_fields_validate_raw_inputs():
    mappings = [
        FieldMappingCreate(
            source_field="__composite_id",
            canonical_field="source_record_id",
            transform="join_fields",
            transform_options={"fields": ["town_code", "plat_lot"], "separator": ":"},
            is_required=True,
        ),
    ]

    assert missing_required_source_fields(
        {"town_code": "PROV", "plat_lot": "001-002"},
        mappings,
    ) == []
    assert missing_required_source_fields({"town_code": "PROV"}, mappings) == ["plat_lot"]


def test_parcel_coordinates_are_optional_but_must_be_a_complete_pair():
    mapping = {"id": "source_record_id", "lat": "latitude", "lon": "longitude"}

    assert normalize_parcel({"id": "pointless"}, mapping).source_record_id == "pointless"
    with pytest.raises(ValueError, match="must be supplied together"):
        normalize_parcel({"id": "partial", "lat": "40.7"}, mapping)


def test_parcel_postal_codes_are_normalized_as_text():
    normalized = normalize_parcel(
        {"id": "duval-1", "postal": 32207},
        {"id": "source_record_id", "postal": "postal_code"},
    )

    assert normalized.values["postal_code"] == "32207"


def test_value_map_is_case_insensitive_and_rejects_invalid_stage():
    mapping = FieldMappingCreate(
        source_field="__approval_stage",
        canonical_field="approval_stage",
        transform="value_map",
        transform_options={
            "field": "status",
            "values": {"under review": "pre_approval", "issued": "approved"},
        },
    )
    prepared, field_mapping = prepare_mapped_record(
        {"id": "1", "status": "  UNDER REVIEW "},
        [FieldMappingCreate(source_field="id", canonical_field="source_record_id"), mapping],
    )
    assert normalize_permit(prepared, field_mapping).values["approval_stage"] == "pre_approval"

    bad_mapping = mapping.model_copy(
        update={"transform_options": {"field": "status", "values": {"issued": "final"}}}
    )
    prepared, field_mapping = prepare_mapped_record(
        {"id": "1", "status": "issued"},
        [FieldMappingCreate(source_field="id", canonical_field="source_record_id"), bad_mapping],
    )
    with pytest.raises(ValueError, match="Unknown approval stage"):
        normalize_permit(prepared, field_mapping)


def test_required_first_nonempty_treats_whitespace_as_missing():
    mappings = [
        FieldMappingCreate(
            source_field="__source_record_id",
            canonical_field="source_record_id",
            transform="first_nonempty",
            transform_options={"fields": ["state_id", "local_id"]},
            is_required=True,
        )
    ]

    assert missing_required_source_fields(
        {"state_id": " ", "local_id": "\t"},
        mappings,
    ) == ["state_id|local_id"]


def test_regex_extract_reads_case_identity_from_another_field():
    mapping = FieldMappingCreate(
        source_field="__application_number",
        canonical_field="application_number",
        transform="regex_extract",
        transform_options={
            "source_field": "link",
            "pattern": r"(?i)(rev(?:ii|iii)\d{2}-\d+)",
        },
    )

    prepared, field_mapping = prepare_mapped_record(
        {"link": "https://example.test/Notice-of-Application-REVII26-014"},
        [mapping],
    )

    mapped_key = next(
        key for key, canonical in field_mapping.items()
        if canonical == "application_number"
    )
    assert prepared[mapped_key] == "REVII26-014"


def test_regex_extract_rejects_an_unknown_capture_group():
    mapping = FieldMappingCreate(
        source_field="case_number",
        canonical_field="application_number",
        transform="regex_extract",
        transform_options={"pattern": r"(PZ-\d+)", "group": 2},
    )

    with pytest.raises(ValueError, match="group does not exist"):
        prepare_mapped_record({"case_number": "PZ-123"}, [mapping])


def test_object_path_transform_can_read_list_indexes():
    mappings = [
        FieldMappingCreate(source_field="id", canonical_field="source_record_id"),
        FieldMappingCreate(
            source_field="location",
            canonical_field="longitude",
            transform="object_path",
            transform_options={"path": ["coordinates", "0"]},
        ),
        FieldMappingCreate(
            source_field="__latitude",
            canonical_field="latitude",
            transform="object_path",
            transform_options={
                "source_field": "location",
                "path": ["coordinates", "1"],
            },
        ),
    ]
    prepared, field_mapping = prepare_mapped_record(
        {
            "id": "point-1",
            "location": {"type": "Point", "coordinates": [-122.38356, 47.6667]},
        },
        mappings,
    )
    normalized = normalize_permit(prepared, field_mapping)

    assert float(normalized.values["longitude"]) == pytest.approx(-122.38356)
    assert float(normalized.values["latitude"]) == pytest.approx(47.6667)


def test_conditional_map_uses_ordered_generic_rules():
    mapping = FieldMappingCreate(
        source_field="__approval_stage",
        canonical_field="approval_stage",
        transform="conditional_map",
        transform_options={
            "cases": [
                {"field": "approved_at", "operator": "present", "value": "approved"},
                {
                    "field": "status",
                    "operator": "in",
                    "values": ["Approved and Released"],
                    "value": "approved",
                },
            ],
            "default": "pre_approval",
        },
    )
    prepared, field_mapping = prepare_mapped_record(
        {"id": "1", "status": " approved AND released "},
        [FieldMappingCreate(source_field="id", canonical_field="source_record_id"), mapping],
    )

    assert normalize_permit(prepared, field_mapping).values["approval_stage"] == "approved"


def test_each_catalog_mapping_normalizes_representative_record():
    samples = {
        "austin_tx_issued_construction_permits": {
            "project_id": "A-1", "permit_number": "BP-1", "permit_location": "100 Main St",
            "issue_date": "2026-07-01T00:00:00.000", "link": {"url": "https://example.test/a"},
        },
        "seattle_wa_issued_building_permits": {
            "permitnum": "S-1", "originaladdress1": "200 Pine St", "estprojectcost": "250000",
            "statuscurrent": "Reviews In Process", "link": {"url": "https://example.test/s"},
        },
        "seattle_wa_land_use_permits": {
            ":id": "row-2dta_qmr9~zi65",
            "permitnum": "3044186-LU",
            "permitclass": "Industrial",
            "permitclassmapped": "Non-Residential",
            "permittypemapped": "Master Use Permit",
            "permittypedesc": None,
            "description": "Land Use Application to allow a 9-story Business Support Services (Data Center) building.",
            "housingunits": None,
            "housingunitsremoved": None,
            "housingunitsadded": None,
            "estprojectcost": "220000000.0000",
            "applieddate": "2026-06-05",
            "issueddate": None,
            "expiresdate": None,
            "decisiondate": None,
            "statuscurrent": "Reviews In Process",
            "originaladdress1": "3625 1ST AVE S",
            "originalcity": "SEATTLE",
            "originalstate": "WA",
            "originalzip": "98134",
            "contractorcompanyname": None,
            "link": {"url": "https://services.seattle.gov/portal/customize/LinkToRecord.aspx?altId=3044186-LU"},
            "latitude": "47.57035461",
            "longitude": "-122.33579131",
            "location1": {"latitude": "47.57035461", "longitude": "-122.33579131"},
        },
        "seattle_wa_street_use_public_notices": {
            "address": "5311 Ballard Ave NW",
            "city": "SEATTLE",
            "state": "WA",
            "zip_code": "98107",
            "business": "Radiator Whisky",
            "application_type": "Curb Space Cafe",
            "size": "12 ft x 10 ft",
            "application_number": "SUPSM0009602",
            "start_of_public_comment_period": "2026-07-08T00:00:00.000",
            "end_of_public_comment_period": "2026-07-22T00:00:00.000",
            "location": {
                "type": "Point",
                "coordinates": [-122.38356, 47.6667],
            },
        },
        "san_francisco_ca_planning_department_non_project_records": {
            "record_id": "2026-006230CUA",
            "parent_id": "2026-006230PRJ",
            "record_type": "CUA",
            "record_status": "Submitted",
            "open_date": "2026-07-14T00:00:00.000",
            "close_date": None,
            "project_name": "3995 24TH STREET",
            "description": "A Conditional Use authorization is sought to extend the hours of operation for an existing Starbucks.",
            "project_address": "3995 24TH ST 94114",
            "block": "6508",
            "lot": "025",
            "building_permits": None,
            "applicant_org": "Greenbergfarrow",
            "pim_link": {"url": "https://sfplanninggis.org/pim?search=2026-006230CUA"},
        },
        "marin_county_ca_commercial_building_permits": {
            "unique_id": "OM_94301",
            "permit_tracking_id": "94301",
            "permit_number": "",
            "received_date": "2026-06-15T00:00:00.000",
            "issued_date": None,
            "address": "3422 STATE ROUTE 1, STINSON BEACH, CA 94970",
            "parcel_number": "195-193-35",
            "zipcode": "94970",
            "city_town": "STINSON BEACH",
            "city_town_inferred": "STINSON BEACH",
            "type_permit": "COMMERCIAL",
            "permit_work_class": "New; OtherTransportation; ",
            "fee_code_title": "All Commercial Uses - New construction; Electrical Permits",
            "description": "(N) Two-Story Fire Station, Driveway, Accessible Parking Stalls, Ev Stalls",
            "contractor": None,
            "construction_value": "9205000",
            "latitude": "37.8984955",
            "longitude": "-122.6398061",
        },
        "san_jose_ca_planning_permit_applications": {
            "OBJECTID": 246744,
            "FOLDERRSN": "1968004",
            "FOLDERNUM": "671531",
            "FOLDERDESC": "Japantown Corp Yard mixed-use building with office space and residential units",
            "FOLDERNAME": "ER22-112",
            "ADDRESS": "653 7TH ST",
            "APN": "24939044",
            "APPLICANT": "Sean McEachern (Shea Properties)",
            "OWNERNAME": "Shea Properties",
            "WORKDESC": "Addendum",
            "SUBDESC": "Private Project, NEPA not applicable",
            "INDATE": 1651223219000,
            "ISSUEDATE": 1783468800000,
            "FINALDATE": None,
            "REFERENCENUM": "ER22-112",
            "ZONING": "",
            "LASTUPDATE": 1783594737000,
            "ENTERPRISEID": "PLN-PMPL-0000246747",
            "GlobalID": "{155B248D-5349-4CA1-97BE-784A9533AF4B}",
            "PERMITSTATUS": "Under Review",
            "PERMITISSUE": "ISSUED",
            "PERMITTYPE": "Environmental Review ",
            "FOLDERYR": "22",
            "geometry": {"x": -121.89330186193912, "y": 37.350830461721635},
        },
        "washington_ecology_sepa_register": {
            "separegisterid": "191961",
            "sepanumber": "202504947",
            "proposalname": "Kyle Single-Use Dock Maintenance Project",
            "proposaltypename": "Project",
            "proposaldescription": "Shoreline exemption permit for dock maintenance",
            "leadagencyname": "Douglas County",
            "leadagencyfilenumber": "SE-2025-06",
            "leadagencyissuedate": "2025-11-24T00:00:00.000",
            "siteline1address": "68 Orchard Dr",
            "sitecityname": "Orondo",
            "sitezipcode": "98843",
            "siteparcelnumber": "26211230009",
            "sitesectiontownrange": "Section 12, Township 26N, Range 21E",
            "sitelatitudedecimal": "47.768638",
            "sitelongitudedecimal": "-120.153727",
            "applicantname": "Gerald Kyle",
            "documenttypecode": "ODNS/NOA",
            "documentsubtypecode": "NOA",
            "countyname": "DOUGLAS",
            "regionname": "Central",
            "commentsduedate": "2025-12-29T00:00:00.000",
            "publisheddate": "2025-11-26T00:00:00.000",
            "separegisterlink": {
                "url": "https://apps.ecology.wa.gov/separ/Main/SEPA/Record.aspx?SEPANumber=202504947",
            },
        },
        "pierce_county_wa_pals_permits": {
            "OBJECTID": 618063,
            "applicationNumber": 987744,
            "applicationType": "Residential Fire Sprinkler System",
            "applicationStatus": "Issued",
            "parcelNumber": "0220072023",
            "workType": "Tenant Improvement",
            "buildingType": "Commercial",
            "housingType": None,
            "sqFtTotal": 2500,
            "buildingValuation": 100000,
            "dwellingUnits": "0",
            "acreage": 1.2,
            "projectValue": 125000,
            "projectId": 50332,
            "applicationDept": "*BUILDING*",
            "applicationDate": 1769213242000,
            "submittalDate": 1769213242000,
            "approvalDate": 1769676431000,
            "denialDate": None,
            "issuedDate": 1769676490000,
            "finalDate": None,
            "workDescription": "Review for commercial tenant improvement",
            "siteAddress": "28926 31st AV E",
            "projectName": "Retail Pad",
            "urlOnlinePermits": "https://pals.piercecountywa.gov/palsonline/#/permitSearch/permit/departmentStatus?applPermitId=987744",
            "lotsSubmitted": None,
            "geometry": {"x": -122.60184784163869, "y": 47.241701901638855},
        },
        "bellingham_wa_nonres_building_permits": {
            "OBJECTID": 178399906,
            "PERMIT_NO": "BLD2025-0814",
            "PERMIT_CATEGORY": "BUILDING",
            "PERMIT_CLASS": "NONRESIDENTIAL",
            "APPLIED": 1757894400000,
            "APPROVED": None,
            "ISSUED": None,
            "FINALED": None,
            "EXPIRED": 1789689600000,
            "PARENT_PROJECT_NO": None,
            "PARENT_PERMIT_NO": None,
            "PermitType": "BUILDING NONRESIDENTIAL",
            "PermitSubType": "ADDITION",
            "STATUS": "REQUEST FOR INFO",
            "SITE_ADDR": "200 E CHESTNUT ST",
            "DESCRIPTION": "2 STORY OFFICE & KITCHEN ADDITION TO (E) RESTAURANT: FIAMMA",
            "JOBVALUE": 540321.42,
            "EXIST_FLOOR_AREA": None,
            "NEW_FLOOR_AREA": 2362,
            "TOTAL_FLOOR_AREA": 4962,
            "NUM_STORIES": None,
            "SCOPEOFWORK": None,
            "SITE_APN": "380330163051",
            "SITE_ALTERNATE_ID": None,
            "GEO_STATUS": "ACTIVE",
            "GIS_OBJECT_ID": 12345,
            "Occupancy_Class_1": None,
            "Floor_Area_1": None,
            "Occupancy_Class_2": None,
            "Floor_Area_2": None,
            "Neighborhood": "DOWNTOWN",
            "Zoning_Description": "Downtown District Urban Village",
            "Query_Result": "New Construction Applied not yet Issued (in last year)",
            "geometry": {"x": -122.47955604935133, "y": 48.74774419347438},
        },
        "chicago_il_building_permits": {
            "id": "C-1", "permit_": "10001", "street_number": "300", "street_direction": "W",
            "street_name": "Lake St", "reported_cost": "500000",
        },
        "new_york_ny_dob_now_approved_permits": {
            "tracking_number": "N-1", "job_filing_number": "M0001", "house_no": "400",
            "street_name": "Broadway", "owner_name": "NY Owner", "estimated_job_costs": "750000",
        },
        "austin_tx_plan_review_cases": {
            "folderrsn": "13443068", "permit_number": "2024-162610 PR",
            "project_name": "3309 GOODWIN AVE", "status_current": "In Review",
            "folder_description": "Commercial finish-out for a new store",
            "applied_date": "2026-07-01T00:00:00.000",
            "web_link": {"url": "https://example.test/austin-review"},
        },
        "new_york_ny_dob_now_job_applications": {
            ":id": "row-test-1", "job_filing_number": "M00855935-I1",
            "filing_status": "Plan Examiner Review",
            "house_no": "418", "street_name": "EAST 14 STREET", "borough": "Manhattan",
            "job_type": "Alteration", "job_description": "Interior retail fit-out",
            "filing_date": "2026-07-01T00:00:00.000",
        },
        "austin_tx_site_plan_cases": {
            "folderrsn": "155510", "permit_number": "SP-26-1000C",
            "case_type": "Site Plan", "case_name": "STARBUCKS SOUTH LAMAR",
            "status": "In Review", "description_of_work": "New retail coffee shop",
            "proposed_land_use": "RETAIL", "street_number": "100",
            "street_name": "S LAMAR", "street_type": "BLVD",
            "application_start_date": "2026-07-01T00:00:00.000",
        },
        "new_york_ny_legacy_job_applications": {
            "job_s1_no": "3294719", "job__": "440673852", "job_type": "A2",
            "job_status_descrp": "PLAN EXAM", "job_description": "Retail tenant fit-out",
            "house__": "100", "street_name": "BROADWAY", "borough": "MANHATTAN",
            "pre__filing_date": "07/01/2026", "initial_cost": "$37300.00",
        },
        "new_orleans_la_permits_blds": {
            ":id": "row-test-nola-1", "permitnum": "26-20590-FGAS",
            "permittypemapped": "Mechanical", "permittypedesc": "Mechanical Fuel Gas",
            "workclass": "Mechanical Fuel Gas", "permitclassmapped": "Residential",
            "statuscurrent": "Application Submitted", "description": "Install a gas line",
            "originaladdress1": "994 Bragg St", "originalcity": "New Orleans",
            "originalstate": "LA", "originalzip": "70124", "applieddate": "2026-07-13T14:05:50.000",
            "link": {"url": "http://onestopapp.nola.gov/Redirect.aspx?SearchString=3MXG1U"},
        },
        "east_baton_rouge_la_building_permits": {
            "permitid": "9340123",
            "permitnumber": "182979",
            "permittype": "Existing Bldg - Remodel Only (C)",
            "designation": "Commercial",
            "projectdescription": "Renovation to convert 976sf office space into Parent Resource Center for University View Academy.",
            "squarefootage": "976",
            "projectvalue": "250000",
            "creationdate": "2026-06-10T00:00:00.000",
            "issueddate": "2026-07-17T00:00:00.000",
            "address": "3112 VALLEY CREEK DR BATON ROUGE LA 70808",
            "streetaddress": "3112 VALLEY CREEK DR",
            "city1": "BATON ROUGE",
            "state1": "LA",
            "zip": "70808",
            "parishname": "East Baton Rouge",
            "ownername": "Barry Harris",
            "applicantname": "Michael Jackson",
            "contractorname": "CONTOUR DEVELOPMENT GROUP LLC - Michael Jevon Jackson",
            "lat": "30.402",
            "long": "-91.106",
        },
        "san_francisco_ca_building_permits_primary_address": {
            "record_id": "1545854157209", "permit_number": "202603226060",
            "permit_type_definition": "additions alterations or repairs",
            "status": "filed", "description": "Retail tenant improvement",
            "street_number": "760", "street_name": "14th", "street_suffix": "St",
            "proposed_use": "retail sales", "permit_creation_date": "2026-07-01T00:00:00.000",
            "data_loaded_at": "2026-07-16T04:38:02.190",
        },
        "boulder_co_construction_permits": {
            "PermitID": "9a91ea18-c6f4-4a18-a0f9-09973c4db52f",
            "PermitNum": "PMT2026-00123", "PermitType": "Building",
            "PermitWorkType": "Tenant Finish", "ProjectName": "Retail Fit-Out",
            "Description": "Interior tenant finish for retail store",
            "StatusCurrent": "In Review", "OriginalAddress": "1000 Pearl St",
            "OriginalCity": "Boulder", "OriginalState": "CO", "OriginalZip": "80302",
            "COBPIN": "R000001", "EstProjectCost": 650000,
            "AppliedDate": 1784073600000,
        },
        "denver_co_commercial_construction_permits": {
            "GLOBALID": "{8F92C5FD-2222-4444-AAAA-1234567890AB}",
            "LOG_NUM": "2026-LOG-1000", "PERMIT_NUM": "2026-COMM-1000",
            "CLASS": "Commercial", "ADDRESS": "100 W Colfax Ave",
            "SCHEDNUM": "0001001000", "CONTRACTOR_NAME": "Builder Inc",
            "VALUATION": 750000, "UNITS": 0, "DATE_RECEIVED": 1784073600000,
            "DATE_ISSUED": 1784160000000, "STAT_CODE_1": "Issued",
            "LOCATION": {"x": -104.9903, "y": 39.7392},
        },
        "denver_co_residential_construction_permits": {
            "GLOBALID": "{7F92C5FD-2222-4444-AAAA-1234567890AB}",
            "LOG_NUM": "2026-LOG-1001", "PERMIT_NUM": "2026-RES-1001",
            "CLASS": "Residential", "ADDRESS": "101 W Colfax Ave",
            "SCHEDNUM": "0001001001", "CONTRACTOR_NAME": "Builder Inc",
            "VALUATION": 250000, "UNITS": 1, "DATE_RECEIVED": 1784073600000,
            "DATE_ISSUED": 1784160000000, "STAT_CODE_1": "Issued",
            "LOCATION": {"x": -104.9902, "y": 39.7391},
        },
        "denver_co_demolition_permits": {
            "GLOBALID": "{6F92C5FD-2222-4444-AAAA-1234567890AB}",
            "LOG_NUM": "2026-LOG-1002", "PERMIT_NUM": "2026-DEMO-1002",
            "CLASS": "Demolition", "ADDRESS": "102 W Colfax Ave",
            "SCHEDNUM": "0001001002", "CONTRACTOR_NAME": "Demo Inc",
            "VALUATION": 50000, "UNITS": 0, "DATE_RECEIVED": 1784073600000,
            "DATE_ISSUED": 1784160000000, "STAT_CODE_1": "Issued",
            "LOCATION": {"x": -104.9901, "y": 39.7390},
        },
        "somerville_ma_building_permit_applications": {
            "application_id": "APP-2026-00123", "application_number": "B-26-123",
            "file_number": "BLD-26-123", "application_type": "Building Permit",
            "application_subtype": "Commercial", "application_category": "Alteration",
            "project_description_or_business_name": "Retail tenant fit-out",
            "status": "Under Review", "application_address": "100 Broadway",
            "parcel_number": "34-A-10", "applicant_company_name": "Applicant LLC",
            "contractor_company": "Builder Inc", "estimated_construction_cost": "450000",
            "application_latitude": "42.3876", "application_longitude": "-71.0995",
            "application_date": "2026-07-15T00:00:00.000",
        },
        "san_diego_ca_development_permit_approvals_2026": {
            "DEVELOPMENT_ID": "DEV-1000", "PROJECT_ID": "PRJ-1154192",
            "PROJECT_TYPE": "Building Construction", "PROJECT_STATUS": "In Review",
            "PROJECT_TITLE": "STARBUCKS TENANT IMPROVEMENT",
            "PROJECT_SCOPE": "Tenant improvement for a coffee shop",
            "JOB_ID": "JOB-109484", "GIS_ADDRESS": "207 05th Av, San Diego, CA",
            "GIS_APN": "5353441201", "JOB_BC_CODE_DESCRIPTION": "Tenant Improvements",
            "GIS_LATITUDE": "32.707662", "GIS_LONGITUDE": "-117.159941",
            "APPROVAL_ID": "PMT-3408464", "APPROVAL_TYPE": "Building Permit",
            "APPROVAL_STATUS": "In Review",
            "APPROVAL_SCOPE": "Interior retail tenant improvement",
            "APPROVAL_CREATE_DATE": "2026-03-26", "APPROVAL_ISSUE_DATE": "",
            "APPROVAL_CLOSE_DATE": "", "APPROVAL_EXPIRE_DATE": "",
            "APPROVAL_VALUATION": "159000.00", "APPROVAL_FLOOR_AREA": "4500",
            "APPROVAL_PERMIT_HOLDER": "Coffee Tenant LLC",
        },
        "cleveland_oh_building_permit_applications": {
            "PERMIT_ID": "B26001234", "PERMIT_TYPE": "Building",
            "PERMIT_SUBTYPE": "Commercial", "PERMIT_CATEGORY": "Alteration",
            "PLAN_TYPE": "Plan Review", "USE_GROUP_1": "Mercantile",
            "WORK_DESCRIPTION": "Interior retail tenant improvement",
            "PERMIT_ISSUED": "Pending", "PRIMARY_ADDRESS": "100 Euclid Ave",
            "PARCEL_NUMBER": "101-01-001", "CONTRACTOR_BUSINESS_NAME": "Builder Inc",
            "CONTRACTOR_LICENSE_ID": "LIC-100", "JOB_VALUE": 900000,
            "FILE_DATE": 1784073600000,
        },
        "cincinnati_oh_building_permits": {
            ":id": "row-cincy-1", "permitnum": "CBLD2026-00421",
            "description": "Interior alteration for national retail tenant",
            "applieddate": "2026-07-15T00:00:00.000", "issueddate": None,
            "completeddate": None, "expiresdate": "2027-01-15T00:00:00.000",
            "coissueddate": None, "statuscurrent": "ROUTE",
            "statuscurrentmapped": "In Review", "originaladdress1": "100 Vine St",
            "originalcity": "Cincinnati", "originalstate": "OH",
            "originalzip": "45202", "jurisdiction": "CINCINNATI",
            "permitclass": "OBC", "permitclassmapped": "Non-Residential",
            "workclass": "ALT", "workclassmapped": "Existing",
            "permittype": "COMM", "permittypemapped": "Building",
            "proposeduse": "M", "companyname": "National Retail Buildout LLC",
            "totalsqft": "24000", "estprojectcostdec": "850000",
            "units": "1", "pin": "00100010001", "fee": "1200",
            "link": "http://cagis.hamilton-co.org/opal/Permit.aspx?permit=CBLD2026-00421",
            "latitude": "39.1015", "longitude": "-84.5125",
            "neighborhood": "Downtown",
        },
        "portland_or_development_and_building_applications": {
            "FOLDERKEY": 1234567, "APPLICATION": "2026-012345-000-00-CO",
            "TYPE": "CO", "PERMIT": "Commercial Building Permit",
            "FOLDERTYPE": "Alteration", "WORK_DESCRIPTION": "Tenant improvement",
            "OCCUPANCYGROUP": "M", "STATUS": "Under Review",
            "DESCRIPTION": "Interior remodel for retail tenant",
            "HOUSE": 100, "DIRECTION": "N", "PROPSTREET": "Broadway",
            "STREETTYPE": "St", "CITY": "Portland", "STATEIDKEY": "R123456",
            "SUBMITTEDVALUATION": 750000, "TOTALSQFT": 5000, "NUMNEWUNITS": 0,
            "CREATEDATE": 1784073600000,
        },
        "pittsburgh_pa_issued_building_permits": {
            "permit_id": "P-2026-00123", "permit_type": "Building",
            "work_type": "Alteration", "commercial_or_residential": "Commercial",
            "status": "Issued", "work_description": "Retail tenant fit-out",
            "address": "100 Grant St", "parcel_num": "0001-A-00010",
            "owner_name": "Property Owner LLC", "contractor_name": "Builder Inc",
            "total_project_value": "350000", "latitude": "40.4406",
            "longitude": "-79.9959", "issue_date": "2026-07-15T00:00:00",
        },
        "milwaukee_wi_commercial_permit_work": {
            "Record ID": "COM-2026-00123",
            "Permit Type": "Commercial Alteration Permit",
            "Status": "Issued",
            "Address": "100 W Wisconsin Ave",
            "Construction Total Cost": "$350,000",
            "Use of Building": "Retail",
            "Date Opened": "2026-07-01T00:00:00",
            "Date Issued": "2026-07-15T00:00:00",
        },
        "minneapolis_mn_commercial_construction_permits": {
            "OBJECTID": 1001, "permitNumber": "BLDG-2026-00123",
            "permitType": "Commercial", "workType": "Remodel",
            "occupancyType": "Mercantile", "status": "In Process",
            "milestone": "Plan Review", "Display": "100 Nicollet Mall",
            "APN": "0102824110001",
            "comments": "Interior tenant improvement for retail use",
            "value": "350000", "totalFees": "2500",
            "issueDate": None, "completeDate": None,
            "applicantName": "BuildCo Inc", "fullName": "Property Owner LLC",
            "applicantAddress1": "PO BOX 100", "applicantCity": "MINNEAPOLIS",
            "Longitude": "-93.2712", "Latitude": "44.9765",
            "Neighborhoods_Desc": "Downtown West", "Wards": "7",
        },
        "st_louis_mo_commercial_occupancy_applications": {
            "OccupancyApplicationID": 13669,
            "PermitType": "Commercial Occupancy",
            "PermitTypeID": 44,
            "ApplicationDate": "2026-06-16",
            "ProjectAddress": "3750 WASHINGTON BLVD",
            "UnitNumber": "",
            "ProjectCity": "St. Louis",
            "ProjectState": "MO",
            "ProjectZipCode": "63108",
            "ProjectParcelID": "228700400",
            "ProjectASRParcelID": "22879400000",
            "ProjectHandle": "12287000400",
            "OwnerName": "CONTEMPORARY ART MUSEUM ST LOUIS",
            "OwnerAddress": "3750 WASHINGTON BLVD",
            "OwnerCity": "ST LOUIS",
            "OwnerState": "MO",
            "OwnerZipCode": "63108",
            "BusinessType": "Cafe",
            "BusinessTypeDescription": "FULL DRINK CAFE W/PATIO SEATING",
            "CurrentResult": "Open",
            "CurrentResultDate": "2026-06-23",
            "OccupancyPermitTotalFee": 80.0,
            "ProjectX": "895930.4815",
            "ProjectY": "1022149.703",
        },
        "louisville_jefferson_ky_active_construction_permits": {
            "ObjectId": 1001,
            "PERMIT_NUMBER": "BLD-C-26-00123",
            "PERMIT_TYPE": "Commercial",
            "PERMIT_STATUS": "Issued",
            "CONTRACTOR": "BuildCo Inc",
            "CATEGORY_NAME": "Retail",
            "WORK_TYPE": "Alteration",
            "ZONING": "C-2",
            "SQFT": 4500,
            "PERMIT_FEE": 1250,
            "PROJECT_COSTS": 350000,
            "ADDRESS": "100 W MAIN ST",
            "CITY": "LOUISVILLE",
            "STATE": "KY",
            "ZIPCODE": "40202",
            "LATITUDE": 38.2542,
            "LONGITUDE": -85.7594,
            "DISTRICT": "4",
            "NEIGHBORHOOD": "Downtown",
            "ISSUE_DATE": 1784073600000,
        },
        "montgomery_county_md_commercial_permits": {
            "permitno": "COM-2026-00123", "applicationtype": "Commercial Building",
            "worktype": "Alteration", "usecode": "Retail", "status": "Issued",
            "description": "Interior tenant fit-out for retail use", "stno": "100",
            "predir": "N", "stname": "Washington", "suffix": "St",
            "city": "Rockville", "state": "MD", "zip": "20850",
            "declaredvaluation": "500000", "buildingarea": "4500",
            "latitude": "39.084", "longitude": "-77.1528",
            "addeddate": "2026-07-01T00:00:00.000",
            "issueddate": "2026-07-15T00:00:00.000",
        },
        "maryland_imap_sdat_parcel_points": {
            "OBJECTID": 1, "JURSCODE": "STMA", "ACCTID": "1901000047",
            "ADDRESS": "18214 BAUER RD", "CITY": "LEXINGTON PARK",
            "ZIPCODE": "20653", "OWNADD1": "18214 BAUER RD",
            "OWNADD2": None, "OWNCITY": "SAINT MARYS CITY",
            "OWNSTATE": "MD", "OWNERZIP": "20686", "OWNZIP2": None,
            "ZONING": "RPD", "CIUSE": None, "DESCCIUSE": None,
            "LU": "R", "DESCLU": "Residential", "ACRES": 1.5,
            "LANDAREA": 1.5, "YEARBLT": "1976", "SQFTSTRC": 2505,
            "BLDG_UNITS": 1, "TRADATE": "20250429", "CONSIDR1": "637500",
            "NFMLNDVL": 637500, "NFMIMPVL": 334800,
            "NFMTTLVL": 972300,
            "SDATWEBADR": "https://sdat.dat.maryland.gov/RealProperty/Pages/viewdetails.aspx?County=19&SearchType=ACCT&District=01&AccountNumber=000047",
            "MDPVDATE": "2023JUN", "SDATDATE": "2026MAY",
            "geometry": {"x": -76.4579, "y": 38.2746},
        },
        "henderson_nv_commercial_development_permits": {
            "GISHISTORYQUEUEID": "f689e904-45bd-41fb-8842-6a70843d2760",
            "CASENUMBER": "BCOM2026395457", "CASETYPE": "Commercial Building",
            "CASEWORKCLASS": "New", "WORKCLASS": "Commercial",
            "STATUS": "Pending", "DESCRIPTION": "Two generator units on slab",
            "PROJECTNAME": "Retail Center", "MAIN_ADDRESS_LINE1": "100 Water St",
            "SPATIALID": "19103411003", "OWNER": "Property Owner LLC",
            "APPLICATIONDATE": 1784073600000, "LASTCHANGEDON": 1784160000000,
        },
        "vermont_act250_large_development_context": {
            "ProjectID": 8277, "AppNum": "4C1234-1", "AppType": "Major",
            "ProjectName": "Burlington Retail Redevelopment",
            "Description": "Construction of a mixed-use retail and restaurant building",
            "ProjectTown": "Burlington", "District": "4C",
            "Status": "Pending", "GisLatitude": "44.4762",
            "GisLongitude": "-73.2121",
            "LINK": "https://anrweb.vt.gov/Act250/Details.aspx?Num=4C1234-1",
        },
        "montgomery_al_commercial_construction_permits": {
            "OBJECTID": 58957,
            "GlobalID": "{39CB553C-B2AA-4298-BAA3-3A3D347967BD}",
            "PermitNo": "BD250476",
            "PermitStatus": "ISSUED",
            "IssuedDate": "2025-03-10",
            "ExpiredDate": "2026-07-13",
            "last_edited_date": 1752158830000,
            "CodeDetail": "Building",
            "PermitCode": "B105",
            "PermitDescription": "Five or More Family Apartments - Master Permit",
            "ProjectType": "New",
            "UseType": "Commercial",
            "JobDescription": "Erect a new multifamily complex",
            "PhysicalAddress": "10510 CHANTILLY PKWY MONTGOMERY AL 36117",
            "Address": "1200 BRICKELL AVE MIAMI FL 33131",
            "ParcelNo": "09 06 23 2 000 003.001",
            "OwnerName": "OREI MONTGOMERY PROPERTY OWNER LLC",
            "OwnerAddress": "MOORESVILLE NC 28117",
            "ContractorName": "COURTNEY BURROWS",
            "EstimatedCost": 17625000.0,
            "FinalValue": 1309600.0,
            "Total_Fee": 106325.0,
            "Zoning": "R-65-M",
            "DistrictCouncil": 9,
            "Year": "2025",
            "Month": "3",
            "geometry": {"x": -86.1358, "y": 32.3574},
        },
        "fayetteville_ar_permit_lifecycle_narrow": {
            "OBJECTID": 305000,
            "PERMITNUMBER": "COMM-2026-0001",
            "PM_TYPE": "Commercial Building Permit",
            "FULLADD": "100 W CENTER ST",
            "DESCRIPTION": "Interior retail tenant improvement",
            "PM_STATUS": "In Review",
            "VALUE": 9100000.0,
            "PM_WCLASS": "Alteration",
            "IMP_AREA": 4500.0,
            "ISSUEDATE": None,
            "FINALIZEDATE": None,
            "URL": "https://egov.fayetteville-ar.gov/energov_prod/selfservice#/permit/test",
            "last_edited_date": 1784316810000,
            "geometry": {"x": -94.1574, "y": 36.0626},
        },
        "fort_worth_tx_civic_commercial_permits": {
            "CAPID": 844269,
            "Unique_ID": "PB16-0001412201281400468139246",
            "Permit_No": "PB16-00014",
            "Permit_Type": "Commercial Building Permit",
            "Permit_SubType": "Remodel",
            "Permit_Category": "NA",
            "Current_Status": "Plan Review",
            "File_Date": 1451865600000,
            "Status_Date": 1454544000000,
            "B1_SPECIAL_TEXT": "WAYNE'S GROCERY",
            "B1_WORK_DESC": "COM REROOF OF EXISTING GROCERY STORE",
            "Address": "1704 VAUGHN BLVD",
            "Zip_Code": "76105",
            "Owner_Full_Name": "WAYNE'S GROCERY CORPORATION",
            "JobValue": 22000.0,
            "Use_Type": "Sales and Service",
            "Specific_Use": "Retail Store",
            "Units": "0",
            "SqFt": "0",
            "Latitude": 32.72775917047564,
            "Longitude": -97.2797600590043,
            "geometry": {"x": -97.27976770230153, "y": 32.7277648776862},
        },
        "texas_comptroller_sales_tax_locations": {
            "tp_number": "17418232123",
            "tp_name": "STARBUCKS CORPORATION",
            "org_type": "CORPORATION",
            "loc_number": "9812",
            "loc_name": "STARBUCKS",
            "address_number": "1000",
            "address_text": "MAIN ST STE 120",
            "permit_date": "2026-07-09T00:00:00.000",
            "juris_city": "HOUSTON",
            "loc_city": "HOUSTON",
            "loc_state": "TX",
            "loc_zip": "77002",
            "loc_county": "101",
            "naics": "722515",
            "first_sale_date": "2026-08-01T00:00:00.000",
            "out_of_business_date": None,
        },
        "charleston_sc_active_commercial_permits": {
            "OBJECTID": 31100001,
            "PMPERMITID": "24-123456",
            "PERMIT_NUMBER": "BC2026-001",
            "PERMIT_TYPE": "Building Commercial",
            "WORK_CLASS": "Alteration",
            "PERMIT_STATUS": "Under Review",
            "APPLICATION_DATE": 1771516168000,
            "ISSUE_DATE": None,
            "FINALED_DATE": None,
            "DESCRIPTION": "Retail tenant improvement for national coffee chain",
            "PROJECT": "King Street Coffee",
            "MAIN_PARCEL_NUMBER": "457-01-02-003",
            "PERMIT_ADDRESS_LINE1": "100 KING ST",
            "PERMIT_ADDRESS_LINE2": "CHARLESTON SC 29401",
            "ZIPCODE": "29401",
            "MAIN_ZONE": "GB",
            "DISTRICT": "Peninsula",
            "FLD_ZONE": "X",
            "VALUATION": 250000,
            "SQUARE_FEET": 4500,
            "TOTAL_FEE_AMOUNT": 1850,
        },
        "charleston_sc_trc_development_plans": {
            "OBJECTID": 1042,
            "TRC_PLAN_NUMBER": "TRC-SP-2026-001",
            "PLAN_NUMBER": "PLN-2026-001",
            "PLPLANID": "PL-1042",
            "PRPROJECTID": "PR-1042",
            "PLAN_TYPE": "TRC - Site Plan",
            "WORK_CLASS": "TRC - Site Plan",
            "PLAN_STATUS": "Needs Review",
            "APPLY_DATE": 1771516168000,
            "COMPLETE_DATE": None,
            "DESCRIPTION": "New retail outparcel and parking revisions",
            "PROJECT": "Wambaw Retail Pad",
            "MAIN_PARCEL_NUMBER": "310-00-00-001",
            "MAIN_ADDRESS_LINE1": "2057 WAMBAW CREEK RD",
            "MAIN_ADDRESS_LINE2": "CHARLESTON SC 29492",
            "PARCELADDR_LINE1": "2057 WAMBAW CREEK RD",
            "PARCELADDR_LINE2": "CHARLESTON SC 29492",
            "VALUATION": 1250000,
            "SQUARE_FEET": 9800,
            "TotalAcres": 2.4,
            "DisturbedAreaAcres": 1.3,
            "NumResUnits": 0,
            "BuildingFootprintSqft": 9800,
            "NumberofKeyedRooms": 0,
        },
        "provo_ut_building_permit_applications": {
            "OBJECTID": 98560150,
            "xxClient_BP_Applications_View_dateEntered": 1783468800000,
            "xxClient_BP_Applications_View_dateIssued": None,
            "xxClient_BP_Applications_View_PermitNumber": "PRBD20260001",
            "xxClient_BP_Applications_View_PAName": "National retailer tenant finish",
            "xxClient_BP_Applications_View_Type": "Tenant Improvement",
            "xxClient_BP_Applications_View_BuildingUse": "COM",
            "xxClient_BP_Applications_View_streetAddress": "1200 N UNIVERSITY AVE, Provo, UT 84604",
            "xxClient_BP_Applications_View_ZoneLand": "Commercial",
            "xxClient_BP_Applications_View_NumberUnits": 0,
            "xxClient_BP_Applications_View_TotalValuation": 650000,
            "xxClient_BP_Applications_View_ContractorName": "Wasatch Retail Builders LLC",
            "xxClient_BP_Applications_View_Status": "In Plan Check",
            "xxClient_BP_Applications_View_dateFinalized": None,
            "ADDRESS_ADDRESS": "1200 N UNIVERSITY AVE",
            "ADDRESS_ADDRESS_DESIGNATION": "COM",
            "ADDRESS_ADDRESS_STATUS": "DVD",
            "geometry": {"x": -111.6585, "y": 40.2502},
        },
        "provo_ut_planning_applications": {
            "OBJECTID": 460830,
            "xxClient_Planning_Application_View_dateEntered": 1783468800000,
            "xxClient_Planning_Application_View_PAName": "University retail pad",
            "xxClient_Planning_Application_View_PermitNumber": "PLMPPA20260001",
            "xxClient_Planning_Application_View_Location": "1200 N UNIVERSITY AVE",
            "xxClient_Planning_Application_View_RecordID": 1162896,
            "xxClient_Planning_Application_View_Address": "1200 N UNIVERSITY AVE, Provo, UT 84604",
            "xxClient_Planning_Application_View_PublicNotSummary": "Minor project plan for new retail pad and drive-through circulation.",
            "xxClient_Planning_Application_View_Status": "COMP",
            "xxClient_Planning_Application_View_StatusDescription": "Complete Application",
            "xxClient_Planning_Application_View_DateCRCPrinted": None,
            "xxClient_Planning_Application_View_dateRevisionsReceived": None,
            "xxClient_Planning_Application_View_LastHearingType": "Planning Commission",
            "xxClient_Planning_Application_View_LastHearingDate": 1784073600000,
            "xxClient_Planning_Application_View_AppealDeadlineDate": None,
            "xxClient_Planning_Application_View_CVDateLastModified": 1784073600000,
            "xxClient_Planning_Application_View_dateClosed": None,
            "xxClient_Planning_Application_View_dateExpiration": 1815609600000,
            "xxClient_Planning_Application_View_DateReceived": 1783382400000,
            "xxClient_Planning_Application_View_DatePCAdminHearing": None,
            "xxClient_Planning_Application_View_DateCouncilHearing": None,
            "ADDRESS_ADDRESS": "1200 N UNIVERSITY AVE",
            "ADDRESS_ADDRESS_DESIGNATION": "COM",
            "ADDRESS_ADDRESS_STATUS": "DVD",
            "geometry": {"x": -111.6585, "y": 40.2502},
        },
        "maine_dep_land_applications_and_permits": {
            "OBJECTID": 10772,
            "GIS_OBJECTID": "8029913068277532099",
            "ATS_NUMBER": "PBR_ID-77392",
            "LICENSE_NUMBER": "PBR_ID-77392",
            "TOWN": "OAKLAND",
            "APPLICANT_NAME": "LARRY & JUNE KASSMAN",
            "PROJECT_DESCRIPTION": "Stormwater and land permit context for site improvements",
            "STATUS": "Completed",
            "RECEIVED_DATE": "2023-07-18",
            "ACCEPTED_DATE": "2023-07-27",
            "CONCLUSION_DATE": "2023-07-27",
            "WATERBODY_NAME": "MESSALONSKEE LAKE",
            "TAX_MAP_MAP_NUMBER": "001",
            "TAX_MAP_LOT_NUMBER": "002",
        },
        "bismarck_nd_development_activities": {
            "ObjectId": 3,
            "GlobalID": "85f53001-1590-4786-90f4-267d6544d391",
            "TRAKiT_ID": "SP2024-005",
            "TYPE": "Site Plan",
            "DESCRIPTION": "This site plan is for the construction of a lift station",
            "Link": "https://bismarcknd.gov/2384/Open-Development-Projects",
            "HearingBoard": None,
            "HearingDate": None,
            "Final_ID": None,
            "PROJECT_NO": "SP2024-005",
            "PROJECT_NAME": "STATE PENITENTIARY LIFT STATION",
            "PROJECTTYPE": "SITE PLAN REVIEW",
            "PROJECTSUBTYPE": "CITY WITHOUT LANDSCAPE PLAN",
            "PRIMARY_PIN": None,
            "SITE_APN": "0115-002-010",
            "SITE_ADDR": "3100 RAILROAD AVE",
            "SITE_CITY": "BISMARCK",
            "SITE_STATE": "ND",
            "SITE_ZIP": "58501",
            "ZONING": None,
            "GENPLAN": None,
            "LAND_USE": None,
            "PROJECT_LOC": None,
            "PLANNER": "Jenny Wollmuth",
            "APPLIED": 1707372000000,
            "APPROVED": None,
            "CLOSED": None,
            "STATUS": "Staff Review",
            "STATUS_DATE": 1707976800000,
            "EXPIRED": None,
            "OWNER_NAME": "STATE OF ND",
            "APPLICANT_NAME": "APEX ENGINEERING GROUP, INC.",
            "DEVELOPER_NAME": None,
            "CONTRACTOR_NAME": "",
            "REFERENCE_NO": None,
            "SITE_ALTERNATE_ID": None,
            "SITE_GEOTYPE": "PARCEL",
            "geometry": {
                "rings": [[
                    [-100.7475960, 46.8022150],
                    [-100.7400000, 46.8022150],
                    [-100.7400000, 46.8080000],
                    [-100.7475960, 46.8080000],
                    [-100.7475960, 46.8022150],
                ]]
            },
        },
        "lincoln_ne_development_applications": {
            "OBJECTID": 5001,
            "APPNUM": "CZ26001",
            "SUBTYPE": "Change of Zone",
            "HYPERLINK": "https://www.lincoln.ne.gov/City/Departments/Planning-Department/Development-Review/PATS",
            "STATUS": "Staff Review",
            "SUBMITTAL_DATE": 1784073600000,
            "DESCRIPTION": "Rezoning and site plan for a national retailer",
            "NUMBER_OF_DUS": 0,
            "NUMBER_OF_LOTS": 2,
            "PLANNER_ASSIGNED": "Planning Staff",
            "PROJECT_NAME": "Highway Retail Center",
            "EFFECTIVE_DATE": None,
            "PC_RESOLUTION_": None,
            "CC_RESOLUTION_": None,
            "CC_ORDINANCE_": None,
            "CB_RESOLUTION_": None,
            "ZONING_SIGN_POSTED": 1784160000000,
            "ZONING_SIGN_PULLED": None,
            "PERMIT_BEING_AMENDED": None,
            "PC_HEARING": 1786665600000,
            "GlobalID": "a7b4f5ab-0e6c-4e2b-aef6-000000000001",
            "geometry": {
                "rings": [[
                    [-96.7051, 40.8129],
                    [-96.7031, 40.8129],
                    [-96.7031, 40.8141],
                    [-96.7051, 40.8141],
                    [-96.7051, 40.8129],
                ]]
            },
        },
        "new_york_ny_pluto_parcels": {
            "bbl": "100010010.0", "address": "1 Centre St", "zipcode": "10007",
            "latitude": "40.713", "longitude": "-74.004", "lotarea": "25000",
            "bldgarea": "100000", "assessland": "2500000", "assesstot": "8000000",
            "landuse": "05", "zonedist1": "C6-4", "ownername": "CITY OF NEW YORK",
            "version": "26v1",
        },
        "san_diego_ca_sangis_parcel_spine": {
            "objectid": 3, "apn": "6782511200", "apn_8": "67825112",
            "parcelid": 13238, "situs_address": 100, "situs_fraction": "",
            "situs_pre_dir": "W", "situs_street": "BERNARDO",
            "situs_suffix": "CT", "situs_post_dir": "",
            "situs_building": "", "situs_suite": "",
            "situs_community": "SAN DIEGO", "situs_zip": "92127",
            "situs_juris": "SD", "acreage": "3.24", "sub_type": 1,
            "multi": "N", "nucleus_use_cd": "400", "nucleus_zone_cd": "70",
            "asr_landuse": 40, "asr_zone": 7,
            "geometry": {
                "rings": [[
                    [-117.2, 32.8],
                    [-117.1, 32.8],
                    [-117.1, 32.9],
                    [-117.2, 32.9],
                    [-117.2, 32.8],
                ]]
            },
        },
        "louisville_jefferson_ky_lojic_parcels_narrow": {
            "OBJECTID": 1, "LRSN": 123456, "PARCELID": "001A00010000",
            "PARCEL_TYPE": 1, "GLOBALID": "{11111111-2222-3333-4444-555555555555}",
            "PIN": "001A00010000", "SHAPE.AREA": 15000, "SHAPE.LEN": 500,
            "geometry": {
                "rings": [[
                    [-85.760, 38.254],
                    [-85.759, 38.254],
                    [-85.759, 38.255],
                    [-85.760, 38.254],
                ]]
            },
        },
        "vermont_vcgi_statewide_parcels_narrow": {
            "OBJECTID": 1001, "SPAN": "114-035-10123", "GLIST_SPAN": "11403510123",
            "PARCID": "035-10123", "MAPID": "035-10123", "TOWN": "BURLINGTON",
            "TNAME": "Burlington", "PROPTYPE": "PARCEL", "SOURCENAME": "Burlington",
            "SOURCETYPE": "Municipal Grand List", "SOURCEDATE": "2026-04-01",
            "EDITDATE": 1784073600000, "MATCHSTAT": "MATCH",
            "OWNER1": "BURLINGTON RETAIL OWNER LLC", "OWNER2": "",
            "ADDRGL1": "PO BOX 100", "ADDRGL2": "", "CITYGL": "BURLINGTON",
            "STGL": "VT", "ZIPGL": "05401", "DESCPROP": "Commercial",
            "CAT": "Commercial", "E911ADDR": "100 CHURCH ST",
            "LOCAPROP": "100 CHURCH STREET", "ACRESGL": "0.85",
            "REAL_FLV": "2500000", "HSTED_FLV": "0", "NRES_FLV": "2500000",
            "LAND_LV": "900000", "IMPRV_LV": "1600000",
            "geometry": {
                "rings": [[
                    [-73.214, 44.476],
                    [-73.213, 44.476],
                    [-73.213, 44.477],
                    [-73.214, 44.477],
                    [-73.214, 44.476],
                ]]
            },
        },
        "rhode_island_statewide_tax_parcels_narrow": {
            "OBJECTID": 2001, "TownCode": "PROV", "PlatLot": "001-002",
            "Acres": "0.45", "E911Desc": "Commercial", "E911_Type": "Retail",
            "IMP_sqft": "12000", "Last_UPD": 1784073600000,
            "geometry": {
                "rings": [[
                    [-71.415, 41.823],
                    [-71.414, 41.823],
                    [-71.414, 41.824],
                    [-71.415, 41.824],
                    [-71.415, 41.823],
                ]]
            },
        },
        "new_hampshire_dra_granit_parcel_mosaic_narrow": {
            "objectid": 65017, "parceloid": 173431,
            "nh_gis_id": "104001-252-010-000", "oid_1": None,
            "pid": "252-010-000", "displayid": "252-010-000",
            "u_id": "4001-550", "town": "Acworth", "townid": "4001",
            "countyid": "10", "streetaddress": "RHOADES RD",
            "slu": "22", "sluc": "22", "slum": None, "localnbc": "40",
            "nbc": 0, "name": "CamaID: 252-010-000",
            "SHAPE__Length": 4386.46, "SHAPE__Area": 1069756.88,
            "centroid": {"x": -72.292, "y": 43.196},
            "geometry": {
                "rings": [[
                    [-72.293, 43.195],
                    [-72.291, 43.195],
                    [-72.291, 43.197],
                    [-72.293, 43.197],
                    [-72.293, 43.195],
                ]]
            },
        },
        "montgomery_al_parcels_nearby_narrow": {
            "OBJECTID": 1,
            "ParcelNo": "01 07 35 0 000 001.000",
            "PID": "0107350000001000",
            "PropertyAddr1": "HUGHES FERRY RD",
            "PropertyCity": "MONTGOMERY",
            "PropertyState": "AL",
            "PropertyZip": "36110",
            "Calc_Acre": 36.3949261,
            "AssessmentClass": "3",
            "Neighborhood": "BRLS",
            "MunicipalityCode": "01",
            "FireDist": "I",
            "RecordYear": 2026,
            "centroid": {"x": -86.23945176157477, "y": 32.49316384545932},
            "geometry": {
                "rings": [[
                    [-86.240, 32.493],
                    [-86.239, 32.493],
                    [-86.239, 32.494],
                    [-86.240, 32.494],
                    [-86.240, 32.493],
                ]]
            },
        },
        "arkansas_statewide_parcels_nearby_narrow": {
            "objectid": 1,
            "countyfips": "05023",
            "countyid": "023-001-09300-001",
            "parcelid": "001-09300-001",
            "sourceref": "202200336",
            "sourcedate": 1641880800000,
            "adrnum": None,
            "predir": None,
            "pstrnam": "NOLA PORTER",
            "pstrtype": "RD",
            "psufdir": None,
            "adrcity": "Rural",
            "adrzip5": 0,
            "adrlabel": "NOLA PORTER RD",
            "parceltype": "AV",
            "subdivision": "11-09-12",
            "nbhd": "1",
            "section": 11,
            "township": "09",
            "range": "12",
            "str": "11-09-12",
            "taxcode": "023212",
            "taxarea": 9.96,
            "camaprov": "ACT",
            "county": "Cleburne",
            "dataprov": "DataScout OneMap",
            "camadate": 1771826400000,
            "pubdate": 1775019600000,
            "globalid": "{15FD3BA7-A97F-45FE-B284-6815AE169853}",
            "geometry": {"x": -92.24012393203219, "y": 35.42370171028212},
        },
        "collin_county_tx_parcels_nearby_narrow": {
            "OBJECTID": 118,
            "PROP_ID": 37,
            "propID": 37,
            "geoID": "R-0002-00A-0030-1",
            "gisPropID": 37,
            "propYear": 2026,
            "dataDate": "2026-07-10T00:48:07.697",
            "situsBldgNum": "1630",
            "situsStreetPrefix": None,
            "situsStreetName": "COIT",
            "situsStreetSuffix": "RD",
            "situsUnit": None,
            "situsCity": "PLANO",
            "situsZip": "75075",
            "situsConcat": "1630 COIT RD, PLANO, TX 75075",
            "situsConcatShort": "1630 COIT RD",
            "propType": "Real",
            "propSubType": "Commercial",
            "propCategoryCode": "F1",
            "propUseCode": "MDO",
            "comPropFlag": "T",
            "landSizeAcres": 1.1309,
            "landSizeSqft": 49262,
            "legalAbsSubName": "AMERICAN NATIONAL BANK",
            "legalAbsSubBlock": "A",
            "legalAbsSubLot": "3",
            "mapID": "112.T",
            "nbhdCode": None,
            "marketAreaCode": "PW",
            "entityCodes": "GCN,JCN,SPL,CPL",
            "entitySchoolCode": "SPL",
            "entityCityCode": "CPL",
            "entityMUD": "F",
            "entityTIF": "F",
            "entitySBCL": "F",
            "udiPropFlag": "F",
            "udiGroupID": None,
            "ecoGroupID": 62284,
            "propSplitFromPID": None,
            "GlobalID": "ce822750-5224-4e59-9344-fc05eae5390c",
            "geometry": {
                "rings": [[
                    [-96.768, 33.020],
                    [-96.767, 33.020],
                    [-96.767, 33.021],
                    [-96.768, 33.021],
                    [-96.768, 33.020],
                ]]
            },
        },
        "tennessee_comptroller_impact_parcels_nearby_narrow": {
            "OBJECTID": 1,
            "COUNTY_ID": 34,
            "PARCEL_TYPE": 1,
            "GISLINK": "034003    00800",
            "GISLINK2": " ",
            "CALC_ACRE": 28.640078,
            "PARCELWP": "008.00",
            "GlobalID": None,
            "geometry": {
                "rings": [[
                    [-86.500, 35.900],
                    [-86.499, 35.900],
                    [-86.499, 35.901],
                    [-86.500, 35.901],
                    [-86.500, 35.900],
                ]]
            },
        },
        "greenville_county_sc_parcels_narrow": {
            "OBJECTID": 484845,
            "PIN": "0001000100100",
            "STRNUM": "23",
            "LOCATE": "NORTH MAIN ST",
            "JURIS": "1",
            "DIST": "501",
            "MKTAREA": "C00081",
            "LANDUSE": "520",
            "PROPTYPE": "COMMERCIAL",
            "IMPROVED": "YES",
            "SUBDIV": "DOWNTOWN",
            "TACRES": 0.08,
            "geometry": {
                "rings": [[
                    [-82.398, 34.851],
                    [-82.397, 34.851],
                    [-82.397, 34.852],
                    [-82.398, 34.852],
                    [-82.398, 34.851],
                ]]
            },
        },
        "sedgwick_county_ks_parcels_nearby_narrow": {
            "OBJECTID": 1,
            "PIN": "00134235",
            "GEOCODE": "B 14458",
            "AIN": "087215210220100900",
            "RDParDocID": "745530",
            "MultUnitTP": " ",
            "MultSubNO": " ",
            "RDMulDocID": " ",
            "MultBldgNO": " ",
            "MultUnitNO": " ",
            "UnitLevel": 0,
            "UnitStatus": " ",
            "ParcSqFTC": 39373.68823,
            "ParcAcresC": 0.9039,
            "ParcAreaTP": 1,
            "EditDT": 1548335859000,
            "geometry": {
                "rings": [[
                    [-97.3322226, 37.6029134],
                    [-97.3329992, 37.6029078],
                    [-97.3329998, 37.6033884],
                    [-97.3322231, 37.6033940],
                    [-97.3322226, 37.6029134],
                ]]
            },
        },
        "utah_county_ut_parcels_nearby_narrow": {
            "OBJECTID": 1,
            "PARCEL_ID": "010350006",
            "PARCEL_ADD": "33 N 100 W",
            "PARCEL_CITY": "Lehi",
            "PARCEL_ZIP": "84043",
            "OWN_TYPE": "Private",
            "RECORDER": "1-801-851-8179",
            "ParcelsCur": 1783468800000,
            "ParcelsRec": 1783468800000,
            "ParcelsPub": 1783468800000,
            "ParcelYear": "2026",
            "ParcelNotes": "Dynamic snapshot from county",
            "CoParcel_URL": "https://maps.utahcounty.gov/ParcelMap/ParcelMap.html",
            "ACCOUNT_NUM": None,
            "geometry": {
                "rings": [[
                    [-111.8508796, 40.3881996],
                    [-111.8515306, 40.3881832],
                    [-111.8515363, 40.3883149],
                    [-111.8508852, 40.3883312],
                    [-111.8508796, 40.3881996],
                ]]
            },
        },
        "sioux_falls_sd_parcels_nearby_narrow": {
            "OBJECTID": 89934485,
            "TAG": "011635201005000",
            "ADDRESS": "3910 E WILCOX ST",
            "ACREAGE": 3.54,
            "SQFT": 154001.0,
            "ACTIVITY": "51 - Low-Intensity Commercial",
            "OWNNAME1": "FLEET PROPERTIES LLC",
            "OWNNAME2": None,
            "OWNADDRESS": "PO BOX 7340",
            "OWNCITY": "FARGO",
            "OWNSTATE": "ND",
            "OWNZIP": "58106",
            "OWNZIP2": "0000",
            "PARHOUSE": "3910",
            "PARHALF": None,
            "PARPR": "E",
            "PARSTREET": "WILCOX",
            "PARTYPE": "ST",
            "PARPD": None,
            "COUNTY": "MINNEHAHA",
            "COUNTYID": "84141",
            "LANDUSE": 540,
            "NUMUNITS": 0,
            "LegalStartDate": 1227052800000,
            "FORM_DATE": 1421971200000,
            "PARCELTYPE": "Standard Tax Parcel",
            "ZIPCODE": 57104,
            "geometry": {
                "rings": [[
                    [-96.6629, 43.6055],
                    [-96.6590, 43.6055],
                    [-96.6590, 43.6072],
                    [-96.6629, 43.6072],
                    [-96.6629, 43.6055],
                ]]
            },
        },
        "cass_county_nd_parcels_nearby_narrow": {
            "OBJECTID": 178800536,
            "GISPIN": "01001000100101",
            "DASHPIN": "01-0010-00100-104",
            "ALTPIN": "01001000100104",
            "PIN": "01001000100104",
            "LMVENU": "01",
            "VENUDESC": "Fargo City",
            "PropertyAddress": "2601 12 ST N UNIT 400",
            "SchoolDistrict": "S001",
            "Section": "2",
            "Lot": 2.0,
            "CommRes": "C",
            "FireDistrict": None,
            "WaterDistrict": "W060",
            "CountyParks": "PK01",
            "Subdivision": "Airport 1st",
            "PLATID": "489667",
            "SOURCE": "FGO",
            "ACRES": 2.93437,
            "UNIQUEID": 258780919.0,
            "LandCity": "FARGO",
            "LandSt": "ND",
            "LandZip": "58102",
            "LandZip2": "",
            "AmbDistrict": None,
            "geometry": {
                "rings": [[
                    [-96.7941805, 46.9114210],
                    [-96.7902000, 46.9114210],
                    [-96.7902000, 46.9131000],
                    [-96.7941805, 46.9131000],
                    [-96.7941805, 46.9114210],
                ]]
            },
        },
        "maine_geolibrary_organized_towns_parcels_nearby_narrow": {
            "OBJECTID": 1,
            "TOWN": "Aurora",
            "COUNTY": "Hancock",
            "GEOCODE": "09020",
            "STATE_ID": "09020_001-001-000",
            "MAP_BK_LOT": "001-001-000",
            "PARENT": "",
            "PROP_LOC": "ELLSWORTH RD",
            "PROPLOCNUM": 0,
            "TYPE": "",
            "FMUPDORG": "umch",
            "FMUPDAT": "12/20/2010",
            "FMSRCORG": "",
            "GlobalID": "219aa1b7-065a-469b-8f42-339679f089f1",
            "CNTYCODE": "09",
            "geometry": {
                "rings": [[
                    [-68.3102557, 44.8190040],
                    [-68.3135760, 44.8185584],
                    [-68.3155176, 44.8183034],
                    [-68.3160056, 44.8192194],
                    [-68.3105028, 44.8199279],
                    [-68.3102557, 44.8190040],
                ]]
            },
        },
        "indianapolis_marion_county_in_parcels": {
            "OBJECTID": 10, "STATEPARCELNUMBER": "49-11-11-123-456.000-101",
            "PARCEL_TAG": "491111123456000101", "PARCEL_I": 1001,
            "PARCEL_C": "123456", "CAMAPARCELID": "CAMA-1001",
            "STNUMBER": "200", "PRE_DIR": "N", "FULL_STNAME": "MERIDIAN ST",
            "CITY": "INDIANAPOLIS", "STATE": "IN", "ZIPCODE": "46204",
            "FULLOWNERNAME": "MARION OWNER LLC",
            "OWNERADDRESS": "PO BOX 100", "OWNERADDRESS2": "",
            "OWNERCITY": "INDIANAPOLIS", "OWNERSTATE": "IN", "OWNERZIP": "46204",
            "PROPERTY_CLASS": "400", "PROPERTY_SUB_CLASS_DESCRIPTION": "Commercial",
            "ASSESSORYEAR_LANDTOTAL": "250000",
            "ASSESSORYEAR_IMPTOTAL": "750000",
            "ASSESSORYEAR_TOTALAV": "1000000",
            "LEGAL_DESCRIPTION_": "DOWNTOWN LOT", "ACREAGE": "0.75",
            "geometry": {
                "rings": [[
                    [-86.16, 39.76],
                    [-86.15, 39.76],
                    [-86.15, 39.77],
                    [-86.16, 39.77],
                    [-86.16, 39.76],
                ]]
            },
        },
        "hennepin_mn_county_parcels": {
            "OBJECTID": 1, "PID": "0102824110001",
            "PID_TEXT": "01-028-24-11-0001", "HOUSE_NO": "100",
            "FRAC_HOUSE_NO": "", "STREET_NM": "NICOLLET MALL",
            "CONDO_NO": "", "MUNIC_NM": "MINNEAPOLIS", "ZIP_CD": "55402",
            "OWNER_NM": "RETAIL PROPERTY OWNER LLC",
            "TAXPAYER_NM": "RETAIL PROPERTY OWNER LLC",
            "TAXPAYER_NM_2": "PO BOX 100", "TAXPAYER_NM_3": "",
            "MAILING_MUNIC_NM": "MINNEAPOLIS",
            "MKT_VAL_TOT": "5000000", "TAXABLE_VAL_TOT": "5000000",
            "NET_IMPRV_AMT": "3200000", "LAND_MV1": "1800000",
            "PR_TYP_CD1": "203", "PR_TYP_NM1": "Commercial",
            "SALE_DATE": "202406", "SALE_PRICE": "4500000",
            "PARCEL_AREA": "15000", "LAT": "44.9765", "LON": "-93.2712",
            "geometry": {
                "rings": [[
                    [-93.272, 44.976],
                    [-93.271, 44.976],
                    [-93.271, 44.977],
                    [-93.272, 44.976],
                ]]
            },
        },
        "st_louis_mo_city_parcels": {
            "OBJECTID": 1, "ParcelId": "00010000100", "Handle": "100",
            "CityBlock": 1, "Parcel": 100, "OwnerCode": 0,
            "ColParcelId": "00010000100", "SITEADDR": "100 MARKET ST",
            "LowAddrNum": 100, "StPreDir": "", "StName": "MARKET",
            "StType": "ST", "StSufDir": "", "StdUnitNum": "",
            "ZIP": 63101, "Location": "100 MARKET ST",
            "OwnerName": "RETAIL PROPERTY OWNER LLC", "OwnerName2": "",
            "OwnerAddr": "PO BOX 100", "OwnerCity": "ST LOUIS",
            "OwnerState": "MO", "OwnerCountry": "USA", "OwnerZIP": "63101",
            "AsrClassCode": 4, "PropertyClassCode": 4,
            "AsrLandUse1": 400, "CDALandUse1": 400, "Zoning": "I",
            "LandArea": 15000, "SQFT": 12000,
            "AsdLand": 250000, "AsdImprove": 750000, "AsdTotal": 1000000,
            "BillLand": 250000, "BillImprove": 750000, "BillTotal": 1000000,
            "AprLand": 1000000, "AprComLand": 1000000,
            "AprComImprove": 3000000, "ResSalePrice": 1250000,
            "ResSaleDate": 1717200000000, "RecDailyDate": 1717200000000,
            "RecDailyNum": 12345, "RecBookNum": "100", "RecPageNum": 1,
            "OwnerUpdate": 1717200000000, "FirstDate": 1717200000000,
            "LastDate": 1717200000000, "PriorAsdDate": 1717200000000,
            "LowerParcelId": "00010000100",
            "geometry": {
                "rings": [[
                    [-90.200, 38.627],
                    [-90.199, 38.627],
                    [-90.199, 38.628],
                    [-90.200, 38.627],
                ]]
            },
        },
        "allegheny_county_pa_parcels_nearby_narrow": {
            "OBJECTID": 4888406,
            "PIN": "0102P00193000000",
            "MAPBLOCKLOT": "102-P-193",
            "MUNICODE": 941,
            "CALCACREAGE": 0.07,
            "MODIFIEDON": "5/16/2013 8:35:32 AM",
            "GlobalID": "{6A619D35-B15C-42D9-9577-C38FB6D8AC00}",
            "geometry": {
                "rings": [[
                    [-80.094944, 40.39552],
                    [-80.095035, 40.395504],
                    [-80.095056, 40.39586],
                    [-80.094965, 40.395863],
                    [-80.094944, 40.39552],
                ]]
            },
        },
        "denver_co_assessor_parcels": {
            "OBJECTID": 1, "SCHEDNUM": "0001001000", "OWNER_NAME": "OWNER LLC",
            "SITUS_ADDRESS_LINE1": "100 W Colfax Ave", "SITUS_ZIP": "80202",
            "LAND_AREA": 12500, "APPRAISED_LAND_VALUE": 900000,
            "APPRAISED_IMP_VALUE": 2100000, "APPRAISED_TOTAL_VALUE": 3000000,
            "D_CLASS_CN": "COMMERCIAL", "ZONE_ID": "D-C",
            "SALE_DATE": 1751328000000, "SALE_PRICE": 2750000,
            "centroid": {"x": -104.9903, "y": 39.7392},
        },
        "colorado_statewide_public_parcels_nearby_narrow": {
            "OBJECTID": 1,
            "countyName": "Adams",
            "countyFips": "001",
            "parcel_id": "0171901104005",
            "account": None,
            "situsAdd": "11844 STEELE ST",
            "sitAddCty": "THORNTON",
            "sitAddZip": None,
            "landAcres": 0.17,
            "zoningCode": None,
            "zoningDesc": None,
            "landUseCde": None,
            "landUseDsc": "Residential",
            "dateReceived": "4/23/2026",
            "URL": None,
            "geometry": {
                "rings": [[
                    [-104.949092, 39.912106],
                    [-104.949097, 39.9123],
                    [-104.948703, 39.912299],
                    [-104.948704, 39.912111],
                    [-104.949092, 39.912106],
                ]]
            },
        },
        "new_jersey_njgin_statewide_parcels_nearby_narrow": {
            "OBJECTID": 1,
            "PAMS_PIN": "0703_14_6",
            "PIN_NODUP": "0703_14_6",
            "PCL_MUN": "0703",
            "PCLBLOCK": "14",
            "PCLLOT": "6",
            "PCLQCODE": " ",
            "COUNTY": "ESSEX",
            "MUN_NAME": "CALDWELL BORO TWP",
            "PROP_CLASS": "2",
            "PROP_LOC": "35 HILLSIDE AVE",
            "ST_ADDRESS": "35 HILLSIDE AVE",
            "CITY_STATE": "CALDWELL, NJ",
            "ZIP5": "07006",
            "LAND_DESC": "75X200",
            "CALC_ACRE": 0.3444,
            "PCLLASTUPD": None,
            "PCL_PBDATE": 1695168000000,
            "PCL_GUID": "94ed7180-5f09-4889-82fc-c05db53e80de",
            "geometry": {
                "rings": [[
                    [-74.268775, 40.840395],
                    [-74.268967, 40.84025],
                    [-74.269479, 40.840638],
                    [-74.269284, 40.840785],
                    [-74.268775, 40.840395],
                ]]
            },
        },
        "florida_fdor_statewide_cadastral_parcels": {
            "OBJECTID": 2, "CO_NO": 11, "PARCEL_ID": "03206-000-000",
            "PARCELNO": "03206-000-000", "STATE_PAR_": "C11-000-000-9790-7",
            "ASMNT_YR": 2025, "DOR_UC": "059", "PA_UC": "00",
            "JV": 500000, "AV_SD": 5000, "AV_NSD": 5000,
            "LND_VAL": 5000, "LND_SQFOOT": 1089000,
            "TOT_LVG_AR": 0, "SALE_PRC1": 0,
            "QUAL_CD1": None, "VI_CD1": None, "OWN_NAME": "EMP1 LLC",
            "OWN_ADDR1": "7045 NW 22ND ST SUITE B", "OWN_ADDR2": " ",
            "OWN_CITY": "GAINESVILLE", "OWN_STATE_": "FL", "OWN_ZIPCD": 32653,
            "PHY_ADDR1": "12628 NW 150TH AVE", "PHY_ADDR2": " ",
            "PHY_CITY": "ALACHUA", "PHY_ZIPCD": 32615,
            "ALT_KEY": "13497", "PUBLIC_LND": " ",
            "centroid": {"x": -82.48237396858843, "y": 29.794941524135016},
        },
        "miami_dade_fl_property_appraiser_parcels": {
            "OBJECTID": 1, "PID": 538415, "FOLIO": "0101000000020",
            "PARENT_FOLIO": None, "CANCEL_FLAG": "N", "REFERENCE_ONLY_FLAG": "N",
            "TRUE_SITE_ADDR": "16 SE 2 ST", "TRUE_SITE_CITY": "Miami",
            "TRUE_SITE_ZIP_CODE": "33131-0000",
            "TRUE_OWNER1": "16 SE 2ND STREET DOWNTOWN", "TRUE_OWNER2": "INVESTMENT LLC",
            "TRUE_MAILING_ADDR1": "31 SE 5TH ST 2704", "TRUE_MAILING_CITY": "MIAMI",
            "TRUE_MAILING_STATE": "FL", "TRUE_MAILING_ZIP_CODE": "33131",
            "LOT_SIZE": 60198, "BUILDING_GROSS_AREA": 0,
            "LAND_VAL_CUR": None, "LAND_VAL_PRI": 33108900,
            "BUILDING_VAL_CUR": None, "BUILDING_VAL_PRI": 8584,
            "TOTAL_VAL_CUR": None, "TOTAL_VAL_PRI": 33117484,
            "DOR_DESC": "PARKING LOT", "PRIMARY_ZONE": "6401",
            "DOS_1": "20210623", "PRICE_1": 46000000,
            "ASSESSMENT_YEAR_PRI": 2025,
            "geometry": {"x": -80.192951, "y": 25.772241},
        },
        "orange_county_fl_property_appraiser_parcels": {
            "OBJECTID": 1, "PARCEL": "272306428405151", "PARENT_ID": "",
            "NAME1": "SZABO NANCY JOY SR", "NAME2": "SZABO NANCY JOY JR",
            "SITUS": "DAVENPORT RD", "SITUS_CITY": "Winter Garden",
            "SITUS_ZIP": "34787", "LATITUDE": 28.50444968,
            "LONGITUDE": -81.64423097, "SHAPE.STArea()": 208187.85,
            "GROSS_AREA": 0, "LIVING_AREA": 0, "LAND_MKT": 724500,
            "TOTAL_MKT": 724500, "DOR_CODE": "0001", "ZONING_CODE": "ORG-A-1",
            "ADD1": "2813 MARQUESAS CT", "CITY": "WINDERMERE",
            "STATE": "FL", "ZIP": "34786", "ZIP4": "7824",
            "SALE_DATE": 1665633600000, "SALE_ADJ_VALUE": 699900,
        },
        "hillsborough_county_fl_property_appraiser_parcels": {
            "OBJECTID": 1, "FOLIO": "1933290000", "PIN": "A-01-29-18-ZZZ-000005-00010.0",
            "STRAP": "182901ZZZ000005000100", "OWNER": "TAMPA RETAIL OWNER LLC",
            "SITE_ADDR": "100 E KENNEDY BLVD", "SITE_CITY": "TAMPA",
            "SITE_ZIP": "33602", "DOR_C": "1100", "ACREAGE": 1.25,
            "ACT": 42000, "LAND": 2100000, "BLDG": 6300000, "JUST": 8400000,
            "ADDR_1": "PO BOX 100", "CITY": "TAMPA", "STATE": "FL", "ZIP": "33601",
            "S_DATE": 1750204800000, "AMT": 7750000,
            "centroid": {"x": -82.4593, "y": 27.9478},
        },
        "duval_county_fl_property_appraiser_parcels": {
            "OBJECTID": 1, "RE": "073685-0000", "RE_NOSPACE": "0736850000",
            "LNAMEOWNER": "JACKSONVILLE RETAIL OWNER LLC", "STREET_NO": "117",
            "ST_DIR": "W", "LONGNAME": "DUVAL ST", "UNIT_NO": "",
            "ADDRCITY": "JACKSONVILLE", "ZIPCODE": 32202, "ACRES": 0.82,
            "PUSE": "1100", "DESCPU": "STORE", "TOT_LND_VA": 1200000,
            "TOT_BLD_VA": 2800000, "MAILADDR1": "PO BOX 100",
            "MAILCITY": "JACKSONVILLE", "MAILSTATE": "FL", "MAILZIP": "32201",
            "centroid": {"x": -81.6596, "y": 30.3322},
        },
        "broward_county_fl_dor_parcel_centroids": {
            "OBJECTID": 1, "CO_NO": 16, "PARCEL_ID": "504210010010",
            "DOR_UC": "011", "OWN_NAME": "BROWARD RETAIL OWNER LLC",
            "OWN_ADDR1": "PO BOX 100", "OWN_CITY": "FORT LAUDERDALE",
            "OWN_STATE_": "FL", "OWN_ZIPCD": 33302,
            "PHY_ADDR1": "100 E LAS OLAS BLVD", "PHY_CITY": "FORT LAUDERDALE",
            "PHY_ZIPCD": 33301, "LND_SQFOOT": 31000, "TOT_LVG_AR": 54000,
            "LND_VAL": 4200000, "JV": 12600000, "AV_SD": 6200000,
            "AV_NSD": 6100000, "SALE_PRC1": 11000000,
            "geometry": {"x": -80.1436, "y": 26.1197},
        },
        "polk_county_fl_property_appraiser_parcels": {
            "OBJECTID": 1, "PARCELID": "232824000000013020", "DOR_CD": "1100",
            "DORDESC": "STORES", "TOT_LND_VAL": 900000, "TOT_BLD_VAL": 2600000,
            "TOT_XF_VAL": 50000, "TOTALVAL": 3550000, "ASSESSVAL": 3400000,
            "TOT_ACREAGE": 1.1, "NAME": "LAKELAND RETAIL OWNER LLC",
            "MAIL_ADDR_1": "PO BOX 100", "MAIL_ZIP": "33802",
            "PROP_ADRNO": "100", "PROP_ADRSTR": "KENTUCKY", "PROP_ADRSUF": "AVE",
            "PROP_CITY": "LAKELAND", "PROP_ZIP": "33801",
            "centroid": {"x": -81.9571, "y": 28.0395},
        },
        "cary_nc_development_applications": {
            "OBJECTID": 40163,
            "ApplicationName": "7001 Weston Pkwy - Multi-Family and Retail",
            "ApplicationNumber": "26-DP-10884",
            "ApplicationDate": 1781568000000,
            "ActionDate": None,
            "Status": "In Review",
            "SummaryDescription": "Convert existing office bldg to 248 multi-family units & 3,100sf of retail",
            "IDTApplicationURL": "https://townofcary.geocivix.com/secure/project/?projectid=2206697",
            "UseGroup": "Mixed - Commercial/Residential",
            "UseCategory": "Retail Sales & Service",
            "UseType": "Retail store",
            "ReviewType": "New plan",
            "PlanTier": "Tier 1",
            "TotalSqFt": 3100,
            "geometry": {
                "rings": [[
                    [-78.8120, 35.8300],
                    [-78.8110, 35.8300],
                    [-78.8110, 35.8310],
                    [-78.8120, 35.8310],
                    [-78.8120, 35.8300],
                ]]
            },
        },
        "cary_nc_building_permit_applications": {
            "permitnum": "26-00010569",
            "description": "INTERIOR ALTERATION",
            "statuscurrent": "IN PLAN CHECK (PC)",
            "statuscurrentmapped": "In Review",
            "applieddate": "2026-07-23",
            "issuedate": None,
            "completeddate": None,
            "statusdate": "2026-07-23",
            "originaladdress1": "3550 NW CARY PKWY 100",
            "originalcity": "CARY",
            "originalstate": "NC",
            "originalzip": "27513",
            "pin": "754357261",
            "permitclassmapped": "Non-Residential",
            "workclassmapped": "Existing",
            "permittypemapped": "Building",
            "permittypedesc": "INTERIOR ALTERATION (B105)",
            "projectcost": 200000,
            "totalsqft": 6000,
            "contractorcompanyname": None,
            "ownername": "JCG PTNR LLC",
            "latitude": 35.797443,
            "longitude": -78.818693,
            "_record_url": "https://data.townofcary.org/api/v2/catalog/datasets/permit-applications/records/example",
        },
        "raleigh_nc_development_plans": {
            "OBJECTID": 54325,
            "submitted": 1783958796523,
            "approved": None,
            "updated": 1784211052207,
            "plan_type": "DSLC - Preliminary Subdivision",
            "status": "In Review",
            "acreage": 8.93,
            "major_street": "9800 Falls Of Neuse Rd",
            "developer": "Blew & Associates, P.A.",
            "plan_name": "DSLC - 7 BREW OF RALEIGH",
            "lots_req": 2,
            "sq_ft_req": None,
            "units_req": None,
            "zoning": "",
            "plan_number": "SUB-0040-2026",
            "geometry": {"x": -78.6001225135742, "y": 35.90674353926273},
        },
        "charlotte_nc_rezoning_petitions": {
            "OBJECTID": 27499,
            "Petition": "2026-034",
            "Petitioner": "Sam's Mart, LLC",
            "ExistZone": "N1-A",
            "ReqZone": "ML-1(CD)",
            "Type": "CD",
            "SPA": None,
            "Acres": 7.51,
            "Received": 1778817600000,
            "Approved": None,
            "Status": "Pen",
            "Hyperlink": "https://www.charlottenc.gov/Growth-and-Development/Planning-and-Development/Rezoning/2026/2026-034",
            "Propluse": None,
            "geometry": {
                "rings": [
                    [
                        [-80.6502351037746, 35.24593744600604],
                        [-80.65017659217126, 35.24561394432064],
                        [-80.64967129682668, 35.24574101457934],
                        [-80.64973882972543, 35.24607107177273],
                        [-80.6502351037746, 35.24593744600604],
                    ]
                ]
            },
        },
        "new_hanover_nc_commercial_site_plans": {
            "OBJECTID": 2165610,
            "PLPLANID": "041e8ed2-7ba6-40ae-8353-1afe71b707b8",
            "PLAN_NUMBER": "SITECN-26-000030",
            "PLAN_TYPE": "NHC Commercial Site",
            "WORK_CLASS": "New",
            "PLAN_STATUS": "In Review",
            "APPLY_DATE": 1784206678000,
            "COMPLETE_DATE": None,
            "EXPIRE_DATE": 1815742678000,
            "APPROVAL_EXPIRE_DATE": None,
            "PROJECT": None,
            "DESCRIPTION": "Addition of a secondary driveway to an existing gas station site.",
            "Applicant": "Bluewater Engineering, PLLC",
            "OWNER": "MM FOWLER INC",
            "GENERAL_CONTRACTOR": None,
            "SQUARE_FEET": None,
            "VALUATION": None,
            "MAIN_ZONE": "B-2",
            "PID": "R07918-005-015-000",
            "Lat": 34.1072261,
            "Lon": -77.8990533,
            "GlobalID": "{041E8ED2-7BA6-40AE-8353-1AFE71B707B8}",
            "geometry": {"x": -77.8990533, "y": 34.1072261},
        },
        "madison_wi_current_planning_projects": {
            "ESRI_OID": 9912,
            "ID": "155772",
            "RECORD_RecordID": "LNDUSE-2026-00032",
            "PROJECT_ProjectAlias": "1001 Wisconsin Pl",
            "RECORD_Status": "Application Under Review",
            "DATES_SubmittedDate": 1783036800000,
            "DATES_Circulated": 1784073600000,
            "Project_Description": "Edgewater Hotel restaurant and bar expansion",
            "Requests": "Conditional Use",
            "MeetingDates": "Plan Commission: August 2026",
            "APO_ADDRESS_PARTIAL_LINE": "1001 WISCONSIN PL",
            "CONTACT_RespParty_OrgName": "The Edgewater Hospitality Co",
            "APO_OWNER_Full_Name": "EDGEWATER HOTEL COMPANY LLC",
            "APO_PARCEL_NUMBER": "070914442010",
            "ProjectURL": "https://www.cityofmadison.com/dpced/planning/development/current-development-proposals/1001-wisconsin-pl/155772/",
            "ASI_LU_PInf_LndUseLegURL": "https://madison.legistar.com/LegislationDetail.aspx?ID=155772",
            "ASI_LU_PInf_ReZonLegURL": None,
            "ASI_LU_PInf_UDCLegURL": None,
            "geometry": {"x": -89.38691, "y": 43.07942},
        },
        "orlando_fl_permit_applications": {
            "permit_number": "BLD2026-15486",
            "application_type": "Building Permit",
            "worktype": "Alteration",
            "plan_review_type": "Commercial",
            "application_status": "Open",
            "processed_date": "2026-06-25T00:00:00.000",
            "under_review_date": "2026-06-26T00:00:00.000",
            "pending_issuance_date": None,
            "issue_permit_date": None,
            "final_date": None,
            "coo_date": None,
            "coc_date": None,
            "permit_address": "1500 E COLONIAL DR",
            "project_name": "PUBLIX 0662",
            "contractor_name": "HGR CONSTRUCTION INC",
            "estimated_cost": "1000000",
            "square_footage": "27462",
            "parcel_number": "292225153601070",
            "neighborhood": "Colonialtown South",
            "geocoded_column": {"type": "Point", "coordinates": [-81.3569, 28.5538]},
        },
        "mesa_az_commercial_permit_submittals": {
            "row_number": "88613",
            "record_id": "PMT26-11010",
            "record_type": "Commercial",
            "type_of_submittal": "Sub",
            "record_open_date": "2026-06-12T00:00:00.000",
            "record_status": "In Review",
            "record_status_date": "2026-07-16T00:00:00.000",
            "task": "Application Submittal",
            "description": "Dutch Bros #11114",
            "status": "Accepted - Plan Review Req",
            "status_date": "2026-07-16T00:00:00.000",
            "distribution_date": "2026-07-16T00:00:00.000",
            "submittal_date": "2026-07-16T10:26:38.000",
            "permit_address": "3703 S POWER RD",
            "street_address": "3703 S POWER RD",
            "longitude": "-111.686999",
            "latitiude": "33.348592",
        },
        "tempe_az_building_permits_commercial_context": {
            "OBJECTID": 7759174,
            "PermitNum": "DR250023",
            "Description": "CONSTRUCT NEW ONE-STORY RESTAURANT BUILDING, KIOSKS, RESTROOMS W/ASSOCIATED SEATING AREAS",
            "AppliedDateDtm": None,
            "IssuedDateDtm": 1779926400000,
            "CompletedDateDtm": None,
            "Type": "",
            "StatusCurrent": "Ready for Issuance",
            "OriginalAddress1": "70 E RIO SALADO PKWY",
            "OriginalCity": "TEMPE",
            "PermitClass": "DR - Drainage",
            "PermitType": "Engineering,Drainage,NA,NA",
            "PermitTypeDesc": "Drainage Permit",
            "StatusDateDtm": 1779926400000,
            "TotalSqFt": 0,
            "EstProjectCost": 0,
            "HousingUnits": 0,
            "ContractorCompanyName": None,
            "ContractorLicNum": None,
            "ProjectName": "Hayden Ferry Lakeside Plaza",
            "Zone": "MU-4",
            "Latitude": 33.43007254,
            "Longitude": -111.93848293,
        },
        "wake_county_nc_building_permits_commercial": {
            "OBJECTID": 267568,
            "PERMIT_NUMBER": "CBPR-175796-2026",
            "PERMIT_STATUS": "In Review",
            "APPLICATION_DATE": 1784073600000,
            "ISSUE_DATE": None,
            "FINALED_DATE": None,
            "EXPIRATION_DATE": None,
            "DESCRIPTION": "SHOPS AT MIDWAY - NO TRADES - LEVEL 2 - Michaels-#6725 Application",
            "PERMIT_TYPE": "Commercial Building",
            "WORK_CLASS": "Building Renovation or Repair",
            "PROPOSED_USE": "327C   RETAIL STORE",
            "SQUARE_FEET": 200.0,
            "VALUATION": 1500.0,
            "CONTRACTOR": None,
            "PIN": "1744652987",
            "DISTRICT": "Knightdale",
            "LINK": "https://energovcitizenaccess.tylertech.com/WakeCountyNC/SelfService#/permit/687e7fb5-abe9-4290-bafa-4dec15442958",
            "X": -78.50727644,
            "Y": 35.79843032,
        },
        "greensboro_nc_building_permits_commercial": {
            "OBJECTID": 59003,
            "PermitNum": 202612947,
            "PlanReviewNum": "2026-2088",
            "BP_ENTRY_DATE": 1783701780000,
            "IssuedDate": None,
            "StatusCurrent": "Active                                                      ",
            "ApplicationType": "Int/Ext Alterations",
            "Description": "Mezzanine - Mech/Elec/Fire sprinkler system to renovate for office space.",
            "OccupancyDesc": "Business",
            "TypeConstructionDesc": "V-A Any material - protected",
            "Contractor": "PLAN REVIEW",
            "OwnerName": "CHICKASHA I LLC",
            "FullAddress": "4490 CHICKASHA DR",
            "TotalCost": 46256,
            "BuildingSqFt": 687,
            "Zoning": "CD-HI",
            "BP_COMM_RESID_MULT": "C",
            "CancelDate": None,
            "FinalCO": None,
            "FinalCODate": None,
            "AdSakey": 312227,
            "geometry": {"x": -79.7124855455585, "y": 36.192195221879075},
        },
        "buffalo_ny_planning_zoning_approvals": {
            "uniqueid": "9456581237700004035000",
            "apbldgreviewkey": "9689278-4035000",
            "reviewtype": "ZONING",
            "result": "Approved",
            "resultdttm": "2026-07-17T00:00:00.000",
            "apno": "USE26-9689278",
            "apbldgkey": "9689278",
            "aptype": "USE",
            "address": "309 GERMANIA",
            "city": "Buffalo",
            "state": "NY",
            "zip": "14220",
            "prclid": "1237700004035000",
            "location": {
                "type": "Point",
                "coordinates": [-78.837, 42.848],
            },
            "latitude": "42.848",
            "longitude": "-78.837",
            "neighborhood": "Hopkins-Tifft",
        },
        "hartford_ct_building_permits_lifecycle": {
            "OBJECTID": 3553,
            "RECORD_ID": "COM-ALT-26-000302",
            "DESCRIPTION": "install roof sign on existing structure",
            "DATE_OPENED": "2026-06-29 ",
            "DATE_CLOSED": None,
            "RECORD_TYPE_TYPE": "Commercial",
            "B1_APP_TYPE_ALIAS": "Commercial Alteration Permit",
            "RECORD_STATUS": "Pending",
            "PROPERTY_ADDRESS": "317 WEST SERVICE RD, HARTFORD, CT 06120",
            "Location": "317 WEST SERVICE RD ",
            "UNIT": None,
            "PROPERTY_CITY": "HARTFORD",
            "PROPERTY_STATE": "CT",
            "PROPERTY_ZIP": "06120",
            "PARCEL_ID": "304074015",
            "Total_Construction_Cost": 7500.0,
            "DateIssued": None,
            "GlobalID": "{CBB433C4-0ADD-4B50-94AB-1123A3EACC5F}",
        },
        "new_york_state_sla_pending_licenses": {
            "application_id": "NA-0340-26-120427",
            "premises_county": "Nassau",
            "type": "1",
            "class": "340",
            "description": "Restaurant",
            "legalname": "Chipotle Mexican Grill of Colorado LLC",
            "dba": "Chipotle Mexican Grill",
            "actual_address_of_premises": "85 Henry St",
            "additional_address_information": None,
            "city": "Freeport",
            "state_name": "New York",
            "zip_code": "11520",
            "received_date": "2026-07-17T15:37:00.000",
            "status": "Under Review",
            "aka_address": None,
            "georeference": {
                "type": "Point",
                "coordinates": [-73.5792, 40.65521],
            },
        },
        "florida_dep_erp_applications_commercial_context": {
            "OBJECTID": 802664,
            "TEMP_ID": 802664,
            "APP_NO": "0418997-003-EI",
            "SITE_ID": "418997",
            "PROJ_NO": "003",
            "PROJ_NAME": "SHACK MOORING EXPANSION",
            "SITE_NAME": "THE SHACK RESTAURANT",
            "COMPANY": "KIT INVESTMENT OF FLORIDA, LLC",
            "ADDRESS": "4845 DIXIE HWY NE",
            "CITY": "PALM BAY",
            "ZIP5": 32905,
            "PER_TYPE": "EI",
            "PER_SUB": "E29",
            "PER_DESC": "<10 ac project area, <1 ac works, <10 boat slips",
            "RCVD_DATE": 1783382400000,
            "AGENCY_ACT": "Pending",
            "ACT_DATE": None,
            "EXPIR_DATE": None,
            "COMP_DATE": None,
            "PROJ_DESC": None,
            "DOCUMENTS": "https://prodenv.dep.state.fl.us/DepNexus/public/electronic-documents/ERP_418997/gis-facility!search",
            "REPORTS": "https://prodapps.dep.state.fl.us/pa/summarypending/PaDataNexus/printDetail?site_id=0418997&program1=ERP",
            "geometry": {"x": -80.6091205, "y": 28.0331524},
        },
        "miami_dade_fl_wasd_unincorporated_permits_narrow": {
            "OBJECTID": 429514,
            "ID": 567648,
            "EFFECTIVE": "Active",
            "MUNICID": "30",
            "PROJNAME": "BAL HARBOUR SHOPS LLC",
            "PROJDESC": "RETAIL SALES",
            "PROJZIP": "",
            "BLDPRCNO": "M2026017062",
            "BLDPRCSTAT": "APPLIED",
            "BLDPRCISDT": 1780272000000,
            "BLDPRCSTDT": None,
            "BLDPRMNO": "",
            "BLDPRMSTAT": "",
            "BLDPRMIDT": None,
            "BLDPRMSTDT": 1780272000000,
            "COTYPE": "",
            "CODATE": None,
            "EEOSNO": None,
            "WSCNO": None,
            "DEALLOCTYP": "Incomplete",
            "INSERTDATE": 1780887607000,
            "UPDATEDATE": None,
            "geometry": {"x": -80.12545032073432, "y": 25.88816880157457},
        },
        "wake_county_nc_parcels": {
            "OBJECTID": 1, "PIN_NUM": "1703891234", "REID": "0123456",
            "PARCEL_PK": "987654", "OWNER": "WAKE RETAIL OWNER LLC",
            "SITE_ADDRESS": "100 FAYETTEVILLE ST", "FULL_STREET_NAME": "FAYETTEVILLE ST",
            "CITY_DECODE": "RALEIGH", "ZIPNUM": "27601", "CALC_AREA": "24829",
            "BLDG_VAL": "3250000", "LAND_VAL": "900000",
            "TOTAL_VALUE_ASSD": "4150000", "ADDR1": "PO BOX 100",
            "ADDR2": "RALEIGH NC 27602", "SALE_DATE": "2024-04-30",
            "TOTSALPRICE": "5200000", "centroid": {"x": -78.6382, "y": 35.7796},
        },
        "cook_county_il_assessor_parcels_current_year_nearby": {
            "pin": "17032270241105",
            "pin10": "1703227024",
            "row_id": "170322702411052026",
            "year": "2026.0",
            "class": "299",
            "triad_name": "City",
            "township_name": "North Chicago",
            "nbhd_code": "74022",
            "tax_code": "74002",
            "zip_code": "60611",
            "lon": "-87.6206525272",
            "lat": "41.897883532",
            "cook_municipality_name": "CITY OF CHICAGO",
            "ward_num": "42",
            "chicago_community_area_name": "NEAR NORTH SIDE",
            "chicago_industrial_corridor_name": "",
            "econ_enterprise_zone_num": "",
            "econ_industrial_growth_zone_num": "",
            "econ_qualified_opportunity_zone_num": "17031081403",
            "econ_central_business_district_num": "1",
            "env_flood_fema_sfha": False,
            "env_flood_fs_factor": "1",
            "env_flood_fs_risk_direction": "0",
            "env_ohare_noise_contour_no_buffer_bool": False,
            "env_ohare_noise_contour_half_mile_buffer_bool": False,
            "env_airport_noise_dnl": "",
            "tax_tif_district_num": "",
            "tax_tif_district_name": "",
            "access_cmap_walk_total_score": "134.5",
            "misc_subdivision_id": "1703A_A",
        },
        "los_angeles_ca_building_permits_submitted": {
            "permit_nbr": "26016-10000-15835",
            "primary_address": "6081 W CENTER DR 202B-202C",
            "zip_code": "90045",
            "apn": "4104001035",
            "zone": "C2-1",
            "permit_type": "Bldg-Alter/Repair",
            "permit_sub_type": "Commercial",
            "use_desc": "Retail",
            "submitted_date": "2026-07-10T00:00:00.000",
            "issue_date": None,
            "status_desc": "Submitted",
            "status_date": "2026-07-10T00:00:00.000",
            "valuation": "50000",
            "square_footage": "2400",
            "business_unit": "Regular Plan Check",
            "work_desc": "CHANGE OF USE FORM RETAIL (M) GYM (A-3) OCCUPANCY",
            "lat": "33.97811",
            "lon": "-118.39245",
            "refresh_time": "2026-07-12T00:00:00.000",
        },
        "new_york_ny_dohmh_restaurant_permit_applicants": {
            ":id": "row-gw3u_ck4n-7u9i",
            "camis": "50182600",
            "dba": "BROOKLYN DUMPLING SHOP",
            "boro": "Manhattan",
            "building": "235",
            "street": "WEST   46 STREET",
            "zipcode": "10036",
            "cuisine_description": "Chinese",
            "inspection_date": "1900-01-01T00:00:00.000",
            "action": None,
            "inspection_type": None,
            "record_date": "2026-07-17T06:00:15.000",
            "bin": "1024737",
            "bbl": "1010180006",
            "latitude": "40.759124635911",
            "longitude": "-73.986348218206",
            "location": {"latitude": "40.759124635911", "longitude": "-73.986348218206"},
        },
        "boston_ma_article_80_development_projects": {
            "objectid": 348999,
            "project_id": 5027,
            "project__project_name": "408 South Huntington Avenue",
            "project_status": "Under Review",
            "project__record_type": "Large Project",
            "project_street_number": "408",
            "project_street_name": "South Huntington",
            "project_street_suffix": "Avenue",
            "project_zip_code": "02130",
            "neighborhood": "Jamaica Plain",
            "last_filed_date": "2026-07-16",
            "last_board_approved_date": None,
            "coo_permit_date": None,
            "project_uses": "Residential",
            "gross_square_footage": 92500,
            "total_development_cost": 42000000,
            "description": "Demolition of existing commercial building and new 5-story multifamily building.",
            "website_url": "https://www.bostonplans.org/projects/development-projects/408-south-huntington-avenue",
            "latitude": 42.3301,
            "longitude": -71.1112,
        },
            "sacramento_ca_commercial_building_permits_applied_current_year": {
                "OBJECTID": 10900,
                "Type": "Commercial",
                "Sub_Type": "Remodel",
                "Category": "Retail Store",
            "Application": "COM-2613499",
            "Rpt_Status": "Applied",
            "Status_Date": "06/26/2026",
            "Current_Status": "Applied",
            "Parcel_No": "00601050090000",
            "Address": "1020 12TH ST 110",
            "Site_Location": None,
            "ZIP": "95814",
            "Project_Sq_Ft": 650,
            "Valuation": 50000,
            "Activity_Code": "B1 ALTER/REPAIR",
                "Contractor": None,
                "Work_Desc": "EPC - EXPEDITED - Accessibility restroom upgrade to existing nonconforming condition.",
                "Project_Name": "Remodel Cafe, unleased",
            },
            "detroit_mi_bseed_building_permits": {
                "record_id": "P00012345",
                "address": "1234 WOODWARD AVE",
                "submitted_date": "2026-07-02T00:00:00.000",
                "issued_date": "2026-07-15T00:00:00.000",
                "work_description": "Interior alteration for retail tenant build-out.",
                "permit_type": "Building",
                "construction_type": "Commercial Alteration",
                "current_use_type": "Retail",
                "proposed_use_type": "Retail",
                "num_units": 0,
                "amt_permit_cost": "250000",
                "amt_estimated_contractor_cost": "300000",
                "amt_estimated_department_cost": "0",
            },
            "nashville_tn_planning_development_applications": {
                "OBJECTID": 576,
                "PERTYPE": "Specific Plan Amendment",
            "DATE_ACCEPTED": 1784118581000,
            "MPCNUM": "2008SP-013-001",
            "BILLNUM": "",
            "PROJECT_DESC": "BUCHANAN POINT SP",
            "LOCATION_DESC": "555 MCCRORY CREEK RD 37214",
            "MPC_DATE": 1787806800000,
            "READ3_DATE": None,
            "READ3": None,
            "CD": "15 (Jeff Gregg)",
            "CAPTION": "A request to amend a Specific Plan to permit industrial and commercial uses.",
            "PSTAT": "New",
            "READ2_DATE": None,
            "MPC_ACTION_DESC": None,
            "READ2": None,
            "READ1_DATE": None,
            "READ1": None,
            "Parcels": "Map 096, Parcel(s) 020-023, 025, 026",
            "Acreage": "188.53",
            "ExistingZoning": "R10; SP",
            "NewZoning": None,
            "CommunityPlan": "14, Donelson - Hermitage - Old Hickory",
            "geometry": {"x": -86.65229090644056, "y": 36.147133559952785},
        },
        "delaware_firstmap_statewide_parcels_narrow": {
            "OBJECTID": 17810643,
            "PIN": "0600500019",
            "ACRES": 0.29410104,
            "COUNTY": "New Castle",
            "UPDATED": 1782864000000,
            "centroid": {"x": -75.52104459228563, "y": 39.835052931073655},
            "geometry": {
                "rings": [[
                    [-75.52092528443355, 39.83522338557626],
                    [-75.52081899307417, 39.834910673876756],
                    [-75.52127695600264, 39.83496886694226],
                    [-75.52116505466434, 39.83526917634252],
                    [-75.52092528443355, 39.83522338557626],
                ]]
            },
        },
        "delaware_dnrec_stormwater_noi": {
            "permitnumber": "6744",
            "projectname": "203 HANSE CT",
            "owneroperator": "MGI LEASING INC",
            "project_location": "203 HANSEN CT",
            "datereceived": "2022-06-07T10:22:00.000",
            "projecttype": "Industrial",
            "delegateagency": "City Of Newark",
            "permitstatuscode": "Active",
            "latitude": "39.66",
            "longitude": "-75.78",
            "estimatedarea": "1.30",
            "constructcounty": "New Castle",
        },
        "delaware_dnrec_septic_permits_narrow": {
            "permitnumber": "283246",
            "taxparcelnumbers": "ED-00-056.00-01-29.05.000",
            "county": "Kent",
            "septicsystemtype": "Elevated Mound",
            "septicsystemsubtype": "Standard",
            "permitstatus": "Application Received",
            "constructiontype": "Replacement",
            "septicpropusecode": "4-bedroom",
            "flowrate": "480",
            "proposedsize": "1110",
            "minimumsize": "1104",
            "appreceiveddate": "2026-07-16T00:00:00.000",
            "pretreattype": "Septic Tank",
            "contractor": "Site Contractor LLC",
            "latitude": "39.10",
            "longitude": "-75.50",
            "url_for_permit_details": "https://den.dnrec.delaware.gov/Detail/PermitDetail.aspx?id=60848750&Panel=ViewAll",
        },
        "virginia_vgin_statewide_parcels_narrow": {
            "OBJECTID": 1,
            "VGIN_QPID": 5110500000734,
            "FIPS": "51105",
            "LOCALITY": "Lee County",
            "PARCELID": None,
            "PTM_ID": None,
            "LASTUPDATE": 1540958400000,
            "GPIN": None,
            "PIN": None,
            "Address": None,
            "City": None,
            "State": None,
            "Zip": None,
            "VGIN_Locality_Name": "Lee County",
            "centroid": {"x": -83.5801701470685, "y": 36.59760114118398},
            "geometry": {
                "rings": [[
                    [-83.57996717120515, 36.59760745451736],
                    [-83.5802353808084, 36.597584941783424],
                    [-83.58030788919194, 36.59761102725115],
                    [-83.57996717120515, 36.59760745451736],
                ]]
            },
        },
        "fairfax_county_va_development_tracker_site_records": {
            "OBJECTID": 148,
            "GlobalID": "{6EC1FFE9-2DBF-49CD-8DB5-807FE39BE54D}",
            "RECORDID": "006553-CON-001-1",
            "APPTYPEALIAS": "Conservation Plan",
            "PROJECT_NAME": "MAYMONT SEC 2 LOT 31 [DR]",
            "PARCEL_ID": "0193 22  0031",
            "SUPERVISOR_DISTRICT": "HUNTER MILL",
            "RECORD_STATUS": "Application Accepted",
            "RECORD_STATUS_DATE": 1459814400000,
            "SUBMITTED_DATE": 1458864000000,
            "ACCEPTED_DATE": 1458864000000,
            "APPROVED_DATE": None,
            "PROJECT_STATUS": "Review",
            "ADDRESS_1": "9834 CORSINI CT",
            "CITY": "VIENNA",
            "STATE": "VA",
            "ZIP_CODE": "22182",
            "MAR_ADDRESS": "9834 CORSINI CT, VIENNA, VA, 22182",
            "PUBLIC_VIEW": "Yes",
            "LINK_URL": "https://plus.fairfaxcounty.gov/CitizenAccess/urlrouting.ashx?type=1000&Module=Site&capID1=16WW3&capID2=00000&capID3=00NLE&agencyCode=FFX&FromACA=Y",
            "CLOSED_DATE": None,
            "APPROVED_PLAN_LINK": None,
            "VALID_PARCEL_ID": "Yes",
            "DATA_CENTER": "NO",
            "TOTAL_DWELLING_UNITS": None,
            "centroid": {"x": -77.28366293357432, "y": 38.95785383971839},
        },
        "norfolk_va_permits_and_inspections_permit_records": {
            "ftpuser": "ZP26-01595",
            "permit_address": "244 GRANBY STREET",
            "permit_application_date": "2026-06-22T00:00:00.000",
            "permit_type": "Zoning",
            "permit_status": "Pending",
            "permit_use_class": "Commercial",
            "permit_work_type": "New",
            "permit_description": "",
            "permit_structure": "Business License Review",
            "permit_use_type": "Commercial",
            "permit_use_group": "R-3",
            "geocoded_column": {
                "type": "Point",
                "coordinates": [-76.29069435, 36.84918635],
            },
            "parcel_gpin": "1427963242",
        },
        "norfolk_va_conditional_use_permits": {
            "OBJECTID": 4158,
            "CPCITEM": None,
            "ORDINANCE": None,
            "APPLICANT": "APPLEBEES NEIGHBORHOOD GRILL & BAR",
            "ADDRESS": "5750 E VIRGINIA BEACH BOULEVARD",
            "LINK": "https://gisshare.norfolk.gov/planning/pdf/.pdf",
            "TYPE": "Extended Hours, ABC On-Premises",
            "EFFECTIVE_DATE": 1783987200000,
            "EXPIRATION_DATE": None,
            "ENTERTAINMENT_TYPE": "No Entertainment",
            "LATEST_CLOSING_HOUR": "2:00 am",
            "geometry": {"x": -76.20777486519532, "y": 36.856192122365805},
        },
        "virginia_beach_va_building_permit_applications": {
            "OBJECTID": 95892,
            "PermitNumber": "2026-BDCA-11397",
            "PermitType": "Building",
            "ConstructionType": "Commercial",
            "WorkType": "Addition and or Alteration",
            "ApplicationDate": "2026/04/29",
            "IssueDate": "2026/04/29",
            "FinalDate": None,
            "Status": "Pending Revisions",
            "WorkDesc": "ONE STORY COMMERCIAL STORAGE",
            "GPIN": "24162870810000",
            "StreetAddress": "1330 CREDLE RD",
            "AddressUnit": "",
            "City": "Virginia Beach",
            "State": "VA",
            "Zip": "23454",
        },
        "lynchburg_va_development_projects_locations": {
            "OBJECTID": 11500,
            "Parcel_ID": "24605004",
            "LRSN": 24605004,
            "Address": "2735 WARDS RD",
            "RecordNo": "SPR2607-0001",
            "Name": "Wards Road Car Wash",
            "Type": "SITE PLAN",
            "SubType": "ADMIN REVIEW",
            "StartDate": 1783468800000,
            "EndDate": None,
            "Status": "AWAITING PAYMENT",
            "Neighborhood": "WARDS RD COMMERCIAL CORRIDOR",
            "geometry": {"x": -79.18130211895715, "y": 37.36033955899184},
        },
        "washington_dc_dob_building_permits_2026": {
            "OBJECTID": 1119328466,
            "DCRAINTERNALNUMBER": 142605750.0,
            "PERMIT_ID": "B2605595",
            "ISSUE_DATE": None,
            "PERMIT_TYPE_NAME": "CONSTRUCTION",
            "PERMIT_SUBTYPE_NAME": "ALTERATION AND REPAIR",
            "PERMIT_CATEGORY_NAME": "NA",
            "APPLICATION_STATUS_NAME": "READY FOR ISSUANCE",
            "FULL_ADDRESS": "1100 L ST NW, WASHINGTON, DC 20005",
            "DESC_OF_WORK": "Level 2 alteration of tenant office space with new interior partitions and lighting.",
            "SSL": "0316    0032",
            "ZONING": "D-4-R",
            "PERMIT_APPLICANT": "CHRIS VU",
            "OWNER_NAME": "12TH & L STREETS LTD PARTNERSHIP",
            "FEES_PAID": 554,
            "CITY": "WASHINGTON",
            "STATE": "DC",
            "ZIPCODE": "20005",
            "LATITUDE": 38.90355024,
            "LONGITUDE": -77.02754707,
            "WARD": "2",
            "ANC": "ANC 2C",
            "NEIGHBORHOODCLUSTER": "Cluster 8",
            "BUSINESSIMPROVEMENTDISTRICT": "DOWNTOWN BID",
            "LASTMODIFIEDDATE": 1784214258000,
            "GLOBALID": "{56CBD447-788C-0C05-E063-792F520AB1E8}",
            "geometry": {"x": -77.02754935813694, "y": 38.90355769255569},
        },
        "washington_dc_basic_business_licenses_retail_openings": {
            "OBJECTID": 13057241,
            "CUSTOMERNUMBER": "931326000183",
            "LICENSESTATUS": "Active",
            "LICENSETYPE": "Business License",
            "LICENSESUBTYPE": "Public Health Food Establish",
            "LICENSESTATUSDATE": 1782878400000,
            "LICENSESTARTDATE": 1782878400000,
            "LICENSEENDDATE": 1848628800000,
            "INITIALISSUEDATE": 1782878400000,
            "PRIMARYACTIVITY": "Restaurant",
            "BUSINESSACTIVITY": "Caterers",
            "PREMISEADDRESS": "1501 K ST NW, WASHINGTON, DC, 20005",
            "PREMISEINDC": "Y",
            "ENTITYNAME": "Maman 1501 K Street LLC",
            "ENTITYTRADENAME": "Maman",
            "ENTITYTYPE": "Limited Liability Company (LLC)",
            "DATAREFRESHEDON": 1784260800000,
            "WARD": "Ward 2",
            "ANC": "ANC 2C",
            "NEIGHBORHOODCLUSTER": "Cluster 6",
            "BUSINESSIMPROVEMENTDISTRICT": "Downtown BID",
            "MAR_ID": 279201.0,
            "SSL": "0198    0041,0198    0846",
            "LATITUDE": 38.9029524,
            "LONGITUDE": -77.03511817,
        },
        "washington_dc_owner_parcels_nearby": {
            "OBJECTID": 7335931,
            "SSL": "PAR 01550037",
            "PREMISEADD": "2935 MILLS AVE NE WASHINGTON DC 20018",
            "OWNERNAME": "TERRY, LISA",
            "ADDRESS1": "351 TENNESSEE AVE NE",
            "ADDRESS2": None,
            "CITYSTZIP": "WASHINGTON DC 20002-6445",
            "PROPTYPE": "Residential-Single Family (Det",
            "USECODE": "012",
            "LANDAREA": 8250,
            "OLDLAND": 369600,
            "OLDIMPR": 645900,
            "OLDTOTAL": 1015500,
            "NEWLAND": 371420,
            "NEWIMPR": 681380,
            "NEWTOTAL": 1052800,
            "SALEPRICE": 0,
            "SALEDATE": 1129780800000,
            "VACLNDUSE": None,
            "EXTRACTDAT": 1775448000000,
            "LAST_EDITED_DATE": 1773080339000,
            "centroid": {"x": -76.97335965437271, "y": 38.928317904070155},
        },
        "massachusetts_massgis_l3_property_tax_parcels": {
            "OBJECTID": 1,
            "TOWN_ID": 80,
            "MAP_PAR_ID": "119_193_000_000",
            "LOC_ID": "M_166890_866132",
            "PROP_ID": "119_193_000_000",
            "POLY_TYPE": "FEE",
            "USE_CODE": "1010",
            "SITE_ADDR": "96 WEST MAIN ST",
            "CITY": "DUDLEY",
            "ZIP": "01571",
            "OWNER1": "EKBERG, DONNA MARIE",
            "BLDG_VAL": 238200,
            "LAND_VAL": 77700,
            "OTHER_VAL": 6200,
            "TOTAL_VAL": 322100,
            "FY": 2026,
            "LOT_SIZE": 0.2452,
            "LOT_UNITS": "Acres",
            "LS_DATE": "19860211",
            "LS_PRICE": 0,
            "ZONING": "B15",
            "YEAR_BUILT": 1943,
            "BLD_AREA": 2402,
            "UNITS": 0,
            "LAST_EDIT": 20111020,
            "GlobalID": "9b040210-f40d-449e-8520-b84fe5ad20de",
            "centroid": {"x": -71.89992893203083, "y": 42.04488415648192},
        },
        "allegheny_county_pa_property_assessments": {
            "PARID": "001-H-01-0010",
            "PROPERTYHOUSENUM": "123",
            "PROPERTYFRACTION": "",
            "PROPERTYADDRESS": "Main St",
            "PROPERTYUNIT": "3B",
            "PROPERTYCITY": "Pittsburgh",
            "PROPERTYSTATE": "PA",
            "PROPERTYZIP": "15213",
            "MUNICODE": "Pittsburgh",
            "MUNIDESC": "Pittsburgh",
            "CLASS": "R",
            "CLASSDESC": "Residential",
            "USEDESC": "Single Family",
            "LOTAREA": "6543",
            "COUNTYTOTAL": "250000",
            "SALEDATE": "07/01/2026",
            "SALEPRICE": "215000",
            "ASOFDATE": "2026-07-07",
        },
        "bend_or_planning_applications": {
            "OBJECTID": 1,
            "ApplicationNumber": "PL-26-001",
            "ApplicationDate": 1785542400000,
            "ApplicationDescription": "Commercial site plan",
            "ProjectTypeCode": "SP",
            "ApplicationTypeCode": "SITE",
            "AppStatusDesc": "Under Review",
            "Address": "100 NW Test Ave",
            "TAXLOT": "17120000100",
            "DecisionDate": None,
            "LASTUPDATE": 1785628800000,
            "OverallStatus": "A",
            "centroid": {"x": -121.3153, "y": 44.0582},
        },
        "bend_or_permit_applications_point": {
            "OBJECTID": 2,
            "ApplicationNumber": "BP-26-002",
            "ApplicationDate": 1785542400000,
            "IssueDate": None,
            "DateFinaled": None,
            "SQFT": 12000,
            "Units": 1,
            "ProjectValuation": 1500000,
            "ApplicationType": "TI",
            "ApplicationStatus": "RV",
            "BldgUse": "COM",
            "UseDesc": "Retail",
            "Owner": "Example Owner LLC",
            "Address": "200 NE Test St",
            "TAXLOT": "17120000200",
            "LASTUPDATE": 1785628800000,
            "OverallStatus": "A",
            "ApplicationDescription": "Retail tenant improvement",
            "ProposedLandUse": "Retail",
            "geometry": {"x": -121.3001, "y": 44.0601},
        },
        "bend_or_permit_applications_line": {
            "OBJECTID": 3,
            "ApplicationNumber": "PR-26-003",
            "ApplicationDate": 1785542400000,
            "IssueDate": 1785628800000,
            "DateFinaled": None,
            "SQFT": 5000,
            "Units": 1,
            "ProjectValuation": 600000,
            "ApplicationType": "INF",
            "ApplicationStatus": "PI",
            "StatusDesc": "Permit Issued",
            "BldgUse": "COM",
            "UseDesc": "Commercial",
            "Owner": "Example Corridor LLC",
            "Address": "NW Test Corridor",
            "TAXLOT": "17120000300",
            "LASTUPDATE": 1785628800000,
            "OverallStatus": "I",
        },
        "washington_state_lcb_local_authority_letters": {
            "license": "432561",
            "applicationdate": "2026-07-31T00:00:00.000",
            "countyname": "King",
            "cityname": "Seattle",
            "l_a_type": "New Application",
            "licenseename": "Example Retail LLC",
            "tradename": "Example Market",
            "streetaddress": "100 Pine St",
            "city": "Seattle",
            "state": "WA",
            "zipcode": "98101",
            "privdesc01": "Grocery Store - Beer/Wine",
            "privdesc02": None,
            "privdesc03": None,
            "la_posted_date": "2026-08-01T00:00:00.000",
            "systemdate": "2026-08-01T12:00:00.000",
            "ubi": "600000001",
            "location": {"latitude": "47.6101", "longitude": "-122.3344"},
        },
        "everett_wa_planning_application_notices": {
            "guid": "https://www.everettwa.gov/DocumentCenter/View/54345/notice/1",
            "title": "Notice of Application",
            "link": "https://www.everettwa.gov/DocumentCenter/View/54345/Notice-of-Application-REVII26-014",
            "published_at": "Fri, 31 Jul 2026 15:07:37 -0800",
            "description": "Application for replacement of two commercial storage silos.",
        },
        "taylor_tx_development_notices": {
            "guid": "https://www.taylortx.gov/CivicAlerts.aspx?aid=2079/639217198500000000",
            "title": "Notice of Public Hearings - PZ 2026-2715 - Employment Center Plan - Project Mustang",
            "link": "https://www.taylortx.gov/CivicAlerts.aspx?aid=2079",
            "published_at": "Fri, 07 Aug 2026 16:17:30 -0600",
            "description": "",
        },
        "san_marcos_tx_planning_application_notices": {
            "article_id": "2617",
            "title": "ZC-26-07 (Wonder World Medical CM to BP)",
            "link": "https://www.sanmarcostx.gov/m/newsflash/Home/Detail/2617",
            "published_at": "August 11, 2026",
            "description": "Commercial to Business Park zoning application.",
        },
        "savannah_ga_commercial_building_permits": {
            "OBJECTID": 104549,
            "PIN": "20005 02003",
            "PermitNumber": "26-03951-BC",
            "PermitType": "Building Commercial Permit",
            "WorkClass": "New",
            "PermitStatus": "In Review",
            "District": "Hitch Village/Fred Wessels Homes",
            "IssuedDate": None,
            "FinalizedDate": None,
            "Address": "620 EAST BAY ST",
            "Description": "FOUNDATION PERMIT - HOTEL WITH BASEMENT",
            "Permit_Value": 450000,
        },
        "columbus_oh_site_engineering_applications": {
            "OBJECTID": 7721,
            "B1_ALT_ID": "26345-00571",
            "B1_PER_GROUP": "Engineering",
            "B1_PER_TYPE": "Site Compliance Plan",
            "B1_PER_SUB_TYPE": "Final",
            "B1_PER_CATEGORY": "New Application",
            "B1_PARCEL_NBR": "010034024",
            "SITE_ADDRESS": "1339 E 5TH AVE",
            "B1_SITUS_ZIP": "43219",
            "B1_SHORT_NOTES": "Columbus Climate Controls CO Project",
            "APPLICANT_BUS_NAME": "MARKROB PROPERTIES LLC",
            "FILED_YEAR": 2026,
            "B1_FILE_DD": 1787112000000,
            "B1_APPL_STATUS": "Under Review",
            "LAST_STATUS_DT": 1787162736000,
            "B1_WORK_DESC": "Additional retail showroom and associated parking.",
            "ACA_URL": "https://ca.columbus.gov/permits/example",
        },
        "columbus_oh_commercial_building_permits": {
            "OBJECTID": 479976,
            "B1_ALT_ID": "ALTC2603559",
            "B1_PER_GROUP": "Building",
            "B1_PER_TYPE": "Commercial",
            "B1_PER_SUB_TYPE": "Structural",
            "B1_PER_CATEGORY": "Alteration",
            "GENERAL_TYPE": "Commercial - Other",
            "B1_PARCEL_NBR": "31844202025015",
            "SITE_ADDRESS": "2140 IKEA WAY",
            "B1_SITUS_ZIP": "43240",
            "PERMIT_STATUS": "Final Inspection Approved",
            "APPLICANT_BUS_NAME": "GRA+D Architects",
            "SQFT": 1855,
            "G3_VALUE_TTL": 777294,
            "ISSUED_YEAR": 2026,
            "ISSUED_DT": 1771977600000,
            "LAST_STATUS_DT": 1786924800000,
            "VALUE_DESC": "Additions and alterations - non-residential",
            "ACA_URL": "https://ca.columbus.gov/permits/example",
            "UNITS": 0,
            "B1_APPL_STATUS": "Active",
        },
        "tacoma_wa_commercial_permit_lifecycle": {
            "objectid": 110780,
            "permit_number": "BLDCA26-0252",
            "last_action": "Create",
            "permit_group": "Permits",
            "permit_type": "Building",
            "permit_subtype": "Commercial",
            "permit_category": "Alteration",
            "current_status": "Pending Intake Screening",
            "application_date": 1787184000000,
            "issued_date": None,
            "address_line_1": "601 S 8TH ST",
            "description": "Commercial tenant improvement and interior demolition.",
            "fees_paid": 0,
            "latitude": 47.255,
            "longitude": -122.445,
            "parcel_number": "2008010010",
            "zip": "98402",
            "valuation": 800000,
            "housing_units": 0,
            "link": "https://aca-prod.accela.com/TACOMA/record/example",
            "pull_date": 1787216441000,
            "globalid_1": "a1aac0f4-6b5f-4421-b6f8-4269011e19b1",
            "council_district_number": 2,
        },
        "arlington_tx_commercial_permit_applications": {
            "ImportDate": 1787258880996,
            "OBJECTID": 438,
            "FOLDERYEAR": "26",
            "FOLDERSEQUENCE": "069196",
            "FOLDERTYPE": "SI",
            "STATUSDESC": "Pending",
            "InDate": 1787184000000,
            "SUBDESC": "Business",
            "WORKDESC": "New",
            "FOLDERNAME": "200 E FRONT STREET Suite 150",
            "ConstructionValuationDeclared": None,
            "MainUse": "Restaurant",
            "LandUseDescription": "Food Services",
            "Structure": "Commercial",
            "Census": "327",
            "NameofBusiness": "Game Theory Restaurant & Bar",
            "SignConstructionValue": 25000,
            "FOLDERDESCRIPTION": "New illuminated wall sign.",
            "PROPGISID1": "1234567",
            "PlanningSector": "Central",
            "ZoningUse": "Commercial",
        },
        "arlington_tx_commercial_issued_permits": {
            "ImportDate": 1787278661000,
            "OBJECTID": 245788,
            "FOLDERYEAR": "26",
            "FOLDERSEQUENCE": "069196",
            "FOLDERTYPE": "SI",
            "STATUSDESC": "Issued",
            "ISSUEDATE": 1787234055000,
            "FINALDATE": None,
            "InDate": 1787184000000,
            "SUBDESC": "Business",
            "WORKDESC": "New",
            "FOLDERNAME": "200 E FRONT STREET Suite 150",
            "ConstructionValuationDeclared": None,
            "MainUse": "Restaurant",
            "LandUseDescription": "Food Services",
            "Structure": "Commercial",
            "Census": "327",
            "NameofBusiness": "Game Theory Restaurant & Bar",
            "SignConstructionValue": 25000,
            "PROPGISID1": 1234567,
            "PlanningSector": "Central",
            "ZoningUse": "Commercial",
        },
        "detroit_mi_bseed_building_plan_reviews": {
            "ObjectId": 91382,
            "record_id": "BLD2026-01024",
            "address": "1200 WOODWARD AVE",
            "submitted_date": 1786752000000,
            "task": "Building Plan Review",
            "task_status": "Routed for Electronic Review",
            "task_status_date": 1786752000000,
            "work_description": "INTERIOR TENANT BUILDOUT",
            "parcel_id": "01000123.",
            "longitude": -83.0458,
            "latitude": 42.3314,
        },
        "dallas_tx_legistar_planning_agendas": {
            "source_record_id": "legistar:cityofdallas:4543:115220",
            "event_type": "planning_hearing_agenda_item",
            "stage": "hearing_scheduled",
            "title": "Zoning case Z234-001",
            "summary": "Public hearing for a commercial zoning application.",
            "evidence_excerpt": "Public hearing for a commercial zoning application.",
            "agenda_item_number": "5",
            "reference_number": "Z234-001",
            "meeting_name": "City Plan Commission",
            "governing_body": "City Plan Commission",
            "meeting_at": "2026-09-03T00:00:00",
            "published_at": "2026-08-12T15:10:00Z",
            "decision_at": None,
            "modified_at": "2026-08-12T19:00:00Z",
            "source_url": "https://cityofdallas.legistar.com/LegislationDetail.aspx?ID=1",
        },
    }

    for entry in load_catalog():
        mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
        prepared, field_mapping = prepare_mapped_record(samples[entry.key], mappings)
        if entry.record_type == "parcel":
            normalized = normalize_parcel(
                prepared, field_mapping, defaults=entry.settings.get("defaults")
            )
            assert normalized.source_record_id
            address_optional_parcel_sources = {
                "rhode_island_statewide_tax_parcels_narrow",
                "tennessee_comptroller_impact_parcels_nearby_narrow",
                "sedgwick_county_ks_parcels_nearby_narrow",
                "delaware_firstmap_statewide_parcels_narrow",
                "virginia_vgin_statewide_parcels_narrow",
            }
            if entry.key not in address_optional_parcel_sources and not str(
                entry.settings.get("export_policy", "")
            ).startswith("derived_geometry_"):
                assert normalized.values.get("address")
            if "owner_name" in set(field_mapping.values()):
                assert normalized.values.get("owner_name")
            if entry.key != "allegheny_county_pa_property_assessments":
                assert normalized.values.get("latitude") is not None
                assert normalized.values.get("longitude") is not None
            assert normalized.values.get("parcel_group_id") or entry.key != (
                "miami_dade_fl_property_appraiser_parcels"
            )
            continue
        if entry.record_type == "planning":
            normalized = normalize_planning_record(
                prepared, field_mapping, defaults=entry.settings.get("defaults")
            )
            assert normalized.source_record_id
            assert normalized.values.get("title")
            assert normalized.values.get("stage") == "hearing_scheduled"
            assert normalized.values.get("source_url")
            continue
        normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings.get("defaults"))
        assert normalized.source_record_id
        assert normalized.values.get("permit_number") or normalized.values.get("application_number")
        assert normalized.values.get("address") or normalized.values.get("project_name")
        assert normalized.values.get("approval_stage") in {"pre_approval", "approved"}


def test_new_orleans_catalog_uses_row_identity_and_preserves_pre_approval_records():
    entry = next(entry for entry in load_catalog() if entry.key == "new_orleans_la_permits_blds")

    assert entry.settings["connector"] == {
        "page_size": 500,
        "order_by": ":id ASC",
        "query": {"$select": ":*,*"},
    }
    assert entry.settings["reconciliation_mode"] == "periodic_full"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert set(entry.settings["canary_required_fields"]) == {
        ":id", "permitnum", "description", "originaladdress1", "statuscurrent",
    }

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    application = {
        ":id": "row-application", "permitnum": "26-20590-FGAS",
        "statuscurrent": "Application Submitted", "description": "Install a gas line",
        "originaladdress1": "994 Bragg St",
    }
    prepared, field_mapping = prepare_mapped_record(application, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.source_record_id == "row-application"
    assert normalized.values["permit_number"] == "26-20590-FGAS"
    assert normalized.values["status"] == "Application Submitted"
    assert normalized.values["approval_stage"] == "pre_approval"

    issued = {**application, ":id": "row-issued", "issuedate": "2026-07-15T13:26:11.000"}
    prepared, field_mapping = prepare_mapped_record(issued, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])
    assert normalized.values["approval_stage"] == "approved"


def test_boulder_catalog_uses_guid_identity_and_issue_date_boundary():
    entry = next(entry for entry in load_catalog() if entry.key == "boulder_co_construction_permits")

    assert entry.adapter == "arcgis"
    assert entry.settings["connector"] == {
        "page_size": 1000,
        "order_by_fields": "PermitID ASC",
    }
    assert entry.settings["reconciliation_mode"] == "daily_full_snapshot"

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    application = {
        "PermitID": "permit-guid-1",
        "PermitNum": "PMT2026-00123",
        "StatusCurrent": "In Review",
        "Description": "Commercial tenant finish for new retail store",
        "OriginalAddress": "1000 Pearl St",
        "AppliedDate": 1784073600000,
    }
    prepared, field_mapping = prepare_mapped_record(application, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.source_record_id == "permit-guid-1"
    assert normalized.values["permit_number"] == "PMT2026-00123"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["filed_at"].isoformat() == "2026-07-15T00:00:00+00:00"

    issued = {**application, "IssuedDate": 1784160000000, "StatusCurrent": "Issued"}
    prepared, field_mapping = prepare_mapped_record(issued, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])
    assert normalized.values["approval_stage"] == "approved"


def test_somerville_catalog_filters_building_applications_and_preserves_review_stage():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "somerville_ma_building_permit_applications"
    )

    assert entry.settings["connector"] == {
        "page_size": 1000,
        "order_by": "application_id ASC",
        "query": {"$where": "application_type='Building Permit'"},
    }
    assert entry.settings["attribution_required"] is True
    assert entry.settings["share_alike_review_required"] is True

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    application = {
        "application_id": "application-guid-1",
        "application_number": "B-26-123",
        "status": "Under Review",
        "project_description_or_business_name": "Commercial fit-out for a retail tenant",
        "application_address": "100 Broadway",
        "application_date": "2026-07-15T00:00:00.000",
    }
    prepared, field_mapping = prepare_mapped_record(application, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.source_record_id == "application-guid-1"
    assert normalized.values["description"] == "Commercial fit-out for a retail tenant"
    assert normalized.values["approval_stage"] == "pre_approval"

    issued = {**application, "status": "Issued", "issue_date": "2026-07-16T00:00:00.000"}
    prepared, field_mapping = prepare_mapped_record(issued, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])
    assert normalized.values["approval_stage"] == "approved"


def test_cleveland_catalog_retains_pending_tasks_and_contractors():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "cleveland_oh_building_permit_applications"
    )

    assert entry.adapter == "arcgis"
    assert entry.settings["connector"] == {
        "page_size": 2000,
        "order_by_fields": "OBJECTID ASC",
        "keyset_field": "OBJECTID",
    }
    assert entry.settings["share_alike_review_required"] is True

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    application = {
        "PERMIT_ID": "B26001234",
        "PERMIT_ISSUED": "Pending",
        "WORK_DESCRIPTION": "Commercial fit-out for a national retail tenant",
        "PRIMARY_ADDRESS": "100 Euclid Ave",
        "PARCEL_NUMBER": "101-01-001",
        "CONTRACTOR_BUSINESS_NAME": "Builder Inc",
        "FILE_DATE": 1784073600000,
    }
    prepared, field_mapping = prepare_mapped_record(application, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.source_record_id == "B26001234"
    assert normalized.values["contractor_name"] == "Builder Inc"
    assert normalized.values["approval_stage"] == "pre_approval"

    issued = {**application, "PERMIT_ISSUED": "Yes", "ISSUE_DATE": 1784160000000}
    prepared, field_mapping = prepare_mapped_record(issued, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])
    assert normalized.values["approval_stage"] == "approved"


def test_cincinnati_catalog_filters_commercial_and_preserves_review_stage():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "cincinnati_oh_building_permits"
    )

    assert entry.adapter == "socrata"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert entry.settings["connector"] == {
        "page_size": 500,
        "order_by": "applieddate DESC",
        "query": {
            "$select": (
                ":id,permitnum,description,applieddate,issueddate,completeddate,"
                "expiresdate,coissueddate,statuscurrent,statuscurrentmapped,"
                "originaladdress1,originalcity,originalstate,originalzip,"
                "jurisdiction,permitclass,workclass,"
                "workclassmapped,permittype,permittypemapped,proposeduse,"
                "companyname,totalsqft,estprojectcostdec,units,pin,fee,link,"
                "latitude,longitude,neighborhood"
            ),
            "$where": (
                "permitnum IS NOT NULL AND originaladdress1 IS NOT NULL AND "
                "permitclass = 'OBC' AND permittypemapped IN "
                "('Building','Signs','Fire Protection Systems','HVAC','Plumbing Permits') AND "
                "statuscurrent NOT IN "
                "('WITHDRWN','EXPIRED','APP_EXP','VOIDED','REVOKED','DENIED') AND "
                "(applieddate >= '2024-01-01' OR issueddate >= '2024-01-01' "
                "OR completeddate >= '2024-01-01')"
            ),
        },
    }

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    application = {
        ":id": "row-cincy-1",
        "permitnum": "CBLD2026-00421",
        "description": "Interior alteration for national retail tenant",
        "applieddate": "2026-07-15T00:00:00.000",
        "statuscurrent": "ROUTE",
        "statuscurrentmapped": "In Review",
        "originaladdress1": "100 Vine St",
        "originalcity": "Cincinnati",
        "originalstate": "OH",
        "originalzip": "45202",
        "jurisdiction": "CINCINNATI",
        "permitclass": "OBC",
        "permitclassmapped": "Non-Residential",
        "workclassmapped": "Existing",
        "permittypemapped": "Building",
        "proposeduse": "M",
        "companyname": "National Retail Buildout LLC",
        "totalsqft": "24000",
        "estprojectcostdec": "850000",
        "units": "1",
        "pin": "00100010001",
        "link": "http://cagis.hamilton-co.org/opal/Permit.aspx?permit=CBLD2026-00421",
        "latitude": "39.1015",
        "longitude": "-84.5125",
    }
    prepared, field_mapping = prepare_mapped_record(application, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.source_record_id == "row-cincy-1"
    assert normalized.values["permit_number"] == "CBLD2026-00421"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["status"] == "ROUTE / In Review"
    assert normalized.values["contractor_name"] == "National Retail Buildout LLC"
    assert normalized.values["parcel_id"] == "00100010001"
    assert normalized.values["source_url"].startswith("http://cagis.hamilton-co.org/opal/")

    issued = {**application, ":id": "row-cincy-2", "statuscurrent": "ISSUED", "issueddate": "2026-07-16T00:00:00.000"}
    prepared, field_mapping = prepare_mapped_record(issued, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])
    assert normalized.values["approval_stage"] == "approved"


def test_portland_catalog_scopes_development_records_and_quarantines_bad_dates():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "portland_or_development_and_building_applications"
    )

    assert entry.settings["connector"] == {
        "page_size": 4000,
        "where": "TYPE IN ('CO','RS','SD','LU','DR','PC')",
        "order_by_fields": "OBJECTID ASC",
        "keyset_field": "OBJECTID",
    }

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    application = {
        "FOLDERKEY": 1234567,
        "APPLICATION": "2026-012345-000-00-CO",
        "STATUS": "Under Review",
        "DESCRIPTION": "Commercial remodel for a national retailer",
        "HOUSE": 100,
        "PROPSTREET": "Broadway",
        "STREETTYPE": "St",
        "CREATEDATE": 1784073600000,
        "ISSUED": 4395523200000,
    }
    prepared, field_mapping = prepare_mapped_record(application, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.source_record_id == "1234567"
    assert normalized.values["address"] == "100 Broadway St"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert "issued_at" not in normalized.values

    approved = {**application, "STATUS": "Approved", "ISSUED": None}
    prepared, field_mapping = prepare_mapped_record(approved, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])
    assert normalized.values["approval_stage"] == "approved"


def test_pittsburgh_catalog_is_explicitly_issued_only_and_attributed():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "pittsburgh_pa_issued_building_permits"
    )

    assert entry.adapter == "ckan"
    assert entry.settings["signal_stage"] == "approved_only"
    assert entry.settings["attribution_required"] is True
    assert entry.settings["connector"]["resource_id"] == "f4d1177a-f597-4c32-8cbf-7885f56253f6"


def test_milwaukee_catalog_is_commercial_confirmation_only_and_attributed():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "milwaukee_wi_commercial_permit_work"
    )

    assert entry.adapter == "ckan"
    assert entry.settings["signal_stage"] == "approved_only"
    assert entry.settings["attribution_required"] is True
    assert entry.settings["record_filters"] == [
        {
            "field": "Permit Type",
            "values": ["Commercial Alteration Permit", "Commercial New Construction Permit"],
        }
    ]
    assert entry.settings["connector"]["resource_id"] == "828e9630-d7cb-42e4-960e-964eae916397"


def test_louisville_active_construction_catalog_is_confirmation_only():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "louisville_jefferson_ky_active_construction_permits"
    )

    assert entry.adapter == "arcgis"
    assert entry.settings["signal_stage"] == "approved_only"
    assert entry.settings["defaults"]["approval_stage"] == "approved"
    assert entry.settings["connector"]["keyset_field"] == "ObjectId"
    assert entry.settings["connector"]["page_size"] == 200
    assert entry.settings["record_filters"][0]["field"] == "PERMIT_TYPE"


def test_minneapolis_catalog_filters_commercial_and_preserves_preapproval_stage():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "minneapolis_mn_commercial_construction_permits"
    )
    mappings = entry.field_mappings
    application = {
        "OBJECTID": 1001,
        "permitNumber": "BLDG-2026-00123",
        "permitType": "Commercial",
        "workType": "Remodel",
        "occupancyType": "Mercantile",
        "status": "In Process",
        "milestone": "Plan Review",
        "Display": "100 Nicollet Mall",
        "APN": "0102824110001",
        "comments": "Interior retail tenant improvement",
        "value": "350000",
        "issueDate": None,
        "completeDate": None,
        "applicantName": "BuildCo Inc",
        "fullName": "Property Owner LLC",
        "Latitude": "44.9765",
        "Longitude": "-93.2712",
    }

    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert entry.settings["record_filters"] == [
        {"field": "permitType", "value": "Commercial"}
    ]
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    prepared, field_mapping = prepare_mapped_record(application, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.source_record_id == "1001"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["status"] == "In Process / Plan Review"
    assert normalized.values["contractor_name"] == "BuildCo Inc"

    issued = {**application, "status": "Issued", "issueDate": 1784073600000}
    prepared, field_mapping = prepare_mapped_record(issued, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])
    assert normalized.values["approval_stage"] == "approved"
    assert normalized.values["issued_at"].isoformat() == "2026-07-15T00:00:00+00:00"


def test_st_louis_occupancy_catalog_preserves_open_and_issued_stages():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "st_louis_mo_commercial_occupancy_applications"
    )
    application = {
        "OccupancyApplicationID": 13669,
        "PermitType": "Commercial Occupancy",
        "ApplicationDate": "2026-06-16",
        "ProjectAddress": "3750 WASHINGTON BLVD",
        "UnitNumber": "",
        "ProjectCity": "St. Louis",
        "ProjectState": "MO",
        "ProjectZipCode": "63108",
        "ProjectASRParcelID": "22879400000",
        "ProjectParcelID": "228700400",
        "ProjectHandle": "12287000400",
        "OwnerName": "CONTEMPORARY ART MUSEUM ST LOUIS",
        "OwnerAddress": "3750 WASHINGTON BLVD",
        "OwnerCity": "ST LOUIS",
        "OwnerState": "MO",
        "OwnerZipCode": "63108",
        "BusinessType": "Cafe",
        "BusinessTypeDescription": "FULL DRINK CAFE W/PATIO SEATING",
        "CurrentResult": "Open",
        "CurrentResultDate": "2026-06-23",
    }

    assert entry.adapter == "json_array"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    prepared, field_mapping = prepare_mapped_record(application, entry.field_mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.source_record_id == "13669"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["parcel_id"] == "22879400000"
    assert "latitude" not in normalized.values
    assert normalized.unmapped["ProjectHandle"] == "12287000400"

    issued = {**application, "CurrentResult": "Issued"}
    prepared, field_mapping = prepare_mapped_record(issued, entry.field_mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])
    assert normalized.values["approval_stage"] == "approved"
    assert normalized.values["issued_at"].isoformat() == "2026-06-23T00:00:00+00:00"


def test_montgomery_county_catalog_is_confirmation_only_and_keyset_paginated():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "montgomery_county_md_commercial_permits"
    )

    assert entry.settings["signal_stage"] == "approved_only"
    assert entry.settings["connector"] == {
        "page_size": 500,
        "keyset_fields": ["permitno"],
    }
    assert entry.settings["license"] == "Public Domain"


def test_maryland_imap_sdat_parcel_points_are_statewide_proximity_context():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "maryland_imap_sdat_parcel_points"
    )

    suppressed = set(entry.settings["suppressed_fields"])
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }
    mapped_fields = {mapping.source_field for mapping in entry.field_mappings}
    mapped_canonical = {mapping.canonical_field for mapping in entry.field_mappings}

    assert entry.adapter == "arcgis"
    assert entry.record_type == "parcel"
    assert entry.settings["signal_stage"] == "parcel_context"
    assert entry.settings["license"] == "Public Domain"
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    assert entry.settings["connector"]["include_geometry"] is True
    assert "owner-name assets" in entry.settings["rights_basis"].casefold()
    assert suppressed.isdisjoint(out_fields)
    assert suppressed.isdisjoint(mapped_fields)
    assert "owner_name" not in mapped_canonical
    assert "ACCTID IS NOT NULL" in entry.settings["connector"]["where"]

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    parcel = {
        "OBJECTID": 1,
        "JURSCODE": "STMA",
        "ACCTID": "1901000047",
        "ADDRESS": "18214 BAUER RD",
        "CITY": "LEXINGTON PARK",
        "ZIPCODE": "20653",
        "OWNADD1": "18214 BAUER RD",
        "OWNCITY": "SAINT MARYS CITY",
        "OWNSTATE": "MD",
        "OWNERZIP": "20686",
        "ZONING": "RPD",
        "DESCLU": "Residential",
        "SQFTSTRC": 2505,
        "TRADATE": "20250429",
        "CONSIDR1": "637500",
        "NFMLNDVL": 637500,
        "NFMIMPVL": 334800,
        "NFMTTLVL": 972300,
        "SDATWEBADR": "https://sdat.dat.maryland.gov/RealProperty/Pages/viewdetails.aspx?County=19&SearchType=ACCT&District=01&AccountNumber=000047",
        "MDPVDATE": "2023JUN",
        "SDATDATE": "2026MAY",
        "geometry": {"x": -76.4579, "y": 38.2746},
    }
    prepared, field_mapping = prepare_mapped_record(parcel, mappings)
    normalized = normalize_parcel(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.source_record_id == "STMA:1901000047"
    assert normalized.values["address"] == "18214 BAUER RD"
    assert normalized.values["owner_mailing_address"] == "18214 BAUER RD SAINT MARYS CITY MD 20686"
    assert normalized.values["land_use"] == "Residential"
    assert normalized.values["zoning_code"] == "RPD"
    assert normalized.values["last_sale_date"].isoformat() == "2025-04-29T00:00:00+00:00"
    assert normalized.values["latitude"] == Decimal("38.2746")
    assert normalized.values["longitude"] == Decimal("-76.4579")


def test_henderson_catalog_uses_source_uuid_and_preserves_pending_stage():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "henderson_nv_commercial_development_permits"
    )

    assert entry.settings["connector"] == {
        "page_size": 1000,
        "order_by_fields": "OBJECTID ASC",
        "keyset_field": "OBJECTID",
    }
    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    application = {
        "GISHISTORYQUEUEID": "f689e904-45bd-41fb-8842-6a70843d2760",
        "CASENUMBER": "BCOM2026395457",
        "STATUS": "Pending",
        "DESCRIPTION": "Commercial remodel for a retailer",
        "MAIN_ADDRESS_LINE1": "100 Water St",
        "SPATIALID": "19103411003",
        "OWNER": "Property Owner LLC",
        "APPLICATIONDATE": 1784073600000,
    }
    prepared, field_mapping = prepare_mapped_record(application, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.source_record_id == "f689e904-45bd-41fb-8842-6a70843d2760"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["parcel_id"] == "19103411003"

    issued = {**application, "STATUS": "Active - Issued", "ISSUEDATE": 1784160000000}
    prepared, field_mapping = prepare_mapped_record(issued, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])
    assert normalized.values["approval_stage"] == "approved"


def test_hartford_commercial_permit_lifecycle_preserves_pre_approval_chain_context():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "hartford_ct_building_permits_lifecycle"
    )
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }
    suppressed = set(entry.settings["suppressed_fields"])

    assert entry.adapter == "arcgis"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert "RECORD_TYPE_TYPE = 'Commercial'" in entry.settings["connector"]["where"]
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    assert entry.settings["freshness_field"] == "DATE_OPENED"
    assert entry.settings["canary_freshness_probe"]["connector"]["order_by_fields"] == "DATE_OPENED DESC, OBJECTID ASC"
    assert "Ready to Issue" in entry.settings["canary_stage_probes"][0]["connector"]["where"]
    assert "Issued" in entry.settings["canary_stage_probes"][1]["connector"]["where"]
    assert "ASSIGNED_TO" not in out_fields
    assert suppressed.isdisjoint(out_fields)

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    pending = {
        "OBJECTID": 3553,
        "RECORD_ID": "COM-ALT-26-000302",
        "DESCRIPTION": "STARBUCKS tenant plumbing and sign fit-out",
        "DATE_OPENED": "2026-06-29 ",
        "DATE_CLOSED": None,
        "RECORD_TYPE_TYPE": "Commercial",
        "B1_APP_TYPE_ALIAS": "Commercial Alteration Permit",
        "RECORD_STATUS": "Pending",
        "PROPERTY_ADDRESS": "317 WEST SERVICE RD, HARTFORD, CT 06120",
        "Location": "317 WEST SERVICE RD ",
        "UNIT": None,
        "PROPERTY_CITY": "HARTFORD",
        "PROPERTY_STATE": "CT",
        "PROPERTY_ZIP": "06120",
        "PARCEL_ID": "304074015",
        "Total_Construction_Cost": 7500.0,
        "DateIssued": None,
        "GlobalID": "{CBB433C4-0ADD-4B50-94AB-1123A3EACC5F}",
    }
    prepared, field_mapping = prepare_mapped_record(pending, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.source_record_id == "COM-ALT-26-000302"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["project_name"] == "STARBUCKS tenant plumbing and sign fit-out"
    assert normalized.values["parcel_id"] == "304074015"
    assert normalized.values["valuation"] == Decimal("7500.0")
    assert normalized.values["filed_at"].isoformat() == "2026-06-29T00:00:00+00:00"

    issued = {**pending, "RECORD_STATUS": "Issued", "DateIssued": "2026-07-02 "}
    prepared, field_mapping = prepare_mapped_record(issued, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])

    assert normalized.values["approval_stage"] == "approved"
    assert normalized.values["issued_at"].isoformat() == "2026-07-02T00:00:00+00:00"


def test_service_rejects_unbounded_page_counts(db):
    source = SimpleNamespace(id="not-used")
    with pytest.raises(ValueError, match="between 1 and 100"):
        execute_source_run(db, source, max_pages=0)
    with pytest.raises(ValueError, match="between 1 and 100"):
        execute_source_run(db, source, max_pages=101)


def test_columbus_site_engineering_preserves_pre_approval_project_context():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "columbus_oh_site_engineering_applications"
    )
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }
    suppressed = set(entry.settings["suppressed_fields"])

    assert entry.adapter == "arcgis"
    assert entry.settings["license"] == "Creative Commons CC0 1.0 Universal"
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert "Site Compliance Plan" in entry.settings["connector"]["where"]
    assert entry.settings["connector"]["keyset_field"] == "OBJECTID"
    assert "APPLICANT_FULL_NAME" not in out_fields
    assert suppressed.isdisjoint(out_fields)

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    application = {
        "OBJECTID": 7721,
        "B1_ALT_ID": "26345-00571",
        "B1_PER_GROUP": "Engineering",
        "B1_PER_TYPE": "Site Compliance Plan",
        "B1_PER_SUB_TYPE": "Final",
        "B1_PER_CATEGORY": "New Application",
        "B1_PARCEL_NBR": "010034024",
        "SITE_ADDRESS": "1339 E 5TH AVE",
        "B1_SITUS_ZIP": "43219",
        "B1_SHORT_NOTES": "Columbus Climate Controls CO Project",
        "APPLICANT_BUS_NAME": "MARKROB PROPERTIES LLC",
        "FILED_YEAR": 2026,
        "B1_FILE_DD": 1787112000000,
        "B1_APPL_STATUS": "Under Review",
        "LAST_STATUS_DT": 1787162736000,
        "B1_WORK_DESC": "Additional retail showroom and associated parking.",
        "ACA_URL": "https://ca.columbus.gov/permits/example",
    }
    prepared, field_mapping = prepare_mapped_record(application, mappings)
    normalized = normalize_permit(
        prepared,
        field_mapping,
        defaults=entry.settings["defaults"],
    )

    assert normalized.source_record_id == "26345-00571"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["project_name"] == "Columbus Climate Controls CO Project"
    assert normalized.values["parcel_id"] == "010034024"
    assert normalized.values["applicant_name"] == "MARKROB PROPERTIES LLC"
    assert normalized.values["filed_at"].year == 2026

    completed = {**application, "B1_APPL_STATUS": "Completed"}
    prepared, field_mapping = prepare_mapped_record(completed, mappings)
    normalized = normalize_permit(
        prepared,
        field_mapping,
        defaults=entry.settings["defaults"],
    )
    assert normalized.values["approval_stage"] == "approved"


def test_columbus_commercial_permits_are_approved_confirmation():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "columbus_oh_commercial_building_permits"
    )
    out_fields = {
        field.strip()
        for field in entry.settings["connector"]["out_fields"].split(",")
    }

    assert entry.settings["signal_stage"] == "approved_only"
    assert "B1_PER_TYPE = 'Commercial'" in entry.settings["connector"]["where"]
    assert "APPLICANT_FULL_NAME" not in out_fields

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    permit = {
        "OBJECTID": 479976,
        "B1_ALT_ID": "ALTC2603559",
        "B1_PER_GROUP": "Building",
        "B1_PER_TYPE": "Commercial",
        "B1_PER_SUB_TYPE": "Structural",
        "B1_PER_CATEGORY": "Alteration",
        "GENERAL_TYPE": "Commercial - Other",
        "B1_PARCEL_NBR": "31844202025015",
        "SITE_ADDRESS": "2140 IKEA WAY",
        "B1_SITUS_ZIP": "43240",
        "PERMIT_STATUS": "Final Inspection Approved",
        "APPLICANT_BUS_NAME": "GRA+D Architects",
        "SQFT": 1855,
        "G3_VALUE_TTL": 777294,
        "ISSUED_YEAR": 2026,
        "ISSUED_DT": 1771977600000,
        "LAST_STATUS_DT": 1786924800000,
        "VALUE_DESC": "Additions and alterations - non-residential",
        "ACA_URL": "https://ca.columbus.gov/permits/example",
        "UNITS": 0,
        "B1_APPL_STATUS": "Active",
    }
    prepared, field_mapping = prepare_mapped_record(permit, mappings)
    normalized = normalize_permit(
        prepared,
        field_mapping,
        defaults=entry.settings["defaults"],
    )

    assert normalized.source_record_id == "ALTC2603559"
    assert normalized.values["approval_stage"] == "approved"
    assert normalized.values["permit_number"] == "ALTC2603559"
    assert normalized.values["valuation"] == Decimal("777294")
    assert normalized.values["square_feet"] == 1855


def test_tacoma_commercial_permits_preserve_pre_approval_context():
    entry = next(
        entry for entry in load_catalog()
        if entry.key == "tacoma_wa_commercial_permit_lifecycle"
    )
    out_fields = set(entry.settings["connector"]["out_fields"].split(","))
    assert entry.settings["signal_stage"] == "pre_approval_and_approved"
    assert entry.settings["connector"]["keyset_field"] == "objectid"
    assert "applicant_name" not in out_fields

    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in entry.field_mappings]
    permit = {
        "objectid": 110780,
        "permit_number": "BLDCA26-0252",
        "last_action": "Create",
        "permit_group": "Permits",
        "permit_type": "Building",
        "permit_subtype": "Commercial",
        "permit_category": "Alteration",
        "current_status": "Pending Intake Screening",
        "application_date": 1787184000000,
        "issued_date": None,
        "address_line_1": "601 S 8TH ST",
        "description": "Commercial tenant improvement.",
        "fees_paid": 0,
        "latitude": 47.255,
        "longitude": -122.445,
        "parcel_number": "2008010010",
        "zip": "98402",
        "valuation": 800000,
        "housing_units": 0,
        "link": "https://aca-prod.accela.com/TACOMA/record/example",
        "pull_date": 1787216441000,
        "globalid_1": "a1aac0f4-6b5f-4421-b6f8-4269011e19b1",
        "council_district_number": 2,
    }
    prepared, field_mapping = prepare_mapped_record(permit, mappings)
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])
    assert normalized.source_record_id == "BLDCA26-0252"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["parcel_id"] == "2008010010"

    prepared, field_mapping = prepare_mapped_record(
        {**permit, "current_status": "Permit Issued"}, mappings
    )
    normalized = normalize_permit(prepared, field_mapping, defaults=entry.settings["defaults"])
    assert normalized.values["approval_stage"] == "approved"


def test_arlington_lifecycle_pair_preserves_retail_signal_and_identity():
    entries = {
        entry.key: entry
        for entry in load_catalog()
        if entry.key.startswith("arlington_tx_commercial_")
    }
    application = entries["arlington_tx_commercial_permit_applications"]
    issued = entries["arlington_tx_commercial_issued_permits"]
    assert application.settings["license"] == "Creative Commons Attribution 4.0 International"
    assert application.settings["signal_stage"] == "pre_approval_and_approved"
    assert issued.settings["signal_stage"] == "approved_only"
    assert "applicant_name" not in application.settings["connector"]["out_fields"]

    record = {
        "ImportDate": 1787258880996,
        "OBJECTID": 438,
        "FOLDERYEAR": "26",
        "FOLDERSEQUENCE": "069196",
        "FOLDERTYPE": "SI",
        "STATUSDESC": "Pending",
        "InDate": 1787184000000,
        "SUBDESC": "Business",
        "WORKDESC": "New",
        "FOLDERNAME": "200 E FRONT STREET Suite 150",
        "ConstructionValuationDeclared": None,
        "MainUse": "Restaurant",
        "LandUseDescription": "Food Services",
        "Structure": "Commercial",
        "Census": "327",
        "NameofBusiness": "Game Theory Restaurant & Bar",
        "SignConstructionValue": 25000,
        "FOLDERDESCRIPTION": "New illuminated wall sign.",
        "PROPGISID1": "1234567",
        "PlanningSector": "Central",
        "ZoningUse": "Commercial",
    }
    mappings = [SimpleNamespace(**mapping.model_dump()) for mapping in application.field_mappings]
    prepared, field_mapping = prepare_mapped_record(record, mappings)
    normalized = normalize_permit(
        prepared, field_mapping, defaults=application.settings["defaults"]
    )
    assert normalized.source_record_id == "26-069196-SI"
    assert normalized.values["approval_stage"] == "pre_approval"
    assert normalized.values["project_name"] == "Game Theory Restaurant & Bar"
    assert normalized.values["valuation"] == Decimal("25000")

    prepared, field_mapping = prepare_mapped_record(
        {**record, "STATUSDESC": "Approved for Issue"}, mappings
    )
    normalized = normalize_permit(
        prepared, field_mapping, defaults=application.settings["defaults"]
    )
    assert normalized.values["approval_stage"] == "approved"


def test_san_jose_planning_companion_sources_are_registered_for_document_ingestion():
    candidates = {
        entry.key: entry
        for entry in load_candidate_catalog()
        if entry.jurisdiction == "San Jose, CA"
    }

    hearings = candidates["san_jose_ca_planning_director_hearings"]
    assert hearings.record_type == "planning"
    assert hearings.adapter == "planning_documents"
    assert hearings.status == "technical_hold"
    assert hearings.can_run_canary is False
    assert "file_numbers" in hearings.candidate_source_fields
    assert "staff_recommendation" in hearings.candidate_source_fields

    settings = hearings.probe_settings
    assert settings is not None
    connector = settings["connector"]
    assert connector["document_allowed_hosts"] == ["www.sanjoseca.gov"]
    assert connector["max_index_pages"] == 1
    assert connector["max_documents"] == 24
    assert connector["max_document_bytes"] == 10 * 1024 * 1024
    assert connector["max_items_per_document"] == 100
    assert connector["max_item_characters"] == 50_000
    assert connector["max_records"] == 250
    assert connector["meeting_name"] == "Planning Director Hearing"
    assert connector["stages"] == {
        "agenda": "hearing_scheduled",
        "minutes": "decision_recorded",
    }
    assert settings["signal_stage"] == "pre_approval_and_approved"
    assert settings["freshness_semantics"] == "ingestion_observed_at"
    assert settings["freshness_sla_hours"] == 168
    assert settings["defaults"] == {
        "jurisdiction": "San Jose, CA",
        "city": "San Jose",
        "state": "CA",
        "confidence": 0.95,
    }

    item_pattern = re.compile(connector["item_pattern"], re.IGNORECASE | re.MULTILINE)
    file_pattern = re.compile(connector["file_pattern"], re.IGNORECASE | re.MULTILINE)
    heading = "4.A SP26-005 & ER26-024"
    assert item_pattern.search(heading).group("item_number") == "4.A"
    assert [match.group("file_number") for match in file_pattern.finditer(heading)] == [
        "SP26-005",
        "ER26-024",
    ]

    values = connector["value_patterns"]
    assert set(values) == {
        "project_description",
        "address",
        "owner_name",
        "environmental_review",
        "staff_recommendation",
    }
    sample = """4.A SP26-005 & ER26-024
PROJECT DESCRIPTION: Special Use Permit for a retaining wall.
PROJECT LOCATION: 6763 Crystal Springs Drive
PROPERTY OWNER: Example Property Owner LLC
ENVIRONMENTAL REVIEW: Exempt under CEQA Guidelines Section 15303.
STAFF RECOMMENDATION: Consider the exemption and approve the permit.
ADJOURNMENT
"""
    extracted = {
        field: re.search(pattern, sample, re.IGNORECASE | re.MULTILINE).group("value").strip()
        for field, pattern in values.items()
    }
    assert extracted["project_description"].startswith("Special Use Permit")
    assert extracted["address"] == "6763 Crystal Springs Drive"
    assert extracted["owner_name"] == "Example Property Owner LLC"
    assert extracted["environmental_review"].startswith("Exempt under CEQA")
    assert extracted["staff_recommendation"].startswith("Consider the exemption")

    mappings = {
        mapping.source_field: mapping.canonical_field for mapping in hearings.probe_field_mappings
    }
    assert mappings["source_record_id"] == "source_record_id"
    assert mappings["stage"] == "stage"
    assert mappings["address"] == "address"
    assert mappings["owner_name"] == "owner_name"
    assert mappings["meeting_at"] == "meeting_at"
    assert mappings["source_url"] == "source_url"
    assert "project_description" not in mappings
    assert "environmental_review" not in mappings
    assert "staff_recommendation" not in mappings
    assert "HTTP 403" in hearings.blocker_summary
    assert "2026-08-22" in hearings.blocker_summary
    assert "browser automation" in hearings.blocker_summary

    energy = candidates["san_jose_ca_large_energy_projects"]
    assert energy.record_type == "planning"
    assert energy.adapter == "html_table"
    assert energy.status == "technical_hold"
    assert "file_number" in energy.candidate_source_fields
    assert "environmental_review_status" in energy.candidate_source_fields


def test_dallas_legistar_planning_candidate_is_bounded_and_rights_gated():
    candidates = {
        entry.key: entry for entry in load_candidate_catalog(include_promoted=True)
    }

    dallas = candidates["dallas_tx_legistar_planning_agendas"]
    assert dallas.record_type == "planning"
    assert dallas.adapter == "legistar"
    assert dallas.status == "operational_retry"
    assert dallas.can_run_canary is True

    settings = dallas.probe_settings
    assert settings is not None
    connector = settings["connector"]
    assert connector["endpoint"] == "https://webapi.legistar.com/v1/cityofdallas"
    assert "City Plan Commission" in connector["body_names"]
    assert connector["event_page_size"] == 20
    assert connector["max_events"] == 40
    assert connector["max_items_per_event"] == 150
    assert connector["max_records"] == 250
    assert connector["lookback_days"] == 45
    assert connector["future_days"] == 120
    assert connector["max_evidence_characters"] == 10_000
    assert settings["signal_stage"] == "pre_approval"
    assert settings["freshness_field"] == "modified_at"
    assert settings["freshness_sla_hours"] == 336
    assert "canary_stage_probes" not in settings

    mappings = {
        mapping.source_field: mapping.canonical_field
        for mapping in dallas.probe_field_mappings
    }
    assert mappings["source_record_id"] == "source_record_id"
    assert mappings["reference_number"] == "reference_number"
    assert mappings["governing_body"] == "governing_body"
    assert "decision_at" not in mappings
    assert mappings["source_url"] == "source_url"
    assert "Rights and data-minimization scope were approved" in dallas.blocker_summary
    assert "pre-approval only" in dallas.notes
    assert {mapping.canonical_field for mapping in dallas.probe_field_mappings} <= {
        "source_record_id",
        "reference_number",
        "event_type",
        "stage",
        "title",
        "summary",
        "evidence_excerpt",
        "agenda_item_number",
        "meeting_name",
        "governing_body",
        "project_name",
        "address",
        "city",
        "state",
        "postal_code",
        "parcel_id",
        "jurisdiction",
        "applicant_name",
        "owner_name",
        "developer_name",
        "latitude",
        "longitude",
        "meeting_at",
        "published_at",
        "decision_at",
        "source_url",
        "confidence",
    }

    assert "atlanta_ga_legistar_planning_agendas" not in candidates

    production = {
        entry.key: entry for entry in load_catalog()
    }["dallas_tx_legistar_planning_agendas"]
    assert production.record_type == "planning"
    assert production.is_active is True
    assert production.settings["signal_stage"] == "pre_approval"
    assert production.settings["promotion_rights_approved"] is True
    assert production.settings["export_policy"] == (
        "derived_planning_intelligence_only_no_raw_source_or_document_export"
    )


def test_madison_legistar_candidate_preserves_full_planning_lifecycle():
    candidates = {entry.key: entry for entry in load_candidate_catalog()}

    madison = candidates["madison_wi_legistar_plan_commission"]
    assert madison.record_type == "planning"
    assert madison.adapter == "legistar"
    assert madison.status == "legal_hold"
    assert madison.can_run_canary is False
    assert "3 hearing_scheduled and 64 decision_recorded" in madison.notes

    settings = madison.probe_settings
    assert settings is not None
    connector = settings["connector"]
    assert connector["endpoint"] == "https://webapi.legistar.com/v1/madison"
    assert connector["body_names"] == ["PLAN COMMISSION"]
    assert connector["max_events"] == 20
    assert connector["max_items_per_event"] == 200
    assert connector["max_records"] == 250
    assert connector["lookback_days"] == 90
    assert connector["future_days"] == 120
    assert settings["signal_stage"] == "pre_approval_and_approved"
    assert settings["freshness_field"] == "modified_at"
    assert settings["freshness_sla_hours"] == 168

    mappings = {
        mapping.source_field: mapping.canonical_field
        for mapping in madison.probe_field_mappings
    }
    assert mappings["source_record_id"] == "source_record_id"
    assert mappings["reference_number"] == "reference_number"
    assert mappings["stage"] == "stage"
    assert mappings["decision_at"] == "decision_at"
    assert mappings["source_url"] == "source_url"
    assert "bounded commercial storage" in madison.blocker_summary


def test_arapahoe_legistar_candidate_is_current_bounded_and_rights_gated():
    candidates = {entry.key: entry for entry in load_candidate_catalog()}

    arapahoe = candidates["arapahoe_county_co_legistar_planning"]
    assert arapahoe.record_type == "planning"
    assert arapahoe.adapter == "legistar"
    assert arapahoe.status == "legal_hold"
    assert arapahoe.can_run_canary is False
    assert "8 hearing_scheduled and 17 decision_recorded" in arapahoe.notes
    assert "no record lacked a file or matter identity" in arapahoe.notes

    settings = arapahoe.probe_settings
    assert settings is not None
    connector = settings["connector"]
    assert connector["endpoint"] == "https://webapi.legistar.com/v1/arapahoe"
    assert connector["body_names"] == [
        "Planning Commission",
        "Board of Adjustment",
        "East Arapahoe County Advisory Planning Commission",
    ]
    assert connector["event_page_size"] == 10
    assert connector["max_events"] == 20
    assert connector["max_items_per_event"] == 200
    assert connector["max_records"] == 250
    assert connector["lookback_days"] == 120
    assert connector["future_days"] == 120
    assert settings["signal_stage"] == "pre_approval_and_approved"
    assert settings["freshness_field"] == "modified_at"
    assert settings["freshness_sla_hours"] == 168
    assert settings["external_reference_extractors"] == [
        {
            "source_field": "legistar_matter_id",
            "namespace": "legistar:arapahoe:legislation",
            "transform": "scalar",
        }
    ]
    assert "explicit approval" in arapahoe.blocker_summary


def test_maricopa_planning_agenda_candidate_is_bounded_and_commercially_gated():
    candidates = {entry.key: entry for entry in load_candidate_catalog()}

    maricopa = candidates["maricopa_county_az_planning_zoning_agendas"]
    assert maricopa.record_type == "planning"
    assert maricopa.adapter == "planning_documents"
    assert maricopa.status == "legal_hold"
    assert maricopa.can_run_canary is False
    assert "18 project-level hearing records" in maricopa.notes
    assert "zero missing case identities" in maricopa.notes

    settings = maricopa.probe_settings
    assert settings is not None
    connector = settings["connector"]
    assert connector["endpoint"] == (
        "https://www.maricopa.gov/AgendaCenter/Planning-Zoning-Commission-9"
    )
    assert connector["document_allowed_hosts"] == ["www.maricopa.gov"]
    assert connector["max_index_pages"] == 1
    assert connector["max_documents"] == 12
    assert connector["max_document_bytes"] == 1024 * 1024
    assert connector["max_items_per_document"] == 50
    assert connector["max_item_characters"] == 10_000
    assert connector["max_records"] == 250
    assert connector["stages"] == {"agenda": "hearing_scheduled"}
    assert settings["signal_stage"] == "pre_approval"
    assert settings["external_reference_extractors"] == [
        {
            "source_field": "reference_number",
            "namespace": "maricopa:planning_case",
            "transform": "scalar",
        }
    ]

    item_pattern = re.compile(connector["item_pattern"], re.IGNORECASE | re.MULTILINE)
    file_pattern = re.compile(connector["file_pattern"], re.IGNORECASE | re.MULTILINE)
    sample = "4.\nCPA260007 and Z260018 Staff Report"
    assert item_pattern.search(sample).group("item_number") == "4."
    assert [match.group("file_number") for match in file_pattern.finditer(sample)] == [
        "CPA260007",
        "Z260018",
    ]
    assert "commercial-purpose" in maricopa.blocker_summary


def test_jacksonville_planning_candidate_is_bounded_suppressed_and_rights_gated():
    candidates = {entry.key: entry for entry in load_candidate_catalog()}

    jacksonville = candidates["jacksonville_fl_planning_commission_agendas"]
    assert jacksonville.record_type == "planning"
    assert jacksonville.adapter == "planning_documents"
    assert jacksonville.status == "legal_hold"
    assert jacksonville.can_run_canary is False
    assert "19 hearing_scheduled and 19 decision_recorded" in jacksonville.notes
    assert "zero retained owner or agent lines" in jacksonville.notes

    settings = jacksonville.probe_settings
    assert settings is not None
    connector = settings["connector"]
    assert connector["document_allowed_hosts"] == ["www.jacksonville.gov"]
    assert connector["document_type_patterns"] == {
        "minutes": "Results Agenda",
        "agenda": "Meeting Agenda",
    }
    assert connector["suppression_patterns"] == ["^Owner[(]s[)]:.*$"]
    assert connector["max_index_pages"] == 1
    assert connector["max_documents"] == 2
    assert connector["max_document_bytes"] == 1024 * 1024
    assert connector["max_items_per_document"] == 100
    assert connector["max_item_characters"] == 20_000
    assert connector["max_records"] == 200
    assert connector["stages"] == {
        "agenda": "hearing_scheduled",
        "minutes": "decision_recorded",
    }
    assert settings["signal_stage"] == "pre_approval_and_approved"
    assert settings["external_reference_extractors"] == [
        {
            "source_field": "reference_number",
            "namespace": "jacksonville:planning_case",
            "transform": "scalar",
        }
    ]

    item_pattern = re.compile(connector["item_pattern"], re.IGNORECASE | re.MULTILINE)
    file_pattern = re.compile(connector["file_pattern"], re.IGNORECASE | re.MULTILINE)
    sample = "Ex-Parte 2. 2026-0554 (Companion 2026-0553)\nCouncil District-2"
    assert item_pattern.search(sample).group("item_number") == "2"
    assert [match.group("file_number") for match in file_pattern.finditer(sample)] == [
        "2026-0554",
        "2026-0553",
    ]
    assert "explicit approval" in jacksonville.blocker_summary


def test_hillsborough_legistar_candidate_is_current_bounded_and_rights_gated():
    candidates = {entry.key: entry for entry in load_candidate_catalog()}

    hillsborough = candidates["hillsborough_county_fl_legistar_land_use"]
    assert hillsborough.record_type == "planning"
    assert hillsborough.adapter == "legistar"
    assert hillsborough.status == "legal_hold"
    assert hillsborough.can_run_canary is False
    assert "330 decision-backed planning records" in hillsborough.notes
    assert "zero email or phone contacts" in hillsborough.notes
    assert "McDonald's" in hillsborough.notes

    settings = hillsborough.probe_settings
    assert settings is not None
    connector = settings["connector"]
    assert connector["endpoint"] == "https://webapi.legistar.com/v1/hillsboroughcounty"
    assert connector["body_names"] == [
        "BOCC Land Use",
        "Zoning Hearing Master",
        "Land Use Hearing Officer",
    ]
    assert connector["record_stages"] == ["decision_recorded"]
    assert len(connector["suppression_patterns"]) == 2
    assert connector["event_page_size"] == 10
    assert connector["max_events"] == 30
    assert connector["max_items_per_event"] == 250
    assert connector["max_records"] == 500
    assert connector["lookback_days"] == 120
    assert connector["future_days"] == 120
    assert settings["signal_stage"] == "pre_approval_and_approved"
    assert settings["freshness_field"] == "modified_at"
    assert settings["external_reference_extractors"] == [
        {
            "source_field": "legistar_matter_id",
            "namespace": "legistar:hillsboroughcounty:legislation",
            "transform": "scalar",
        },
        {
            "source_field": "reference_number",
            "namespace": "hillsborough:land_use_case",
            "transform": "scalar",
        },
    ]
    assert "public applicant/entity retention" in hillsborough.blocker_summary


def test_mesquite_planning_candidate_is_current_bounded_and_rights_gated():
    candidates = {entry.key: entry for entry in load_candidate_catalog()}

    mesquite = candidates["mesquite_tx_planning_zoning_agendas"]
    assert mesquite.record_type == "planning"
    assert mesquite.adapter == "planning_documents"
    assert mesquite.status == "legal_hold"
    assert mesquite.can_run_canary is False
    assert "21 pre-approval zoning-hearing records" in mesquite.notes
    assert "zero missing case identities" in mesquite.notes
    assert "Chick-fil-A" in mesquite.notes
    assert "BJ's Wholesale" in mesquite.notes

    settings = mesquite.probe_settings
    assert settings is not None
    connector = settings["connector"]
    assert connector["endpoint"].endswith("/Planning-Zoning-Commission-18/")
    assert connector["document_allowed_hosts"] == ["www.cityofmesquite.com"]
    assert connector["max_index_pages"] == 1
    assert connector["max_documents"] == 12
    assert connector["max_document_bytes"] == 1024 * 1024
    assert connector["max_items_per_document"] == 50
    assert connector["max_records"] == 250
    assert len(connector["suppression_patterns"]) == 2
    assert connector["stages"] == {"agenda": "hearing_scheduled"}
    assert settings["signal_stage"] == "pre_approval"
    assert settings["freshness_sla_hours"] == 504
    assert settings["external_reference_extractors"] == [
        {
            "source_field": "reference_number",
            "namespace": "mesquite:planning_case",
            "transform": "scalar",
        }
    ]

    item_pattern = re.compile(connector["item_pattern"], re.IGNORECASE | re.MULTILINE)
    file_pattern = re.compile(connector["file_pattern"], re.IGNORECASE | re.MULTILINE)
    sample = "4. ZONING APPLICATION NO. Z0626-0458"
    assert item_pattern.search(sample).group("item_number") == "4"
    assert file_pattern.search(sample).group("file_number") == "Z0626-0458"
    assert "explicit City approval" in mesquite.blocker_summary


def test_port_st_lucie_legistar_candidate_has_exact_project_identity_and_rights_gate():
    candidates = {entry.key: entry for entry in load_candidate_catalog()}

    psl = candidates["port_st_lucie_fl_legistar_planning"]
    assert psl.record_type == "planning"
    assert psl.adapter == "legistar"
    assert psl.status == "legal_hold"
    assert psl.can_run_canary is False
    assert "31 project hearing records" in psl.notes
    assert "7 hearing_scheduled and 24 decision_recorded" in psl.notes
    assert "Pollo Tropical" in psl.notes
    assert "Dollar Tree" in psl.notes

    settings = psl.probe_settings
    assert settings is not None
    connector = settings["connector"]
    assert connector["endpoint"] == "https://webapi.legistar.com/v1/psl"
    assert connector["body_names"] == ["Planning and Zoning Board"]
    assert connector["matter_types"] == [
        "Public Hearing",
        "Public Hearing - Quasi Judicial",
    ]
    assert len(connector["suppression_patterns"]) == 2
    assert connector["max_events"] == 20
    assert connector["max_records"] == 300
    assert connector["lookback_days"] == 120
    assert connector["future_days"] == 120
    assert settings["signal_stage"] == "pre_approval_and_approved"
    assert settings["freshness_field"] == "modified_at"
    assert settings["external_reference_extractors"] == [
        {
            "source_field": "legistar_matter_id",
            "namespace": "legistar:psl:legislation",
            "transform": "scalar",
        },
        {
            "source_field": "reference_number",
            "namespace": "legistar:psl:file",
            "transform": "scalar",
        },
        {
            "source_field": "title",
            "namespace": "psl:planning_project",
            "transform": "regex_extract",
            "pattern": r"\b(P[0-9]{2}-[0-9]{3}(?:-A[0-9]+)?)\b",
            "group": 1,
        },
    ]
    assert "explicit City approval" in psl.blocker_summary
