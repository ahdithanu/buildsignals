from __future__ import annotations

from collections.abc import Callable, Collection
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from time import monotonic
from typing import Protocol
from uuid import uuid4

from sqlalchemy import or_, update
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.ingestion import IngestionRun, IngestionSource
from app.models.ingestion_onboarding import (
    OrganizationIngestionEnrollment,
    OrganizationIngestionEnrollmentSource,
)
from app.models.organization import Organization
from app.services.ingestion.health import resolve_resume_checkpoint
from app.services.ingestion.service import execute_source_run
from app.utils.org_scope import (
    SYSTEM_USER_ID,
    RequestContext,
    reset_current_context,
    set_current_context,
)

SUCCESSFUL_RUN_STATUSES = frozenset({"completed", "partial"})
DEFAULT_LEASE_SECONDS = 60 * 60
DEFAULT_WALL_CLOCK_SECONDS = 50 * 60
DEFAULT_MAX_ORGANIZATIONS = 100
DEFAULT_MAX_SOURCES = 100
DEFAULT_MAX_SOURCES_PER_ORGANIZATION = 25
MAX_ERROR_LENGTH = 4000


class SessionFactory(Protocol):
    def __call__(self) -> Session: ...


RunSource = Callable[..., IngestionRun]
Clock = Callable[[], datetime]


@dataclass(frozen=True)
class DispatchSourceResult:
    organization_id: str
    source_key: str
    outcome: str
    run_id: str | None = None
    run_status: str | None = None
    error: str | None = None
    next_run_at: datetime | None = None


@dataclass
class DispatchResult:
    started_at: datetime
    completed_at: datetime
    organizations_considered: int = 0
    organizations_dispatched: int = 0
    sources_due: int = 0
    sources_claimed: int = 0
    sources_succeeded: int = 0
    sources_failed: int = 0
    sources_skipped: int = 0
    deadline_reached: bool = False
    plan_only: bool = False
    source_results: list[DispatchSourceResult] = field(default_factory=list)


def dispatch_enrolled_ingestion(
    *,
    session_factory: SessionFactory = SessionLocal,
    allowed_source_keys: Collection[str],
    catalog_manifest_digest: str | None = None,
    organization_ids: Collection[str] | None = None,
    max_organizations: int = DEFAULT_MAX_ORGANIZATIONS,
    max_sources: int = DEFAULT_MAX_SOURCES,
    max_sources_per_organization: int = DEFAULT_MAX_SOURCES_PER_ORGANIZATION,
    wall_clock_seconds: int = DEFAULT_WALL_CLOCK_SECONDS,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    plan_only: bool = False,
    now: Clock | None = None,
    run_source: RunSource = execute_source_run,
) -> DispatchResult:
    """Dispatch due catalog-backed sources across active customer organizations."""
    _validate_bounds(
        max_organizations=max_organizations,
        max_sources=max_sources,
        max_sources_per_organization=max_sources_per_organization,
        wall_clock_seconds=wall_clock_seconds,
        lease_seconds=lease_seconds,
    )
    clock = now or _utcnow
    started_at = clock()
    started_monotonic = monotonic()
    result = DispatchResult(
        started_at=started_at,
        completed_at=started_at,
        plan_only=plan_only,
    )
    reviewed_keys = frozenset(allowed_source_keys)
    if not reviewed_keys:
        result.completed_at = clock()
        return result

    organizations = _active_organization_ids(
        session_factory,
        requested_ids=organization_ids,
        limit=max_organizations,
    )
    result.organizations_considered = len(organizations)
    handled_sources = 0

    for organization_id in organizations:
        if handled_sources >= max_sources:
            break
        if monotonic() - started_monotonic >= wall_clock_seconds:
            result.deadline_reached = True
            break
        remaining = min(max_sources - handled_sources, max_sources_per_organization)
        org_results, due_count, claimed_count = _dispatch_organization(
            organization_id,
            session_factory=session_factory,
            allowed_source_keys=reviewed_keys,
            catalog_manifest_digest=catalog_manifest_digest,
            limit=remaining,
            lease_seconds=lease_seconds,
            deadline_monotonic=started_monotonic + wall_clock_seconds,
            plan_only=plan_only,
            clock=clock,
            run_source=run_source,
        )
        result.sources_due += due_count
        result.sources_claimed += claimed_count
        handled_sources += due_count if plan_only else claimed_count
        result.source_results.extend(org_results)
        if org_results:
            result.organizations_dispatched += 1
        if any(item.outcome == "deadline" for item in org_results):
            result.deadline_reached = True
            break

    result.sources_succeeded = sum(
        item.outcome == "succeeded" for item in result.source_results
    )
    result.sources_failed = sum(item.outcome == "failed" for item in result.source_results)
    result.sources_skipped = sum(
        item.outcome in {"skipped", "lease_lost", "deadline"}
        for item in result.source_results
    )
    result.completed_at = clock()
    return result


def _dispatch_organization(
    organization_id: str,
    *,
    session_factory: SessionFactory,
    allowed_source_keys: frozenset[str],
    catalog_manifest_digest: str | None,
    limit: int,
    lease_seconds: int,
    deadline_monotonic: float,
    plan_only: bool,
    clock: Clock,
    run_source: RunSource,
) -> tuple[list[DispatchSourceResult], int, int]:
    token = set_current_context(RequestContext(organization_id, SYSTEM_USER_ID))
    db = session_factory()
    results: list[DispatchSourceResult] = []
    due_count = claimed_count = 0
    try:
        dispatch_time = clock()
        enrollment = db.get(OrganizationIngestionEnrollment, organization_id)
        if enrollment is None or not enrollment.enabled:
            return results, due_count, claimed_count
        if (
            catalog_manifest_digest is not None
            and enrollment.catalog_manifest_digest != catalog_manifest_digest
        ):
            error = "Enrollment catalog manifest does not match the worker manifest"
            enrollment.last_dispatch_at = dispatch_time
            enrollment.last_error = error
            db.commit()
            return [
                DispatchSourceResult(
                    organization_id=organization_id,
                    source_key="*",
                    outcome="failed",
                    error=error,
                )
            ], due_count, claimed_count
        due_rows = _due_enrollment_sources(
            db,
            organization_id=organization_id,
            allowed_source_keys=allowed_source_keys,
            as_of=dispatch_time,
            limit=limit,
        )
        due_count = len(due_rows)
        enrollment.last_dispatch_at = dispatch_time
        enrollment.last_error = None
        db.commit()
        if plan_only:
            return [
                DispatchSourceResult(
                    organization_id=organization_id,
                    source_key=row.source_key,
                    outcome="planned",
                    next_run_at=row.next_run_at,
                )
                for row in due_rows
            ], due_count, claimed_count

        for due_row in due_rows:
            if monotonic() >= deadline_monotonic:
                results.append(
                    DispatchSourceResult(
                        organization_id=organization_id,
                        source_key=due_row.source_key,
                        outcome="deadline",
                        error="Dispatcher wall-clock limit reached",
                    )
                )
                break
            lease_token = uuid4().hex
            claimed = _claim_enrollment_source(
                db,
                row_id=due_row.id,
                organization_id=organization_id,
                as_of=clock(),
                lease_token=lease_token,
                lease_seconds=lease_seconds,
            )
            if claimed is None:
                results.append(
                    DispatchSourceResult(
                        organization_id=organization_id,
                        source_key=due_row.source_key,
                        outcome="skipped",
                    )
                )
                continue
            claimed_count += 1
            results.append(
                _execute_claimed_source(
                    db,
                    claimed,
                    lease_token=lease_token,
                    clock=clock,
                    run_source=run_source,
                )
            )

        failures = [item.error for item in results if item.error]
        enrollment = db.get(OrganizationIngestionEnrollment, organization_id)
        if enrollment is not None:
            enrollment.last_error = failures[0][:MAX_ERROR_LENGTH] if failures else None
            db.commit()
        return results, due_count, claimed_count
    except Exception as exc:
        db.rollback()
        error = _error_text(exc)
        enrollment = db.get(OrganizationIngestionEnrollment, organization_id)
        if enrollment is not None:
            enrollment.last_error = error
            enrollment.last_dispatch_at = clock()
            db.commit()
        results.append(
            DispatchSourceResult(
                organization_id=organization_id,
                source_key="*",
                outcome="failed",
                error=error,
            )
        )
        return results, due_count, claimed_count
    finally:
        db.close()
        reset_current_context(token)


def _execute_claimed_source(
    db: Session,
    row: OrganizationIngestionEnrollmentSource,
    *,
    lease_token: str,
    clock: Clock,
    run_source: RunSource,
) -> DispatchSourceResult:
    source = None
    if row.ingestion_source_id:
        source = db.get(IngestionSource, row.ingestion_source_id)
    if source is None or source.key != row.source_key or not source.is_active:
        error = "Enrolled ingestion source is missing, mismatched, or inactive"
        next_run_at = _complete_claim(
            db,
            row,
            lease_token=lease_token,
            succeeded=False,
            completed_at=clock(),
            error=error,
        )
        return DispatchSourceResult(
            organization_id=row.organization_id,
            source_key=row.source_key,
            outcome="failed",
            error=error,
            next_run_at=next_run_at,
        )

    run: IngestionRun | None = None
    error: str | None = None
    try:
        checkpoint = resolve_resume_checkpoint(db, source.id)
        run = run_source(
            db,
            source,
            max_pages=row.max_pages_per_run,
            checkpoint=checkpoint,
            trigger="customer_dispatch",
        )
        succeeded = run.status in SUCCESSFUL_RUN_STATUSES
        if not succeeded:
            error = run.error_message or f"Ingestion run ended with status {run.status}"
    except Exception as exc:
        db.rollback()
        succeeded = False
        error = _error_text(exc)

    next_run_at = _complete_claim(
        db,
        row,
        lease_token=lease_token,
        succeeded=succeeded,
        completed_at=clock(),
        error=error,
    )
    if next_run_at is None:
        return DispatchSourceResult(
            organization_id=row.organization_id,
            source_key=row.source_key,
            outcome="lease_lost",
            run_id=run.id if run else None,
            run_status=run.status if run else None,
            error="Enrollment source lease was lost before completion",
        )
    return DispatchSourceResult(
        organization_id=row.organization_id,
        source_key=row.source_key,
        outcome="succeeded" if succeeded else "failed",
        run_id=run.id if run else None,
        run_status=run.status if run else None,
        error=error,
        next_run_at=next_run_at,
    )


def _active_organization_ids(
    session_factory: SessionFactory,
    *,
    requested_ids: Collection[str] | None,
    limit: int,
) -> list[str]:
    db = session_factory()
    try:
        query = db.query(Organization.id).filter(Organization.is_active.is_(True))
        if requested_ids is not None:
            query = query.filter(Organization.id.in_(set(requested_ids)))
        return [row[0] for row in query.order_by(Organization.id).limit(limit).all()]
    finally:
        db.close()


def _due_enrollment_sources(
    db: Session,
    *,
    organization_id: str,
    allowed_source_keys: frozenset[str],
    as_of: datetime,
    limit: int,
) -> list[OrganizationIngestionEnrollmentSource]:
    return (
        db.query(OrganizationIngestionEnrollmentSource)
        .filter(
            OrganizationIngestionEnrollmentSource.organization_id == organization_id,
            OrganizationIngestionEnrollmentSource.source_key.in_(allowed_source_keys),
            OrganizationIngestionEnrollmentSource.status == "active",
            or_(
                OrganizationIngestionEnrollmentSource.next_run_at.is_(None),
                OrganizationIngestionEnrollmentSource.next_run_at <= as_of,
            ),
            or_(
                OrganizationIngestionEnrollmentSource.lease_expires_at.is_(None),
                OrganizationIngestionEnrollmentSource.lease_expires_at <= as_of,
            ),
        )
        .order_by(
            OrganizationIngestionEnrollmentSource.next_run_at,
            OrganizationIngestionEnrollmentSource.source_key,
        )
        .limit(limit)
        .all()
    )


def _claim_enrollment_source(
    db: Session,
    *,
    row_id: str,
    organization_id: str,
    as_of: datetime,
    lease_token: str,
    lease_seconds: int,
) -> OrganizationIngestionEnrollmentSource | None:
    result = db.execute(
        update(OrganizationIngestionEnrollmentSource)
        .where(
            OrganizationIngestionEnrollmentSource.id == row_id,
            OrganizationIngestionEnrollmentSource.organization_id == organization_id,
            OrganizationIngestionEnrollmentSource.status == "active",
            or_(
                OrganizationIngestionEnrollmentSource.next_run_at.is_(None),
                OrganizationIngestionEnrollmentSource.next_run_at <= as_of,
            ),
            or_(
                OrganizationIngestionEnrollmentSource.lease_expires_at.is_(None),
                OrganizationIngestionEnrollmentSource.lease_expires_at <= as_of,
            ),
        )
        .values(
            lease_token=lease_token,
            lease_expires_at=as_of + timedelta(seconds=lease_seconds),
            last_dispatched_at=as_of,
            updated_at=as_of,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        return None
    db.commit()
    return db.get(OrganizationIngestionEnrollmentSource, row_id)


def _complete_claim(
    db: Session,
    row: OrganizationIngestionEnrollmentSource,
    *,
    lease_token: str,
    succeeded: bool,
    completed_at: datetime,
    error: str | None,
) -> datetime | None:
    failures = 0 if succeeded else row.consecutive_failures + 1
    delay_minutes = (
        row.cadence_minutes
        if succeeded
        else min(row.cadence_minutes, 15 * (2 ** min(failures - 1, 6)), 24 * 60)
    )
    next_run_at = completed_at + timedelta(minutes=delay_minutes)
    values: dict[str, object] = {
        "lease_token": None,
        "lease_expires_at": None,
        "consecutive_failures": failures,
        "last_error": None if succeeded else (error or "Unknown ingestion failure")[:MAX_ERROR_LENGTH],
        "next_run_at": next_run_at,
        "updated_at": completed_at,
    }
    if succeeded:
        values["last_completed_at"] = completed_at
    result = db.execute(
        update(OrganizationIngestionEnrollmentSource)
        .where(
            OrganizationIngestionEnrollmentSource.id == row.id,
            OrganizationIngestionEnrollmentSource.organization_id == row.organization_id,
            OrganizationIngestionEnrollmentSource.lease_token == lease_token,
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        return None
    db.commit()
    return next_run_at


def _validate_bounds(
    *,
    max_organizations: int,
    max_sources: int,
    max_sources_per_organization: int,
    wall_clock_seconds: int,
    lease_seconds: int,
) -> None:
    values = {
        "max_organizations": max_organizations,
        "max_sources": max_sources,
        "max_sources_per_organization": max_sources_per_organization,
        "wall_clock_seconds": wall_clock_seconds,
        "lease_seconds": lease_seconds,
    }
    invalid = [name for name, value in values.items() if value < 1]
    if invalid:
        raise ValueError(f"Dispatcher bounds must be positive: {', '.join(invalid)}")
    if max_organizations > 10_000 or max_sources > 10_000:
        raise ValueError("Dispatcher organization and source limits cannot exceed 10000")
    if max_sources_per_organization > 1_000:
        raise ValueError("max_sources_per_organization cannot exceed 1000")
    if wall_clock_seconds > 24 * 60 * 60 or lease_seconds > 24 * 60 * 60:
        raise ValueError("Dispatcher wall-clock and lease limits cannot exceed 24 hours")
    if lease_seconds < wall_clock_seconds:
        raise ValueError("lease_seconds must be greater than or equal to wall_clock_seconds")


def _error_text(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"[:MAX_ERROR_LENGTH]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
