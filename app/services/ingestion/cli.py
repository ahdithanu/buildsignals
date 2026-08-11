from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from sqlalchemy import or_

from app.db import SessionLocal
from app.models.ingestion import IngestionSource
from app.models.organization import Organization
from app.services.brand_intelligence import load_brand_catalog, sync_brand_catalog
from app.services.ingestion.catalog import (
    load_candidate_catalog,
    load_catalog,
    sync_catalog,
)
from app.services.ingestion.health import (
    CandidateCanaryResult,
    evaluate_source_health,
    list_candidate_canary_attempts,
    record_candidate_canary_attempt,
    resolve_resume_checkpoint,
    validate_candidate_source_canary,
    validate_source_canary,
)
from app.services.ingestion.promotion import prepare_promotion_manifest
from app.services.ingestion.service import execute_source_run, list_sources
from app.utils.org_scope import (
    SYSTEM_USER_ID,
    RequestContext,
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
    prepare = catalog_commands.add_parser(
        "prepare-promotion",
        help="Compile a reviewed candidate into a validated promoted catalog",
    )
    prepare.add_argument("--candidate-key", required=True)
    prepare.add_argument("--review-file", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument(
        "--promoted-catalog",
        type=Path,
        help="Existing promoted catalog to merge (defaults to the checked-in catalog)",
    )
    prepare.add_argument(
        "--replace",
        action="store_true",
        help="Replace an existing promoted entry with the same candidate key",
    )

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
    run_all.add_argument(
        "--source-key", action="append", dest="source_keys",
        help="Run only this source key (repeat for multiple sources)",
    )

    scheduled = subcommands.add_parser(
        "scheduled",
        help="Sync the production catalog, run selected sources, and check health",
    )
    scheduled.add_argument("--organization", required=True, help="Organization ID or slug")
    scheduled.add_argument(
        "--source-key", action="append", dest="source_keys", required=True,
        help="Source key to run (repeat for multiple sources)",
    )
    scheduled.add_argument(
        "--max-pages-per-source", type=int, default=10,
        choices=range(1, 101), metavar="1..100",
    )
    scheduled.add_argument(
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
    health.add_argument(
        "--source-key", action="append", dest="source_keys",
        help="Report only this source key (repeat for multiple sources)",
    )

    retries = subcommands.add_parser(
        "retry-candidates",
        help="Canary due operational-retry candidates without promoting them",
    )
    retries.add_argument("--organization", required=True, help="Organization ID or slug")
    retries.add_argument(
        "--candidate-key", action="append", dest="candidate_keys",
        help="Limit retries to this candidate key (repeat for multiple candidates)",
    )
    retries.add_argument(
        "--sample-size", type=int, default=10,
        choices=range(1, 101), metavar="1..100",
    )
    retries.add_argument(
        "--as-of", type=date.fromisoformat, default=date.today(), metavar="YYYY-MM-DD",
        help="Evaluate candidate audit dates as of this date",
    )
    retries.add_argument(
        "--force", action="store_true",
        help="Retry selected due candidates even after a successful canary",
    )
    return parser


def _select_sources(
    db,
    *,
    source_keys: list[str] | None = None,
    stage: str = "all",
) -> list[IngestionSource]:
    sources = list_sources(db)
    if source_keys:
        requested = set(source_keys)
        available = {source.key for source in sources}
        missing = sorted(requested - available)
        if missing:
            raise ValueError(f"Ingestion source not found: {', '.join(missing)}")
        sources = [source for source in sources if source.key in requested]
    if stage != "all":
        sources = [
            source for source in sources
            if (source.settings or {}).get("signal_stage") == stage
        ]
    return sources


def _validate_catalog_source_keys(catalog_entries, source_keys: list[str]) -> None:
    available = {entry.key for entry in catalog_entries}
    missing = sorted(set(source_keys) - available)
    if missing:
        raise ValueError(
            f"Scheduled source not found in production catalog: {', '.join(missing)}"
        )


def _select_due_candidates(
    db,
    *,
    as_of: date,
    candidate_keys: list[str] | None = None,
    force: bool = False,
):
    candidates = load_candidate_catalog()
    by_key = {candidate.key: candidate for candidate in candidates}
    if candidate_keys:
        missing = sorted(set(candidate_keys) - set(by_key))
        if missing:
            raise ValueError(f"Ingestion candidate not found: {', '.join(missing)}")
        candidates = [by_key[key] for key in dict.fromkeys(candidate_keys)]

    due = []
    for candidate in candidates:
        if not candidate.can_run_canary or candidate.next_audit_on > as_of:
            continue
        latest = list_candidate_canary_attempts(db, candidate.key, limit=1)
        if (
            not force
            and latest
            and latest[0].ok
            and latest[0].created_at.date() >= candidate.next_audit_on
        ):
            continue
        due.append(candidate)
    return due


def _retry_candidates(db, candidates, *, sample_size: int) -> bool:
    failed = False
    for candidate in candidates:
        try:
            result = validate_candidate_source_canary(
                candidate, sample_size=sample_size
            )
        except Exception as exc:
            result = CandidateCanaryResult(
                candidate_key=candidate.key,
                candidate_name=candidate.name,
                ok=False,
                records_fetched=0,
                records_valid=0,
                records_failed=0,
                approval_stages={},
                sample_record_ids=[],
                next_checkpoint=None,
                errors=[f"{type(exc).__name__}: {exc}"],
            )
        record_candidate_canary_attempt(
            db, candidate, result, sample_size=sample_size
        )
        db.commit()
        failed = failed or not result.ok
        print(
            f"{candidate.key}: ok={result.ok} fetched={result.records_fetched} "
            f"valid={result.records_valid} failed={result.records_failed}"
        )
        for error in result.errors:
            print(f"  {error}")
    return failed


def _run_sources(
    db,
    sources: list[IngestionSource],
    *,
    max_pages: int,
    reset_checkpoints: bool,
) -> bool:
    failed = False
    for source in sources:
        try:
            checkpoint = (
                None if reset_checkpoints
                else resolve_resume_checkpoint(db, source.id)
            )
            run_result = execute_source_run(
                db,
                source,
                max_pages=max_pages,
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
    return failed


def _report_health(db, sources: list[IngestionSource], *, as_json: bool = False) -> int:
    results = [evaluate_source_health(db, source) for source in sources]
    if as_json:
        print(json.dumps([result.__dict__ for result in results], default=str))
    else:
        for result in results:
            print(
                f"{result.source_key}: {result.status} "
                f"age_hours={result.ingestion_age_hours} "
                f"failure_rate={result.run_failure_rate}"
            )
            for reason in result.reasons:
                print(f"  {reason}")
    statuses = {result.status for result in results}
    return 2 if statuses & {"critical", "unknown"} else 1 if "degraded" in statuses else 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "catalog" and args.catalog_command == "prepare-promotion":
        try:
            kwargs = {
                "candidate_key": args.candidate_key,
                "review_path": args.review_file,
                "output_path": args.output,
                "replace": args.replace,
            }
            if args.promoted_catalog is not None:
                kwargs["promoted_catalog_path"] = args.promoted_catalog
            promoted = prepare_promotion_manifest(**kwargs)
            print(
                f"prepared {args.candidate_key} in {args.output} "
                f"({len(promoted)} promoted sources)"
            )
            return 0
        except Exception as exc:
            print(f"error: {exc}")
            return 1

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
            return _report_health(
                db,
                _select_sources(db, source_keys=args.source_keys),
                as_json=args.json,
            )

        if args.command == "retry-candidates":
            selected = _select_due_candidates(
                db,
                as_of=args.as_of,
                candidate_keys=args.candidate_keys,
                force=args.force,
            )
            if not selected:
                print(f"no runnable candidate canaries are due as of {args.as_of}")
                return 0
            return 1 if _retry_candidates(
                db, selected, sample_size=args.sample_size
            ) else 0

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
            selected = _select_sources(
                db, source_keys=args.source_keys, stage=args.stage
            )
            failed = _run_sources(
                db,
                selected,
                max_pages=args.max_pages_per_source,
                reset_checkpoints=args.reset_checkpoints,
            )
            if not selected:
                print(f"no active sources matched stage={args.stage}")
                if args.source_keys:
                    return 1
            return 1 if failed else 0

        if args.command == "scheduled":
            catalog_entries = load_catalog()
            _validate_catalog_source_keys(catalog_entries, args.source_keys)
            sync_result = sync_catalog(db, catalog_entries)
            db.commit()
            print(
                f"catalog sync: created={sync_result.created} updated={sync_result.updated} "
                f"unchanged={sync_result.unchanged}"
            )
            selected = _select_sources(db, source_keys=args.source_keys)
            run_failed = _run_sources(
                db,
                selected,
                max_pages=args.max_pages_per_source,
                reset_checkpoints=args.reset_checkpoints,
            )
            health_exit = _report_health(db, selected)
            if health_exit == 2:
                return 2
            return 1 if run_failed or health_exit == 1 else 0

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
