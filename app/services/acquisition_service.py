from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session, joinedload

from app.models.acquisition import (
    ParcelAcquisitionActivity,
    ParcelAcquisitionCase,
    ParcelAcquisitionSource,
)
from app.models.organization_membership import OrganizationMembership
from app.models.parcel import NearbyParcelCandidate, NearbyParcelSearch, ParcelRecord
from app.models.user import User
from app.services.audit_service import log_change
from app.utils.org_scope import active_query, get_org_id

CASE_STATUSES = {"candidate", "shortlisted", "contacted", "dismissed", "promoted"}
ACTIVITY_TYPES = {"call", "email", "sms", "meeting", "note"}
def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_acquisition_case_for_candidate(
    db: Session,
    candidate: NearbyParcelCandidate,
) -> ParcelAcquisitionCase:
    organization_id = get_org_id()
    if candidate.organization_id != organization_id:
        raise ValueError("Parcel candidate belongs to another organization")
    parcel = active_query(db.query(ParcelRecord), ParcelRecord).filter(
        ParcelRecord.id == candidate.parcel_id
    ).with_for_update().first()
    search = active_query(db.query(NearbyParcelSearch), NearbyParcelSearch).filter(
        NearbyParcelSearch.id == candidate.search_id
    ).first()
    if parcel is None or search is None:
        raise ValueError("Parcel candidate references another organization")
    case = active_query(
        db.query(ParcelAcquisitionCase), ParcelAcquisitionCase
    ).filter(ParcelAcquisitionCase.parcel_id == candidate.parcel_id).first()
    if case is None:
        case = ParcelAcquisitionCase(
            organization_id=organization_id,
            parcel_id=candidate.parcel_id,
            status=candidate.review_status,
            assigned_to_user_id=candidate.assigned_to_user_id,
            assigned_to_name=candidate.assigned_to_name,
            assigned_by_user_id=candidate.assigned_by_user_id,
            assigned_at=candidate.assigned_at,
        )
        db.add(case)
        db.flush()
    existing_source = active_query(
        db.query(ParcelAcquisitionSource), ParcelAcquisitionSource
    ).filter(
        ParcelAcquisitionSource.case_id == case.id,
        ParcelAcquisitionSource.candidate_id == candidate.id,
    ).first()
    if existing_source is None:
        db.add(ParcelAcquisitionSource(
            organization_id=organization_id,
            case_id=case.id,
            candidate_id=candidate.id,
            search_id=candidate.search_id,
        ))
    db.flush()
    return case


def get_acquisition_case(
    db: Session, case_id: str
) -> ParcelAcquisitionCase | None:
    return active_query(
        db.query(ParcelAcquisitionCase), ParcelAcquisitionCase
    ).options(
        joinedload(ParcelAcquisitionCase.parcel),
        joinedload(ParcelAcquisitionCase.sources),
        joinedload(ParcelAcquisitionCase.activities),
    ).filter(ParcelAcquisitionCase.id == case_id).first()


def update_acquisition_case(
    db: Session,
    *,
    case_id: str,
    actor_user_id: str,
    status: str | None = None,
    assigned_to_user_id: str | None = None,
    assignment_supplied: bool = False,
    follow_up_at: datetime | None = None,
) -> ParcelAcquisitionCase | None:
    case = get_acquisition_case(db, case_id)
    if case is None:
        return None
    if status is not None and status not in CASE_STATUSES:
        raise ValueError("Invalid acquisition case status")
    old_values = _case_values(case)
    if status is not None:
        case.status = status
        if status == "contacted" and case.contacted_at is None:
            case.contacted_at = utcnow()
        if status in {"candidate", "shortlisted", "dismissed"}:
            candidate_ids = [source.candidate_id for source in case.sources]
            if candidate_ids:
                active_query(
                    db.query(NearbyParcelCandidate), NearbyParcelCandidate
                ).filter(NearbyParcelCandidate.id.in_(candidate_ids)).update(
                    {NearbyParcelCandidate.review_status: status},
                    synchronize_session=False,
                )
    if assignment_supplied and assigned_to_user_id is None:
        case.assigned_to_user_id = None
        case.assigned_to_name = None
        case.assigned_by_user_id = None
        case.assigned_at = None
        _sync_candidate_assignment(db, case)
    elif assigned_to_user_id is not None:
        membership = active_query(
            db.query(OrganizationMembership), OrganizationMembership
        ).join(User, User.id == OrganizationMembership.user_id).filter(
            OrganizationMembership.user_id == assigned_to_user_id,
        ).first()
        if membership is None:
            raise LookupError("Assignee is not a member of this organization")
        case.assigned_to_user_id = membership.user_id
        case.assigned_to_name = membership.user.full_name
        case.assigned_by_user_id = actor_user_id
        case.assigned_at = utcnow()
        _sync_candidate_assignment(db, case)
    if follow_up_at is not None:
        case.follow_up_at = follow_up_at
    log_change(
        db,
        "parcel_acquisition_case",
        case.id,
        "update",
        actor_id=actor_user_id,
        organization_id=get_org_id(),
        old_values=old_values,
        new_values=_case_values(case),
    )
    db.flush()
    return case


def record_acquisition_activity(
    db: Session,
    *,
    case_id: str,
    actor_user_id: str,
    activity_type: str,
    notes: str | None,
    occurred_at: datetime | None,
    follow_up_at: datetime | None,
) -> ParcelAcquisitionActivity:
    if activity_type not in ACTIVITY_TYPES:
        raise ValueError("Invalid acquisition activity type")
    case = get_acquisition_case(db, case_id)
    if case is None:
        raise LookupError("Parcel acquisition case not found")
    activity = ParcelAcquisitionActivity(
        organization_id=get_org_id(),
        case_id=case.id,
        activity_type=activity_type,
        notes=notes,
        actor_user_id=actor_user_id,
        occurred_at=occurred_at or utcnow(),
        follow_up_at=follow_up_at,
    )
    db.add(activity)
    if activity_type != "note":
        case.status = "contacted"
        case.contacted_at = activity.occurred_at
    if follow_up_at is not None:
        case.follow_up_at = follow_up_at
    log_change(
        db,
        "parcel_acquisition_case",
        case.id,
        "record_activity",
        actor_id=actor_user_id,
        organization_id=get_org_id(),
        new_values={
            "activity_type": activity_type,
            "occurred_at": activity.occurred_at.isoformat(),
            "follow_up_at": follow_up_at.isoformat() if follow_up_at else None,
            "status": case.status,
        },
    )
    db.flush()
    return activity


def _case_values(case: ParcelAcquisitionCase) -> dict:
    return {
        "status": case.status,
        "assigned_to_user_id": case.assigned_to_user_id,
        "assigned_to_name": case.assigned_to_name,
        "assigned_by_user_id": case.assigned_by_user_id,
        "assigned_at": case.assigned_at.isoformat() if case.assigned_at else None,
        "contacted_at": case.contacted_at.isoformat() if case.contacted_at else None,
        "follow_up_at": case.follow_up_at.isoformat() if case.follow_up_at else None,
        "promoted_deal_id": case.promoted_deal_id,
    }


def _sync_candidate_assignment(
    db: Session, case: ParcelAcquisitionCase
) -> None:
    candidate_ids = [source.candidate_id for source in case.sources]
    if not candidate_ids:
        return
    active_query(db.query(NearbyParcelCandidate), NearbyParcelCandidate).filter(
        NearbyParcelCandidate.id.in_(candidate_ids)
    ).update(
        {
            NearbyParcelCandidate.assigned_to_user_id: case.assigned_to_user_id,
            NearbyParcelCandidate.assigned_to_name: case.assigned_to_name,
            NearbyParcelCandidate.assigned_by_user_id: case.assigned_by_user_id,
            NearbyParcelCandidate.assigned_at: case.assigned_at,
        },
        synchronize_session=False,
    )
