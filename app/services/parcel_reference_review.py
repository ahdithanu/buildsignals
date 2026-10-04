"""Explicit analyst acceptance of corroborated parcel identity candidates."""
from uuid import uuid4

from app.models.graph import GraphEntityType, GraphRelationship, GraphRelationshipType
from app.models.ingestion import PermitRecord, RawSourceRecord
from app.models.parcel import ParcelRecord
from app.schemas.graph import GraphEvidenceCreate, GraphRelationshipCreate
from app.schemas.parcel_reference import ParcelReferenceAcceptance
from app.services.audit_service import log_change
from app.services.graph_service import create_relationship, entity_for_record
from app.services.parcel_reference import permit_parcel_candidates
from app.utils.org_scope import active_query, get_org_id

REVIEW_SYSTEM = "reviewed_parcel_reference"


def accept_parcel_reference(db, permit_id: str, payload: ParcelReferenceAcceptance, *, actor_id: str):
    # Serialize competing reviews and ingestion updates to these canonical rows.
    permit = active_query(db.query(PermitRecord), PermitRecord).filter_by(
        id=permit_id, is_active=True,
    ).populate_existing().with_for_update().first()
    parcel = active_query(db.query(ParcelRecord), ParcelRecord).filter_by(
        id=payload.parcel_id, source_id=payload.parcel_source_id, is_active=True,
    ).populate_existing().with_for_update().first()
    if permit is None or parcel is None:
        raise LookupError("Permit or parcel not found")
    if (permit.latest_raw_record_id != payload.expected_permit_raw_id
            or parcel.latest_raw_record_id != payload.expected_parcel_raw_id):
        raise ValueError("Source evidence changed; reload and review the candidate")
    result = permit_parcel_candidates(db, permit_id, payload.parcel_source_id)
    if result["status"] != "candidate_requires_review" or result["truncated"]:
        raise ValueError("Acceptance requires exactly one current candidate")
    candidate = result["candidates"][0]
    if candidate["parcel_id"] != parcel.id or candidate["identity_assessment"] != "address_corroborated":
        raise ValueError("Acceptance requires corroborating state, city, and address evidence")
    raws = []
    for record, record_type in ((permit, "permit"), (parcel, "parcel")):
        raw = db.query(RawSourceRecord).filter_by(
            id=record.latest_raw_record_id, organization_id=get_org_id(),
            source_id=record.source_id, record_type=record_type,
        ).first()
        if raw is None:
            raise ValueError("Current source evidence is unavailable")
        raws.append(raw)
    permit_entity = entity_for_record(db, "permit", permit.id)
    parcel_entity = entity_for_record(db, "parcel", parcel.id)
    if (permit_entity is None or parcel_entity is None
            or permit_entity.entity_type != GraphEntityType.permit
            or parcel_entity.entity_type != GraphEntityType.parcel):
        raise ValueError("Typed graph entities must exist before acceptance")
    conflicting = active_query(db.query(GraphRelationship), GraphRelationship).filter(
        GraphRelationship.source_entity_id == permit_entity.id,
        GraphRelationship.relationship_type == GraphRelationshipType.permit_for,
        GraphRelationship.source_system == REVIEW_SYSTEM,
        GraphRelationship.is_current.is_(True),
        GraphRelationship.target_entity_id != parcel_entity.id,
    ).first()
    if conflicting:
        raise ValueError("Another parcel is already accepted; resolve the existing review first")
    review_id = str(uuid4())
    provenance = {
        "review_id": review_id, "actor_id": actor_id, "reason": payload.reason,
        "permit_id": permit.id, "parcel_id": parcel.id,
        "permit_raw_source_record_id": raws[0].id,
        "parcel_raw_source_record_id": raws[1].id,
        "permit_normalization_hash": permit.normalization_hash,
        "parcel_normalization_hash": parcel.normalization_hash,
        "confidence_kind": "analyst_assigned_not_calibrated",
        "requested_confidence": payload.confidence,
        "method": result["method"],
    }
    relationship = create_relationship(db, GraphRelationshipCreate(
        source_entity_id=permit_entity.id, target_entity_id=parcel_entity.id,
        relationship_type=GraphRelationshipType.permit_for,
        source_system=REVIEW_SYSTEM, source_id=f"{permit.id}:{parcel.id}",
        confidence=payload.confidence,
        evidence=[GraphEvidenceCreate(
            source_system=REVIEW_SYSTEM, source_id=f"{review_id}:{raw.id}",
            evidence_type="analyst_parcel_identity_acceptance", observed_at=raw.received_at,
            confidence=payload.confidence,
            payload={**provenance, "raw_source_record_id": raw.id, "record_type": raw.record_type},
        ) for raw in raws],
    ))
    log_change(db, "graph_relationship", relationship.id, "parcel_reference_accepted",
               actor_id=actor_id, new_values=provenance)
    db.flush()
    return relationship
