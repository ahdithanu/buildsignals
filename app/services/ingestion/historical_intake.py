"""Bounded Columbus qualification imports into a new, local-only database."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, func
from sqlalchemy.orm import Session

from app.db import Base
from app.models.ingestion import PermitRecord
from app.models.organization import Organization
from app.services.ingestion.catalog import load_catalog
from app.services.ingestion.connectors.base import ConnectorError, RetryingHttpClient
from app.services.ingestion.measured_coverage import measured_coverage
from app.services.ingestion.service import create_source, execute_source_run
from app.utils.org_scope import (
    SYSTEM_USER_ID,
    RequestContext,
    get_org_id,
    reset_current_context,
    set_current_context,
)

SOURCE_FIELDS = {
    "columbus_oh_site_engineering_applications": "B1_FILE_DD",
    "columbus_oh_commercial_building_permits": "ISSUED_DT",
}


def historical_entry(source_key: str, start: date, end: date):
    if source_key not in SOURCE_FIELDS:
        raise ValueError("Source has not been qualified for this local intake")
    if not 1 <= (end - start).days <= 31 or end > datetime.now(timezone.utc).date():
        raise ValueError("Choose a completed interval of 1 to 31 days")
    entry = next(e for e in load_catalog() if e.key == source_key).model_copy(deep=True)
    settings = entry.settings
    connector = settings["connector"]
    predicate = connector["where"]
    if source_key == "columbus_oh_commercial_building_permits":
        suffix = " AND ISSUED_YEAR >= 2025"
        if not predicate.endswith(suffix):
            raise ValueError("Commercial scope changed; historical scope needs review")
        predicate = predicate.removesuffix(suffix)
    field = SOURCE_FIELDS[source_key]
    connector["where"] = (
        f"({predicate}) AND {field} >= TIMESTAMP '{start.isoformat()} 00:00:00'"
        f" AND {field} < TIMESTAMP '{end.isoformat()} 00:00:00'"
    )
    connector["page_size"] = 250
    settings["schedule_mode"] = "manual"
    settings["reconciliation_mode"] = "periodic_full"
    settings["historical_qualification"] = {
        "start_inclusive": start.isoformat(), "end_exclusive": end.isoformat(),
        "date_field": field, "coverage_verified": False,
    }
    return entry


def provider_count(entry, client):
    payload = client.get_json(entry.base_url, params={
        "f": "json", "where": entry.settings["connector"]["where"],
        "returnCountOnly": "true", "returnGeometry": "false",
    })
    count = payload.get("count") if isinstance(payload, dict) else None
    if type(count) is not int or count < 0 or "error" in payload:
        raise ValueError("Provider did not return a valid count")
    return count


def run_local_intake(database: Path, entry, *, max_pages: int = 4):
    if not 1 <= max_pages <= 4:
        raise ValueError("Local qualification is limited to 1-4 pages (1000 rows)")
    database = database.resolve()
    # Exclusive creation prevents overwriting any existing application database.
    with database.open("xb"):
        pass
    engine = create_engine("sqlite:///" + str(database))
    token = set_current_context(RequestContext(str(uuid4()), SYSTEM_USER_ID))
    try:
        Base.metadata.create_all(engine)
        client = RetryingHttpClient(timeout=30, max_retries=1)
        started = datetime.now(timezone.utc).isoformat()
        before = provider_count(entry, client)
        with Session(engine) as db:
            db.add(Organization(id=get_org_id(), name="Historical qualification", slug="qualification"))
            db.commit()
            source = create_source(db, entry)
            db.commit()
            run = execute_source_run(db, source, max_pages=max_pages, trigger="manual")
            result = {
                "source_key": entry.key, "run_id": run.id, "status": run.status,
                "records_seen": run.records_seen, "records_inserted": run.records_inserted,
                "records_failed": run.records_failed, "checkpoint": run.checkpoint,
            }
            coverage = measured_coverage(db, record_type="permit")
            source_coverage = next(item for item in coverage["sources"] if item["source_id"] == source.id)
            geocoded = sum(row["geocoded_records"] for row in source_coverage["observed_states"])
            permits = db.query(PermitRecord).filter_by(
                organization_id=get_org_id(), source_id=source.id,
            )
            parcel_references = permits.filter(
                func.length(func.trim(PermitRecord.parcel_id)) > 0,
            ).count()
            result["workflow_readiness"] = {
                "stored_permits": source_coverage["stored_records"],
                "geocoded_permits": geocoded,
                "permits_with_parcel_reference": parcel_references,
                "permits_without_coordinates": source_coverage["stored_records"] - geocoded,
                "nearby_search_ready": False,
                "reason": "Coordinates alone do not verify parcel-provider coverage or ranked candidates. "
                "Parcel references are not joined parcel facts or for-sale listings.",
            }
        count_error = None
        try:
            after = provider_count(entry, client)
        except (ConnectorError, ValueError) as exc:
            # Keep the completed import auditable even if the final check fails.
            after = None
            count_error = type(exc).__name__
        scope = entry.model_dump(mode="json")
        return {
            **result, "started_at": started,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "database": str(database), "provider_count_before": before,
            "provider_count_after": after,
            "provider_count_error": count_error,
            "count_reconciled": (
                result["status"] == "completed" and result["records_failed"] == 0
                and before == after == result["records_seen"] == result["records_inserted"]
            ),
            "coverage_verified": False,
            "limitations": "Counts are not a frozen snapshot or proof of historical completeness. "
            "Current source values were captured now, not known at their historical event dates.",
            "scope": scope,
            "scope_sha256": hashlib.sha256(
                json.dumps(scope, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
        }
    finally:
        reset_current_context(token)
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-key", choices=SOURCE_FIELDS, required=True)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--max-pages", type=int, default=4)
    args = parser.parse_args()
    entry = historical_entry(args.source_key, args.start, args.end)
    report = args.database.resolve().with_suffix(".qualification.json")
    if report.exists():
        parser.error("Qualification report already exists; choose a new database path")
    result = run_local_intake(args.database, entry, max_pages=args.max_pages)
    with report.open("x") as output:
        json.dump(result, output, indent=2)
        output.write("\n")
    print(json.dumps({k: v for k, v in result.items() if k != "scope"}, indent=2))
    print(f"Qualification report: {report}")
    if not result["count_reconciled"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
