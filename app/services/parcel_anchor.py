"""Read-only, evidence-bound nearby anchors; never enrich permit coordinates."""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import LargeBinary, Text, cast, func

from app.models.audit_log import AuditLog
from app.models.brand import PermitBrandMatch
from app.models.deal import Deal
from app.models.graph import (
    GraphEntity,
    GraphEntityLink,
    GraphEntityType,
    GraphRelationship,
    GraphRelationshipEvidence,
    GraphRelationshipType,
)
from app.models.ingestion import PermitRecord, RawSourceRecord
from app.models.parcel import ParcelRecord
from app.services.brand_intelligence import list_deal_brand_matches
from app.services.parcel_reference import REVIEW_SYSTEM, permit_parcel_candidates
from app.utils.org_scope import active_query, get_org_id

MAX_REVIEW_ROWS = 64
MAX_AUDIT_ROWS = 32
MAX_PROVENANCE_BYTES = 16384
MAX_ACCEPTANCE_AGE = timedelta(days=90)


def _utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _coordinates(latitude, longitude):
    return (
        isinstance(latitude, (int, float)) and not isinstance(latitude, bool)
        and isinstance(longitude, (int, float)) and not isinstance(longitude, bool)
        and math.isfinite(latitude) and math.isfinite(longitude)
        and -90 <= latitude <= 90 and -180 <= longitude <= 180
    )


def _hash(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _typed_entities(db, record_type, record_id, entity_type):
    return active_query(db.query(GraphEntity), GraphEntity).join(
        GraphEntityLink, GraphEntityLink.entity_id == GraphEntity.id,
    ).filter(
        GraphEntityLink.organization_id == get_org_id(),
        GraphEntityLink.record_type == record_type, GraphEntityLink.record_id == record_id,
        GraphEntity.entity_type == entity_type,
    ).populate_existing().limit(2).all()


def _byte_size(db, column):
    value = cast(column, Text)
    if db.get_bind().dialect.name == "postgresql":
        return func.octet_length(value)
    return func.length(cast(value, LargeBinary))


def _review_is_authoritative(db, relationship, permit, parcel, now):
    evidence_size = _byte_size(db, GraphRelationshipEvidence.payload)
    audit_size = _byte_size(db, AuditLog.new_values)
    evidence_query = active_query(db.query(GraphRelationshipEvidence), GraphRelationshipEvidence).filter(
        GraphRelationshipEvidence.relationship_id == relationship.id,
    )
    audit_query = db.query(AuditLog).filter(
        AuditLog.organization_id == get_org_id(), AuditLog.entity_type == "graph_relationship",
        AuditLog.entity_id == relationship.id, AuditLog.action == "parcel_reference_accepted",
    )
    # Row limits are not byte limits. Check DB-side sizes before fetching review
    # bodies, and repeat the size predicates on retrieval to cover intervening edits.
    evidence_meta = evidence_query.with_entities(
        GraphRelationshipEvidence.id, evidence_size.label("byte_size"),
    ).limit(MAX_REVIEW_ROWS + 1).all()
    audit_meta = audit_query.with_entities(
        AuditLog.id, audit_size.label("byte_size"),
    ).order_by(AuditLog.created_at.desc(), AuditLog.id).limit(MAX_AUDIT_ROWS + 1).all()
    if (len(evidence_meta) > MAX_REVIEW_ROWS or len(audit_meta) > MAX_AUDIT_ROWS
            or any(row.byte_size is None or row.byte_size > MAX_PROVENANCE_BYTES
                   for row in (*evidence_meta, *audit_meta))):
        return False
    evidence = evidence_query.with_entities(
        GraphRelationshipEvidence.source_system, GraphRelationshipEvidence.source_id,
        GraphRelationshipEvidence.evidence_type, GraphRelationshipEvidence.payload,
    ).filter(GraphRelationshipEvidence.id.in_([row.id for row in evidence_meta]),
             evidence_size <= MAX_PROVENANCE_BYTES).limit(MAX_REVIEW_ROWS + 1).all()
    audits = audit_query.with_entities(AuditLog.actor_id, AuditLog.created_at, AuditLog.new_values).filter(
        AuditLog.id.in_([row.id for row in audit_meta]), audit_size <= MAX_PROVENANCE_BYTES,
    ).limit(MAX_AUDIT_ROWS + 1).all()
    if len(evidence) != len(evidence_meta) or len(audits) != len(audit_meta):
        return False
    binding = {
        "permit_id": permit.id, "parcel_id": parcel.id,
        "permit_raw_source_record_id": permit.latest_raw_record_id,
        "parcel_raw_source_record_id": parcel.latest_raw_record_id,
        "permit_normalization_hash": permit.normalization_hash,
        "parcel_normalization_hash": parcel.normalization_hash,
        "method": "source_scoped_exact_reference_v1",
        "confidence_kind": "analyst_assigned_not_calibrated",
    }
    for audit in audits:
        # Generic graph upserts refresh verification dates but are not a new
        # analyst acceptance. Its authoritative audit starts the 90-day clock.
        if (not audit.actor_id or not audit.new_values or audit.created_at is None
                or not now - MAX_ACCEPTANCE_AGE <= _utc(audit.created_at) <= now):
            continue
        try:
            values = json.loads(audit.new_values)
        except (ValueError, TypeError):
            continue
        if not isinstance(values, dict) or any(values.get(key) != value for key, value in binding.items()):
            continue
        review_id = values.get("review_id")
        if not isinstance(review_id, str) or not review_id or values.get("actor_id") != audit.actor_id:
            continue
        supported = set()
        for row in evidence:
            if (row.source_system != REVIEW_SYSTEM or row.evidence_type != "analyst_parcel_identity_acceptance"
                    or not isinstance(row.payload, dict)):
                continue
            for record_type, raw_id in (("permit", permit.latest_raw_record_id), ("parcel", parcel.latest_raw_record_id)):
                if (row.source_id == f"{review_id}:{raw_id}"
                        and row.payload == {**values, "raw_source_record_id": raw_id, "record_type": record_type}):
                    supported.add(record_type)
        if supported == {"permit", "parcel"}:
            return True
    return False


def _resolve(db, deal_id, brand_match_id):
    result = {
        "deal_id": deal_id, "anchor_brand_match_id": brand_match_id, "permit_id": None,
        "status": "unavailable", "reason": "Deal not found", "latitude": None, "longitude": None,
        "method": None, "parcel_id": None, "relationship_id": None,
        "permit_raw_record_id": None, "parcel_raw_record_id": None,
        "permit_normalization_hash": None, "parcel_normalization_hash": None,
    }

    def unavailable(reason):
        return {**result, "reason": reason}

    deal = active_query(db.query(Deal), Deal).filter(Deal.id == deal_id).populate_existing().first()
    if deal is None:
        raise LookupError("Deal not found")
    match = active_query(db.query(PermitBrandMatch), PermitBrandMatch).filter(
        PermitBrandMatch.id == brand_match_id,
    ).populate_existing().first()
    permit = None if match is None else active_query(db.query(PermitRecord), PermitRecord).filter(
        PermitRecord.id == match.permit_id,
    ).populate_existing().first()
    if permit is None:
        raise LookupError("Permit not found")
    if not any(row.id == brand_match_id for row in list_deal_brand_matches(db, deal_id, limit=100)):
        raise LookupError("Permit brand match is not connected to this deal")
    result.update(permit_id=permit.id, permit_raw_record_id=permit.latest_raw_record_id,
                  permit_normalization_hash=permit.normalization_hash if _hash(permit.normalization_hash) else None)
    if match.review_status != "confirmed" and not (
        match.review_status == "candidate" and permit.approval_stage == "pre_approval"
    ):
        return unavailable("A confirmed or pre-approval retailer signal is required")
    if not permit.is_active or permit.retired_at is not None:
        return unavailable("The anchor permit is no longer active at its source")
    if _coordinates(permit.latitude, permit.longitude):
        return {**result, "status": "ready", "reason": None, "method": "source_coordinate",
                "latitude": float(permit.latitude), "longitude": float(permit.longitude)}
    if permit.latitude is not None or permit.longitude is not None:
        return unavailable("The confirmed retailer signal has invalid coordinates")

    entities = _typed_entities(db, "permit", permit.id, GraphEntityType.permit)
    if len(entities) != 1:
        return unavailable("A unique typed permit entity is required")
    relationships = active_query(db.query(GraphRelationship), GraphRelationship).filter(
        GraphRelationship.source_entity_id == entities[0].id,
        GraphRelationship.relationship_type == GraphRelationshipType.permit_for,
        GraphRelationship.source_system == REVIEW_SYSTEM, GraphRelationship.is_current.is_(True),
    ).populate_existing().limit(2).all()
    if len(relationships) != 1:
        return unavailable("A unique current reviewed parcel relationship is required")
    relationship = relationships[0]
    now = datetime.now(timezone.utc)
    if (relationship.verification_due_at is None or _utc(relationship.verification_due_at) <= now
            or relationship.last_verified_at is None or _utc(relationship.last_verified_at) > now
            or relationship.valid_from is None or _utc(relationship.valid_from) > now
            or (relationship.valid_to is not None and _utc(relationship.valid_to) <= now)):
        return unavailable("Reviewed parcel verification is expired or invalid")
    links = active_query(db.query(GraphEntityLink), GraphEntityLink).join(
        GraphEntity, GraphEntity.id == GraphEntityLink.entity_id,
    ).filter(
        GraphEntity.organization_id == get_org_id(), GraphEntity.entity_type == GraphEntityType.parcel,
        GraphEntityLink.entity_id == relationship.target_entity_id, GraphEntityLink.record_type == "parcel",
    ).populate_existing().limit(2).all()
    if len(links) != 1:
        return unavailable("A unique typed parcel entity is required")
    parcel = active_query(db.query(ParcelRecord), ParcelRecord).filter(
        ParcelRecord.id == links[0].record_id, ParcelRecord.is_active.is_(True),
        ParcelRecord.retired_at.is_(None),
    ).populate_existing().first()
    if parcel is None or not _coordinates(parcel.latitude, parcel.longitude):
        return unavailable("Reviewed parcel is unavailable or has invalid coordinates")
    if not _hash(permit.normalization_hash) or not _hash(parcel.normalization_hash):
        return unavailable("Current normalization hashes are required")
    for record, record_type in ((permit, "permit"), (parcel, "parcel")):
        external_id = record.external_record_id if record_type == "permit" else record.external_parcel_id
        raw = active_query(db.query(RawSourceRecord.id), RawSourceRecord).filter(
            RawSourceRecord.id == record.latest_raw_record_id,
            RawSourceRecord.source_id == record.source_id, RawSourceRecord.record_type == record_type,
            RawSourceRecord.external_record_id == external_id,
        ).first()
        if raw is None:
            return unavailable("Current source evidence is unavailable")
    try:
        candidates = permit_parcel_candidates(db, permit.id, parcel.source_id)
    except LookupError:
        return unavailable("Current parcel reference is unavailable")
    if (candidates["status"] != "candidate_requires_review" or candidates["truncated"]
            or len(candidates["candidates"]) != 1
            or candidates["candidates"][0]["parcel_id"] != parcel.id
            or candidates["candidates"][0]["identity_assessment"] != "address_corroborated"):
        return unavailable("Current parcel reference is ambiguous or not fully corroborated")
    if not _review_is_authoritative(db, relationship, permit, parcel, now):
        return unavailable("Current reviewed parcel evidence lacks matching authoritative acceptance")
    return {**result, "status": "ready", "reason": None, "method": "reviewed_parcel_centroid",
            "latitude": float(parcel.latitude), "longitude": float(parcel.longitude), "parcel_id": parcel.id,
            "relationship_id": relationship.id, "parcel_raw_record_id": parcel.latest_raw_record_id,
            "parcel_normalization_hash": parcel.normalization_hash}


def get_deal_parcel_anchor(db, deal_id: str, brand_match_id: str) -> dict:
    """Preview current eligibility without writing, flushing, or using Census estimates."""
    with db.no_autoflush:
        return _resolve(db, deal_id, brand_match_id)


def resolve_search_anchor(db, deal_id: str, brand_match_id: str, expected_anchor: dict | None) -> dict:
    anchor = get_deal_parcel_anchor(db, deal_id, brand_match_id)
    if anchor["status"] != "ready":
        if expected_anchor is not None:
            raise ValueError("Anchor changed; refresh the preview")
        raise ValueError(anchor["reason"])
    if anchor["method"] == "reviewed_parcel_centroid":
        if expected_anchor is None:
            raise ValueError("An explicit reviewed anchor preview is required")
        if expected_anchor != anchor:
            raise ValueError("Anchor changed; refresh the preview")
        # ID-only queries lock the same rows without truncating PostgreSQL's
        # default activity trace. Full rows are refreshed after all locks below.
        with db.no_autoflush:
            for model, record_id in ((PermitRecord, anchor["permit_id"]),
                                     (PermitBrandMatch, brand_match_id),
                                     (ParcelRecord, anchor["parcel_id"]),
                                     (GraphRelationship, anchor["relationship_id"])):
                record = active_query(db.query(model.id), model).filter(
                    model.id == record_id,
                ).with_for_update().first()
                if record is None:
                    raise ValueError("Anchor changed; refresh the preview")
            try:
                anchor = get_deal_parcel_anchor(db, deal_id, brand_match_id)
            except LookupError as error:
                raise ValueError("Anchor changed; refresh the preview") from error
            if anchor["status"] != "ready" or expected_anchor != anchor:
                raise ValueError("Anchor changed; refresh the preview")
    elif expected_anchor is not None and expected_anchor != anchor:
        raise ValueError("Anchor changed; refresh the preview")
    return anchor
