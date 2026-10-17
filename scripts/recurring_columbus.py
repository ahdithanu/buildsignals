"""Bounded public Columbus application refresh for one explicit tenant."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.db import SessionLocal
from app.models.ingestion import IngestionSource, PermitRecord
from app.models.organization import Organization
from app.schemas.ingestion import IngestionSourceUpdate
from app.services.demo_access import DEMO_ORG_ID, DEMO_USER_ID
from app.services.demo_seed import seed_identity
from app.services.ingestion.catalog import load_catalog
from app.services.ingestion.connectors.base import RetryingHttpClient
from app.services.ingestion.historical_intake import provider_count
from app.services.ingestion.service import create_source, execute_source_run, update_source
from app.utils.org_scope import (
    SYSTEM_USER_ID,
    RequestContext,
    reset_current_context,
    set_current_context,
)

SOURCE_KEY = "columbus_oh_site_engineering_applications"
LEGACY_PRODUCTION = "columbus_oh_site_applications_20261001_20261016"
LEGACY_DEMO = "demo_recent_columbus_oh_site_engineering_applications_20261001_20261016"


def refresh_entry(*, demo: bool, now: datetime | None = None):
    today = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).date()
    start, end = today - timedelta(days=30), today + timedelta(days=1)
    entry = next(row for row in load_catalog() if row.key == SOURCE_KEY).model_copy(deep=True)
    predicate = entry.settings["connector"]["where"]
    entry.settings["connector"].update({
        "where": f"({predicate}) AND B1_FILE_DD >= TIMESTAMP '{start} 00:00:00' AND B1_FILE_DD < TIMESTAMP '{end} 00:00:00'",
        "page_size": 250, "timeout": 30, "max_retries": 1,
    })
    entry.settings.update({
        "schedule_mode": "manual",  # Dedicated scheduler, not the catalog dispatcher.
        "reconciliation_mode": "incremental",  # Aging out is not evidence of deletion.
        "rolling_window_days": 31,
        "demo_snapshot": demo,
    })
    entry.key = "demo_current_columbus_site_applications" if demo else SOURCE_KEY
    entry.name = "Columbus site applications (rolling 31 days)"
    entry.is_active = True
    return entry


def refresh(organization_id: str, *, demo: bool, session_factory=SessionLocal) -> dict:
    if not organization_id or (organization_id == DEMO_ORG_ID) != demo:
        raise ValueError("Demo and production destinations must be separate")
    context = set_current_context(RequestContext(organization_id, DEMO_USER_ID if demo else SYSTEM_USER_ID))
    try:
        with session_factory() as db:
            org = db.get(Organization, organization_id)
            if org is None or not org.is_active:
                raise ValueError("Active destination organization not found")
            # A dedicated connection retains the lock across service commits.
            with db.get_bind().connect() as lease:
                lock_id = 2026101602 if demo else 2026101601
                postgres = lease.dialect.name == "postgresql"
                if postgres and not lease.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_id}):
                    raise RuntimeError("Refresh already running")
                try:
                    if demo:
                        seed_identity(db)
                    entry = refresh_entry(demo=demo)
                    client = RetryingHttpClient(timeout=30, max_retries=1)
                    before = provider_count(entry, client)
                    if not 0 <= before <= 1000:
                        raise ValueError("Provider count exceeds the 1000-record request budget")
                    legacy = LEGACY_DEMO if demo else LEGACY_PRODUCTION
                    candidates = db.query(IngestionSource).filter(
                        IngestionSource.organization_id == organization_id,
                        IngestionSource.key.in_([entry.key, legacy]),
                    ).all()
                    if len(candidates) > 1:
                        raise ValueError("Ambiguous current/legacy sources; refusing duplicate ingestion")
                    source = candidates[0] if candidates else create_source(db, entry)
                    if candidates:
                        if source.base_url != entry.base_url or source.record_type != "permit":
                            raise ValueError("Existing source does not match the reviewed feed")
                        source.key = entry.key
                        update_source(db, source, IngestionSourceUpdate(
                            name=entry.name, settings=entry.settings, is_active=True,
                            field_mappings=entry.field_mappings,
                        ))
                    db.commit()
                    try:
                        run = execute_source_run(db, source, max_pages=4, trigger="scheduled")
                        after = provider_count(entry, client)
                        result = {"mode": "demo" if demo else "production", "run_id": run.id,
                                  "status": run.status, "records_seen": run.records_seen,
                                  "inserted": run.records_inserted, "updated": run.records_updated,
                                  "failed": run.records_failed, "checkpoint": run.checkpoint,
                                  "provider_before": before, "provider_after": after,
                                  "finished_at": datetime.now(timezone.utc).isoformat(),
                                  "stored_source_records": db.query(PermitRecord).filter_by(
                                      organization_id=organization_id, source_id=source.id).count()}
                        print(json.dumps(result), flush=True)
                        if run.status != "completed" or run.records_failed or run.checkpoint or not before == after == run.records_seen:
                            raise RuntimeError("Refresh failed reconciliation; inspect its ingestion run")
                        return result
                    finally:
                        if demo:
                            db.rollback()
                            source.is_active = False
                            db.commit()
                finally:
                    if postgres:
                        lease.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_id})
    finally:
        reset_current_context(context)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organization-id", required=True)
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()
    try:
        refresh(args.organization_id, demo=args.demo)
    except Exception as exc:
        print(json.dumps({"status": "failed", "mode": "demo" if args.demo else "production",
                          "error_type": type(exc).__name__}), flush=True)
        raise SystemExit(1) from None
