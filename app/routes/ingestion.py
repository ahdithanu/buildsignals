from __future__ import annotations

import hmac
import os
from dataclasses import asdict
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.ingestion import (
    IngestionCandidateCanaryAttempt,
    IngestionRun,
    PermitRecord,
)
from app.models.organization_membership import MemberRole
from app.schemas.graph import (
    GraphEntityResponse,
    GraphRelatedEntityResponse,
    GraphRelationshipResponse,
)
from app.schemas.ingestion import (
    CandidateCanaryAttemptResponse,
    CandidateCanaryResponse,
    IngestionCandidateResponse,
    IngestionCoverageResponse,
    IngestionHostPolicyResponse,
    IngestionReliabilitySummaryResponse,
    IngestionRunRequest,
    IngestionRunResponse,
    IngestionSourceCreate,
    IngestionSourceResponse,
    IngestionSourceUpdate,
    PermitDetailResponse,
    PermitEventResponse,
    PermitRecordResponse,
    SourceCanaryRequest,
    SourceCanaryResponse,
    SourceHealthResponse,
    SourceSchedulePlanResponse,
)
from app.schemas.measured_coverage import MeasuredCoverageResponse
from app.schemas.parcel_reference import PermitParcelCandidates
from app.services.brand_intelligence import list_permit_brand_matches
from app.services.graph_service import entity_for_record, relationships_for_entity
from app.services.ingestion.catalog import (
    catalog_source_for_candidate,
    load_candidate_catalog,
    load_catalog,
    normalize_state_code,
    summarize_coverage,
    sync_catalog,
)
from app.services.ingestion.health import (
    evaluate_source_health,
    list_candidate_canary_attempts,
    record_candidate_canary_attempt,
    summarize_ingestion_reliability,
    validate_candidate_source_canary,
    validate_source_canary,
)
from app.services.ingestion.host_policy import audit_ingestion_hosts
from app.services.ingestion.scheduling import build_schedule_plan, source_schedule_policy
from app.services.ingestion.service import (
    ActiveRunConflict,
    create_source,
    execute_source_run,
    get_permit_detail,
    get_source,
    list_sources,
    update_source,
)
from app.utils.auth_deps import get_current_user, require_role
from app.utils.org_scope import active_query

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.get(
    "/permits/{permit_id}/parcel-candidates", response_model=PermitParcelCandidates,
    dependencies=[Depends(get_current_user)],
)
def get_permit_parcel_candidates(
    permit_id: str,
    response: Response,
    parcel_source_id: str = Query(min_length=1, max_length=36),
    db: Session = Depends(get_db),
):
    from app.services.parcel_reference import permit_parcel_candidates

    response.headers["Cache-Control"] = "no-store"
    try:
        return permit_parcel_candidates(db, permit_id, parcel_source_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/coverage/measured", response_model=MeasuredCoverageResponse, dependencies=[Depends(get_current_user)])
def get_measured_coverage(
    response: Response,
    record_type: str = Query(default="parcel", pattern="^(parcel|permit|planning)$"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    freshness_hours: int = Query(default=72, ge=1, le=8760),
    db: Session = Depends(get_db),
):
    from app.services.ingestion.measured_coverage import measured_coverage

    response.headers["Cache-Control"] = "no-store"
    return measured_coverage(db, record_type=record_type, limit=limit,
                             offset=offset, freshness_hours=freshness_hours)


def _normalize_state_filter(state: str | None) -> str | None:
    state_code = normalize_state_code(state)
    if state is not None and state.strip() and state_code is None:
        raise HTTPException(status_code=422, detail="Invalid state filter")
    return state_code


@router.get("/sources", response_model=list[IngestionSourceResponse])
def get_sources(db: Session = Depends(get_db)):
    return list_sources(db)


@router.get("/health", response_model=list[SourceHealthResponse])
def get_ingestion_health(
    state: str | None = Query(default=None, max_length=50),
    db: Session = Depends(get_db),
):
    state_code = _normalize_state_filter(state)
    sources = list_sources(db)
    if state_code:
        sources = [source for source in sources if normalize_state_code(source.jurisdiction) == state_code]
    return [evaluate_source_health(db, source) for source in sources]


@router.get("/reliability-summary", response_model=IngestionReliabilitySummaryResponse)
def get_ingestion_reliability_summary(db: Session = Depends(get_db)):
    return IngestionReliabilitySummaryResponse.model_validate(
        asdict(summarize_ingestion_reliability(db))
    )


@router.get(
    "/schedule-plan",
    response_model=SourceSchedulePlanResponse,
    dependencies=[Depends(require_role(
        MemberRole.admin,
        MemberRole.editor,
        MemberRole.viewer,
    ))],
)
def get_ingestion_schedule_plan(
    state: str | None = Query(default=None, max_length=50),
    as_of: datetime | None = Query(default=None),
    shard_count: int = Query(default=1, ge=1, le=128),
    shard_index: int = Query(default=0, ge=0, le=127),
    db: Session = Depends(get_db),
):
    state_code = _normalize_state_filter(state)
    catalog_entries = load_catalog()
    if state_code:
        catalog_entries = [
            entry for entry in catalog_entries
            if normalize_state_code(entry.jurisdiction) == state_code
        ]
    catalog_keys = {entry.key for entry in catalog_entries}
    runtime_sources = list_sources(db)
    sources = [
        source for source in runtime_sources
        if source.is_active and source.key in catalog_keys
    ]
    runtime_keys = {source.key for source in runtime_sources}
    try:
        plan = build_schedule_plan(
            db,
            sources,
            as_of=as_of,
            shard_count=shard_count,
            shard_index=shard_index,
            policies_by_key={
                entry.key: source_schedule_policy(entry)
                for entry in catalog_entries
            },
            catalog_source_count=len(catalog_entries),
            unsynced_source_keys=catalog_keys - runtime_keys,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SourceSchedulePlanResponse.model_validate(asdict(plan))


@router.get(
    "/host-policy",
    response_model=IngestionHostPolicyResponse,
    dependencies=[Depends(require_role(
        MemberRole.admin,
        MemberRole.editor,
        MemberRole.viewer,
    ))],
)
def get_ingestion_host_policy():
    report = audit_ingestion_hosts(load_catalog())
    executor_name = os.environ.get("INGESTION_HOST_POLICY_EXECUTOR", "").strip() or None
    attested_digest = os.environ.get("INGESTION_HOST_POLICY_DIGEST", "").strip()
    executor_verified = bool(
        executor_name
        and attested_digest
        and hmac.compare_digest(attested_digest, report.policy_digest)
    )
    payload = asdict(report)
    payload.update({
        "ready": report.ready and executor_verified,
        "executor_name": executor_name,
        "executor_verified": executor_verified,
    })
    return IngestionHostPolicyResponse.model_validate(payload)


@router.get("/candidates", response_model=list[IngestionCandidateResponse])
def get_ingestion_candidates(
    state: str | None = Query(default=None, max_length=50),
    db: Session = Depends(get_db),
):
    state_code = _normalize_state_filter(state)
    candidates = load_candidate_catalog(include_promoted=True)
    catalog_entries = load_catalog()
    catalog_backed_keys = {
        candidate.key
        for candidate in candidates
        if catalog_source_for_candidate(candidate, catalog_entries) is not None
    }
    live_keys = {source.key for source in list_sources(db)}
    attempts = (
        active_query(db.query(IngestionCandidateCanaryAttempt), IngestionCandidateCanaryAttempt)
        .order_by(IngestionCandidateCanaryAttempt.created_at.desc())
        .all()
    )
    latest_by_key: dict[str, IngestionCandidateCanaryAttempt] = {}
    for attempt in attempts:
        if attempt.candidate_key not in latest_by_key:
            latest_by_key[attempt.candidate_key] = attempt
    response: list[IngestionCandidateResponse] = []
    for candidate in candidates:
        if candidate.key in live_keys:
            continue
        latest = latest_by_key.get(candidate.key)
        if state_code and normalize_state_code(candidate.jurisdiction) != state_code:
            continue
        payload = {
            **candidate.model_dump(),
            "catalog_backed": candidate.key in catalog_backed_keys,
            "last_canary_at": latest.created_at if latest else None,
            "last_canary_ok": latest.ok if latest else None,
            "last_canary_records_valid": latest.records_valid if latest else None,
            "last_canary_records_failed": latest.records_failed if latest else None,
        }
        response.append(IngestionCandidateResponse.model_validate(payload))
    return response


@router.get("/coverage", response_model=IngestionCoverageResponse)
def get_ingestion_coverage(db: Session = Depends(get_db)):
    return IngestionCoverageResponse.model_validate(
        asdict(summarize_coverage(live_sources=list_sources(db)))
    )


@router.post(
    "/candidates/{candidate_key}/canary",
    response_model=CandidateCanaryResponse,
    dependencies=[Depends(require_role(MemberRole.admin))],
)
def canary_candidate(
    candidate_key: str,
    payload: SourceCanaryRequest,
    db: Session = Depends(get_db),
):
    candidate = next(
        (
            entry
            for entry in load_candidate_catalog(include_promoted=True)
            if entry.key == candidate_key
        ),
        None,
    )
    if candidate is None:
        raise HTTPException(status_code=404, detail="Ingestion candidate not found")
    try:
        result = validate_candidate_source_canary(candidate, sample_size=payload.sample_size)
        record_candidate_canary_attempt(db, candidate, result, sample_size=payload.sample_size)
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail=f"Candidate canary failed: {exc}") from exc


@router.get(
    "/candidates/{candidate_key}/canary-history",
    response_model=list[CandidateCanaryAttemptResponse],
    dependencies=[Depends(require_role(MemberRole.admin))],
)
def get_candidate_canary_history(
    candidate_key: str,
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    candidate = next(
        (
            entry
            for entry in load_candidate_catalog(include_promoted=True)
            if entry.key == candidate_key
        ),
        None,
    )
    if candidate is None:
        raise HTTPException(status_code=404, detail="Ingestion candidate not found")
    return list_candidate_canary_attempts(db, candidate_key, limit=limit)


@router.get("/sources/{source_id}/health", response_model=SourceHealthResponse)
def get_source_health(source_id: str, db: Session = Depends(get_db)):
    source = get_source(db, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Ingestion source not found")
    return evaluate_source_health(db, source)


@router.post(
    "/sources",
    response_model=IngestionSourceResponse,
    status_code=201,
    dependencies=[Depends(require_role(MemberRole.admin))],
)
def add_source(payload: IngestionSourceCreate, db: Session = Depends(get_db)):
    try:
        source = create_source(db, payload)
        db.commit()
        return get_source(db, source.id)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/candidates/{candidate_key}/promote",
    response_model=IngestionSourceResponse,
    status_code=201,
    dependencies=[Depends(require_role(MemberRole.admin))],
)
def promote_candidate(candidate_key: str, db: Session = Depends(get_db)):
    candidate = next(
        (
            entry
            for entry in load_candidate_catalog(include_promoted=True)
            if entry.key == candidate_key
        ),
        None,
    )
    if candidate is None:
        raise HTTPException(status_code=404, detail="Ingestion candidate not found")
    latest_canary = (
        active_query(db.query(IngestionCandidateCanaryAttempt), IngestionCandidateCanaryAttempt)
        .filter(IngestionCandidateCanaryAttempt.candidate_key == candidate_key)
        .order_by(IngestionCandidateCanaryAttempt.created_at.desc())
        .first()
    )
    if (
        latest_canary is None
        or not latest_canary.ok
        or latest_canary.created_at.date() < candidate.next_audit_on
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "Candidate promotion requires a successful persisted canary "
                "on or after its current audit date"
            ),
        )
    try:
        production_source = catalog_source_for_candidate(candidate, load_catalog())
        if production_source is None:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Candidate has passed its canary but requires a reviewed "
                    "production catalog manifest before activation"
                ),
            )
        sync_catalog(db, [production_source])
        db.commit()
        refreshed = next(
            (source for source in list_sources(db) if source.key == candidate.key),
            None,
        )
        if refreshed is None:
            raise HTTPException(status_code=500, detail="Promoted source could not be loaded")
        return refreshed
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch(
    "/sources/{source_id}",
    response_model=IngestionSourceResponse,
    dependencies=[Depends(require_role(MemberRole.admin))],
)
def patch_source(source_id: str, payload: IngestionSourceUpdate, db: Session = Depends(get_db)):
    source = get_source(db, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Ingestion source not found")
    source = update_source(db, source, payload)
    db.commit()
    return get_source(db, source.id)


@router.post(
    "/sources/{source_id}/runs",
    response_model=IngestionRunResponse,
    status_code=201,
    dependencies=[Depends(require_role(MemberRole.admin))],
)
def run_source(source_id: str, payload: IngestionRunRequest, db: Session = Depends(get_db)):
    source = get_source(db, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Ingestion source not found")
    try:
        run = execute_source_run(
            db,
            source,
            max_pages=payload.max_pages,
            checkpoint=payload.checkpoint,
        )
    except ActiveRunConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return run


@router.post(
    "/sources/{source_id}/canary",
    response_model=SourceCanaryResponse,
    dependencies=[Depends(require_role(MemberRole.admin))],
)
def canary_source(
    source_id: str,
    payload: SourceCanaryRequest,
    db: Session = Depends(get_db),
):
    source = get_source(db, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Ingestion source not found")
    try:
        return validate_source_canary(source, sample_size=payload.sample_size)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Source canary failed: {exc}") from exc


@router.get("/runs", response_model=list[IngestionRunResponse])
def get_runs(
    source_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    query = active_query(db.query(IngestionRun), IngestionRun)
    if source_id:
        query = query.filter(IngestionRun.source_id == source_id)
    return query.order_by(IngestionRun.started_at.desc()).limit(limit).all()


@router.get("/permits", response_model=list[PermitRecordResponse])
def get_permits(
    source_id: str | None = Query(default=None),
    state: str | None = Query(default=None, max_length=50),
    status: str | None = Query(default=None, max_length=100),
    approval_stage: str | None = Query(
        default=None, pattern=r"^(pre_approval|approved)$"
    ),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = active_query(db.query(PermitRecord), PermitRecord).filter(
        PermitRecord.is_active.is_(True)
    )
    if source_id:
        query = query.filter(PermitRecord.source_id == source_id)
    if state:
        query = query.filter(PermitRecord.state == state)
    if status:
        query = query.filter(PermitRecord.status == status)
    if approval_stage:
        query = query.filter(PermitRecord.approval_stage == approval_stage)
    return query.order_by(PermitRecord.last_seen_at.desc()).limit(limit).all()


@router.get("/permits/{permit_id}", response_model=PermitDetailResponse)
def get_permit(permit_id: str, db: Session = Depends(get_db)):
    permit = get_permit_detail(db, permit_id)
    if permit is None:
        raise HTTPException(status_code=404, detail="Permit not found")

    graph_entity = entity_for_record(db, "permit", permit.id)
    graph_related = []
    seen_entities: set[tuple[str, str]] = set()
    if graph_entity is not None:
        primary_rows = relationships_for_entity(db, graph_entity.id)
        for relationship, entity, direction in primary_rows:
            key = (relationship.id, entity.id)
            if key in seen_entities:
                continue
            seen_entities.add(key)
            graph_related.append(
                GraphRelatedEntityResponse(
                    entity=GraphEntityResponse.model_validate(entity),
                    relationship=GraphRelationshipResponse.model_validate(relationship),
                    direction=direction,
                )
            )
            if getattr(relationship.relationship_type, "value", relationship.relationship_type) != "permit_for":
                continue
            for nested_relationship, nested_entity, nested_direction in relationships_for_entity(db, entity.id):
                if nested_entity.id == graph_entity.id:
                    continue
                nested_key = (nested_relationship.id, nested_entity.id)
                if nested_key in seen_entities:
                    continue
                seen_entities.add(nested_key)
                graph_related.append(
                    GraphRelatedEntityResponse(
                        entity=GraphEntityResponse.model_validate(nested_entity),
                        relationship=GraphRelationshipResponse.model_validate(nested_relationship),
                        direction=nested_direction,
                    )
                )

    return PermitDetailResponse(
        permit=PermitRecordResponse.model_validate(permit),
        source_key=permit.source.key,
        source_name=permit.source.name,
        source_landing_page=(permit.source.settings or {}).get("official_landing_page"),
        events=[
            PermitEventResponse.model_validate(event)
            for event in sorted(permit.events, key=lambda event: (event.occurred_at, event.created_at))
        ],
        brand_matches=list_permit_brand_matches(db, permit.id, limit=20),
        graph_entity=(
            {
                **GraphEntityResponse.model_validate(graph_entity).model_dump(),
                "aliases": [alias.alias for alias in graph_entity.aliases],
                "links": [
                    {"record_type": link.record_type, "record_id": link.record_id}
                    for link in graph_entity.links
                ],
                "related": [],
            }
            if graph_entity is not None
            else None
        ),
        graph_related=graph_related,
    )
