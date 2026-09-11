"""Resolve draft assessments against tenant-scoped evidence; never infer returns."""
import hashlib
import json
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.buildsignal import BuildSignalPublication, BuildSignalReview, BuildSignalRevision
from app.models.graph import GraphEntity, GraphRelationship, GraphRelationshipEvidence
from app.models.signal import Signal
from app.schemas.buildsignal import (
    AssessmentSourceVersion,
    BuildSignalAssessmentDraft,
    BuildSignalAssessmentResponse,
    BuildSignalReviewCreate,
    ResolvedCitation,
    ResolvedImplication,
)
from app.services.audit_service import log_change
from app.utils.org_scope import get_org_id, scope_query


def save_revision(db: Session, signal_id: str, draft: BuildSignalAssessmentDraft, author_id: str):
    snapshot = resolve_assessment(db, signal_id, draft, lock_sources=True)
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


def _utc(value: datetime | None) -> datetime | None:
    # SQLite strips timezone metadata from UTC graph timestamps.
    return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value


def assessment_source_version(
    evidence: GraphRelationshipEvidence, relationship: GraphRelationship,
) -> AssessmentSourceVersion:
    """V1 hashes a fixed JSON array of source strings, not unbounded payload metadata."""
    content = json.dumps([
        evidence.source_system, evidence.source_id, evidence.source_url,
        evidence.evidence_type, evidence.excerpt,
    ], ensure_ascii=False, separators=(",", ":"))
    return AssessmentSourceVersion(
        evidence_id=evidence.id,
        relationship_id=relationship.id,
        content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        observed_at=_utc(evidence.observed_at),
        created_at=_utc(evidence.created_at),
        confidence=evidence.confidence,
        source_entity_id=relationship.source_entity_id,
        target_entity_id=relationship.target_entity_id,
        relationship_updated_at=_utc(relationship.updated_at),
        relationship_last_verified_at=_utc(relationship.last_verified_at),
        relationship_is_current=relationship.is_current,
    )


def _version_matches(expected: AssessmentSourceVersion, actual: AssessmentSourceVersion) -> bool:
    def normalized(version):
        return {key: _utc(value) if isinstance(value, datetime) else value
                for key, value in version.model_dump().items()}
    return normalized(expected) == normalized(actual)


def resolve_assessment(
    db: Session, signal_id: str, draft: BuildSignalAssessmentDraft, *, lock_sources: bool = False,
) -> BuildSignalAssessmentResponse:
    signal = scope_query(db.query(Signal), Signal).filter(Signal.id == signal_id).first()
    if signal is None:
        raise HTTPException(404, "Signal not found")

    evidence_ids = {citation.evidence_id for citation in draft.citations}
    entity_ids = {item.entity_id for item in draft.implications}
    def rows(query, model):
        query = query.order_by(model.id).populate_existing()
        return (query.with_for_update() if lock_sources else query).all()

    # Consistent entity -> relationship -> evidence ordering bounds lock acquisition.
    # Re-read evidence under lock: its relationship may have changed since the ID lookup.
    entities = {
        row.id: row for row in rows(scope_query(db.query(GraphEntity), GraphEntity)
                                   .filter(GraphEntity.id.in_(entity_ids)), GraphEntity)
    }
    evidence_query = scope_query(db.query(GraphRelationshipEvidence), GraphRelationshipEvidence).filter(
        GraphRelationshipEvidence.id.in_(evidence_ids),
    )
    relationship_ids = {row.relationship_id for row in evidence_query.with_entities(
        GraphRelationshipEvidence.relationship_id,
    ).all()}
    relationships = {
        row.id: row for row in rows(scope_query(db.query(GraphRelationship), GraphRelationship)
                                   .filter(GraphRelationship.id.in_(relationship_ids)), GraphRelationship)
    }
    evidence = {row.id: row for row in rows(evidence_query, GraphRelationshipEvidence)}
    if set(evidence) != evidence_ids or set(entities) != entity_ids:
        raise HTTPException(404, "Assessment reference not found")
    if any(row.relationship_id not in relationships for row in evidence.values()):
        raise HTTPException(404, "Assessment reference not found")
    if draft.source_precondition is not None:
        for expected in draft.source_precondition.evidence:
            source = evidence[expected.evidence_id]
            actual = assessment_source_version(source, relationships[source.relationship_id])
            if not _version_matches(expected, actual):
                raise HTTPException(409, "Source evidence changed. Refresh citations and review before saving again.")

    for implication in draft.implications:
        for evidence_id in implication.evidence_ids:
            relationship = relationships[evidence[evidence_id].relationship_id]
            if implication.entity_id not in (relationship.source_entity_id, relationship.target_entity_id):
                raise HTTPException(422, "Implication evidence must involve its affected entity")

    flags = ["Analyst-authored hypothesis; source linkage does not validate investment causality."]
    if draft.source_precondition is None:
        flags.append("Source-version precondition omitted; the authoring snapshot was not verified.")
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
