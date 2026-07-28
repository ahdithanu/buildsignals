from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import or_

from app.db import SessionLocal
from app.models.ingestion import IngestionSource
from app.models.organization import Organization
from app.services.ingestion.catalog import load_catalog, sync_catalog
from app.services.ingestion.health import (
    evaluate_source_health,
    resolve_resume_checkpoint,
    validate_source_canary,
)
from app.services.brand_intelligence import load_brand_catalog, sync_brand_catalog
from app.services.ingestion.service import execute_source_run, list_sources
from app.utils.org_scope import (
    RequestContext,
    SYSTEM_USER_ID,
    active_query,
    reset_current_context,
    set_current_context,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage external record ingestion")
    subcommands = parser.add_subparsers(dest="command", required=True)

    catalog = subcommands.add_parser("catalog", help="Manage the source catalog")
    catalog_commands = catalog.add_subparsers(dest="catalog_command", required=True)
    sync = catalog_commands.add_parser("sync", help="Synchronize catalog sources")
    sync.add_argument("--organization", required=True, help="Organization ID or slug")
    sync.add_argument("--path", type=Path, help="Alternative catalog JSON file")
    sync.add_argument("--dry-run", action="store_true")

    brands = subcommands.add_parser("brands", help="Manage the retailer brand catalog")
    brand_commands = brands.add_subparsers(dest="brand_command", required=True)
    brand_sync = brand_commands.add_parser("sync", help="Synchronize retailer brands")
    brand_sync.add_argument("--organization", required=True, help="Organization ID or slug")
    brand_sync.add_argument("--path", type=Path, help="Alternative brand catalog JSON file")
    brand_sync.add_argument("--dry-run", action="store_true")

    run = subcommands.add_parser("run", help="Run one catalog source")
    run.add_argument("--organization", required=True, help="Organization ID or slug")
    run.add_argument("--source-key", required=True)
    run.add_argument("--max-pages", type=int, default=1, choices=range(1, 101), metavar="1..100")
    run.add_argument("--resume-latest", action="store_true")

    run_all = subcommands.add_parser("run-all", help="Run every active catalog source")
    run_all.add_argument("--organization", required=True, help="Organization ID or slug")
    run_all.add_argument(
        "--max-pages-per-source", type=int, default=10,
        choices=range(1, 101), metavar="1..100",
    )
    run_all.add_argument(
        "--stage", choices=("all", "pre_approval_and_approved", "approved_only"),
        default="all",
    )
    run_all.add_argument(
        "--reset-checkpoints", action="store_true",
        help="Start a reconciliation pass from the beginning of each source",
    )

    canary = subcommands.add_parser("canary", help="Validate one source without writing data")
    canary.add_argument("--organization", required=True, help="Organization ID or slug")
    canary_target = canary.add_mutually_exclusive_group(required=True)
    canary_target.add_argument("--source-key")
    canary_target.add_argument("--all", action="store_true")
    canary.add_argument("--sample-size", type=int, default=10, choices=range(1, 101), metavar="1..100")

    health = subcommands.add_parser("health", help="Report ingestion source health")
    health.add_argument("--organization", required=True, help="Organization ID or slug")
    health.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    db = SessionLocal()
    token = None
    try:
        organization = db.query(Organization).filter(
            or_(Organization.id == args.organization, Organization.slug == args.organization),
            Organization.is_active.is_(True),
        ).first()
        if organization is None:
            raise ValueError(f"Active organization not found: {args.organization}")
        organization_id = organization.id
        db.rollback()
        token = set_current_context(RequestContext(organization_id, SYSTEM_USER_ID))

        if args.command == "catalog":
            result = sync_catalog(db, load_catalog(args.path), dry_run=args.dry_run)
            if args.dry_run:
                db.rollback()
            else:
                db.commit()
            print(
                f"catalog sync: created={result.created} updated={result.updated} "
                f"unchanged={result.unchanged} dry_run={args.dry_run}"
            )
            return 0

        if args.command == "brands":
            result = sync_brand_catalog(
                db, load_brand_catalog(args.path), dry_run=args.dry_run
            )
            if args.dry_run:
                db.rollback()
            else:
                db.commit()
            print(
                f"brand sync: created={result.created} updated={result.updated} "
                f"unchanged={result.unchanged} dry_run={args.dry_run}"
            )
            return 0

        if args.command == "health":
            results = [evaluate_source_health(db, source) for source in list_sources(db)]
            if args.json:
                print(json.dumps([result.__dict__ for result in results], default=str))
            else:
                for result in results:
                    print(
                        f"{result.source_key}: {result.status} "
                        f"age_hours={result.ingestion_age_hours} "
                        f"failure_rate={result.run_failure_rate}"
                    )
            statuses = {result.status for result in results}
            return 2 if statuses & {"critical", "unknown"} else 1 if "degraded" in statuses else 0

        if args.command == "canary" and args.all:
            failed = False
            for source in list_sources(db):
                try:
                    result = validate_source_canary(source, sample_size=args.sample_size)
                    failed = failed or not result.ok
                    print(
                        f"{result.source_key}: ok={result.ok} fetched={result.records_fetched} "
                        f"valid={result.records_valid} failed={result.records_failed}"
                    )
                    for error in result.errors:
                        print(f"  {error}")
                except Exception as exc:
                    failed = True
                    print(f"{source.key}: error={exc}")
            return 1 if failed else 0

        if args.command == "run-all":
            failed = False
            selected = [
                source for source in list_sources(db)
                if args.stage == "all"
                or (source.settings or {}).get("signal_stage") == args.stage
            ]
            for source in selected:
                try:
                    checkpoint = (
                        None if args.reset_checkpoints
                        else resolve_resume_checkpoint(db, source.id)
                    )
                    run_result = execute_source_run(
                        db,
                        source,
                        max_pages=args.max_pages_per_source,
                        checkpoint=checkpoint,
                        trigger="scheduled",
                    )
                    failed = failed or run_result.status in {"failed", "partial_with_errors"}
                    print(
                        f"{source.key}: status={run_result.status} "
                        f"seen={run_result.records_seen} inserted={run_result.records_inserted} "
                        f"updated={run_result.records_updated} failed={run_result.records_failed}"
                    )
                except Exception as exc:
                    failed = True
                    db.rollback()
                    print(f"{source.key}: error={exc}")
            if not selected:
                print(f"no active sources matched stage={args.stage}")
            return 1 if failed else 0

        source = active_query(db.query(IngestionSource), IngestionSource).filter(
            IngestionSource.key == args.source_key
        ).first()
        if source is None:
            raise ValueError(f"Ingestion source not found: {args.source_key}")
        if args.command == "canary":
            result = validate_source_canary(source, sample_size=args.sample_size)
            print(
                f"canary {result.source_key}: ok={result.ok} fetched={result.records_fetched} "
                f"valid={result.records_valid} failed={result.records_failed} "
                f"stages={result.approval_stages}"
            )
            for error in result.errors:
                print(f"  {error}")
            return 0 if result.ok else 1
        checkpoint = resolve_resume_checkpoint(db, source.id) if args.resume_latest else None
        run = execute_source_run(
            db,
            source,
            max_pages=args.max_pages,
            checkpoint=checkpoint,
            trigger="cli",
        )
        print(
            f"run {run.id}: status={run.status} seen={run.records_seen} "
            f"inserted={run.records_inserted} updated={run.records_updated} "
            f"failed={run.records_failed}"
        )
        return 0 if run.status != "failed" else 1
    except Exception as exc:
        db.rollback()
        print(f"error: {exc}")
        return 1
    finally:
        if token is not None:
            reset_current_context(token)
        db.close()


def _latest_checkpoint(db, source_id: str) -> dict | None:
    return resolve_resume_checkpoint(db, source_id)


if __name__ == "__main__":
    raise SystemExit(main())
