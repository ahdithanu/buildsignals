from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.contact import Contact, ContactStatus
from app.models.deal import Deal, DealStatus
from app.schemas.contact import ContactCreate, ContactUpdate, ContactResponse
from app.services.pipeline_service import move_deal_stage
from app.utils.org_scope import get_org_id, active_query, exclude_deleted
from app.services.audit_service import log_change

router = APIRouter(tags=["contacts"])


def _get_deal_or_404(db: Session, deal_id: str) -> Deal:
    deal = active_query(db.query(Deal), Deal).filter(Deal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found.")
    return deal


def _get_contact_or_404(db: Session, contact_id: str) -> Contact:
    contact = db.get(Contact, contact_id)
    if contact and contact.deleted_at is not None:
        contact = None
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found.")
    return contact


# ── GET /deals/{deal_id}/contacts ──────────────────────────────────────────

@router.get("/deals/{deal_id}/contacts", response_model=list[ContactResponse])
def list_contacts(
    deal_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    _get_deal_or_404(db, deal_id)
    contacts = (
        active_query(db.query(Contact), Contact)
        .filter(Contact.deal_id == deal_id)
        .order_by(Contact.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return contacts


# ── POST /deals/{deal_id}/contacts ─────────────────────────────────────────

@router.post("/deals/{deal_id}/contacts", response_model=ContactResponse, status_code=201)
def create_contact(
    deal_id: str,
    payload: ContactCreate,
    db: Session = Depends(get_db),
):
    _get_deal_or_404(db, deal_id)

    contact = Contact(
        deal_id=deal_id,
        name=payload.name,
        role=payload.role,
        email=payload.email,
        phone=payload.phone,
        company=payload.company,
        status=ContactStatus(payload.status.value),
        notes=payload.notes,
    )
    contact.organization_id = get_org_id()
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


# ── PATCH /contacts/{contact_id} ──────────────────────────────────────────

@router.patch("/contacts/{contact_id}", response_model=ContactResponse)
def update_contact(
    contact_id: str,
    payload: ContactUpdate,
    db: Session = Depends(get_db),
):
    contact = _get_contact_or_404(db, contact_id)
    old_status = contact.status.value if contact.status else None

    update_data = payload.model_dump(exclude_unset=True)

    # Validate status enum value if provided
    if "status" in update_data and update_data["status"] is not None:
        try:
            ContactStatus(update_data["status"].value if hasattr(update_data["status"], "value") else update_data["status"])
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid contact status.")

    for field, value in update_data.items():
        if field == "status" and value is not None:
            setattr(contact, field, ContactStatus(value.value if hasattr(value, "value") else value))
        else:
            setattr(contact, field, value)

    # BUSINESS RULE: contact qualified → auto-advance deal from "new" to "qualified"
    if (
        payload.status is not None
        and payload.status.value == "qualified"
    ):
        deal = _get_deal_or_404(db, contact.deal_id)
        current_deal_status = deal.status.value if isinstance(deal.status, DealStatus) else str(deal.status)
        if current_deal_status == "new":
            move_deal_stage(db, deal, "qualified", changed_by="system")

    db.commit()

    new_status = contact.status.value if contact.status else None
    if new_status != old_status:
        log_change(db, "contact", contact.id, "status_change", old_values={"status": old_status}, new_values={"status": new_status})
        db.commit()

    db.refresh(contact)
    return contact


# ── DELETE /contacts/{contact_id} ────────────────────────────────────────

@router.delete("/contacts/{contact_id}", status_code=204)
def delete_contact(contact_id: str, db: Session = Depends(get_db)):
    contact = _get_contact_or_404(db, contact_id)
    old_name = contact.name
    contact.soft_delete()
    db.commit()
    log_change(db, "contact", contact.id, "soft_delete", old_values={"name": old_name})
    db.commit()
    return None
