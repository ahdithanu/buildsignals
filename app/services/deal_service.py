from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.deal import Deal
from app.models.deal_assumptions import DealAssumptions
from app.models.deal_outputs import DealOutputs
from app.schemas.assumptions import AssumptionsResponse
from app.schemas.deal import DealCreate, DealDetailResponse, DealResponse
from app.schemas.outputs import OutputsResponse
from app.services.graph_service import upsert_deal_graph_context
from app.services.normalization_service import normalize_property_type
from app.utils.org_scope import get_org_id


def create_deal_with_defaults(db: Session, payload: DealCreate) -> Deal:
    deal = Deal(**payload.model_dump())
    deal.organization_id = get_org_id()
    deal.property_type = normalize_property_type(deal.property_type)
    db.add(deal)
    db.flush()

    assumptions = DealAssumptions(deal_id=deal.id)
    assumptions.organization_id = get_org_id()
    outputs = DealOutputs(deal_id=deal.id)
    outputs.organization_id = get_org_id()
    db.add(assumptions)
    db.add(outputs)
    upsert_deal_graph_context(db, deal)
    db.flush()
    return deal


def deal_to_detail_response(deal: Deal) -> DealDetailResponse:
    data = DealResponse.model_validate(deal).model_dump()
    data["assumptions"] = (
        AssumptionsResponse.model_validate(deal.assumptions) if deal.assumptions else None
    )
    data["outputs"] = (
        OutputsResponse.model_validate(deal.outputs) if deal.outputs else None
    )
    data["contacts_count"] = len(deal.contacts) if deal.contacts else 0
    return DealDetailResponse(**data)
