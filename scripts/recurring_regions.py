"""Verified, bounded refresh of explicitly reviewed regional public feeds."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import text

from app.db import SessionLocal
from app.models.ingestion import IngestionSource, PermitRecord
from app.models.organization import Organization
from app.models.planning import PlanningRecord
from app.schemas.ingestion import IngestionSourceUpdate
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

# Only reviewed production entries. Date fields retain their source event meaning.
SOURCES = {
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
}


def regional_entry(key: str, *, now: datetime | None = None):
    field, event = SOURCES[key]
    entry = next(row for row in load_catalog() if row.key == key).model_copy(deep=True)
    if not entry.is_active or not entry.settings.get("rights_basis") or entry.record_type not in {"permit", "planning"}:
        raise ValueError("Feed lacks reviewed active permit scope")
    today = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).date()
    days = 7 if event == "sales_tax_registration" else 31
    start, end = today - timedelta(days=days - 1), today + timedelta(days=1)
    connector = entry.settings["connector"]
    if entry.adapter == "arcgis":
        predicate = connector.get("where", "1=1")
        if key == "savannah_ga_commercial_building_permits":
            # Official schema: IssuedDate is text, observed as MM/DD/YYYY.
            dates = ",".join("'" + (start + timedelta(days=day)).strftime("%m/%d/%Y") + "'" for day in range(31))
            connector["where"] = f"({predicate}) AND IssuedDate IN ({dates})"
        else:
            connector["where"] = f"({predicate}) AND {field} >= TIMESTAMP '{start} 00:00:00' AND {field} < TIMESTAMP '{end} 00:00:00'"
    elif entry.adapter == "socrata":
        query = connector.setdefault("query", {})
        query["$where"] = f"({query.get('$where', '1=1')}) AND {field} >= '{start}T00:00:00' AND {field} < '{end}T00:00:00'"
    elif entry.adapter in {"rss", "civicplus_newsflash", "legistar"} and field is None:
        connector["max_records"] = min(connector.get("max_records", 100), 100)
        if entry.adapter == "legistar":
            connector.update(max_events=5, max_items_per_event=150, max_records=250)
    else:
        raise ValueError("Regional worker supports reviewed ArcGIS/Socrata feeds only")
    connector.update(page_size=250, timeout=30, max_retries=1)
    entry.settings.update(schedule_mode="manual", reconciliation_mode="incremental",
                          rolling_window_days=days if field else None, regional_event_kind=event)
    return entry


def count_source(entry):
    client = RetryingHttpClient(timeout=30, max_retries=1)
    config = entry.settings["connector"]
    if entry.adapter not in {"arcgis", "socrata"}:
        return None  # Archive connectors have no authoritative count endpoint.
    if entry.adapter == "arcgis":
        result = client.get_json(entry.base_url, params={"f": "json", "where": config["where"],
                                 "returnCountOnly": "true", "returnGeometry": "false"})
        count = result.get("count") if isinstance(result, dict) else None
    else:
        result = client.get_json(entry.base_url, params={"$select": "count(*) AS count", "$where": config["query"]["$where"]})
        count = int(result[0]["count"]) if isinstance(result, list) and len(result) == 1 else None
    if type(count) is not int or count < 0:
        raise ValueError("Invalid provider count")
    return count


def verify(entry):
    count = count_source(entry)
    if count is not None and not 0 < count <= 1000:
        raise ValueError("Recent scope is empty or exceeds the 1000-record budget")
    source = SimpleNamespace(**entry.model_dump(exclude={"field_mappings"}), id="verification",
                             field_mappings=entry.field_mappings)
    result = validate_source_canary(source, sample_size=10)
    if not result.ok or result.records_valid == 0:
        raise ValueError("Canary failed: " + "; ".join(result.errors))
    return count, {"source_key": entry.key, "provider_count": count, "sample_valid": result.records_valid,
                   "sample_failed": result.records_failed, "event_kind": entry.settings["regional_event_kind"]}


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
                        if source.base_url != entry.base_url or source.record_type != entry.record_type:
                            raise ValueError("Existing source identity differs")
                        update_source(db, source, IngestionSourceUpdate(settings=entry.settings, field_mappings=entry.field_mappings, is_active=True))
                    else:
                        source = create_source(db, entry)
                    db.commit()
                    run = execute_source_run(db, source, max_pages=4, trigger="scheduled")
                    after = count_source(entry)
                    passed = run.status == "completed" and not run.records_failed and not run.checkpoint and (
                        before is None or before == after == run.records_seen)
                    if not passed:
                        run.status = "partial_with_errors"
                        run.error_message = "Regional refresh did not reconcile; source quarantined"
                        source.is_active = False
                        db.commit()
                    model = PlanningRecord if entry.record_type == "planning" else PermitRecord
                    receipt.update(status=run.status, run_id=run.id, seen=run.records_seen,
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
