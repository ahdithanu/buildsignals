"""Explicit revision release transitions; no deployment or external distribution."""
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.buildsignal import BuildSignalPublication, BuildSignalReview
from app.schemas.buildsignal import PublicationCreate
from app.services.audit_service import log_change
from app.services.buildsignal_assessment import get_revision
from app.utils.org_scope import get_org_id, scope_query


def publication_history(db: Session, revision_id: str, limit: int = 50, skip: int = 0):
    get_revision(db, revision_id)
    return scope_query(db.query(BuildSignalPublication), BuildSignalPublication).filter_by(
        revision_id=revision_id,
    ).order_by(BuildSignalPublication.version.desc()).offset(skip).limit(limit).all()


def change_publication(db: Session, revision_id: str, payload: PublicationCreate, actor_id: str):
    # Review decisions acquire the same revision lock, serializing approval/release.
    revision = get_revision(db, revision_id, lock=True)
    latest = publication_history(db, revision_id, limit=1)
    previous = latest[0] if latest else None
    version = previous.version if previous else 0
    if payload.expected_version != version:
        raise HTTPException(409, "Publication changed; refresh before trying again")
    published = previous is not None and previous.action == "published"
    if (payload.action == "published") == published:
        raise HTTPException(409, "Revision is already published" if published else "Revision is not published")
    review = None
    if payload.action == "published":
        review = scope_query(db.query(BuildSignalReview), BuildSignalReview).filter_by(
            revision_id=revision.id,
        ).order_by(BuildSignalReview.created_at.desc(), BuildSignalReview.id.desc()).first()
        if (review is None or review.decision != "approved" or not review.reviewer_id
                or not revision.author_id or review.reviewer_id == revision.author_id):
            raise HTTPException(409, "Publication requires a current independent approval")
    row = BuildSignalPublication(
        organization_id=get_org_id(), revision_id=revision.id, actor_id=actor_id,
        review_id=review.id if review else None, version=version + 1,
        action=payload.action, rationale=payload.rationale,
    )
    db.add(row)
    try:
        db.flush()
        log_change(db, "buildsignal_publication", row.id, row.action, actor_id=actor_id,
                   organization_id=get_org_id(), new_values={"revision_id": revision.id, "version": row.version})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Publication changed; refresh before trying again") from None
    db.refresh(row)
    return row
