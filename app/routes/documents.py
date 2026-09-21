from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.deal import Deal
from app.models.document import Document
from app.models.organization_membership import MemberRole
from app.schemas.document import DocumentCreate, DocumentResponse
from app.schemas.document_evidence import DocumentExcerptCreate
from app.services.document_evidence import store_document_excerpt
from app.utils.auth_deps import get_current_user, require_role
from app.utils.org_scope import active_query, get_org_id

router = APIRouter(tags=["documents"])


@router.post("/deals/{deal_id}/document-excerpts", response_model=DocumentResponse, status_code=201,
             dependencies=[Depends(require_role(MemberRole.admin, MemberRole.editor))])
def create_document_excerpt(deal_id: str, payload: DocumentExcerptCreate, response: Response,
                            principal: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    if active_query(db.query(Deal), Deal).filter(Deal.id == deal_id).first() is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    doc = store_document_excerpt(db, deal_id, payload, principal["user_id"])
    db.commit()
    db.refresh(doc)
    response.headers["Cache-Control"] = "no-store"
    return doc


@router.get("/deals/{deal_id}/documents/{document_id}/excerpt", dependencies=[Depends(get_current_user)])
def get_document_excerpt(deal_id: str, document_id: str, response: Response, db: Session = Depends(get_db)):
    if active_query(db.query(Deal), Deal).filter(Deal.id == deal_id).first() is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    doc = active_query(db.query(Document), Document).filter(
        Document.id == document_id, Document.deal_id == deal_id,
    ).first()
    if doc is None or doc.evidence_excerpt is None:
        raise HTTPException(status_code=404, detail="Document excerpt not found")
    response.headers["Cache-Control"] = "no-store"
    return {"document_id": doc.id, "deal_id": deal_id, "evidence": doc.evidence_excerpt}


# ── list documents for a deal ────────────────────────────────────────────────

@router.get("/deals/{deal_id}/documents", response_model=list[DocumentResponse])
def list_deal_documents(
    deal_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    deal = active_query(db.query(Deal), Deal).filter(Deal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")
    docs = (
        active_query(db.query(Document), Document)
        .filter(Document.deal_id == deal_id)
        .order_by(Document.uploaded_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return docs


# ── create document record (metadata only) ──────────────────────────────────

@router.post(
    "/deals/{deal_id}/documents",
    response_model=DocumentResponse,
    status_code=201,
    dependencies=[Depends(require_role(MemberRole.admin, MemberRole.editor))],
)
def create_document(
    deal_id: str,
    payload: DocumentCreate,
    db: Session = Depends(get_db),
):
    deal = active_query(db.query(Deal), Deal).filter(Deal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")
    doc = Document(deal_id=deal_id, **payload.model_dump())
    doc.organization_id = get_org_id()
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


# ── soft delete document ───────────────────────────────────────────────────

@router.delete(
    "/documents/{document_id}", status_code=204,
    dependencies=[Depends(require_role(MemberRole.admin))],
)
def delete_document(document_id: str, db: Session = Depends(get_db)):
    doc = active_query(db.query(Document), Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    doc.soft_delete()
    db.commit()
    return None
