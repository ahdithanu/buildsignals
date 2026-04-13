from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.deal import Deal, DealStatus
from app.models.outreach_activity import OutreachActivity, ActivityType
from app.models.pipeline_event import PipelineEvent
from app.services.audit_service import log_change

STAGE_ORDER: list[str] = [
    "new",
    "qualified",
    "underwriting",
    "ic_review",
    "loi_sent",
    "psa",
    "closing",
    "closed",
]

TERMINAL_STAGES = {"closed", "dead"}


def _stage_index(stage: str) -> int:
    try:
        return STAGE_ORDER.index(stage)
    except ValueError:
        return -1


def validate_transition(from_stage: str, to_stage: str) -> None:
    """Raise HTTPException(400) if the transition is invalid."""
    if from_stage in TERMINAL_STAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from terminal stage '{from_stage}'.",
        )

    if to_stage == "dead":
        return  # any non-terminal stage can move to dead

    from_idx = _stage_index(from_stage)
    to_idx = _stage_index(to_stage)

    if from_idx == -1 or to_idx == -1:
        raise HTTPException(status_code=422, detail=f"Unknown stage '{to_stage}'.")

    if to_idx <= from_idx:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot move backward from '{from_stage}' to '{to_stage}'.",
        )


def move_deal_stage(
    db: Session,
    deal: Deal,
    new_stage: str,
    changed_by: str = "system",
) -> PipelineEvent:
    """Validate transition, update deal, create PipelineEvent + system activity log.

    Returns the created PipelineEvent.
    """
    old_stage = deal.status.value if isinstance(deal.status, DealStatus) else str(deal.status)

    # Validate the requested new_stage is a real DealStatus value
    try:
        new_status = DealStatus(new_stage)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unknown stage '{new_stage}'.")

    validate_transition(old_stage, new_stage)

    now = datetime.now(timezone.utc)

    # Update deal
    deal.status = new_status
    deal.updated_at = now

    # Create pipeline event
    event = PipelineEvent(
        deal_id=deal.id,
        from_stage=old_stage,
        to_stage=new_stage,
        changed_by=changed_by,
        created_at=now,
    )
    event.organization_id = deal.organization_id
    db.add(event)

    # Create system activity log
    activity = OutreachActivity(
        deal_id=deal.id,
        activity_type=ActivityType.system,
        subject=f"Deal moved from '{old_stage}' to '{new_stage}'",
        body=f"Stage transition by {changed_by}.",
        completed=True,
        created_at=now,
    )
    activity.organization_id = deal.organization_id
    db.add(activity)

    log_change(db, "deal", deal.id, "stage_change", old_values={"status": old_stage}, new_values={"status": new_stage}, actor_id=changed_by)

    db.flush()
    return event
