"""Bounded stored company replay. Plan by default; never fetch sources or models."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from sqlalchemy import text

from app.db import Base, SessionLocal
from app.models.ingestion import PermitRecord
from app.models.mixins import OrgMixin
from app.models.organization import Organization
from app.models.planning import PlanningRecord
from app.services.brand_intelligence import backfill_brand_matches_batch, load_brand_catalog
from app.services.company_backfill import backfill_planning_company_matches_batch
from app.services.company_catalog import ensure_company_catalog, require_company_rls
from app.services.demo_access import DEMO_ORG_ID, demo_read_only
from app.utils.org_scope import (
    RequestContext,
    active_query,
    reset_current_context,
    set_current_context,
)

MAX_PERMITS = 25_000
MAX_PLANNING = 100


def run(organization_id: str, *, permit_limit=1000, planning_limit=100, batch_size=500,
        after_permit_id=None, after_planning_id=None, execute=False, session_factory=SessionLocal):
    if (not organization_id or organization_id == DEMO_ORG_ID
            or type(permit_limit) is not int or not 0 <= permit_limit <= MAX_PERMITS
            or type(planning_limit) is not int or not 0 <= planning_limit <= MAX_PLANNING
            or type(batch_size) is not int or not 1 <= batch_size <= 500
            or permit_limit + planning_limit == 0
            or any(cursor is not None and (not isinstance(cursor, str) or not 1 <= len(cursor) <= 36)
                   for cursor in (after_permit_id, after_planning_id))):
        raise ValueError("Explicit non-demo tenant and bounded replay limits/cursors are required")
    if demo_read_only.get():
        raise PermissionError("Demo sessions cannot replay company intelligence")
    token = set_current_context(RequestContext(organization_id, "company-replay-operator"))
    result = {"mode": "execute" if execute else "plan", "catalog": None}
    try:
        with session_factory() as db:
            org = db.get(Organization, organization_id)
            if org is None or not org.is_active:
                raise ValueError("Active destination organization not found")
            if execute:
                # Graph projection touches several tenant tables. Check every mapped
                # tenant table rather than relying on role flags alone.
                tables = tuple(sorted(mapper.local_table.name for mapper in Base.registry.mappers
                                      if issubclass(mapper.class_, OrgMixin)))
                require_company_rls(db, tables)
                result["catalog"] = asdict(ensure_company_catalog(db, organization_id))
                db.commit()
            else:
                result["catalog"] = {"definitions": len(load_brand_catalog())}
            for name, model, replay, limit, cursor in (
                ("permits", PermitRecord, backfill_brand_matches_batch, permit_limit, after_permit_id),
                ("planning", PlanningRecord, backfill_planning_company_matches_batch, planning_limit, after_planning_id),
            ):
                counts = dict(scanned=0, matches_created=0, matches_refreshed=0, matches_retracted=0)
                if limit == 0:
                    result[name] = {**counts, "skipped": True, "has_more": False, "next_cursor": cursor}
                    continue
                if not execute:
                    query = active_query(db.query(model.id), model)
                    if model is PermitRecord:
                        query = query.filter(model.is_active.is_(True),
                                             model.approval_stage.in_(("pre_approval", "approved")))
                    if cursor:
                        query = query.filter(model.id > cursor)
                    rows = query.order_by(model.id).limit(limit + 1).all()
                    result[name] = {**counts, "planned": min(len(rows), limit),
                                    "has_more": len(rows) > limit, "next_cursor": cursor}
                    continue
                has_more = True
                while counts["scanned"] < limit and has_more:
                    if db.get_bind().dialect.name == "postgresql":
                        db.execute(text("SELECT set_config('lock_timeout', '5s', true)"))
                    batch = replay(db, after_id=cursor, batch_size=min(batch_size, limit - counts["scanned"]))
                    db.commit()
                    for key in counts:
                        counts[key] += getattr(batch, key)
                    cursor, has_more = batch.next_cursor, batch.has_more
                    if batch.scanned == 0:
                        break
                result[name] = {**counts, "has_more": has_more, "next_cursor": cursor}
            result["status"] = ("planned" if not execute else
                                "partial" if any(result[key]["has_more"] for key in ("permits", "planning"))
                                else "completed")
    finally:
        reset_current_context(token)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organization-id", required=True)
    parser.add_argument("--permit-limit", type=int, default=1000)
    parser.add_argument("--planning-limit", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--after-permit-id")
    parser.add_argument("--after-planning-id")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(run(**vars(args))), flush=True)
    except Exception as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__,
                          "reason": "Inspect internal worker logs; committed batches may require a replay"}), flush=True)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
