"""Resolve draft assessments against tenant-scoped evidence; never infer returns."""
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.graph import GraphEntity, GraphRelationship, GraphRelationshipEvidence
from app.models.signal import Signal
from app.schemas.buildsignal import (
    BuildSignalAssessmentDraft,
    BuildSignalAssessmentResponse,
    ResolvedCitation,
    ResolvedImplication,
)
from app.utils.org_scope import scope_query


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
