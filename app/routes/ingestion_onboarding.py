from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.organization_membership import MemberRole
from app.schemas.ingestion_onboarding import (
    IngestionEnrollmentResponse,
    IngestionEnrollmentSourceResponse,
    IngestionOnboardingActivationResponse,
    IngestionOnboardingPlanResponse,
    IngestionOnboardingRequest,
)
from app.services.audit_service import log_change
from app.services.ingestion.onboarding import (
    activate_ingestion_onboarding,
    build_ingestion_onboarding_plan,
    get_ingestion_enrollment,
    list_ingestion_enrollment_sources,
)
from app.utils.auth_deps import require_role_strict

router = APIRouter(prefix="/ingestion/onboarding", tags=["ingestion-onboarding"])


def _enrollment_payload(db: Session, enrollment) -> dict:
    return {
        **IngestionEnrollmentResponse.model_validate(enrollment).model_dump(),
        "sources": [
            IngestionEnrollmentSourceResponse.model_validate(source).model_dump()
            for source in list_ingestion_enrollment_sources(db)
        ],
    }


@router.post(
    "/plan",
    response_model=IngestionOnboardingPlanResponse,
)
def plan_ingestion_onboarding(
    payload: IngestionOnboardingRequest,
    _principal: dict = Depends(
        require_role_strict(
            MemberRole.admin,
            MemberRole.editor,
            MemberRole.viewer,
        )
    ),
):
    try:
        return IngestionOnboardingPlanResponse.model_validate(
            asdict(
                build_ingestion_onboarding_plan(
                    coverage_mode=payload.coverage_mode,
                    regions=payload.state_codes,
                    record_types=payload.record_types,
                    rollout_waves=payload.rollout_waves,
                    shard_count=payload.shard_count,
                )
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/enrollment",
    response_model=IngestionEnrollmentResponse,
)
def get_current_ingestion_enrollment(
    _principal: dict = Depends(
        require_role_strict(
            MemberRole.admin,
            MemberRole.editor,
            MemberRole.viewer,
        )
    ),
    db: Session = Depends(get_db),
):
    enrollment = get_ingestion_enrollment(db)
    if enrollment is None:
        raise HTTPException(status_code=404, detail="Ingestion enrollment not found")
    return _enrollment_payload(db, enrollment)


@router.put(
    "/enrollment",
    response_model=IngestionOnboardingActivationResponse,
)
def put_ingestion_enrollment(
    payload: IngestionOnboardingRequest,
    principal: dict = Depends(require_role_strict(MemberRole.admin)),
    db: Session = Depends(get_db),
):
    try:
        existing = get_ingestion_enrollment(db)
        activation = activate_ingestion_onboarding(
            db,
            coverage_mode=payload.coverage_mode,
            regions=payload.state_codes,
            record_types=payload.record_types,
            rollout_waves=payload.rollout_waves,
            shard_count=payload.shard_count,
            enabled=payload.enabled,
            created_by=principal["user_id"],
        )
        log_change(
            db,
            "ingestion_enrollment",
            principal["org_id"],
            "updated" if existing is not None else "created",
            actor_id=principal["user_id"],
            organization_id=principal["org_id"],
            new_values={
                "coverage_mode": payload.coverage_mode,
                "state_codes": payload.state_codes,
                "record_types": payload.record_types,
                "rollout_waves": payload.rollout_waves,
                "shard_count": payload.shard_count,
                "enabled": payload.enabled,
                "source_count": activation.plan.source_count,
                "missing_regions": activation.plan.missing_regions,
            },
        )
        db.commit()
        enrollment = get_ingestion_enrollment(db)
        if enrollment is None:
            raise RuntimeError("Ingestion enrollment was not persisted")
        return IngestionOnboardingActivationResponse.model_validate(
            {
                "plan": asdict(activation.plan),
                "enrollment": _enrollment_payload(db, enrollment),
                "catalog_created": activation.catalog_created,
                "catalog_updated": activation.catalog_updated,
                "catalog_unchanged": activation.catalog_unchanged,
                "enrollment_sources_created": activation.enrollment_sources_created,
                "enrollment_sources_updated": activation.enrollment_sources_updated,
                "enrollment_sources_unchanged": activation.enrollment_sources_unchanged,
                "enrollment_sources_removed": activation.enrollment_sources_removed,
                "dry_run": activation.dry_run,
            }
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise
