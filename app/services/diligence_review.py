import hashlib

from sqlalchemy.orm import Session

from app.models.diligence_review import DiligenceReview
from app.models.document import Document
from app.schemas.diligence_review import DiligenceReviewCreate
from app.services.audit_service import log_change
from app.utils.org_scope import active_query, get_org_id


def review_excerpt(db: Session, deal_id: str, payload: DiligenceReviewCreate, actor_id: str):
    doc = active_query(db.query(Document), Document).filter(
        Document.id == payload.document_id, Document.deal_id == deal_id,
    ).with_for_update().populate_existing().first()
    if doc is None or not isinstance(doc.evidence_excerpt, dict):
        raise LookupError("Document excerpt not found")
    evidence = doc.evidence_excerpt
    text = evidence.get("text")
    if not isinstance(text, str) or hashlib.sha256(text.encode()).hexdigest() != evidence.get("text_sha256"):
        raise ValueError("Excerpt integrity check failed")
    if evidence["text_sha256"] != payload.expected_text_sha256:
        raise ValueError("Excerpt changed; reload before reviewing")
    snapshot = {
        "schema_version": "diligence-review-v2", "assessment": payload.assessment,
        "rationale": payload.rationale, "evidence": dict(evidence),
        "document_type": doc.doc_type, "independently_verified": False,
        "changes_screening_result": False,
        "observation": payload.observation.model_dump(mode="json") if payload.observation else None,
    }
    row = DiligenceReview(organization_id=get_org_id(), deal_id=deal_id, document_id=doc.id,
                          reviewer_id=actor_id, criterion=payload.criterion, snapshot=snapshot)
    db.add(row)
    db.flush()
    log_change(db, "diligence_review", row.id, "create", actor_id=actor_id,
               new_values={"deal_id": deal_id, "document_id": doc.id,
                           "criterion": row.criterion, "assessment": payload.assessment,
                           "text_sha256": evidence["text_sha256"]})
    return row
