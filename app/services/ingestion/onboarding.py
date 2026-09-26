from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy.orm import Session

from app.models.ingestion import IngestionSource
from app.models.ingestion_onboarding import (
    OrganizationIngestionEnrollment,
    OrganizationIngestionEnrollmentSource,
)
from app.schemas.ingestion import IngestionSourceCreate
from app.services.ingestion.catalog import (
    US_STATE_CODES,
    CatalogSyncResult,
    extract_state_code,
    load_candidate_catalog,
    load_catalog,
    normalize_state_code,
    sync_catalog,
)
from app.services.ingestion.rollout import (
    require_current_rollout_manifest,
    source_rollout_wave,
)
from app.services.ingestion.scheduling import source_schedule_policy, source_shard
from app.utils.org_scope import active_query, get_org_id, get_user_id

ONBOARDING_REGIONS = (*US_STATE_CODES, "DC")
ONBOARDING_RECORD_TYPES = ("permit", "planning", "parcel")
ONBOARDING_ROLLOUT_WAVES = (1, 2, 3, 4)


@dataclass(frozen=True)
class OnboardingSourceItem:
    source_key: str
    source_name: str
    region: str
    jurisdiction: str | None
    record_type: str
    signal_stage: str
    rollout_wave: int
    shard_index: int
    schedule_mode: str
    interval_minutes: int
    max_pages_per_run: int


@dataclass(frozen=True)
class OnboardingRegionCoverage:
    region: str
    coverage_status: str
    source_count: int
    permit_source_count: int
    planning_source_count: int
    parcel_source_count: int
    pre_approval_source_count: int
    approved_only_source_count: int


@dataclass(frozen=True)
class IngestionOnboardingPlan:
    coverage_mode: str
    requested_regions: list[str]
    covered_regions: list[str]
    missing_regions: list[str]
    source_count: int
    permit_source_count: int
    planning_source_count: int
    parcel_source_count: int
    pre_approval_source_count: int
    approved_only_source_count: int
    automatic_source_count: int
    manual_source_count: int
    shard_count: int
    rollout_waves: list[int]
    regions: list[OnboardingRegionCoverage]
    sources: list[OnboardingSourceItem]


@dataclass(frozen=True)
class IngestionOnboardingActivation:
    plan: IngestionOnboardingPlan
    enrollment: OrganizationIngestionEnrollment | None
    catalog_created: int
    catalog_updated: int
    catalog_unchanged: int
    enrollment_sources_created: int
    enrollment_sources_updated: int
    enrollment_sources_unchanged: int
    enrollment_sources_removed: int
    dry_run: bool


def normalize_onboarding_region(value: str) -> str:
    normalized = value.strip()
    if normalized.upper() == "DC" or normalized.casefold() in {
        "district of columbia",
        "washington, dc",
        "washington dc",
    }:
        return "DC"
    state = normalize_state_code(normalized)
    if state is None:
        raise ValueError(f"Unsupported US state or district: {value}")
    return state


def source_region(entry: IngestionSourceCreate) -> str:
    state = extract_state_code(entry.jurisdiction, entry.settings or {})
    if state is not None:
        return state
    values = [entry.jurisdiction, (entry.settings or {}).get("state")]
    defaults = (entry.settings or {}).get("defaults")
    if isinstance(defaults, dict):
        values.append(defaults.get("state"))
    for value in values:
        if isinstance(value, str):
            try:
                if normalize_onboarding_region(value) == "DC":
                    return "DC"
            except ValueError:
                continue
    raise ValueError(f"Catalog source {entry.key} has no supported US region")


def build_ingestion_onboarding_plan(
    entries: Iterable[IngestionSourceCreate] | None = None,
    *,
    coverage_mode: str = "nationwide",
    regions: Iterable[str] | None = None,
    record_types: Iterable[str] | None = None,
    rollout_waves: Iterable[int] | None = None,
    shard_count: int = 4,
) -> IngestionOnboardingPlan:
    if shard_count < 1 or shard_count > 128:
        raise ValueError("shard_count must be between 1 and 128")
    requested_regions = _normalize_requested_regions(coverage_mode, regions)
    requested_types = _normalize_record_types(record_types)
    selected_waves = _normalize_rollout_waves(rollout_waves)
    selected_entries = [
        entry
        for entry in (list(entries) if entries is not None else load_catalog())
        if entry.is_active
        and source_region(entry) in requested_regions
        and entry.record_type in requested_types
        and source_rollout_wave(entry) in selected_waves
    ]
    selected_entries.sort(key=lambda entry: (source_region(entry), entry.key))
    sources = [_source_item(entry, shard_count=shard_count) for entry in selected_entries]
    covered_regions = sorted({source.region for source in sources})
    missing_regions = sorted(set(requested_regions) - set(covered_regions))

    return IngestionOnboardingPlan(
        coverage_mode=coverage_mode,
        requested_regions=requested_regions,
        covered_regions=covered_regions,
        missing_regions=missing_regions,
        source_count=len(sources),
        permit_source_count=sum(source.record_type == "permit" for source in sources),
        planning_source_count=sum(source.record_type == "planning" for source in sources),
        parcel_source_count=sum(source.record_type == "parcel" for source in sources),
        pre_approval_source_count=sum(
            source.signal_stage in {"pre_approval", "pre_approval_and_approved"}
            for source in sources
        ),
        approved_only_source_count=sum(
            source.signal_stage == "approved_only" for source in sources
        ),
        automatic_source_count=sum(source.schedule_mode == "automatic" for source in sources),
        manual_source_count=sum(source.schedule_mode == "manual" for source in sources),
        shard_count=shard_count,
        rollout_waves=selected_waves,
        regions=[_region_coverage(region, sources) for region in requested_regions],
        sources=sources,
    )


def get_ingestion_enrollment(
    db: Session,
    *,
    organization_id: str | None = None,
) -> OrganizationIngestionEnrollment | None:
    org_id = organization_id or get_org_id()
    return db.get(OrganizationIngestionEnrollment, org_id)


def list_ingestion_enrollment_sources(
    db: Session,
    *,
    organization_id: str | None = None,
) -> list[OrganizationIngestionEnrollmentSource]:
    org_id = organization_id or get_org_id()
    return (
        db.query(OrganizationIngestionEnrollmentSource)
        .filter(OrganizationIngestionEnrollmentSource.organization_id == org_id)
        .order_by(OrganizationIngestionEnrollmentSource.source_key)
        .all()
    )


def activate_ingestion_onboarding(
    db: Session,
    *,
    coverage_mode: str = "nationwide",
    regions: Iterable[str] | None = None,
    record_types: Iterable[str] | None = None,
    rollout_waves: Iterable[int] | None = None,
    shard_count: int = 4,
    enabled: bool = True,
    entries: Iterable[IngestionSourceCreate] | None = None,
    organization_id: str | None = None,
    created_by: str | None = None,
    dry_run: bool = False,
    now: datetime | None = None,
) -> IngestionOnboardingActivation:
    org_id = organization_id or get_org_id()
    if org_id != get_org_id():
        raise ValueError("Onboarding organization must match the active tenant")
    actor_id = created_by or get_user_id()
    current_time = now or datetime.now(timezone.utc)
    catalog_entries = list(entries) if entries is not None else load_catalog()
    plan = build_ingestion_onboarding_plan(
        catalog_entries,
        coverage_mode=coverage_mode,
        regions=regions,
        record_types=record_types,
        rollout_waves=rollout_waves,
        shard_count=shard_count,
    )
    by_key = {entry.key: entry for entry in catalog_entries}
    selected_entries = [by_key[source.source_key] for source in plan.sources]
    manifest = require_current_rollout_manifest(
        catalog_entries,
        candidates=load_candidate_catalog(),
    )
    catalog_result: CatalogSyncResult = sync_catalog(db, selected_entries, dry_run=dry_run)
    if dry_run:
        return IngestionOnboardingActivation(
            plan=plan,
            enrollment=None,
            catalog_created=catalog_result.created,
            catalog_updated=catalog_result.updated,
            catalog_unchanged=catalog_result.unchanged,
            enrollment_sources_created=0,
            enrollment_sources_updated=0,
            enrollment_sources_unchanged=0,
            enrollment_sources_removed=0,
            dry_run=True,
        )

    enrollment = db.get(OrganizationIngestionEnrollment, org_id)
    if enrollment is None:
        enrollment = OrganizationIngestionEnrollment(
            organization_id=org_id,
            created_by=actor_id,
            created_at=current_time,
        )
        db.add(enrollment)
    enrollment.enabled = enabled
    enrollment.coverage_mode = coverage_mode
    enrollment.state_codes = None if coverage_mode == "nationwide" else plan.requested_regions
    enrollment.record_types = sorted(set(record_types or ONBOARDING_RECORD_TYPES))
    enrollment.rollout_waves = plan.rollout_waves
    enrollment.shard_count = shard_count
    enrollment.catalog_manifest_digest = manifest.manifest_digest
    enrollment.last_catalog_sync_at = current_time
    enrollment.last_error = None
    enrollment.updated_at = current_time
    db.flush()

    runtime_sources = {
        source.key: source
        for source in active_query(db.query(IngestionSource), IngestionSource).filter(
            IngestionSource.key.in_([source.source_key for source in plan.sources])
        )
    }
    existing = {
        row.source_key: row
        for row in db.query(OrganizationIngestionEnrollmentSource).filter(
            OrganizationIngestionEnrollmentSource.organization_id == org_id
        )
    }
    created = updated = unchanged = removed = 0
    selected_keys: set[str] = set()
    for item in plan.sources:
        selected_keys.add(item.source_key)
        desired_status = "active" if item.schedule_mode == "automatic" else "manual"
        row = existing.get(item.source_key)
        if row is None:
            created += 1
            row = OrganizationIngestionEnrollmentSource(
                organization_id=org_id,
                source_key=item.source_key,
                status=desired_status,
                next_run_at=current_time if desired_status == "active" and enabled else None,
                created_at=current_time,
            )
            db.add(row)
        else:
            before = _enrollment_source_snapshot(row)
            if row.status != "paused":
                row.status = desired_status
        row.ingestion_source_id = (
            runtime_sources[item.source_key].id if item.source_key in runtime_sources else None
        )
        row.state_code = item.region
        row.record_type = item.record_type
        row.cadence_minutes = item.interval_minutes
        row.max_pages_per_run = item.max_pages_per_run
        if row.status not in {"active", "manual", "paused"}:
            row.status = desired_status
        if row.status == "active" and enabled:
            row.next_run_at = row.next_run_at or current_time
        elif row.status != "paused" or not enabled:
            row.next_run_at = None
        if row.status != "active":
            row.lease_token = None
            row.lease_expires_at = None
        if row.source_key in existing:
            if before == _enrollment_source_snapshot(row):
                unchanged += 1
            else:
                row.updated_at = current_time
                updated += 1

    for key, row in existing.items():
        if key in selected_keys or row.status == "removed":
            continue
        row.status = "removed"
        row.next_run_at = None
        row.lease_token = None
        row.lease_expires_at = None
        row.updated_at = current_time
        removed += 1

    db.flush()
    return IngestionOnboardingActivation(
        plan=plan,
        enrollment=enrollment,
        catalog_created=catalog_result.created,
        catalog_updated=catalog_result.updated,
        catalog_unchanged=catalog_result.unchanged,
        enrollment_sources_created=created,
        enrollment_sources_updated=updated,
        enrollment_sources_unchanged=unchanged,
        enrollment_sources_removed=removed,
        dry_run=False,
    )


def _normalize_requested_regions(
    coverage_mode: str,
    regions: Iterable[str] | None,
) -> list[str]:
    if coverage_mode not in {"nationwide", "selected_states"}:
        raise ValueError("coverage_mode must be nationwide or selected_states")
    supplied = list(regions or [])
    if coverage_mode == "nationwide":
        if supplied:
            raise ValueError("state_codes must be empty for nationwide coverage")
        return list(ONBOARDING_REGIONS)
    normalized = sorted({normalize_onboarding_region(region) for region in supplied})
    if not normalized:
        raise ValueError("selected_states coverage requires at least one state")
    return normalized


def _normalize_record_types(record_types: Iterable[str] | None) -> list[str]:
    selected = sorted(set(ONBOARDING_RECORD_TYPES if record_types is None else record_types))
    invalid = sorted(set(selected) - set(ONBOARDING_RECORD_TYPES))
    if invalid:
        raise ValueError(f"Unsupported onboarding record types: {', '.join(invalid)}")
    if not selected:
        raise ValueError("At least one onboarding record type is required")
    return selected


def _normalize_rollout_waves(rollout_waves: Iterable[int] | None) -> list[int]:
    selected = sorted(set(ONBOARDING_ROLLOUT_WAVES if rollout_waves is None else rollout_waves))
    invalid = sorted(set(selected) - set(ONBOARDING_ROLLOUT_WAVES))
    if invalid:
        raise ValueError("rollout_waves must contain values between 1 and 4")
    if not selected:
        raise ValueError("At least one rollout wave is required")
    return selected


def _source_item(
    entry: IngestionSourceCreate,
    *,
    shard_count: int,
) -> OnboardingSourceItem:
    policy = source_schedule_policy(entry)
    settings = entry.settings or {}
    return OnboardingSourceItem(
        source_key=entry.key,
        source_name=entry.name,
        region=source_region(entry),
        jurisdiction=entry.jurisdiction,
        record_type=entry.record_type,
        signal_stage=str(settings.get("signal_stage") or "unknown"),
        rollout_wave=source_rollout_wave(entry),
        shard_index=source_shard(entry.key, shard_count),
        schedule_mode=policy.schedule_mode,
        interval_minutes=policy.interval_minutes,
        max_pages_per_run=policy.max_pages_per_run,
    )


def _region_coverage(
    region: str,
    sources: list[OnboardingSourceItem],
) -> OnboardingRegionCoverage:
    regional = [source for source in sources if source.region == region]
    return OnboardingRegionCoverage(
        region=region,
        coverage_status="covered" if regional else "missing",
        source_count=len(regional),
        permit_source_count=sum(source.record_type == "permit" for source in regional),
        planning_source_count=sum(source.record_type == "planning" for source in regional),
        parcel_source_count=sum(source.record_type == "parcel" for source in regional),
        pre_approval_source_count=sum(
            source.signal_stage in {"pre_approval", "pre_approval_and_approved"}
            for source in regional
        ),
        approved_only_source_count=sum(
            source.signal_stage == "approved_only" for source in regional
        ),
    )


def _enrollment_source_snapshot(
    row: OrganizationIngestionEnrollmentSource,
) -> tuple[object, ...]:
    return (
        row.ingestion_source_id,
        row.state_code,
        row.record_type,
        row.cadence_minutes,
        row.max_pages_per_run,
        row.status,
        row.next_run_at,
        row.lease_token,
        row.lease_expires_at,
    )
