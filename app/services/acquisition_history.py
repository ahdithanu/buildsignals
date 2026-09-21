"""Store the exact bytes delivered to the analyst, not a recomputed screen."""
import hashlib

from sqlalchemy.orm import Session

from app.models.acquisition_screen import AcquisitionScreenSnapshot
from app.models.diligence_review import DiligenceReview
from app.models.document import Document
from app.utils.org_scope import get_org_id, scope_query


def review_export_context(db: Session, deal_id: str) -> dict:
    """Bounded historical assessments, never inputs to computed screening."""
    limit = 10
    rows = scope_query(db.query(DiligenceReview), DiligenceReview).join(
        Document, Document.id == DiligenceReview.document_id,
    ).filter(
        DiligenceReview.deal_id == deal_id, Document.deal_id == deal_id,
        Document.organization_id == get_org_id(), Document.deleted_at.is_(None),
    ).order_by(DiligenceReview.created_at.desc(), DiligenceReview.id.desc()).limit(limit + 1).all()
    items = []
    for row in rows[:limit]:
        evidence = row.snapshot.get("evidence", {})
        text = evidence.get("text")
        if not isinstance(text, str) or hashlib.sha256(text.encode()).hexdigest() != evidence.get("text_sha256"):
            raise ValueError("Reviewed evidence integrity check failed")
        items.append({"id": row.id, "document_id": row.document_id,
                      "criterion": row.criterion, "reviewer_id": row.reviewer_id,
                      "created_at": row.created_at, "snapshot": row.snapshot})
    return {"items": items, "limit": limit, "has_more": len(rows) > limit,
            "order": "created_at_desc_id_desc", "scope": "opportunity",
            "changes_screening_result": False, "independently_verified": False}


def save_screen_snapshot(db: Session, deal_id: str, author_id: str, content: str):
    row = AcquisitionScreenSnapshot(
        organization_id=get_org_id(), deal_id=deal_id, author_id=author_id,
        content=content, content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
    )
    db.add(row)
    db.flush()
    return row


def verified_snapshot_content(row: AcquisitionScreenSnapshot) -> str:
    if hashlib.sha256(row.content.encode("utf-8")).hexdigest() != row.content_sha256:
        raise ValueError("Stored acquisition snapshot integrity check failed")
    return row.content
