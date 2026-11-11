"""Verified, bounded refresh of explicitly reviewed regional public feeds."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import urlparse

from sqlalchemy import text

from app.db import SessionLocal
from app.models.ingestion import IngestionRun, IngestionSource, PermitRecord
from app.models.organization import Organization
from app.models.planning import PlanningRecord
from app.schemas.ingestion import FieldMappingCreate, IngestionSourceCreate, IngestionSourceUpdate
from app.services.demo_access import DEMO_ORG_ID
from app.services.ingestion.catalog import load_catalog
from app.services.ingestion.connectors.base import RetryingHttpClient
from app.services.ingestion.health import validate_source_canary
from app.services.ingestion.service import create_source, execute_source_run, update_source
from app.utils.org_scope import (
    SYSTEM_USER_ID,
    RequestContext,
    reset_current_context,
    set_current_context,
)

MAX_RECORDS_PER_RUN = 100_000
PAGE_SIZE = 250
# One extra page establishes exhaustion when the final data page is full.
MAX_PAGES_PER_RUN = MAX_RECORDS_PER_RUN // PAGE_SIZE + 1

# Only reviewed production entries. Date fields retain their source event meaning.
SOURCES = {
    "san_francisco_ca_building_permits_primary_address": ("data_loaded_at", "publisher_row_update_not_new_filing"),
    "ocala_fl_gis_new_building_projects": (None, "curated_project_context"),
    "bend_or_permit_applications_point": ("ApplicationDate", "application_or_update"),
    "detroit_mi_bseed_building_plan_reviews": ("submitted_date", "application_or_status_change"),
    "cary_nc_development_applications": ("ApplicationDate", "application_or_action"),
    "raleigh_nc_development_plans": ("submitted", "application_or_update"),
    "tacoma_wa_commercial_permit_lifecycle": ("application_date", "application"),
    "seattle_wa_land_use_permits": ("applieddate", "application"),
    "cincinnati_oh_building_permits": ("applieddate", "application"),
    "fort_worth_tx_civic_commercial_permits": ("File_Date", "application"),
    "arlington_tx_commercial_permit_applications": ("InDate", "application"),
    "arlington_tx_commercial_issued_permits": ("ISSUEDATE", "issuance"),
    "florida_dep_erp_applications_commercial_context": ("RCVD_DATE", "environmental_application"),
    "miami_dade_fl_wasd_unincorporated_permits_narrow": ("BLDPRCISDT", "permit_process"),
    "orlando_fl_permit_applications": ("processed_date", "application_processed"),
    "mesa_az_commercial_permit_submittals": ("submittal_date", "submittal_or_resubmittal"),
    "tempe_az_building_permits_commercial_context": ("StatusDateDtm", "status_change"),
    "savannah_ga_commercial_building_permits": ("IssuedDate", "issuance_only"),
    "texas_comptroller_sales_tax_locations": ("permit_date", "sales_tax_registration"),
    "dallas_tx_legistar_planning_agendas": (None, "planning_meeting"),
    "san_marcos_tx_planning_application_notices": (None, "planning_notice"),
    "taylor_tx_development_notices": (None, "development_notice"),
    "austin_tx_site_plan_cases": ("application_start_date", "site_plan_application"),
}

OCALA_CONTEXT_KEY = "ocala_fl_gis_new_building_projects"
CONTEXT_RECORD_LIMIT = 1000
SF_BUILDING_KEY = "san_francisco_ca_building_permits_primary_address"
SF_BUILDING_FIELDS = (
    "record_id", "permit_number", "primary_address_flag", "data_as_of", "data_loaded_at",
    "permit_type_definition", "application_submission_method", "proposed_occupancy",
    "proposed_use", "status", "status_date", "description", "street_number",
    "street_number_suffix", "street_name", "street_suffix", "unit", "unit_suffix",
    "zipcode", "block", "lot", "revised_cost", "estimated_cost", "proposed_units",
    "permit_creation_date", "approved_date", "issued_date", "completed_date",
)


class ContextConnectorGuard:
    """Reject an unsafe page before the persistence service can see any row."""

    def __init__(self, connector):
        self.connector = connector
        self.identities = set()

    def fetch_page(self, checkpoint=None):
        page = self.connector.fetch_page(checkpoint)
        identities = set(self.identities)
        allowed = {"OBJECTID", "PermitNo", "Applied", "Subtype", "Status", "APN", "Issued", "Expired", "centroid"}
        for row in page.records:
            identity = row.get("PermitNo")
            centroid = row.get("centroid") or {}
            sr = centroid.get("spatialReference") or page.metadata.get("spatial_reference") or {}
            x, y = centroid.get("x"), centroid.get("y")
            if (set(row) - allowed or not isinstance(identity, str) or not identity.strip()
                    or identity in identities or sr.get("wkid") != 4326
                    or type(x) not in {int, float} or type(y) not in {int, float}
                    or not math.isfinite(x) or not math.isfinite(y)
                    or not -90 <= x <= -75 or not 20 <= y <= 35):
                raise ValueError("Ocala context page failed identity, privacy or coordinate validation")
            identities.add(identity)
        if len(identities) > CONTEXT_RECORD_LIMIT:
            raise ValueError("Ocala context exceeds reviewed record ceiling")
        self.identities = identities
        return page


@contextmanager
def context_connector_guard(source):
    # Workers execute one source in one process. Scope the factory override and
    # restore it even on failure; other source profiles never use this wrapper.
    from app.services.ingestion import service

    original = service.build_connector
    if source.key != OCALA_CONTEXT_KEY:
        yield
        return

    def guarded(adapter, config):
        if adapter != "arcgis" or config.get("endpoint") != source.base_url:
            raise ValueError("Unexpected context connector identity")
        return ContextConnectorGuard(original(adapter, config))

    service.build_connector = guarded
    try:
        yield
    finally:
        service.build_connector = original


def ocala_context_entry():
    """Versioned worker scope; delivered with this script, not a new API release."""
    fields = {
        "PermitNo": "permit_number", "Applied": "filed_at",
        "Subtype": "permit_subtype", "Status": "status", "APN": "parcel_id",
        "Issued": "issued_at", "Expired": "expires_at",
    }
    mappings = [FieldMappingCreate(source_field=k, canonical_field=v,
                                  is_required=k == "PermitNo") for k, v in fields.items()]
    mappings.append(FieldMappingCreate(source_field="__source_record_id", canonical_field="source_record_id",
                    transform="join_fields", transform_options={"fields": ["PermitNo"]}, is_required=True))
    for axis, canonical in (("x", "longitude"), ("y", "latitude")):
        mappings.append(FieldMappingCreate(source_field="__" + canonical, canonical_field=canonical,
                        transform="object_path", transform_options={"source_field": "centroid", "path": [axis]}))
    url = "https://gis.ocalafl.org/arcgis/rest/services/Public/GrowthManagement/FeatureServer/19"
    return IngestionSourceCreate(
        key=OCALA_CONTEXT_KEY, name="Ocala GIS building projects (context; publisher currentness unknown)",
        adapter="arcgis", record_type="permit", jurisdiction="Ocala, FL", base_url=url,
        is_active=True, field_mappings=mappings,
        settings={
            "rights_basis": "BuildSignals owner authorized narrow public-data context ingestion on 2026-11-09; publisher commercial license not independently verified. No contact fields or hosted-model transmission authorized by this scope.",
            "license": "Public City GIS; publisher reuse terms unverified",
            "attribution_required": True, "attribution": "City of Ocala Planning Department",
            "official_landing_page": url, "context_only": True,
            "publisher_currentness": "unknown", "signal_stage": "curated_project_context",
            "freshness_semantics": "ingestion_observed_at", "collection_sla_hours": 36,
            "export_policy": "derived_context_only_no_raw_bulk_resale",
            "coordinate_semantics": "project_polygon_centroid_not_verified_parcel",
            "defaults": {"city": "Ocala", "state": "FL", "jurisdiction": "Ocala, FL", "source_url": url},
            "canary_required_fields": ["PermitNo", "centroid"],
            "connector": {"where": "1=1", "out_fields": "OBJECTID,PermitNo,Applied,Subtype,Status,APN,Issued,Expired",
                          "keyset_field": "OBJECTID", "order_by_fields": "OBJECTID ASC",
                          "include_geometry": False, "include_centroid": True, "query": {"outSR": 4326}},
        },
    )

UPDATE_WINDOW_FIELDS = {
    "bend_or_permit_applications_point": "LASTUPDATE",
    "detroit_mi_bseed_building_plan_reviews": "task_status_date",
    "cary_nc_development_applications": "ActionDate",
    "raleigh_nc_development_plans": "updated",
}


def regional_entry(key: str, *, now: datetime | None = None):
    field, event = SOURCES[key]
    entry = (ocala_context_entry() if key == OCALA_CONTEXT_KEY else
             next(row for row in load_catalog() if row.key == key).model_copy(deep=True))
    if key == "austin_tx_site_plan_cases" and entry.settings.get("license") == "Public Domain":
        # Official dataset metadata /api/views/mavg-96ck.json: PUBLIC_DOMAIN,
        # verified 2026-10-16. Retain the catalog's reviewed field/suppression scope.
        entry.settings["rights_basis"] = "City of Austin Site Plan Cases official metadata declares PUBLIC_DOMAIN; attributed derived intelligence within existing field allowlist and suppression scope."
    if key == SF_BUILDING_KEY:
        if (entry.base_url != "https://data.sf.gov/resource/i98e-djp9.json"
                or entry.settings.get("license") != "Open Data Commons Public Domain Dedication and License"):
            raise ValueError("SF profile requires the reviewed canonical PDDL source contract")
        # Canonical publisher metadata declares PDDL, verified 2026-11-10 PST.
        # The rolling window captures changed rows, not just newly filed permits.
        entry.settings.update(
            rights_basis="San Francisco DBI Building Permits official dataset i98e-djp9 declares PDDL. This reviewed profile retains attributed permit, address, parcel-reference and lifecycle context only; no contact fields or source-replacement export.",
            attribution_required=True,
            freshness_semantics="record_updated_at",
            field_allowlist=list(SF_BUILDING_FIELDS),
            export_policy="derived_development_context_no_raw_source_replacement_export",
        )
        entry.settings["connector"]["query"]["$select"] = ",".join(SF_BUILDING_FIELDS)
    if not entry.is_active or not entry.settings.get("rights_basis") or entry.record_type not in {"permit", "planning"}:
        raise ValueError("Feed lacks reviewed active permit scope")
    today = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).date()
    days = 7 if event == "sales_tax_registration" else 31
    start, end = today - timedelta(days=days - 1), today + timedelta(days=1)
    connector = entry.settings["connector"]
    if key == OCALA_CONTEXT_KEY:
        pass  # A curated context inventory is not a rolling application feed.
    elif entry.adapter == "arcgis":
        predicate = connector.get("where", "1=1")
        if key == "savannah_ga_commercial_building_permits":
            # Official schema: IssuedDate is text, observed as MM/DD/YYYY.
            dates = ",".join("'" + (start + timedelta(days=day)).strftime("%m/%d/%Y") + "'" for day in range(31))
            connector["where"] = f"({predicate}) AND IssuedDate IN ({dates})"
        elif key in UPDATE_WINDOW_FIELDS:
            fields = (field, UPDATE_WINDOW_FIELDS[key])
            def window(name):
                if key == "detroit_mi_bseed_building_plan_reviews":
                    return f"({name} >= DATE '{start}' AND {name} < DATE '{end}')"
                return f"({name} >= TIMESTAMP '{start} 00:00:00' AND {name} < TIMESTAMP '{end} 00:00:00')"
            connector["where"] = f"({predicate}) AND (" + " OR ".join(window(name) for name in fields) + ")"
            entry.settings["regional_window_fields"] = list(fields)
        else:
            connector["where"] = f"({predicate}) AND {field} >= TIMESTAMP '{start} 00:00:00' AND {field} < TIMESTAMP '{end} 00:00:00'"
        if key == "bend_or_permit_applications_point":
            connector.update(keyset_field="OBJECTID", order_by_fields="OBJECTID ASC")
    elif entry.adapter == "socrata":
        query = connector.setdefault("query", {})
        query["$where"] = f"({query.get('$where', '1=1')}) AND {field} >= '{start}T00:00:00' AND {field} < '{end}T00:00:00'"
        if key == "cincinnati_oh_building_permits":
            connector["order_by"] = "applieddate DESC, :id ASC"
    elif entry.adapter in {"rss", "civicplus_newsflash", "legistar"} and field is None:
        connector["max_records"] = min(connector.get("max_records", 100), 100)
        if entry.adapter == "legistar":
            connector.update(max_events=5, max_items_per_event=150, max_records=250)
    else:
        raise ValueError("Regional worker supports reviewed ArcGIS/Socrata feeds only")
    connector.update(page_size=PAGE_SIZE, timeout=30, max_retries=1)
    entry.settings.update(schedule_mode="manual", reconciliation_mode="incremental",
                          rolling_window_days=days if field else None, regional_event_kind=event)
    return entry


def count_source(entry):
    client = RetryingHttpClient(timeout=30, max_retries=1,
                               allowed_hosts=frozenset({urlparse(entry.base_url).hostname}))
    config = entry.settings["connector"]
    if entry.adapter not in {"arcgis", "socrata"}:
        return None  # Archive connectors have no authoritative count endpoint.
    if entry.adapter == "arcgis":
        endpoint = entry.base_url.rstrip("/")
        if not endpoint.lower().endswith("/query"):
            endpoint += "/query"
        result = client.get_json(endpoint, params={"f": "json", "where": config["where"],
                                 "returnCountOnly": "true", "returnGeometry": "false"})
        if isinstance(result, dict) and isinstance(result.get("error"), dict):
            code = result["error"].get("code")
            if code in (498, 499):
                raise ValueError("ArcGIS source requires authorized credentials")
            raise ValueError("ArcGIS provider returned an error instead of a count")
        count = result.get("count") if isinstance(result, dict) else None
    else:
        result = client.get_json(entry.base_url, params={"$select": "count(*) AS count", "$where": config["query"]["$where"]})
        count = int(result[0]["count"]) if isinstance(result, list) and len(result) == 1 else None
    if type(count) is not int or count < 0:
        raise ValueError("Invalid provider count")
    return count


def verify(entry):
    count = count_source(entry)
    limit = CONTEXT_RECORD_LIMIT if entry.key == OCALA_CONTEXT_KEY else MAX_RECORDS_PER_RUN
    if count is not None and not 0 < count <= limit:
        raise ValueError(f"Scope is empty or exceeds the {limit}-record budget")
    source = SimpleNamespace(**entry.model_dump(exclude={"field_mappings"}), id="verification",
                             field_mappings=entry.field_mappings)
    result = validate_source_canary(source, sample_size=10)
    if not result.ok or result.records_valid == 0:
        raise ValueError("Canary failed: " + "; ".join(result.errors))
    return count, {"source_key": entry.key, "provider_count": count, "sample_valid": result.records_valid,
                   "sample_failed": result.records_failed, "event_kind": entry.settings["regional_event_kind"]}


def ensure_reactivatable(source, entry):
    """Guard an existing regional source before a scheduled rerun.

    Identity must match, and a source quarantined by a prior failed reconciliation
    (``is_active`` False) must not be silently re-enabled by the next scheduled
    run; it requires an explicit recovery/verification decision first.
    """
    if source.base_url != entry.base_url or source.record_type != entry.record_type:
        raise ValueError("Existing source identity differs")
    if not source.is_active:
        raise RuntimeError("Source is quarantined after a failed run; explicit recovery required")


def run_reconciled(run, before, after):
    # Completed keyset feeds can retain a valid cursor even on their final page.
    return run.status == "completed" and not run.records_failed and (
        before is None or before == after == run.records_seen)


def execute_regional_refresh(db, source):
    """Resume bounded chunks without exceeding the shared 100-page call limit."""
    checkpoint = None
    remaining = (CONTEXT_RECORD_LIMIT // PAGE_SIZE + 1 if source.key == OCALA_CONTEXT_KEY
                 else MAX_PAGES_PER_RUN)
    totals = dict(records_seen=0, records_inserted=0, records_updated=0, records_failed=0)
    run_ids = []
    while remaining:
        pages = min(100, remaining)
        run = execute_source_run(db, source, max_pages=pages,
                                 checkpoint=checkpoint, trigger="scheduled")
        run_ids.append(run.id)
        for key in totals:
            totals[key] += getattr(run, key)
        remaining -= pages
        if (run.status != "partial" or run.records_failed
                or not run.checkpoint or run.checkpoint == checkpoint
                or not run.records_seen or totals["records_seen"] > MAX_RECORDS_PER_RUN):
            break
        checkpoint = run.checkpoint
    return SimpleNamespace(id=run.id, status=run.status, error_message=run.error_message,
                           checkpoint=run.checkpoint, run_ids=run_ids, **totals)


def reconcile_after_refresh(entry, run, before):
    try:
        after = count_source(entry)
    except Exception:
        run.error_message = "Post-refresh provider count unavailable; reconciliation failed"
        return None, False
    return after, run_reconciled(run, before, after)


def refresh(key: str, organization_id: str):
    if not organization_id or organization_id == DEMO_ORG_ID:
        raise ValueError("Explicit non-demo organization required")
    entry = regional_entry(key)
    before, receipt = verify(entry)
    token = set_current_context(RequestContext(organization_id, SYSTEM_USER_ID))
    try:
        with SessionLocal() as db:
            org = db.get(Organization, organization_id)
            if org is None or not org.is_active:
                raise ValueError("Active destination not found")
            with db.get_bind().connect() as lease:
                lock_id = int.from_bytes(hashlib.sha256((organization_id + key).encode()).digest()[:8], "big", signed=True)
                locked = lease.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_id})
                if not locked:
                    raise RuntimeError("Source refresh already running")
                source = None
                try:
                    source = db.query(IngestionSource).filter_by(organization_id=organization_id, key=key).one_or_none()
                    if source:
                        ensure_reactivatable(source, entry)
                        update_source(db, source, IngestionSourceUpdate(settings=entry.settings, field_mappings=entry.field_mappings))
                    else:
                        source = create_source(db, entry)
                    db.commit()
                    with context_connector_guard(source):
                        run = execute_regional_refresh(db, source)
                    after, passed = reconcile_after_refresh(entry, run, before)
                    if not passed:
                        run.status = "partial_with_errors"
                        run.error_message = run.error_message or "Regional refresh did not reconcile; source quarantined"
                        persisted_run = db.get(IngestionRun, run.id)
                        persisted_run.status = run.status
                        persisted_run.error_message = run.error_message
                        source.is_active = False
                        db.commit()
                    model = PlanningRecord if entry.record_type == "planning" else PermitRecord
                    receipt.update(status=run.status, run_id=run.id, run_ids=run.run_ids, seen=run.records_seen,
                                   inserted=run.records_inserted, updated=run.records_updated, failed=run.records_failed,
                                   provider_after=after, stored=db.query(model).filter_by(organization_id=organization_id, source_id=source.id).count())
                    print(json.dumps(receipt), flush=True)
                    if not passed:
                        raise RuntimeError("Regional refresh failed verification")
                finally:
                    lease.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_id})
    finally:
        reset_current_context(token)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-key", required=True, choices=sorted(SOURCES))
    parser.add_argument("--organization-id")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    try:
        if args.verify:
            print(json.dumps({**verify(regional_entry(args.source_key))[1], "status": "verified"}), flush=True)
        else:
            refresh(args.source_key, args.organization_id)
    except Exception as exc:
        print(json.dumps({"source_key": args.source_key, "status": "failed", "error_type": type(exc).__name__,
                          "reason": str(exc)[:500] if args.verify else "Inspect source run and worker logs"}), flush=True)
        raise SystemExit(1) from None
