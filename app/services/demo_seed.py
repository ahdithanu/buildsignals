"""Replay reviewed local Columbus snapshots. No network requests or source activation."""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.ingestion import IngestionRun, IngestionSource
from app.models.organization import Organization
from app.models.organization_membership import MemberRole, OrganizationMembership
from app.models.user import User
from app.schemas.ingestion import FieldMappingCreate, IngestionSourceCreate
from app.services.demo_access import DEMO_EMAIL, DEMO_ORG_ID, DEMO_USER_ID
from app.services.ingestion.service import create_source, replay_permit_snapshot
from app.utils.org_scope import RequestContext, reset_current_context, set_current_context

SOURCE_KEYS = {"columbus_oh_commercial_building_permits", "columbus_oh_site_engineering_applications"}


def seed_identity(db: Session) -> None:
    """Caller must set the demo org context before opening its transaction."""
    org = db.get(Organization, DEMO_ORG_ID)
    user = db.get(User, DEMO_USER_ID)
    if org and org.slug != "buildsignals-demo":
        raise ValueError("Reserved demo organization ID is occupied")
    if user and user.email != DEMO_EMAIL:
        raise ValueError("Reserved demo user ID is occupied")
    if not org:
        db.add(Organization(id=DEMO_ORG_ID, name="BuildSignals Demo", slug="buildsignals-demo"))
    if not user:
        user = User(id=DEMO_USER_ID, email=DEMO_EMAIL, full_name="Demo visitor", password_hash="!nologin")
        db.add(user)
    user.password_hash = "!nologin"
    user.totp_enabled = False
    user.totp_secret = None
    user.totp_secret_ciphertext = None
    user.is_superuser = False
    db.flush()
    memberships = db.query(OrganizationMembership).filter_by(user_id=DEMO_USER_ID).all()
    if any(row.organization_id != DEMO_ORG_ID for row in memberships):
        raise ValueError("Demo user must belong only to its reserved organization")
    if memberships:
        memberships[0].role = MemberRole.viewer
    else:
        db.add(OrganizationMembership(organization_id=DEMO_ORG_ID, user_id=DEMO_USER_ID,
                                      role=MemberRole.viewer, is_default=True))
    db.flush()


def replay_cohort(db: Session, path: Path) -> int:
    """Input is an existing qualification SQLite DB, opened in read-only mode."""
    path = path.resolve(strict=True)
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as source_db:
        source_db.row_factory = sqlite3.Row
        sources = source_db.execute("SELECT * FROM ingestion_sources").fetchall()
        if len(sources) != 1 or sources[0]["key"] not in SOURCE_KEYS:
            raise ValueError("Expected one reviewed Columbus qualification source")
        row = sources[0]
        settings = json.loads(row["settings"])
        scope = settings.get("historical_qualification", {})
        if not ("2024-01-01" <= scope.get("start_inclusive", "") < scope.get("end_exclusive", "") <= "2024-04-01"):
            raise ValueError("Only the reviewed Q1 2024 qualification scope is supported")
        mappings = []
        for mapping in source_db.execute("SELECT * FROM source_field_mappings WHERE source_id = ?", (row["id"],)):
            values = {key: mapping[key] for key in FieldMappingCreate.model_fields}
            for key in ("transform_options", "default_value"):
                values[key] = json.loads(values[key]) if values[key] else None
            mappings.append(FieldMappingCreate(**values))
        key = f"demo_{row['key']}_{scope['start_inclusive'].replace('-', '')}"
        target = db.query(IngestionSource).filter_by(organization_id=DEMO_ORG_ID, key=key).first()
        if not target:
            target = create_source(db, IngestionSourceCreate(
                key=key, name=f"Historical demo: {row['name']}", adapter=row["adapter"],
                jurisdiction=row["jurisdiction"], base_url=row["base_url"], is_active=False,
                settings={**settings, "schedule_mode": "manual", "demo_snapshot": True},
                field_mappings=mappings,
            ))
        if target.is_active or not (target.settings or {}).get("demo_snapshot"):
            raise ValueError("Refusing to replay into an active or non-demo source")
        records = source_db.execute(
            "SELECT r.payload, r.received_at FROM permit_records p "
            "JOIN raw_source_records r ON r.id = p.latest_raw_record_id "
            "WHERE p.source_id = ? ORDER BY p.external_record_id LIMIT 2050", (row["id"],),
        ).fetchall()
        if not records or len(records) > 2049:
            raise ValueError("Missing or oversized qualification cohort")
        runs = source_db.execute("SELECT status, records_failed, checkpoint FROM ingestion_runs").fetchall()
        if not runs or any(run["status"] != "completed" or run["records_failed"] or run["checkpoint"] not in (None, "null", "{}") for run in runs):
            raise ValueError("Qualification run is incomplete or failed")
        run = db.query(IngestionRun).filter_by(source_id=target.id, trigger="demo_replay").first()
        if not run:
            run = IngestionRun(organization_id=DEMO_ORG_ID, source_id=target.id, trigger="demo_replay",
                               status="pending", parameters={"historical_scope": scope})
            db.add(run)
            db.flush()
        for record in records:
            payload = json.loads(record["payload"])
            allowlist = set(settings.get("field_allowlist", []))
            if not allowlist or set(payload) - allowlist:
                raise ValueError("Snapshot contains fields outside the reviewed public-data scope")
            captured = datetime.fromisoformat(record["received_at"])
            if captured.tzinfo is None:
                captured = captured.replace(tzinfo=timezone.utc)
            _, action = replay_permit_snapshot(db, target, run.id, payload, captured)
            if action == "created":
                run.records_inserted = (run.records_inserted or 0) + 1
            elif action in {"updated", "reprocessed"}:
                run.records_updated = (run.records_updated or 0) + 1
        run.records_seen = len(records)
        run.status = "completed"
        if not run.completed_at:
            run.completed_at = datetime.now(timezone.utc)
        db.flush()
        return len(records)


def seed_demo(db: Session, paths: list[Path]) -> int:
    if db.in_transaction():
        raise ValueError("Demo seed requires a fresh session for tenant isolation")
    context = set_current_context(RequestContext(DEMO_ORG_ID, DEMO_USER_ID))
    try:
        with db.begin():
            seed_identity(db)
            count = sum(replay_cohort(db, path) for path in paths)
        return count
    finally:
        reset_current_context(context)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshots", nargs="+", type=Path)
    parser.add_argument("--confirm-demo-seed", action="store_true", required=True,
                        help="Acknowledge writes to the configured DATABASE_URL demo tenant only")
    args = parser.parse_args()
    from app.db import SessionLocal
    with SessionLocal() as db:
        count = seed_demo(db, args.snapshots)
    print(json.dumps({"demo_source_records": count, "unique_projects": "not measured", "production_sources_activated": 0}))


if __name__ == "__main__":
    main()
