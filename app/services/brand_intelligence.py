from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from dateutil import parser as date_parser
from pydantic import TypeAdapter
from sqlalchemy.orm import Session, joinedload

from app.models.brand import BrandAlias, BrandProfile, PermitBrandMatch
from app.models.deal import Deal
from app.models.graph import (
    GraphEntity,
    GraphEntityLink,
    GraphEntityType,
    GraphRelationship,
    GraphRelationshipType,
)
from app.models.ingestion import PermitRecord, RawSourceRecord
from app.models.signal import Signal
from app.schemas.brand import (
    BrandDefinition,
    BrandMatchGraphContext,
    BrandMatchRawEvidence,
    BrandPermitSummary,
    BrandProfileResponse,
    LinkedDealSummary,
    PermitBrandMatchEvidenceResponse,
    PermitBrandMatchResponse,
    PermitBrandOpportunityCreate,
    PermitBrandOpportunityResponse,
)
from app.schemas.deal import DealCreate
from app.schemas.parcel import NearbyParcelSearchSummary
from app.services.deal_service import create_deal_with_defaults, deal_to_detail_response
from app.services.graph_service import normalize_address, normalize_name
from app.services.normalization_service import normalize_signal_type
from app.utils.org_scope import active_query, get_org_id

DEFAULT_BRAND_CATALOG_PATH = Path(__file__).with_name("brand_catalog.json")
DETECTOR_VERSION = "brand-alias-v1"
MINIMUM_CONFIDENCE = 0.70
FIELD_CONFIDENCE = {
    "project_name": 0.98,
    "description": 0.92,
    "proposed_use": 0.85,
    "occupancy_type": 0.80,
}
CONTEXT_FIELDS = (
    "description",
    "proposed_use",
    "occupancy_type",
    "permit_type",
    "permit_subtype",
    "work_class",
    "review_type",
)
RETAIL_CONTEXT_TERMS = (
    "retail",
    "store",
    "tenant",
    "tenant improvement",
    "build out",
    "fit out",
    "restaurant",
    "coffee",
    "drive-through",
    "drive thru",
    "quick service",
    "grocery",
    "supermarket",
    "pharmacy",
    "fitness",
    "gym",
    "health club",
    "mercantile",
    "commercial remodel",
    "sign",
    "sales tax permit",
)
NEGATIVE_CONTEXTS = ("adjacent to", "near", "formerly", "across from", "next to")
TERMINAL_PREAPPROVAL_STATUS_TERMS = (
    "withdrawn",
    "denied",
    "cancelled",
    "canceled",
    "void",
    "expired",
    "closed",
    "aborted",
    "inactive",
    "rejected",
    "suspended",
)
_CATALOG_ADAPTER = TypeAdapter(list[BrandDefinition])


@dataclass(frozen=True)
class BrandCatalogSyncResult:
    created: int = 0
    updated: int = 0
    unchanged: int = 0


@dataclass(frozen=True)
class Detection:
    brand: BrandProfile
    alias: BrandAlias
    field: str
    excerpt: str
    confidence: float
    matched_fields: tuple[str, ...]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def load_brand_catalog(path: Path | str | None = None) -> list[BrandDefinition]:
    catalog_path = Path(path) if path else DEFAULT_BRAND_CATALOG_PATH
    entries = _CATALOG_ADAPTER.validate_python(
        json.loads(catalog_path.read_text(encoding="utf-8"))
    )
    keys = [entry.key for entry in entries]
    if len(keys) != len(set(keys)):
        raise ValueError("Brand catalog contains duplicate keys")
    aliases = [_normalize_text(alias.alias) for entry in entries for alias in entry.aliases]
    duplicates = sorted({alias for alias in aliases if aliases.count(alias) > 1})
    if duplicates:
        raise ValueError(f"Brand catalog contains duplicate aliases: {duplicates}")
    return entries


def sync_brand_catalog(
    db: Session,
    entries: list[BrandDefinition],
    *,
    dry_run: bool = False,
) -> BrandCatalogSyncResult:
    created = updated = unchanged = 0
    for entry in entries:
        brand = active_query(db.query(BrandProfile), BrandProfile).options(
            joinedload(BrandProfile.aliases)
        ).filter(BrandProfile.key == entry.key).first()
        if brand is None:
            created += 1
            if not dry_run:
                brand = BrandProfile(
                    organization_id=get_org_id(),
                    key=entry.key,
                    name=entry.name,
                    normalized_name=normalize_name(entry.name),
                    category=entry.category,
                    scale=entry.scale,
                    priority=entry.priority,
                    is_active=entry.is_active,
                    attributes=entry.attributes or None,
                )
                db.add(brand)
                db.flush()
                _replace_aliases(db, brand, entry)
            continue

        if _brand_snapshot(brand) == _definition_snapshot(entry):
            unchanged += 1
            continue
        updated += 1
        if dry_run:
            continue
        brand.name = entry.name
        brand.normalized_name = normalize_name(entry.name)
        brand.category = entry.category
        brand.scale = entry.scale
        brand.priority = entry.priority
        brand.is_active = entry.is_active
        brand.attributes = entry.attributes or None
        _replace_aliases(db, brand, entry)
    db.flush()
    return BrandCatalogSyncResult(created, updated, unchanged)


def detect_permit_brands(
    db: Session,
    permit: PermitRecord,
    raw: RawSourceRecord,
) -> list[PermitBrandMatch]:
    opening_signal = _is_future_retailer_opening_signal(permit, raw)
    if permit.approval_stage != "pre_approval" and not opening_signal:
        return []
    normalized_status = _normalize_text(permit.status or "")
    if any(_contains(normalized_status, term) for term in TERMINAL_PREAPPROVAL_STATUS_TERMS):
        return []
    if not permit.address and not (
        permit.parcel_id and permit.city and permit.state
    ):
        return []

    aliases = active_query(db.query(BrandAlias), BrandAlias).options(
        joinedload(BrandAlias.brand)
    ).join(BrandProfile).filter(
        BrandAlias.is_active.is_(True),
        BrandProfile.is_active.is_(True),
    ).all()
    if not aliases:
        return []

    fields = {
        field: value
        for field in FIELD_CONFIDENCE
        if (value := getattr(permit, field, None)) and isinstance(value, str)
    }
    combined = _normalize_text(" ".join(fields.values()))
    retail_context = _normalize_text(
        " ".join(
            str(value)
            for field in CONTEXT_FIELDS
            if (value := getattr(permit, field, None))
        )
    )
    if not any(_contains(retail_context, term) for term in RETAIL_CONTEXT_TERMS):
        return []
    best_by_brand: dict[str, Detection] = {}
    for alias in aliases:
        normalized_alias = alias.normalized_alias
        if alias.requires_context and not any(
            _contains(combined, _normalize_text(term)) for term in (alias.context_terms or [])
        ):
            continue
        matched_fields = tuple(
            field
            for field, value in fields.items()
            if _contains(_normalize_text(value), normalized_alias)
            and not _negative_alias_context(value, normalized_alias)
        )
        if len(matched_fields) < alias.minimum_field_matches:
            continue
        for field in matched_fields:
            value = fields[field]
            confidence = round(FIELD_CONFIDENCE[field] * alias.confidence, 4)
            if confidence < MINIMUM_CONFIDENCE:
                continue
            detection = Detection(
                brand=alias.brand,
                alias=alias,
                field=field,
                excerpt=_excerpt(value, alias.alias),
                confidence=confidence,
                matched_fields=matched_fields,
            )
            current = best_by_brand.get(alias.brand_id)
            if current is None or detection.confidence > current.confidence:
                best_by_brand[alias.brand_id] = detection

    matches: list[PermitBrandMatch] = []
    now = utcnow()
    for detection in best_by_brand.values():
        match = active_query(db.query(PermitBrandMatch), PermitBrandMatch).filter(
            PermitBrandMatch.permit_id == permit.id,
            PermitBrandMatch.brand_id == detection.brand.id,
        ).first()
        if match is None:
            match = PermitBrandMatch(
                organization_id=get_org_id(),
                permit_id=permit.id,
                brand_id=detection.brand.id,
                first_raw_record_id=raw.id,
                latest_raw_record_id=raw.id,
                confidence=detection.confidence,
                matched_alias=detection.alias.alias,
                matched_field=detection.field,
                matched_fields=list(detection.matched_fields),
                rule_ids=_rule_ids(opening_signal),
                excerpt=detection.excerpt,
                detector_version=DETECTOR_VERSION,
                first_seen_at=now,
                last_seen_at=now,
            )
            db.add(match)
        else:
            match.latest_raw_record_id = raw.id
            match.last_seen_at = now
            if match.review_status == "retracted":
                match.review_status = "candidate"
            if detection.confidence >= match.confidence:
                match.confidence = detection.confidence
                match.matched_alias = detection.alias.alias
                match.matched_field = detection.field
                match.matched_fields = list(detection.matched_fields)
                match.rule_ids = _rule_ids(opening_signal)
                match.excerpt = detection.excerpt
                match.detector_version = DETECTOR_VERSION
        matches.append(match)

    detected_brand_ids = set(best_by_brand)
    existing_matches = active_query(db.query(PermitBrandMatch), PermitBrandMatch).filter(
        PermitBrandMatch.permit_id == permit.id,
        PermitBrandMatch.review_status == "candidate",
    ).all()
    for match in existing_matches:
        if match.brand_id in detected_brand_ids:
            continue
        match.review_status = "retracted"
        match.latest_raw_record_id = raw.id
        match.last_seen_at = now
    db.flush()
    return matches


def _rule_ids(opening_signal: bool) -> list[str]:
    if opening_signal:
        return [
            "approved_retailer_opening",
            "future_first_sale_date",
            "stable_location",
            "retail_context",
            "exact_alias",
        ]
    return ["pre_approval", "stable_location", "retail_context", "exact_alias"]


def _is_future_retailer_opening_signal(
    permit: PermitRecord,
    raw: RawSourceRecord,
) -> bool:
    if permit.approval_stage not in {"pre_approval", "approved"}:
        return False
    settings = raw.source.settings or {}
    if settings.get("retailer_opening_signal") is not True:
        return False
    date_field = settings.get("opening_signal_date_field")
    if not isinstance(date_field, str) or not date_field:
        return False
    value = raw.payload.get(date_field) if isinstance(raw.payload, dict) else None
    if not value:
        return False
    try:
        parsed = date_parser.parse(str(value))
    except (TypeError, ValueError, OverflowError):
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed > utcnow()


def list_brand_matches(
    db: Session,
    *,
    review_status: str | None = None,
    approval_stage: str | None = None,
    limit: int = 100,
) -> list[PermitBrandMatchResponse]:
    query = active_query(db.query(PermitBrandMatch), PermitBrandMatch).options(
        joinedload(PermitBrandMatch.brand),
        joinedload(PermitBrandMatch.permit),
    )
    if review_status:
        query = query.filter(PermitBrandMatch.review_status == review_status)
    if approval_stage:
        query = query.join(PermitRecord).filter(PermitRecord.approval_stage == approval_stage)
    matches = query.order_by(
        PermitBrandMatch.confidence.desc(), PermitBrandMatch.first_seen_at.desc()
    ).limit(limit).all()
    return _serialize_brand_matches(db, matches)


def list_deal_brand_matches(
    db: Session,
    deal_id: str,
    *,
    limit: int = 20,
) -> list[PermitBrandMatchResponse]:
    deal = active_query(db.query(Deal), Deal).filter(Deal.id == deal_id).first()
    if deal is None:
        return []

    deal_entities = active_query(db.query(GraphEntity), GraphEntity).join(
        GraphEntityLink, GraphEntityLink.entity_id == GraphEntity.id
    ).filter(
        GraphEntityLink.record_type == "deal",
        GraphEntityLink.record_id == deal_id,
    ).all()
    property_entity_ids = [entity.id for entity in deal_entities]
    location_keys = {
        normalize_address(entity.address, entity.city, entity.state)
        for entity in deal_entities
        if entity.address and entity.city and entity.state
    }
    deal_location_key = normalize_address(deal.address, deal.city, deal.state)
    if deal_location_key:
        location_keys.add(deal_location_key)
    location_keys.discard(None)
    if location_keys:
        cities = {entity.city for entity in deal_entities if entity.city}
        states = {entity.state for entity in deal_entities if entity.state}
        if deal.city:
            cities.add(deal.city)
        if deal.state:
            states.add(deal.state)
        candidates = active_query(db.query(GraphEntity), GraphEntity).filter(
            GraphEntity.entity_type == GraphEntityType.property,
            GraphEntity.city.in_(cities),
            GraphEntity.state.in_(states),
        ).all()
        property_entity_ids.extend(
            entity.id
            for entity in candidates
            if entity.id not in property_entity_ids
            and normalize_address(entity.address, entity.city, entity.state) in location_keys
        )
    if not property_entity_ids:
        return _direct_brand_matches_for_deal(db, deal, limit=limit)
    permit_entity_ids = [
        row.source_entity_id
        for row in active_query(db.query(GraphRelationship), GraphRelationship).filter(
            GraphRelationship.relationship_type == GraphRelationshipType.permit_for,
            GraphRelationship.target_entity_id.in_(property_entity_ids),
            GraphRelationship.is_current.is_(True),
        ).all()
    ]
    if not permit_entity_ids:
        return _direct_brand_matches_for_deal(db, deal, limit=limit)
    permit_ids = [
        row.record_id
        for row in active_query(db.query(GraphEntityLink), GraphEntityLink).filter(
            GraphEntityLink.entity_id.in_(permit_entity_ids),
            GraphEntityLink.record_type == "permit",
        ).all()
    ]
    if not permit_ids:
        return _direct_brand_matches_for_deal(db, deal, limit=limit)
    matches = active_query(db.query(PermitBrandMatch), PermitBrandMatch).options(
        joinedload(PermitBrandMatch.brand),
        joinedload(PermitBrandMatch.permit),
    ).filter(
        PermitBrandMatch.permit_id.in_(permit_ids),
        PermitBrandMatch.review_status.in_(("candidate", "confirmed")),
    ).order_by(
        PermitBrandMatch.confidence.desc(), PermitBrandMatch.first_seen_at.desc()
    ).limit(limit).all()
    return _serialize_brand_matches(db, matches)


def list_permit_brand_matches(
    db: Session,
    permit_id: str,
    *,
    limit: int = 20,
) -> list[PermitBrandMatchResponse]:
    matches = active_query(db.query(PermitBrandMatch), PermitBrandMatch).options(
        joinedload(PermitBrandMatch.brand),
        joinedload(PermitBrandMatch.permit),
    ).filter(
        PermitBrandMatch.permit_id == permit_id,
    ).order_by(
        PermitBrandMatch.confidence.desc(), PermitBrandMatch.first_seen_at.desc()
    ).limit(limit).all()
    return _serialize_brand_matches(db, matches)


def get_brand_match_evidence(
    db: Session,
    match_id: str,
) -> PermitBrandMatchEvidenceResponse | None:
    match = active_query(db.query(PermitBrandMatch), PermitBrandMatch).options(
        joinedload(PermitBrandMatch.brand),
        joinedload(PermitBrandMatch.permit),
        joinedload(PermitBrandMatch.first_raw_record).joinedload(RawSourceRecord.source),
        joinedload(PermitBrandMatch.latest_raw_record).joinedload(RawSourceRecord.source),
    ).filter(PermitBrandMatch.id == match_id).first()
    if match is None:
        return None
    summary = PermitBrandMatchResponse.model_validate(match)
    return PermitBrandMatchEvidenceResponse(
        id=match.id,
        brand=BrandProfileResponse.model_validate(match.brand),
        permit=BrandPermitSummary.model_validate(match.permit),
        review_status=match.review_status,
        confidence=match.confidence,
        matched_alias=match.matched_alias,
        matched_field=match.matched_field,
        matched_fields=match.matched_fields or [],
        excerpt=match.excerpt,
        signal_quality=summary.signal_quality,
        signal_quality_label=summary.signal_quality_label,
        signal_quality_note=summary.signal_quality_note,
        rule_ids=match.rule_ids or [],
        detector_version=match.detector_version,
        first_seen_at=match.first_seen_at,
        last_seen_at=match.last_seen_at,
        linked_deals=_linked_deals_for_matches(db, [match]).get(match.id, []),
        first_evidence=_raw_evidence(match.first_raw_record, match),
        latest_evidence=_raw_evidence(match.latest_raw_record, match),
        graph_context=_brand_match_graph_context(db, match.id),
    )


def review_brand_match(
    db: Session,
    match_id: str,
    review_status: str,
) -> PermitBrandMatch | None:
    match = active_query(db.query(PermitBrandMatch), PermitBrandMatch).options(
        joinedload(PermitBrandMatch.brand),
        joinedload(PermitBrandMatch.permit),
    ).filter(PermitBrandMatch.id == match_id).first()
    if match is None:
        return None
    match.review_status = review_status
    relationships = active_query(db.query(GraphRelationship), GraphRelationship).filter(
        GraphRelationship.attributes["brand_match_id"].as_string() == match.id
    ).all()
    for relationship in relationships:
        relationship.attributes = {
            **(relationship.attributes or {}),
            "review_status": review_status,
        }
        relationship.is_current = review_status in {"candidate", "confirmed"}
        relationship.valid_to = None if relationship.is_current else utcnow()
        relationship.last_verified_at = utcnow()
    if review_status == "confirmed":
        linked_deals = _linked_deals_for_matches(db, [match]).get(match.id, [])
        if linked_deals:
            from app.services.parcel_service import maybe_create_default_nearby_parcel_searches

            for linked_deal in linked_deals:
                maybe_create_default_nearby_parcel_searches(
                    db,
                    deal_id=linked_deal.id,
                    anchor_brand_match_id=match.id,
                )
    db.flush()
    return match


def create_or_get_opportunity_from_brand_match(
    db: Session,
    match_id: str,
    payload: PermitBrandOpportunityCreate | None = None,
) -> PermitBrandOpportunityResponse | None:
    match = active_query(db.query(PermitBrandMatch), PermitBrandMatch).options(
        joinedload(PermitBrandMatch.brand),
        joinedload(PermitBrandMatch.permit),
        joinedload(PermitBrandMatch.first_raw_record).joinedload(RawSourceRecord.source),
        joinedload(PermitBrandMatch.latest_raw_record).joinedload(RawSourceRecord.source),
    ).filter(PermitBrandMatch.id == match_id).first()
    if match is None:
        return None

    linked_deals = _linked_deals_for_matches(db, [match]).get(match.id, [])
    if linked_deals:
        existing = active_query(db.query(Deal), Deal).filter(Deal.id == linked_deals[0].id).first()
        if existing is not None:
            review_brand_match(db, match.id, "confirmed")
            from app.services.parcel_service import maybe_create_default_nearby_parcel_searches

            seeded_searches = maybe_create_default_nearby_parcel_searches(
                db,
                deal_id=existing.id,
                anchor_brand_match_id=match.id,
            )
            nearby_parcel_search = None
            if seeded_searches:
                nearby_parcel_search = NearbyParcelSearchSummary.model_validate(
                    next(
                        (search for search in seeded_searches if search.persona == "developer"),
                        seeded_searches[0],
                    )
                )
            db.flush()
            return PermitBrandOpportunityResponse(
                match_id=match.id,
                created=False,
                deal=deal_to_detail_response(existing),
                nearby_parcel_search=nearby_parcel_search,
                nearby_parcel_searches=[
                    NearbyParcelSearchSummary.model_validate(search)
                    for search in seeded_searches
                ],
            )

    deal = create_deal_with_defaults(
        db,
        DealCreate(
            name=payload.name if payload and payload.name else _opportunity_name(match),
            address=match.permit.address,
            city=match.permit.city,
            state=match.permit.state,
            zip_code=None,
            property_type="Retail",
            source="Permit brand match",
            notes=_opportunity_notes(match),
        ),
    )
    signal = Signal(
        organization_id=get_org_id(),
        deal_id=deal.id,
        signal_type=normalize_signal_type("permit") or "Permit Activity",
        source=match.latest_raw_record.source.name if match.latest_raw_record and match.latest_raw_record.source else match.brand.name,
        description=_signal_description(match),
        severity=round(match.confidence * 10, 2),
    )
    db.add(signal)
    review_brand_match(db, match.id, "confirmed")
    nearby_parcel_search = None
    seeded_searches = []
    from app.services.parcel_service import maybe_create_default_nearby_parcel_searches
    seeded_searches = maybe_create_default_nearby_parcel_searches(
        db,
        deal_id=deal.id,
        anchor_brand_match_id=match.id,
    )
    if seeded_searches:
        developer_search = next(
            (search for search in seeded_searches if search.persona == "developer"),
            seeded_searches[0],
        )
        nearby_parcel_search = NearbyParcelSearchSummary.model_validate(developer_search)
    db.flush()
    db.refresh(deal)
    return PermitBrandOpportunityResponse(
        match_id=match.id,
        created=True,
        deal=deal_to_detail_response(deal),
        nearby_parcel_search=nearby_parcel_search,
        nearby_parcel_searches=[
            NearbyParcelSearchSummary.model_validate(search)
            for search in seeded_searches
        ],
    )


def _raw_evidence(
    raw: RawSourceRecord,
    match: PermitBrandMatch,
) -> BrandMatchRawEvidence:
    source = raw.source
    return BrandMatchRawEvidence(
        raw_record_id=raw.id,
        external_record_id=raw.external_record_id,
        content_hash=raw.content_hash,
        received_at=raw.received_at,
        source_updated_at=raw.source_updated_at,
        source_key=source.key,
        source_name=source.name,
        source_url=source.base_url,
        payload_excerpt=_payload_excerpt(raw.payload, match),
    )


def _opportunity_name(match: PermitBrandMatch) -> str:
    if match.permit.address:
        return f"{match.brand.name} at {match.permit.address}"
    location = ", ".join(part for part in (match.permit.city, match.permit.state) if part)
    if location:
        return f"{match.brand.name} in {location}"
    return match.brand.name


def _opportunity_notes(match: PermitBrandMatch) -> str:
    filing_number = match.permit.application_number or match.permit.permit_number or "Pending filing number"
    stage = "Approved" if match.permit.approval_stage == "approved" else "Pre-approval"
    source_name = (
        match.latest_raw_record.source.name
        if match.latest_raw_record and match.latest_raw_record.source
        else "Permit source"
    )
    parts = [
        f"{stage} retailer signal for {match.brand.name}.",
        f"Filing: {filing_number}.",
        f"Status: {match.permit.status or 'Unknown'}.",
        f"Confidence: {round(match.confidence * 100)}%.",
        f"Evidence: {match.excerpt}",
        f"Source: {source_name}.",
    ]
    return " ".join(parts)


def _signal_description(match: PermitBrandMatch) -> str:
    filing_number = match.permit.application_number or match.permit.permit_number or "pending filing number"
    return (
        f"{match.brand.name} permit signal created from {filing_number}: "
        f"{match.excerpt}"
    )


def serialize_brand_match(
    db: Session,
    match: PermitBrandMatch,
) -> PermitBrandMatchResponse:
    return _serialize_brand_matches(db, [match])[0]


def _serialize_brand_matches(
    db: Session,
    matches: list[PermitBrandMatch],
) -> list[PermitBrandMatchResponse]:
    linked_deals_by_match = _linked_deals_for_matches(db, matches)
    return [
        PermitBrandMatchResponse(
            id=match.id,
            permit_id=match.permit_id,
            review_status=match.review_status,
            confidence=match.confidence,
            matched_alias=match.matched_alias,
            matched_field=match.matched_field,
            matched_fields=match.matched_fields or [],
            rule_ids=match.rule_ids or [],
            excerpt=match.excerpt,
            detector_version=match.detector_version,
            first_seen_at=match.first_seen_at,
            last_seen_at=match.last_seen_at,
            brand=BrandProfileResponse.model_validate(match.brand),
            permit=BrandPermitSummary.model_validate(match.permit),
            linked_deals=linked_deals_by_match.get(match.id, []),
        )
        for match in matches
    ]


def _linked_deals_for_matches(
    db: Session,
    matches: list[PermitBrandMatch],
) -> dict[str, list[LinkedDealSummary]]:
    if not matches:
        return {}

    linked_by_match = _direct_deals_for_matches(db, matches)
    match_by_permit_id = {match.permit_id: match for match in matches}
    permit_links = active_query(db.query(GraphEntityLink), GraphEntityLink).filter(
        GraphEntityLink.record_type == "permit",
        GraphEntityLink.record_id.in_(tuple(match_by_permit_id)),
    ).all()
    if not permit_links:
        return linked_by_match

    permit_id_by_entity_id = {link.entity_id: link.record_id for link in permit_links}
    permit_relationships = active_query(db.query(GraphRelationship), GraphRelationship).filter(
        GraphRelationship.relationship_type == GraphRelationshipType.permit_for,
        GraphRelationship.is_current.is_(True),
        GraphRelationship.source_entity_id.in_(tuple(permit_id_by_entity_id)),
    ).all()
    if not permit_relationships:
        return linked_by_match

    property_entities = active_query(db.query(GraphEntity), GraphEntity).filter(
        GraphEntity.id.in_(tuple({relationship.target_entity_id for relationship in permit_relationships}))
    ).all()
    property_entity_ids = {entity.id for entity in property_entities}
    location_keys = {
        normalize_address(entity.address, entity.city, entity.state)
        for entity in property_entities
        if entity.address and entity.city and entity.state
    }
    location_keys.discard(None)
    if location_keys:
        cities = {entity.city for entity in property_entities if entity.city}
        states = {entity.state for entity in property_entities if entity.state}
        candidate_properties = active_query(db.query(GraphEntity), GraphEntity).filter(
            GraphEntity.entity_type == GraphEntityType.property,
            GraphEntity.city.in_(tuple(cities)),
            GraphEntity.state.in_(tuple(states)),
        ).all()
        property_entity_ids.update(
            entity.id
            for entity in candidate_properties
            if normalize_address(entity.address, entity.city, entity.state) in location_keys
        )

    deal_links = active_query(db.query(GraphEntityLink), GraphEntityLink).filter(
        GraphEntityLink.record_type == "deal",
        GraphEntityLink.entity_id.in_(tuple(property_entity_ids)),
    ).all()
    if not deal_links:
        return linked_by_match

    deal_ids = sorted({link.record_id for link in deal_links})
    deals = active_query(db.query(Deal), Deal).filter(Deal.id.in_(deal_ids)).all()
    deal_by_id = {deal.id: deal for deal in deals}
    deals_by_property_entity: dict[str, list[LinkedDealSummary]] = {}
    for link in deal_links:
        deal = deal_by_id.get(link.record_id)
        if deal is None:
            continue
        deals_by_property_entity.setdefault(link.entity_id, []).append(
            LinkedDealSummary(id=deal.id, name=deal.name)
        )

    for relationship in permit_relationships:
        permit_id = permit_id_by_entity_id.get(relationship.source_entity_id)
        match = match_by_permit_id.get(permit_id) if permit_id else None
        if match is None:
            continue
        linked = deals_by_property_entity.get(relationship.target_entity_id, [])
        if not linked:
            continue
        deduped = {deal.id: deal for deal in linked_by_match.get(match.id, [])}
        for deal in linked:
            deduped[deal.id] = deal
        linked_by_match[match.id] = sorted(
            deduped.values(),
            key=lambda item: item.name.lower(),
        )
    return linked_by_match


def _direct_brand_matches_for_deal(
    db: Session,
    deal: Deal,
    *,
    limit: int = 20,
) -> list[PermitBrandMatchResponse]:
    location_key = normalize_address(deal.address, deal.city, deal.state)
    if not location_key or not deal.city or not deal.state:
        return []

    candidate_permits = active_query(db.query(PermitRecord), PermitRecord).filter(
        PermitRecord.city == deal.city,
        PermitRecord.state == deal.state,
    ).all()
    permit_ids = [
        permit.id
        for permit in candidate_permits
        if normalize_address(permit.address, permit.city, permit.state) == location_key
    ]
    if not permit_ids:
        return []

    matches = active_query(db.query(PermitBrandMatch), PermitBrandMatch).options(
        joinedload(PermitBrandMatch.brand),
        joinedload(PermitBrandMatch.permit),
    ).filter(
        PermitBrandMatch.permit_id.in_(permit_ids),
        PermitBrandMatch.review_status.in_(("candidate", "confirmed")),
    ).order_by(
        PermitBrandMatch.confidence.desc(), PermitBrandMatch.first_seen_at.desc()
    ).limit(limit).all()
    return _serialize_brand_matches(db, matches)


def _direct_deals_for_matches(
    db: Session,
    matches: list[PermitBrandMatch],
) -> dict[str, list[LinkedDealSummary]]:
    location_keys_by_match = {
        match.id: normalize_address(match.permit.address, match.permit.city, match.permit.state)
        for match in matches
        if match.permit.address and match.permit.city and match.permit.state
    }
    location_keys = {key for key in location_keys_by_match.values() if key}
    if not location_keys:
        return {}

    cities = {match.permit.city for match in matches if match.permit.city}
    states = {match.permit.state for match in matches if match.permit.state}
    candidate_deals = active_query(db.query(Deal), Deal).filter(
        Deal.city.in_(tuple(cities)),
        Deal.state.in_(tuple(states)),
    ).all()
    deals_by_location: dict[str, list[LinkedDealSummary]] = {}
    for deal in candidate_deals:
        key = normalize_address(deal.address, deal.city, deal.state)
        if not key or key not in location_keys:
            continue
        deals_by_location.setdefault(key, []).append(
            LinkedDealSummary(id=deal.id, name=deal.name)
        )

    return {
        match_id: sorted(deals_by_location.get(location_key, []), key=lambda item: item.name.lower())
        for match_id, location_key in location_keys_by_match.items()
        if location_key in deals_by_location
    }


def _brand_match_graph_context(
    db: Session,
    match_id: str,
) -> list[BrandMatchGraphContext]:
    relationships = active_query(db.query(GraphRelationship), GraphRelationship).options(
        joinedload(GraphRelationship.source_entity),
        joinedload(GraphRelationship.target_entity),
        joinedload(GraphRelationship.evidence),
    ).filter(
        GraphRelationship.attributes["brand_match_id"].as_string() == match_id
    ).order_by(GraphRelationship.last_verified_at.desc()).all()
    return [
        BrandMatchGraphContext(
            relationship_id=relationship.id,
            relationship_type=relationship.relationship_type.value,
            source_entity_id=relationship.source_entity_id,
            source_entity_type=relationship.source_entity.entity_type.value,
            source_entity_name=relationship.source_entity.display_name,
            target_entity_id=relationship.target_entity_id,
            target_entity_type=relationship.target_entity.entity_type.value,
            target_entity_name=relationship.target_entity.display_name,
            review_status=(relationship.attributes or {}).get("review_status"),
            is_current=relationship.is_current,
            confidence=relationship.confidence,
            evidence_count=len(relationship.evidence),
            valid_from=relationship.valid_from,
            valid_to=relationship.valid_to,
            last_verified_at=relationship.last_verified_at,
            related_entity=BrandMatchGraphContext.RelatedEntity(
                id=relationship.target_entity_id,
                entity_type=relationship.target_entity.entity_type.value,
                display_name=relationship.target_entity.display_name,
                address=relationship.target_entity.address,
                city=relationship.target_entity.city,
                state=relationship.target_entity.state,
            ),
            evidence_preview=(
                BrandMatchGraphContext.EvidencePreview(
                    source_system=relationship.evidence[0].source_system,
                    source_url=relationship.evidence[0].source_url,
                    excerpt=relationship.evidence[0].excerpt,
                )
                if relationship.evidence
                else None
            ),
        )
        for relationship in relationships
    ]


def _payload_excerpt(payload: dict, match: PermitBrandMatch) -> dict[str, object]:
    if not isinstance(payload, dict):
        return {}
    blocked_fragments = ("phone", "email", "fax", "violation")
    priority = (
        "dba", "project_name", "business", "tenant", "applicant",
        "work_desc", "description", "use_desc", "cuisine_description",
        "status_desc", "status", "inspection_date", "inspection_type",
        "action", "record_date", "submitted_date", "issue_date",
        "primary_address", "building", "street", "address",
        "city", "boro", "state", "zipcode", "zip_code",
        "permit_nbr", "camis", "application_number", "permit_number",
        "apn", "bbl", "bin", "latitude", "longitude",
    )
    selected: dict[str, object] = {}
    normalized_alias = _normalize_text(match.matched_alias)
    for key in priority:
        if key in payload and _include_payload_field(key, payload[key], blocked_fragments):
            selected[key] = payload[key]
    for key, value in payload.items():
        if len(selected) >= 24:
            break
        if key in selected or not _include_payload_field(key, value, blocked_fragments):
            continue
        if normalized_alias and _contains(_normalize_text(str(value)), normalized_alias):
            selected[key] = value
    return selected


def _include_payload_field(
    key: str,
    value: object,
    blocked_fragments: tuple[str, ...],
) -> bool:
    normalized_key = key.casefold()
    if any(fragment in normalized_key for fragment in blocked_fragments):
        return False
    if value is None or value == "":
        return False
    if isinstance(value, (str, int, float, bool)):
        return True
    return False


def _replace_aliases(db: Session, brand: BrandProfile, entry: BrandDefinition) -> None:
    for alias in list(brand.aliases):
        db.delete(alias)
    db.flush()
    for definition in entry.aliases:
        db.add(BrandAlias(
            organization_id=get_org_id(),
            brand_id=brand.id,
            alias=definition.alias,
            normalized_alias=_normalize_text(definition.alias),
            confidence=definition.confidence,
            requires_context=definition.requires_context,
            minimum_field_matches=definition.minimum_field_matches,
            context_terms=definition.context_terms or None,
            is_active=True,
        ))
    db.flush()
    db.expire(brand, ["aliases"])


def _brand_snapshot(brand: BrandProfile) -> dict:
    return {
        "name": brand.name,
        "category": brand.category,
        "scale": brand.scale,
        "priority": brand.priority,
        "is_active": brand.is_active,
        "attributes": brand.attributes or {},
        "aliases": sorted(
            [
                {
                    "alias": alias.alias,
                    "confidence": alias.confidence,
                    "requires_context": alias.requires_context,
                    "minimum_field_matches": alias.minimum_field_matches,
                    "context_terms": alias.context_terms or [],
                }
                for alias in brand.aliases
            ],
            key=lambda value: _normalize_text(value["alias"]),
        ),
    }


def _definition_snapshot(entry: BrandDefinition) -> dict:
    return {
        "name": entry.name,
        "category": entry.category,
        "scale": entry.scale,
        "priority": entry.priority,
        "is_active": entry.is_active,
        "attributes": entry.attributes,
        "aliases": sorted(
            [alias.model_dump() for alias in entry.aliases],
            key=lambda value: _normalize_text(value["alias"]),
        ),
    }


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", normalized).split())


def _contains(text: str, alias: str) -> bool:
    return bool(alias) and f" {alias} " in f" {text} "


def _excerpt(value: str, alias: str, radius: int = 180) -> str:
    match = re.search(re.escape(alias), value, flags=re.IGNORECASE)
    if match is None:
        return value[: radius * 2]
    start = max(0, match.start() - radius)
    end = min(len(value), match.end() + radius)
    return value[start:end]


def _negative_alias_context(value: str, normalized_alias: str) -> bool:
    normalized = _normalize_text(value)
    return any(
        f"{negative} {normalized_alias}" in normalized for negative in NEGATIVE_CONTEXTS
    )
