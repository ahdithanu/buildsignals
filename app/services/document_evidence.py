"""Retain attributed text without claiming possession or verification of a file."""
import hashlib
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.document import Document
from app.schemas.document_evidence import DocumentExcerptCreate
from app.services.audit_service import log_change
from app.utils.org_scope import get_org_id


def store_document_excerpt(db: Session, deal_id: str, payload: DocumentExcerptCreate, actor_id: str):
    content = payload.text.encode("utf-8")
    digest = hashlib.sha256(content).hexdigest()
    evidence = {
        "schema_version": "document-excerpt-v1", "source_title": payload.source_title,
        "source_date": payload.source_date.isoformat(), "locator": payload.locator,
        "text": payload.text, "text_sha256": digest, "received_at": datetime.now(timezone.utc).isoformat(),
        "submitted_by": actor_id, "authorized_to_store": True,
        "evidence_kind": "analyst_provided_excerpt", "original_file_received": False,
        "independently_verified": False,
    }
    doc = Document(organization_id=get_org_id(), deal_id=deal_id, filename=payload.source_title,
                   doc_type=payload.document_type, created_by=actor_id, evidence_excerpt=evidence)
    db.add(doc)
    db.flush()
    log_change(db, "document", doc.id, "evidence_excerpt_created", actor_id=actor_id,
               new_values={"deal_id": deal_id, "text_sha256": digest, "text_size_bytes": len(content),
                           "document_type": payload.document_type, "independently_verified": False})
    return doc
