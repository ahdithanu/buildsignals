"""Resolve draft assessments against tenant-scoped evidence; never infer returns."""
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.buildsignal import BuildSignalPublication, BuildSignalReview, BuildSignalRevision
from app.models.graph import GraphEntity, GraphRelationship, GraphRelationshipEvidence
from app.models.signal import Signal
from app.schemas.buildsignal import (
    BuildSignalAssessmentDraft,
    BuildSignalAssessmentResponse,
    BuildSignalReviewCreate,
    ResolvedCitation,
    ResolvedImplication,
)
from app.services.audit_service import log_change
from app.utils.org_scope import get_org_id, scope_query


def save_revision(db: Session, signal_id: str, draft: BuildSignalAssessmentDraft, author_id: str):
    snapshot = resolve_assessment(db, signal_id, draft)
    row = BuildSignalRevision(signal_id=signal_id, organization_id=get_org_id(),
                              author_id=author_id, snapshot=snapshot.model_dump(mode="json"))
    db.add(row)
    db.flush()
    log_change(db, "buildsignal_revision", row.id, "create", actor_id=author_id,
               organization_id=get_org_id(), new_values={"signal_id": signal_id})
    db.commit()
    db.refresh(row)
    return row


def get_revision(db: Session, revision_id: str, lock: bool = False):
    query = scope_query(db.query(BuildSignalRevision), BuildSignalRevision).filter_by(id=revision_id)
    row = (query.with_for_update() if lock else query).first()
    if row is None:
        raise HTTPException(404, "Assessment revision not found")
    return row


def review_revision(db: Session, revision_id: str, payload: BuildSignalReviewCreate, reviewer_id: str):
    revision = get_revision(db, revision_id, lock=True)
    if revision.author_id == reviewer_id:
        raise HTTPException(409, "A revision requires an independent reviewer")
    latest = scope_query(db.query(BuildSignalPublication), BuildSignalPublication).filter_by(
        revision_id=revision.id,
    ).order_by(BuildSignalPublication.version.desc()).first()
    if latest and latest.action == "published":
        raise HTTPException(409, "Withdraw the published revision before recording another review")
    row = BuildSignalReview(revision_id=revision.id, organization_id=get_org_id(),
                            reviewer_id=reviewer_id, **payload.model_dump())
    db.add(row)
    db.flush()
    log_change(db, "buildsignal_review", row.id, payload.decision, actor_id=reviewer_id,
               organization_id=get_org_id(), new_values={"revision_id": revision.id})
    db.commit()
    db.refresh(row)
    return row


def resolve_assessment(
    db: Session, signal_id: str, draft: BuildSignalAssessmentDraft,
) -> BuildSignalAssessmentResponse:
    signal = scope_query(db.query(Signal), Signal).filter(Signal.id == signal_id).first()
    if signal is None:
        raise HTTPException(404, "Signal not found")

    evidence_ids = {citation.evidence_id for citation in draft.citations}
    evidence = {
        row.id: row for row in scope_query(db.query(GraphRelationshipEvidence), GraphRelationshipEvidence)
        .filter(GraphRelationshipEvidence.id.in_(evidence_ids)).all()
    }
    entity_ids = {item.entity_id for item in draft.implications}
    entities = {
        row.id: row for row in scope_query(db.query(GraphEntity), GraphEntity)
        .filter(GraphEntity.id.in_(entity_ids)).all()
    }
    relationships = {
        row.id: row for row in scope_query(db.query(GraphRelationship), GraphRelationship)
        .filter(GraphRelationship.id.in_({row.relationship_id for row in evidence.values()})).all()
    }
    if set(evidence) != evidence_ids or set(entities) != entity_ids:
        raise HTTPException(404, "Assessment reference not found")
    if any(row.relationship_id not in relationships for row in evidence.values()):
        raise HTTPException(404, "Assessment reference not found")

    flags = ["Analyst-authored hypothesis; source linkage does not validate investment causality."]
    for claim in ("change", "thesis"):
        if not any(c.claim == claim and c.stance == "contradicts" for c in draft.citations):
            flags.append(f"No contradicting evidence supplied for {claim}; counterevidence review required.")
    if not any(c.claim == "thesis" and c.stance == "supports" for c in draft.citations):
        flags.append("Investment thesis has no supporting citation.")
    if any(not row.is_current for row in relationships.values()):
        flags.append("Includes historical relationships; verify their relevance to the event date.")
    if draft.event_at is None:
        flags.append("Event date is unknown; detection time is not the event date.")

    return BuildSignalAssessmentResponse(
        **draft.model_dump(exclude={"citations", "implications"}),
        signal_id=signal.id,
        generated_at=datetime.now(timezone.utc),
        citations=[ResolvedCitation(
            **citation.model_dump(),
            **{key: getattr(evidence[citation.evidence_id], key) for key in (
                "source_system", "source_id", "source_url", "excerpt", "observed_at", "relationship_id",
            )},
            relationship_is_current=relationships[evidence[citation.evidence_id].relationship_id].is_current,
            relationship_last_verified_at=(
                relationships[evidence[citation.evidence_id].relationship_id].last_verified_at
            ),
        ) for citation in draft.citations],
        implications=[ResolvedImplication(
            **item.model_dump(), entity_name=entities[item.entity_id].display_name,
            entity_type=entities[item.entity_id].entity_type.value,
        ) for item in draft.implications],
        review_flags=flags,
    )
