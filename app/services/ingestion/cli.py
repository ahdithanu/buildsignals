from __future__ import annotations

import argparse
import hmac
import json
import os
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import or_

from app.config import ENVIRONMENT
from app.db import SessionLocal
from app.models.ingestion import IngestionSource
from app.models.organization import Organization
from app.services.brand_intelligence import load_brand_catalog, sync_brand_catalog
from app.services.ingestion.build_signals_export import (
    build_batches,
    list_exportable_permits,
    publish_batch,
)
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
from app.services.ingestion.host_policy import audit_ingestion_hosts, candidate_host_policy_entries
from app.services.ingestion.promotion import prepare_promotion_manifest
from app.services.ingestion.rollout import (
    DEFAULT_ROLLOUT_MANIFEST_PATH,
    build_production_rollout_manifest,
    require_current_rollout_manifest,
    rollout_manifest_json,
    scope_rollout_wave,
)
from app.services.ingestion.scheduling import (
    build_schedule_plan,
    source_schedule_policy,
    source_shard,
)
from app.services.ingestion.service import ActiveRunConflict, execute_source_run, list_sources
from app.services.ingestion.source_access import (
    build_source_access_contract,
    source_access_contract_json,
    source_access_contract_markdown,
)
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
    host_audit = catalog_commands.add_parser(
        "host-audit",
        help="Compare catalog source hosts with the static outbound allowlist",
    )
    host_audit.add_argument("--path", type=Path, help="Alternative catalog JSON file")
    host_audit.add_argument(
        "--allowed-hosts",
        help="Comma-separated host list (defaults to INGESTION_ALLOWED_HOSTS)",
    )
    host_audit.add_argument("--json", action="store_true")
    host_audit.add_argument("--print-required-hosts", action="store_true")
    host_audit.add_argument("--print-policy-digest", action="store_true")
    host_audit.add_argument(
        "--allow-unused-hosts",
        action="store_true",
        help="Allow a reviewed shared policy to cover more hosts than this scope",
    )
    host_audit.add_argument(
        "--source-key", action="append", dest="source_keys",
        help="Audit only this production source key (repeatable)",
    )
    host_audit.add_argument(
        "--stage", choices=("all", "pre_approval_and_approved", "approved_only"),
        default="all",
    )
    host_audit.add_argument(
        "--shard-count", type=int, default=1, choices=range(1, 129), metavar="1..128",
    )
    host_audit.add_argument(
        "--shard-index", type=int, default=0, choices=range(0, 128), metavar="0..127",
    )
    host_audit.add_argument(
        "--rollout-wave", type=int, choices=range(1, 5), metavar="1..4",
    )
    rollout_manifest = catalog_commands.add_parser(
        "rollout-manifest",
        help="Build a deterministic nationwide activation manifest",
    )
    rollout_manifest.add_argument(
        "--shard-count", type=int, default=4, choices=range(1, 129), metavar="1..128",
    )
    rollout_manifest.add_argument("--output", type=Path)
    rollout_manifest.add_argument("--check", action="store_true")
    candidate_host_audit = catalog_commands.add_parser(
        "candidate-host-audit",
        help="Audit runnable retry-candidate hosts without fetching them",
    )
    candidate_host_audit.add_argument(
        "--candidate-key", action="append", dest="candidate_keys",
        help="Audit only this runnable candidate key (repeatable)",
    )
    candidate_host_audit.add_argument(
        "--allowed-hosts",
        help="Comma-separated host list (defaults to INGESTION_ALLOWED_HOSTS)",
    )
    candidate_host_audit.add_argument("--json", action="store_true")
    candidate_host_audit.add_argument("--print-required-hosts", action="store_true")
    candidate_host_audit.add_argument("--print-policy-digest", action="store_true")
    source_request = catalog_commands.add_parser(
        "source-request",
        help="Build a reusable access contract for a blocked candidate source",
    )
    source_request.add_argument("--candidate-key", required=True)
    source_request.add_argument(
        "--format", choices=("markdown", "json"), default="markdown"
    )
    source_request.add_argument("--output", type=Path)

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

    publish = subcommands.add_parser(
        "publish-build-signals",
        help="Publish normalized pre-approval and approved records to the Vercel application",
    )
    publish.add_argument("--organization", required=True, help="Organization ID or slug")
    publish.add_argument(
        "--target-url",
        default=os.environ.get("BUILD_SIGNALS_INGESTION_URL"),
        help="Versioned import endpoint (defaults to BUILD_SIGNALS_INGESTION_URL)",
    )
    publish.add_argument(
        "--source-key", action="append", dest="source_keys",
        help="Publish only this source key (repeat for multiple sources)",
    )
    publish.add_argument(
        "--stage", choices=("pre_approval_and_approved", "approved_only"),
        default="pre_approval_and_approved",
    )
    publish.add_argument("--limit", type=int, default=5_000, choices=range(1, 50_001))
    publish.add_argument("--dry-run", action="store_true")
    publish.add_argument("--output", type=Path, help="Write dry-run contract JSON to this file")

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

    scheduled_due = subcommands.add_parser(
        "scheduled-due",
        help="Sync the catalog, plan due sources, and optionally run the due shard",
    )
    scheduled_due.add_argument(
        "--organization", required=True, help="Organization ID or slug"
    )
    scheduled_due.add_argument(
        "--source-key", action="append", dest="source_keys",
        help="Limit the plan to this production source key (repeatable)",
    )
    scheduled_due.add_argument(
        "--stage", choices=("all", "pre_approval_and_approved", "approved_only"),
        default="all",
    )
    scheduled_due.add_argument(
        "--as-of", type=datetime.fromisoformat, metavar="ISO-8601",
        help="Build a deterministic plan at this timestamp",
    )
    scheduled_due.add_argument(
        "--shard-count", type=int, default=1, choices=range(1, 129), metavar="1..128",
    )
    scheduled_due.add_argument(
        "--shard-index", type=int, default=0, choices=range(0, 128), metavar="0..127",
    )
    scheduled_due.add_argument(
        "--max-pages-per-source", type=int, choices=range(1, 101), metavar="1..100",
        help="Override each source's catalog page limit for this execution",
    )
    scheduled_due.add_argument(
        "--plan-only", action="store_true",
        help="Print the due plan without executing sources",
    )
    scheduled_due.add_argument(
        "--rollout-wave", type=int, choices=range(1, 5), metavar="1..4",
        help="Limit execution to one reviewed nationwide rollout wave",
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


def _scope_catalog_entries(
    catalog_entries,
    *,
    source_keys: list[str] | None = None,
    stage: str = "all",
    shard_count: int = 1,
    shard_index: int = 0,
    rollout_wave: int | None = None,
):
    if shard_index < 0 or shard_index >= shard_count:
        raise ValueError("shard_index must be between 0 and shard_count - 1")
    if source_keys:
        _validate_catalog_source_keys(catalog_entries, source_keys)
    requested = set(source_keys or [])
    scoped = [
        entry for entry in catalog_entries
        if (not requested or entry.key in requested)
        and (stage == "all" or (entry.settings or {}).get("signal_stage") == stage)
        and source_shard(entry.key, shard_count) == shard_index
    ]
    scoped = scope_rollout_wave(scoped, rollout_wave)
    if source_keys:
        excluded = sorted(requested - {entry.key for entry in scoped})
        if excluded:
            raise ValueError(
                "Requested sources are outside the selected stage, shard, or "
                f"rollout wave: {', '.join(excluded)}"
            )
    return scoped


def _enforce_catalog_host_policy(catalog_entries) -> None:
    if ENVIRONMENT not in {"staging", "production"}:
        return
    host_policy = audit_ingestion_hosts(catalog_entries)
    if host_policy.coverage_ready:
        expected_digest = os.environ.get("INGESTION_HOST_POLICY_DIGEST", "").strip()
        if not expected_digest:
            raise ValueError("INGESTION_HOST_POLICY_DIGEST must be configured")
        if not hmac.compare_digest(
            expected_digest, host_policy.policy_digest
        ):
            raise ValueError("Ingestion host policy digest does not match this executor scope")
        return
    details = []
    if host_policy.missing_hosts:
        details.append(f"missing hosts: {','.join(host_policy.missing_hosts)}")
    if host_policy.unsafe_sources:
        details.append(
            "unsafe sources: "
            + ",".join(item.source_key for item in host_policy.unsafe_sources)
        )
    raise ValueError("Ingestion host policy blocked execution; " + "; ".join(details))


def _enforce_rollout_manifest_attestation(manifest) -> None:
    if ENVIRONMENT not in {"staging", "production"}:
        return
    expected_digest = os.environ.get(
        "INGESTION_ROLLOUT_MANIFEST_DIGEST", ""
    ).strip()
    if not expected_digest:
        raise ValueError("INGESTION_ROLLOUT_MANIFEST_DIGEST must be configured")
    if not hmac.compare_digest(expected_digest, manifest.manifest_digest):
        raise ValueError("Production rollout manifest digest does not match deployment")


def _validate_candidate_rollout_scope(manifest, candidates, *, sample_size: int) -> None:
    if sample_size != manifest.candidate_retries.sample_size:
        raise ValueError(
            "Candidate sample size does not match the reviewed rollout manifest"
        )
    approved_candidates = set(manifest.candidate_retries.candidate_keys)
    unapproved = sorted(
        candidate.key for candidate in candidates
        if candidate.key not in approved_candidates
    )
    if unapproved:
        raise ValueError(
            "Candidates are absent from the reviewed rollout manifest: "
            + ", ".join(unapproved)
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


def _run_due_sources(
    db,
    sources_by_id: dict[str, IngestionSource],
    items,
    *,
    max_pages_override: int | None = None,
) -> tuple[bool, list[IngestionSource]]:
    failed = False
    attempted: list[IngestionSource] = []
    for item in items:
        if not item.due:
            continue
        source = sources_by_id[item.source_id]
        try:
            run_result = execute_source_run(
                db,
                source,
                max_pages=max_pages_override or item.max_pages_per_run,
                checkpoint=resolve_resume_checkpoint(db, source.id),
                trigger="scheduled",
            )
            attempted.append(source)
            failed = failed or run_result.status in {"failed", "partial_with_errors"}
            print(
                f"{source.key}: status={run_result.status} "
                f"seen={run_result.records_seen} inserted={run_result.records_inserted} "
                f"updated={run_result.records_updated} failed={run_result.records_failed}"
            )
        except ActiveRunConflict:
            db.rollback()
            print(f"{source.key}: status=concurrent_claim")
        except Exception as exc:
            failed = True
            db.rollback()
            print(f"{source.key}: error={exc}")
    return failed, attempted


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
    if args.command == "catalog" and args.catalog_command == "host-audit":
        try:
            entries = load_catalog(args.path)
            entries = _scope_catalog_entries(
                entries,
                source_keys=args.source_keys,
                stage=args.stage,
                shard_count=args.shard_count,
                shard_index=args.shard_index,
                rollout_wave=args.rollout_wave,
            )
            report = audit_ingestion_hosts(
                entries,
                allowed_hosts=args.allowed_hosts,
            )
            if args.print_required_hosts:
                print(",".join(report.required_hosts))
            elif args.print_policy_digest:
                print(report.policy_digest)
            elif args.json:
                print(json.dumps(asdict(report), sort_keys=True))
            else:
                status = "ready" if report.ready else "blocked"
                print(
                    f"host policy: {status} sources={report.source_count} "
                    f"required={report.required_host_count} "
                    f"configured={report.configured_host_count}"
                )
                if report.missing_hosts:
                    print(f"missing hosts: {','.join(report.missing_hosts)}")
                for source in report.unsafe_sources:
                    print(f"unsafe source {source.source_key}: {source.reason}")
            audit_ready = report.coverage_ready if args.allow_unused_hosts else report.ready
            if args.print_required_hosts:
                return 0 if not report.unsafe_sources else 1
            if args.print_policy_digest:
                return 0 if report.coverage_ready else 1
            return 0 if audit_ready else 1
        except Exception as exc:
            print(f"error: {exc}")
            return 1
    if args.command == "catalog" and args.catalog_command == "rollout-manifest":
        try:
            content = rollout_manifest_json(build_production_rollout_manifest(
                load_catalog(),
                candidates=load_candidate_catalog(),
                shard_count=args.shard_count,
            ))
            output_path = args.output or DEFAULT_ROLLOUT_MANIFEST_PATH
            if args.check:
                if not output_path.exists() or output_path.read_text(encoding="utf-8") != content:
                    print(f"error: rollout manifest is stale: {output_path}")
                    return 1
                print(f"rollout manifest is current: {output_path}")
            elif args.output:
                output_path.write_text(content, encoding="utf-8")
                print(f"wrote rollout manifest to {output_path}")
            else:
                print(content, end="")
            return 0
        except Exception as exc:
            print(f"error: {exc}")
            return 1
    if args.command == "catalog" and args.catalog_command == "candidate-host-audit":
        try:
            candidates = [
                candidate for candidate in load_candidate_catalog()
                if candidate.can_run_canary
            ]
            if args.candidate_keys:
                by_key = {candidate.key: candidate for candidate in candidates}
                missing = sorted(set(args.candidate_keys) - set(by_key))
                if missing:
                    raise ValueError(
                        "Runnable ingestion candidate not found: " + ", ".join(missing)
                    )
                candidates = [
                    by_key[key] for key in dict.fromkeys(args.candidate_keys)
                ]
            report = audit_ingestion_hosts(
                candidate_host_policy_entries(candidates),
                allowed_hosts=args.allowed_hosts,
            )
            if args.print_required_hosts:
                print(",".join(report.required_hosts))
            elif args.print_policy_digest:
                print(report.policy_digest)
            elif args.json:
                print(json.dumps(asdict(report), sort_keys=True))
            else:
                status = "ready" if report.ready else "blocked"
                print(
                    f"candidate host policy: {status} candidates={len(candidates)} "
                    f"required={report.required_host_count} "
                    f"configured={report.configured_host_count}"
                )
                if report.missing_hosts:
                    print(f"missing hosts: {','.join(report.missing_hosts)}")
                for source in report.unsafe_sources:
                    print(f"unsafe candidate {source.source_key}: {source.reason}")
            if args.print_required_hosts:
                return 0 if not report.unsafe_sources else 1
            if args.print_policy_digest:
                return 0 if report.coverage_ready else 1
            return 0 if report.ready else 1
        except Exception as exc:
            print(f"error: {exc}")
            return 1
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
    if args.command == "catalog" and args.catalog_command == "source-request":
        try:
            candidates = {
                candidate.key: candidate for candidate in load_candidate_catalog()
            }
            candidate = candidates.get(args.candidate_key)
            if candidate is None:
                raise ValueError(
                    f"Ingestion candidate not found: {args.candidate_key}"
                )
            contract = build_source_access_contract(candidate)
            content = (
                source_access_contract_json(contract)
                if args.format == "json"
                else source_access_contract_markdown(contract)
            )
            if args.output:
                args.output.write_text(content, encoding="utf-8")
                print(f"wrote source access request to {args.output}")
            else:
                print(content, end="")
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

        if args.command == "publish-build-signals":
            stages = {"approved"} if args.stage == "approved_only" else {
                "pre_approval", "approved"
            }
            permits = list_exportable_permits(
                db,
                source_keys=args.source_keys,
                stages=stages,
                limit=args.limit,
            )
            batches = build_batches(permits)
            if args.dry_run:
                content = json.dumps(batches, indent=2, sort_keys=True) + "\n"
                if args.output:
                    args.output.write_text(content, encoding="utf-8")
                    print(
                        f"wrote {len(batches)} Build Signals batches "
                        f"({len(permits)} records) to {args.output}"
                    )
                else:
                    print(content, end="")
                return 0
            if not args.target_url:
                raise ValueError(
                    "--target-url or BUILD_SIGNALS_INGESTION_URL is required"
                )
            secret = os.environ.get("BUILD_SIGNALS_INGESTION_SECRET", "")
            inserted = updated = found = 0
            for batch in batches:
                result = publish_batch(args.target_url, secret, batch)
                found += result.records_found
                inserted += result.records_inserted
                updated += result.records_updated
                print(
                    f"published {result.source_key} batch={result.batch_id} "
                    f"found={result.records_found} inserted={result.records_inserted} "
                    f"updated={result.records_updated}"
                )
            print(
                f"Build Signals publish complete: batches={len(batches)} "
                f"found={found} inserted={inserted} updated={updated}"
            )
            return 0

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
            rollout_manifest = require_current_rollout_manifest(
                load_catalog(), candidates=load_candidate_catalog()
            )
            _enforce_rollout_manifest_attestation(rollout_manifest)
            _validate_candidate_rollout_scope(
                rollout_manifest, selected, sample_size=args.sample_size
            )
            _enforce_catalog_host_policy(candidate_host_policy_entries(selected))
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
            scoped_catalog_entries = [
                entry for entry in catalog_entries if entry.key in set(args.source_keys)
            ]
            _enforce_catalog_host_policy(scoped_catalog_entries)
            sync_result = sync_catalog(db, scoped_catalog_entries)
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

        if args.command == "scheduled-due":
            if args.as_of is not None and not args.plan_only:
                raise ValueError("--as-of requires --plan-only")
            if (
                ENVIRONMENT == "production"
                and not args.plan_only
                and args.rollout_wave is None
            ):
                raise ValueError(
                    "Production scheduled execution requires --rollout-wave"
                )
            catalog_entries = load_catalog()
            if args.source_keys:
                _validate_catalog_source_keys(catalog_entries, args.source_keys)
            scoped_catalog_entries = _scope_catalog_entries(
                catalog_entries,
                source_keys=args.source_keys,
                stage=args.stage,
                shard_count=args.shard_count,
                shard_index=args.shard_index,
                rollout_wave=args.rollout_wave,
            )
            if args.rollout_wave is not None:
                rollout_manifest = require_current_rollout_manifest(
                    catalog_entries,
                    candidates=load_candidate_catalog(),
                )
                _enforce_rollout_manifest_attestation(rollout_manifest)
                approved_wave_keys = set(
                    rollout_manifest.waves[args.rollout_wave - 1].source_keys
                )
                unapproved = sorted(
                    entry.key for entry in scoped_catalog_entries
                    if entry.key not in approved_wave_keys
                )
                if unapproved:
                    raise ValueError(
                        "Sources are absent from the reviewed rollout wave: "
                        + ", ".join(unapproved)
                    )
            if not args.plan_only:
                _enforce_catalog_host_policy(scoped_catalog_entries)
            sync_result = sync_catalog(
                db, scoped_catalog_entries, dry_run=args.plan_only
            )
            if args.plan_only:
                db.rollback()
            else:
                db.commit()
            print(
                f"catalog sync: created={sync_result.created} updated={sync_result.updated} "
                f"unchanged={sync_result.unchanged} dry_run={args.plan_only}"
            )
            policies_by_key = {
                entry.key: source_schedule_policy(entry) for entry in catalog_entries
            }
            runtime_sources = list_sources(db)
            runtime_keys = {source.key for source in runtime_sources}
            scoped_catalog_keys = {entry.key for entry in scoped_catalog_entries}
            selected = [
                source
                for source in _select_sources(
                    db, source_keys=args.source_keys, stage=args.stage
                )
                if source.is_active and source.key in scoped_catalog_keys
            ]
            plan = build_schedule_plan(
                db,
                selected,
                as_of=args.as_of,
                shard_count=args.shard_count,
                shard_index=args.shard_index,
                policies_by_key=policies_by_key,
                catalog_source_count=len(scoped_catalog_keys),
                unsynced_source_keys=scoped_catalog_keys - runtime_keys,
            )
            print(json.dumps(asdict(plan), default=str, sort_keys=True))
            if args.plan_only or not plan.due_source_count:
                return 0
            run_failed, attempted = _run_due_sources(
                db,
                {source.id: source for source in selected},
                plan.items,
                max_pages_override=args.max_pages_per_source,
            )
            health_exit = _report_health(db, attempted)
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
