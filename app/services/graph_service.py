from __future__ import annotations

import re
from collections import deque
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Iterable, Optional

from sqlalchemy import func, or_, select, union_all
from sqlalchemy.orm import Session, joinedload

from app.models.contact import Contact
from app.models.deal import Deal
from app.models.graph import (
    GraphEntity,
    GraphEntityAlias,
    GraphEntityLink,
    GraphEntityType,
    GraphRelationship,
    GraphRelationshipEvidence,
    GraphRelationshipType,
)
from app.schemas.graph import GraphEntityCreate, GraphEvidenceCreate, GraphRelationshipCreate
from app.utils.org_scope import active_query, get_org_id

COMPANY_SUFFIXES = {
    "co",
    "company",
    "corp",
    "corporation",
    "inc",
    "incorporated",
    "llc",
    "lp",
    "llp",
    "ltd",
    "limited",
    "partners",
    "properties",
    "property",
    "group",
}

ATTRIBUTE_ALIAS_KEYS = {
    "alias",
    "aliases",
    "alternate_name",
    "alternate_names",
    "aka",
    "business_name",
    "company_name",
    "dba",
    "doing_business_as",
    "engineer_name",
    "developer_name",
    "contractor_name",
    "architect_name",
    "lender_name",
    "owner_name",
    "person_name",
    "property_name",
    "display_name",
    "legal_name",
    "name",
    "site_name",
    "trade_name",
}

UNIT_ADDRESS_KEYS = {
    "apartment": "unit",
    "apt": "unit",
    "suite": "unit",
    "ste": "unit",
    "unit": "unit",
}

ADDRESS_REPLACEMENTS = {
    "street": "st",
    "avenue": "ave",
    "road": "rd",
    "boulevard": "blvd",
    "drive": "dr",
    "lane": "ln",
    "court": "ct",
    "floor": "fl",
}

CONTEXT_BUCKETS: dict[GraphEntityType, str] = {
    GraphEntityType.company: "companies",
    GraphEntityType.developer: "developers",
    GraphEntityType.parcel: "parcels",
    GraphEntityType.owner: "owners",
    GraphEntityType.general_contractor: "contractors",
    GraphEntityType.architect: "architects",
    GraphEntityType.engineer: "engineers",
    GraphEntityType.permit: "permits",
    GraphEntityType.city: "cities",
    GraphEntityType.lender: "lenders",
    GraphEntityType.broker: "brokers",
}

CONTACT_ROLE_SPECS: tuple[tuple[tuple[str, ...], GraphEntityType, GraphRelationshipType], ...] = (
    (("broker", "real estate broker", "agent"), GraphEntityType.broker, GraphRelationshipType.brokered_by),
    (("lender", "loan", "financ", "mortgage", "bank"), GraphEntityType.lender, GraphRelationshipType.financed_by),
    (("owner",), GraphEntityType.owner, GraphRelationshipType.owned_by),
    (("developer", "sponsor"), GraphEntityType.developer, GraphRelationshipType.developed_by),
    (("architect", "designer"), GraphEntityType.architect, GraphRelationshipType.designed_by),
    (("engineer",), GraphEntityType.engineer, GraphRelationshipType.engineer_for),
    (("contractor", "builder"), GraphEntityType.general_contractor, GraphRelationshipType.contracted_by),
)

ADDRESS_AWARE_ENTITY_TYPES = {
    GraphEntityType.developer,
    GraphEntityType.owner,
    GraphEntityType.general_contractor,
    GraphEntityType.architect,
    GraphEntityType.engineer,
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_name(value: str) -> str:
    raw = value.lower().replace("&", " and ")
    raw = re.sub(r"[^a-z0-9\s]", " ", raw)
    words = [w for w in raw.split() if w not in COMPANY_SUFFIXES]
    return " ".join(words) or " ".join(raw.split())


def normalize_address(address: Optional[str], city: Optional[str] = None, state: Optional[str] = None, zip_code: Optional[str] = None) -> Optional[str]:
    parts = [address, city, state, zip_code]
    raw = " ".join(str(part) for part in parts if part is not None and str(part).strip())
    if not raw:
        return None
    raw = re.sub(r"#\s*([A-Za-z0-9-]+)", r" unit \1", raw)
    raw = re.sub(r"[^a-z0-9\s]", " ", raw.lower())
    words = [ADDRESS_REPLACEMENTS.get(w, UNIT_ADDRESS_KEYS.get(w, w)) for w in raw.split()]
    return " ".join(words)


def _name_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _blocking_tokens(normalized_name: str) -> list[str]:
    tokens = [
        token
        for token in normalized_name.split()
        if len(token) >= 4 and not token.isdigit()
    ]
    return tokens[:3]


def _entity_query(db: Session):
    return active_query(db.query(GraphEntity), GraphEntity)


def _collect_attribute_strings(attributes: dict[str, Any] | None, allowed_keys: set[str]) -> list[str]:
    if not isinstance(attributes, dict):
        return []

    values: list[str] = []

    def visit(mapping: dict[str, Any]) -> None:
        for key, value in mapping.items():
            normalized_key = str(key).casefold()
            if normalized_key in allowed_keys:
                values.extend(_coerce_strings(value))
            if isinstance(value, dict):
                visit(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        visit(item)

    visit(attributes)
    return values


def _coerce_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return [str(value)]
    if isinstance(value, dict):
        values: list[str] = []
        for nested in value.values():
            values.extend(_coerce_strings(nested))
        return values
    if isinstance(value, (list, tuple, set)):
        values: list[str] = []
        for item in value:
            values.extend(_coerce_strings(item))
        return values
    return []


def _payload_alias_candidates(payload: GraphEntityCreate) -> list[str]:
    aliases = [payload.display_name, *payload.aliases]
    aliases.extend(_collect_attribute_strings(payload.attributes, ATTRIBUTE_ALIAS_KEYS))
    return aliases


def _normalized_terms(values: Iterable[str]) -> list[str]:
    terms = [normalize_name(value) for value in values if isinstance(value, str) and value.strip()]
    return list(dict.fromkeys(term for term in terms if term))


def _best_name_similarity(terms: Iterable[str], candidate_name: str) -> float:
    best = 0.0
    for term in terms:
        similarity = _name_similarity(term, candidate_name)
        if similarity > best:
            best = similarity
    return best


def _entity_name_terms(entity: GraphEntity) -> list[str]:
    terms = [entity.normalized_name]
    terms.extend(
        alias.normalized_alias
        for alias in getattr(entity, "aliases", [])
        if getattr(alias, "normalized_alias", None)
    )
    return list(dict.fromkeys(term for term in terms if term))


def resolve_entity(db: Session, payload: GraphEntityCreate) -> tuple[GraphEntity, bool]:
    normalized = normalize_name(payload.display_name)
    normalized_address = normalize_address(payload.address, payload.city, payload.state, payload.zip_code)
    alias_candidates = _payload_alias_candidates(payload)
    normalized_terms = _normalized_terms(alias_candidates)
    authoritative_record_id = bool(
        payload.entity_type in {GraphEntityType.permit, GraphEntityType.parcel}
        and payload.source_system
        and payload.source_id
    )

    if payload.source_system and payload.source_id:
        source_match = _entity_query(db).filter(
            GraphEntity.entity_type == payload.entity_type,
            GraphEntity.source_system == payload.source_system,
            GraphEntity.source_id == payload.source_id,
        ).first()
        if source_match:
            previous_display_name = source_match.display_name
            _touch_entity(source_match, payload)
            _refresh_authoritative_display_name(source_match, payload)
            _ensure_aliases(
                db,
                source_match,
                [*alias_candidates, previous_display_name],
                payload.source_system,
                payload.source_id,
            )
            return source_match, False

        alias_source_match = active_query(db.query(GraphEntityAlias), GraphEntityAlias).join(
            GraphEntityAlias.entity
        ).filter(
            GraphEntityAlias.source_system == payload.source_system,
            GraphEntityAlias.source_id == payload.source_id,
            GraphEntity.entity_type == payload.entity_type,
        ).first()
        if alias_source_match:
            previous_display_name = alias_source_match.entity.display_name
            _touch_entity(alias_source_match.entity, payload)
            _refresh_authoritative_display_name(alias_source_match.entity, payload)
            _ensure_aliases(
                db,
                alias_source_match.entity,
                [*alias_candidates, previous_display_name],
                payload.source_system,
                payload.source_id,
            )
            return alias_source_match.entity, False

    if (
        not authoritative_record_id
        and normalized_address
        and payload.entity_type in {GraphEntityType.property, GraphEntityType.parcel}
    ):
        address_match = _entity_query(db).filter(
            GraphEntity.entity_type == payload.entity_type,
            GraphEntity.normalized_address == normalized_address,
        ).first()
        if address_match:
            _touch_entity(address_match, payload)
            _ensure_aliases(
                db,
                address_match,
                alias_candidates,
                payload.source_system,
                payload.source_id,
            )
            return address_match, False

    if not authoritative_record_id:
        exact_terms = normalized_terms or [normalized]
        exact = _entity_query(db).filter(
            GraphEntity.entity_type == payload.entity_type,
            GraphEntity.normalized_name.in_(exact_terms),
        )
        if normalized_address:
            exact = exact.filter(or_(GraphEntity.normalized_address == normalized_address, GraphEntity.normalized_address.is_(None)))
        exact_match = exact.first()
        if exact_match:
            _touch_entity(exact_match, payload)
            _ensure_aliases(db, exact_match, alias_candidates, payload.source_system, payload.source_id)
            return exact_match, False

        alias_match = active_query(db.query(GraphEntityAlias), GraphEntityAlias).filter(
            GraphEntityAlias.normalized_alias.in_(exact_terms),
        ).first()
        if alias_match and alias_match.entity.entity_type == payload.entity_type:
            _touch_entity(alias_match.entity, payload)
            _ensure_aliases(db, alias_match.entity, alias_candidates, payload.source_system, payload.source_id)
            return alias_match.entity, False

        if normalized_address and payload.entity_type in ADDRESS_AWARE_ENTITY_TYPES:
            address_candidates = _entity_query(db).filter(
                GraphEntity.entity_type == payload.entity_type,
                GraphEntity.normalized_address == normalized_address,
            ).order_by(GraphEntity.updated_at.desc()).limit(50).all()
            for candidate in address_candidates:
                similarity = _best_name_similarity(exact_terms, candidate.normalized_name)
                if similarity >= 0.72:
                    _touch_entity(candidate, payload)
                    _ensure_aliases(db, candidate, alias_candidates, payload.source_system, payload.source_id)
                    return candidate, False

        candidates = _resolution_candidates(
            db,
            entity_type=payload.entity_type,
            normalized_names=exact_terms,
            normalized_address=normalized_address,
        )
        for candidate in candidates:
            similarity = _best_name_similarity(exact_terms, candidate.normalized_name)
            address_matches = normalized_address and candidate.normalized_address == normalized_address
            threshold = 0.9 if payload.entity_type in {GraphEntityType.property, GraphEntityType.parcel} else 0.86
            if similarity >= threshold or (address_matches and similarity >= 0.72):
                _touch_entity(candidate, payload)
                _ensure_aliases(db, candidate, alias_candidates, payload.source_system, payload.source_id)
                return candidate, False

    entity = GraphEntity(
        organization_id=get_org_id(),
        entity_type=payload.entity_type,
        display_name=payload.display_name,
        normalized_name=normalized,
        normalized_address=normalized_address,
        source_system=payload.source_system,
        source_id=payload.source_id,
        address=payload.address,
        city=payload.city,
        state=payload.state,
        zip_code=payload.zip_code,
        confidence=payload.confidence,
        attributes=payload.attributes,
        last_verified_at=utcnow(),
    )
    db.add(entity)
    db.flush()
    _ensure_aliases(db, entity, alias_candidates, payload.source_system, payload.source_id)
    return entity, True


def _resolution_candidates(
    db: Session,
    *,
    entity_type: GraphEntityType,
    normalized_names: list[str],
    normalized_address: Optional[str],
) -> list[GraphEntity]:
    filters = []
    if normalized_address:
        filters.append(GraphEntity.normalized_address == normalized_address)
    for normalized_name in normalized_names:
        filters.append(GraphEntity.normalized_name == normalized_name)
        for token in _blocking_tokens(normalized_name):
            filters.append(GraphEntity.normalized_name == token)
            filters.append(GraphEntity.normalized_name.like(f"{token} %"))
            filters.append(GraphEntity.normalized_name.like(f"% {token}"))
            filters.append(GraphEntity.normalized_name.like(f"% {token} %"))
    if not filters:
        return []
    return (
        _entity_query(db)
        .filter(GraphEntity.entity_type == entity_type, or_(*filters))
        .order_by(GraphEntity.updated_at.desc())
        .limit(250)
        .all()
    )


def _touch_entity(entity: GraphEntity, payload: GraphEntityCreate) -> None:
    entity.confidence = max(entity.confidence, payload.confidence)
    entity.last_verified_at = utcnow()
    entity.address = entity.address or payload.address
    entity.city = entity.city or payload.city
    entity.state = entity.state or payload.state
    entity.zip_code = entity.zip_code or payload.zip_code
    entity.normalized_address = entity.normalized_address or normalize_address(payload.address, payload.city, payload.state, payload.zip_code)
    if payload.attributes:
        entity.attributes = {**(entity.attributes or {}), **payload.attributes}


def _refresh_authoritative_display_name(
    entity: GraphEntity,
    payload: GraphEntityCreate,
) -> None:
    if payload.display_name and entity.display_name != payload.display_name:
        entity.display_name = payload.display_name
        entity.normalized_name = normalize_name(payload.display_name)


def _ensure_aliases(
    db: Session,
    entity: GraphEntity,
    aliases: Iterable[str],
    source_system: Optional[str],
    source_id: Optional[str],
) -> None:
    seen = {
        alias.normalized_alias
        for alias in active_query(db.query(GraphEntityAlias), GraphEntityAlias).filter(GraphEntityAlias.entity_id == entity.id).all()
    }
    for alias in aliases:
        normalized = normalize_name(alias)
        if not normalized or normalized in seen:
            continue
        db.add(GraphEntityAlias(
            organization_id=get_org_id(),
            entity_id=entity.id,
            alias=alias,
            normalized_alias=normalized,
            source_system=source_system,
            source_id=source_id,
        ))
        seen.add(normalized)


def link_entity_to_record(
    db: Session,
    entity_id: str,
    record_type: str,
    record_id: str,
    source_system: Optional[str] = None,
) -> GraphEntityLink:
    existing = active_query(db.query(GraphEntityLink), GraphEntityLink).filter(
        GraphEntityLink.entity_id == entity_id,
        GraphEntityLink.record_type == record_type,
        GraphEntityLink.record_id == record_id,
    ).first()
    if existing:
        return existing
    link = GraphEntityLink(
        organization_id=get_org_id(),
        entity_id=entity_id,
        record_type=record_type,
        record_id=record_id,
        source_system=source_system,
    )
    db.add(link)
    db.flush()
    return link


def upsert_deal_graph_context(db: Session, deal: Deal) -> GraphEntity:
    property_entity, _ = resolve_entity(db, GraphEntityCreate(
        entity_type=GraphEntityType.property,
        display_name=deal.name,
        source_system="dealsignal",
        source_id=deal.id,
        address=deal.address,
        city=deal.city,
        state=deal.state,
        zip_code=deal.zip_code,
        confidence=1.0,
        attributes={"property_type": deal.property_type, "record_type": "deal"},
    ))
    link_entity_to_record(db, property_entity.id, "deal", deal.id, "dealsignal")
    return property_entity


def create_relationship(
    db: Session,
    payload: GraphRelationshipCreate,
    *,
    validate_entities: bool = True,
) -> GraphRelationship:
    if validate_entities:
        source = get_entity_or_none(db, payload.source_entity_id)
        target = get_entity_or_none(db, payload.target_entity_id)
        if source is None or target is None:
            raise ValueError("source_entity_id or target_entity_id does not exist")

    relationship = active_query(db.query(GraphRelationship), GraphRelationship).filter(
        GraphRelationship.source_entity_id == payload.source_entity_id,
        GraphRelationship.target_entity_id == payload.target_entity_id,
        GraphRelationship.relationship_type == payload.relationship_type,
        GraphRelationship.source_system == payload.source_system,
        GraphRelationship.source_id == payload.source_id,
    ).first()
    if relationship is None:
        relationship = GraphRelationship(
            organization_id=get_org_id(),
            source_entity_id=payload.source_entity_id,
            target_entity_id=payload.target_entity_id,
            relationship_type=payload.relationship_type,
            confidence=payload.confidence,
            source_system=payload.source_system,
            source_id=payload.source_id,
            attributes=payload.attributes,
            is_current=True,
            valid_from=utcnow(),
            last_verified_at=utcnow(),
        )
        db.add(relationship)
        db.flush()
    else:
        relationship.confidence = max(relationship.confidence, payload.confidence)
        relationship.attributes = {**(relationship.attributes or {}), **(payload.attributes or {})} or None
        relationship.last_verified_at = utcnow()
        relationship.is_current = True
        relationship.valid_to = None

    for evidence in payload.evidence:
        add_relationship_evidence(db, relationship, evidence)
    return relationship


def add_relationship_evidence(
    db: Session,
    relationship: GraphRelationship,
    evidence: GraphEvidenceCreate,
) -> GraphRelationshipEvidence:
    if evidence.source_id:
        existing = active_query(db.query(GraphRelationshipEvidence), GraphRelationshipEvidence).filter(
            GraphRelationshipEvidence.relationship_id == relationship.id,
            GraphRelationshipEvidence.source_system == evidence.source_system,
            GraphRelationshipEvidence.source_id == evidence.source_id,
        ).first()
        if existing:
            existing.observed_at = evidence.observed_at or existing.observed_at
            existing.confidence = max(existing.confidence, evidence.confidence)
            existing.source_url = evidence.source_url or existing.source_url
            existing.payload = evidence.payload or existing.payload
            relationship.last_verified_at = utcnow()
            return existing

    row = GraphRelationshipEvidence(
        organization_id=get_org_id(),
        relationship_id=relationship.id,
        source_system=evidence.source_system,
        source_id=evidence.source_id,
        source_url=evidence.source_url,
        evidence_type=evidence.evidence_type,
        excerpt=evidence.excerpt,
        observed_at=evidence.observed_at,
        confidence=evidence.confidence,
        payload=evidence.payload,
    )
    db.add(row)
    relationship.last_verified_at = utcnow()
    relationship.confidence = max(relationship.confidence, evidence.confidence)
    db.flush()
    return row


def get_entity_or_none(db: Session, entity_id: str) -> Optional[GraphEntity]:
    return _entity_query(db).options(
        joinedload(GraphEntity.aliases),
        joinedload(GraphEntity.links),
    ).filter(GraphEntity.id == entity_id).first()


def get_relationship_or_none(db: Session, relationship_id: str) -> Optional[GraphRelationship]:
    return active_query(db.query(GraphRelationship), GraphRelationship).options(
        joinedload(GraphRelationship.evidence),
        joinedload(GraphRelationship.source_entity).joinedload(GraphEntity.aliases),
        joinedload(GraphRelationship.source_entity).joinedload(GraphEntity.links),
        joinedload(GraphRelationship.target_entity).joinedload(GraphEntity.aliases),
        joinedload(GraphRelationship.target_entity).joinedload(GraphEntity.links),
    ).filter(GraphRelationship.id == relationship_id).first()


def search_entities(
    db: Session,
    query: str,
    *,
    entity_type: Optional[GraphEntityType] = None,
    limit: int = 20,
) -> list[GraphEntity]:
    normalized = normalize_name(query)
    raw = query.strip().lower()
    if not normalized and not raw:
        return []

    candidates = (
        _entity_query(db)
        .outerjoin(GraphEntity.aliases)
        .filter(
            or_(
                GraphEntity.normalized_name == normalized,
                GraphEntity.normalized_name.like(f"{normalized}%"),
                GraphEntity.normalized_name.like(f"% {normalized}%"),
                func.lower(GraphEntity.display_name).like(f"%{raw}%"),
                GraphEntityAlias.normalized_alias == normalized,
                GraphEntityAlias.normalized_alias.like(f"{normalized}%"),
                GraphEntityAlias.normalized_alias.like(f"% {normalized}%"),
            )
        )
        .options(joinedload(GraphEntity.aliases), joinedload(GraphEntity.links))
    )
    if entity_type is not None:
        candidates = candidates.filter(GraphEntity.entity_type == entity_type)

    rows = candidates.distinct().limit(250).all()

    def score(entity: GraphEntity) -> tuple[int, str, str]:
        alias_names = [alias.normalized_alias for alias in entity.aliases]
        if entity.normalized_name == normalized:
            tier = 0
        elif normalized in alias_names:
            tier = 1
        elif entity.normalized_name.startswith(normalized):
            tier = 2
        elif any(alias.startswith(normalized) for alias in alias_names):
            tier = 3
        elif raw and raw in (entity.display_name or "").lower():
            tier = 4
        else:
            tier = 5
        return (tier, entity.display_name.lower(), entity.id)

    rows.sort(key=score)
    return rows[:limit]


def entity_merge_candidates(
    db: Session,
    entity_id: str,
    *,
    limit: int = 10,
    minimum_score: float = 0.6,
) -> list[tuple[GraphEntity, float, list[str]]]:
    entity = get_entity_or_none(db, entity_id)
    if entity is None:
        return []

    query_terms = _entity_name_terms(entity)
    candidates = (
        _entity_query(db)
        .filter(
            GraphEntity.entity_type == entity.entity_type,
            GraphEntity.id != entity.id,
        )
        .options(joinedload(GraphEntity.aliases), joinedload(GraphEntity.links))
        .order_by(GraphEntity.updated_at.desc())
        .limit(250)
        .all()
    )

    scored: list[tuple[GraphEntity, float, list[str]]] = []
    for candidate in candidates:
        reasons: list[str] = []
        score = 0.0

        candidate_terms = _entity_name_terms(candidate)
        name_similarity = max(
            (_name_similarity(left, right) for left in query_terms for right in candidate_terms),
            default=0.0,
        )
        address_match = bool(
            entity.normalized_address
            and candidate.normalized_address
            and entity.normalized_address == candidate.normalized_address
        )
        source_identity_match = bool(
            entity.source_system
            and entity.source_id
            and candidate.source_system
            and candidate.source_id
            and entity.source_system == candidate.source_system
            and entity.source_id == candidate.source_id
        )

        if source_identity_match:
            score = 1.0
            reasons.append("shared source identity")
        elif entity.normalized_name == candidate.normalized_name:
            score = 0.98
            reasons.append("exact normalized name match")
        elif any(term == candidate.normalized_name for term in query_terms) or any(term in candidate_terms for term in query_terms):
            score = 0.96
            reasons.append("alias match")
        else:
            score = round(0.4 + (name_similarity * 0.45), 4)
            if name_similarity >= 0.88:
                reasons.append("strong name similarity")
            elif name_similarity >= 0.72:
                reasons.append("name similarity")

        if address_match:
            score = round(min(1.0, score + 0.18), 4)
            reasons.append("shared normalized address")

        if entity.city and candidate.city and entity.city.casefold() == candidate.city.casefold():
            score = round(min(1.0, score + 0.04), 4)
            reasons.append("same city")

        if entity.state and candidate.state and entity.state.casefold() == candidate.state.casefold():
            score = round(min(1.0, score + 0.04), 4)
            reasons.append("same state")

        if score >= minimum_score:
            scored.append((candidate, score, list(dict.fromkeys(reasons)) or ["review candidate"]))

    scored.sort(key=lambda row: (-row[1], row[0].display_name.lower(), row[0].id))
    return scored[:limit]


def entity_for_record(db: Session, record_type: str, record_id: str) -> Optional[GraphEntity]:
    return _entity_query(db).join(GraphEntity.links).filter(
        GraphEntityLink.record_type == record_type,
        GraphEntityLink.record_id == record_id,
    ).options(
        joinedload(GraphEntity.aliases),
        joinedload(GraphEntity.links),
    ).first()


def relationships_for_entity(db: Session, entity_id: str) -> list[tuple[GraphRelationship, GraphEntity, str]]:
    rows: list[tuple[GraphRelationship, GraphEntity, str]] = []
    outgoing = active_query(db.query(GraphRelationship), GraphRelationship).options(
        joinedload(GraphRelationship.evidence),
        joinedload(GraphRelationship.target_entity),
    ).filter(
        GraphRelationship.source_entity_id == entity_id,
        GraphRelationship.is_current.is_(True),
    ).order_by(
        GraphRelationship.confidence.desc(),
        GraphRelationship.last_verified_at.desc(),
        GraphRelationship.created_at.desc(),
    ).all()
    for relationship in outgoing:
        rows.append((relationship, relationship.target_entity, "outgoing"))

    incoming = active_query(db.query(GraphRelationship), GraphRelationship).options(
        joinedload(GraphRelationship.evidence),
        joinedload(GraphRelationship.source_entity),
    ).filter(
        GraphRelationship.target_entity_id == entity_id,
        GraphRelationship.is_current.is_(True),
    ).order_by(
        GraphRelationship.confidence.desc(),
        GraphRelationship.last_verified_at.desc(),
        GraphRelationship.created_at.desc(),
    ).all()
    for relationship in incoming:
        rows.append((relationship, relationship.source_entity, "incoming"))
    return rows


def find_relationship_paths(db: Session, source_entity_id: str, target_entity_id: str, max_depth: int = 4) -> list[tuple[list[GraphEntity], list[GraphRelationship]]]:
    if source_entity_id == target_entity_id:
        entity = get_entity_or_none(db, source_entity_id)
        return [([entity], [])] if entity else []

    queue = deque([(source_entity_id, [source_entity_id], [])])
    paths: list[tuple[list[GraphEntity], list[GraphRelationship]]] = []
    visited_depth: dict[str, int] = {source_entity_id: 0}

    while queue and len(paths) < 5:
        current_id, entity_ids, relationship_ids = queue.popleft()
        if len(relationship_ids) >= max_depth:
            continue
        for relationship, neighbor, _direction in relationships_for_entity(db, current_id):
            if neighbor.id in entity_ids:
                continue
            next_entity_ids = [*entity_ids, neighbor.id]
            next_relationship_ids = [*relationship_ids, relationship.id]
            if neighbor.id == target_entity_id:
                entities = _entities_by_ids(db, next_entity_ids)
                relationships = _relationships_by_ids(db, next_relationship_ids)
                paths.append((entities, relationships))
                continue
            next_depth = len(next_relationship_ids)
            if visited_depth.get(neighbor.id, max_depth + 1) <= next_depth:
                continue
            visited_depth[neighbor.id] = next_depth
            queue.append((neighbor.id, next_entity_ids, next_relationship_ids))
    return paths


def _entities_by_ids(db: Session, ids: list[str]) -> list[GraphEntity]:
    if not ids:
        return []
    rows = _entity_query(db).filter(GraphEntity.id.in_(ids)).all()
    by_id = {row.id: row for row in rows}
    return [by_id[item_id] for item_id in ids if item_id in by_id]


def _relationships_by_ids(db: Session, ids: list[str]) -> list[GraphRelationship]:
    if not ids:
        return []
    rows = active_query(db.query(GraphRelationship), GraphRelationship).options(
        joinedload(GraphRelationship.evidence)
    ).filter(GraphRelationship.id.in_(ids)).all()
    by_id = {row.id: row for row in rows}
    return [by_id[item_id] for item_id in ids if item_id in by_id]


def opportunity_context(db: Session, opportunity_id: str) -> dict:
    root_links = active_query(db.query(GraphEntityLink), GraphEntityLink).filter(
        GraphEntityLink.record_type == "deal",
        GraphEntityLink.record_id == opportunity_id,
    ).all()
    roots = [link.entity for link in root_links]
    grouped: dict[str, list[tuple[GraphRelationship, GraphEntity, str]]] = {
        "companies": [],
        "developers": [],
        "parcels": [],
        "owners": [],
        "contractors": [],
        "architects": [],
        "engineers": [],
        "permits": [],
        "cities": [],
        "lenders": [],
        "brokers": [],
        "other": [],
    }
    seen: set[tuple[str, str]] = set()
    for root in roots:
        for relationship, entity, direction in relationships_for_entity(db, root.id):
            key = (relationship.id, entity.id)
            if key in seen:
                continue
            seen.add(key)
            bucket = CONTEXT_BUCKETS.get(entity.entity_type, "other")
            grouped[bucket].append((relationship, entity, direction))
    grouped["root_entities"] = roots  # type: ignore[assignment]
    return grouped


def project_contact_to_graph(db: Session, deal: Deal, contact: Contact) -> None:
    spec = _contact_role_spec(contact.role)
    if spec is None:
        return
    entity_type, relationship_type = spec
    display_name = contact.company or contact.name
    if not display_name.strip():
        return

    deal_entity, _ = resolve_entity(db, GraphEntityCreate(
        entity_type=GraphEntityType.property,
        display_name=deal.name,
        source_system="dealsignal",
        source_id=deal.id,
        address=deal.address,
        city=deal.city,
        state=deal.state,
        zip_code=deal.zip_code,
        confidence=1.0,
        attributes={"property_type": deal.property_type, "record_type": "deal"},
    ))
    link_entity_to_record(db, deal_entity.id, "deal", deal.id, "dealsignal")
    contact_entity, _ = resolve_entity(db, GraphEntityCreate(
        entity_type=entity_type,
        display_name=display_name,
        source_system="dealsignal",
        source_id=f"contact:{contact.id}",
        confidence=0.85,
        aliases=[alias for alias in {contact.name, contact.company} if alias and alias != display_name],
        attributes={
            "contact_id": contact.id,
            "contact_name": contact.name,
            "contact_role": contact.role,
            "contact_company": contact.company,
            "contact_email": contact.email,
            "contact_phone": contact.phone,
            "deal_id": deal.id,
        },
    ))

    expire_contact_relationships(db, contact)
    create_relationship(db, GraphRelationshipCreate(
        source_entity_id=deal_entity.id,
        target_entity_id=contact_entity.id,
        relationship_type=relationship_type,
        confidence=0.9,
        source_system="dealsignal",
        source_id=f"contact:{contact.id}:{relationship_type.value}",
        attributes={
            "contact_id": contact.id,
            "contact_name": contact.name,
            "contact_role": contact.role,
            "contact_company": contact.company,
            "deal_id": deal.id,
        },
        evidence=[
            GraphEvidenceCreate(
                source_system="dealsignal",
                source_id=contact.id,
                evidence_type="deal_contact",
                excerpt=_contact_excerpt(contact),
                observed_at=contact.created_at,
                confidence=0.9,
                payload={
                    "contact_id": contact.id,
                    "deal_id": deal.id,
                    "name": contact.name,
                    "role": contact.role,
                    "company": contact.company,
                    "email": contact.email,
                    "phone": contact.phone,
                },
            )
        ],
    ))


def sync_deal_contacts_to_graph(db: Session, deal: Deal) -> None:
    contacts = active_query(db.query(Contact), Contact).filter(Contact.deal_id == deal.id).all()
    for contact in contacts:
        project_contact_to_graph(db, deal, contact)


def expire_contact_relationships(db: Session, contact: Contact) -> None:
    relationships = active_query(db.query(GraphRelationship), GraphRelationship).filter(
        GraphRelationship.source_system == "dealsignal",
        GraphRelationship.source_id.like(f"contact:{contact.id}%"),
    ).all()
    if not relationships:
        return
    now = utcnow()
    for relationship in relationships:
        relationship.is_current = False
        relationship.valid_to = now
        relationship.last_verified_at = now


def _contact_role_spec(role: Optional[str]) -> Optional[tuple[GraphEntityType, GraphRelationshipType]]:
    if not role:
        return None
    normalized = normalize_name(role)
    for keywords, entity_type, relationship_type in CONTACT_ROLE_SPECS:
        if any(keyword in normalized for keyword in keywords):
            return entity_type, relationship_type
    return None


def _contact_excerpt(contact: Contact) -> str:
    parts = [contact.name]
    if contact.company and contact.company not in parts:
        parts.append(contact.company)
    if contact.role:
        parts.append(contact.role)
    return " | ".join(parts)


def count_opportunity_connected_entities(db: Session, opportunity_id: str) -> int:
    root_ids = [
        link.entity_id
        for link in active_query(db.query(GraphEntityLink), GraphEntityLink).filter(
            GraphEntityLink.record_type == "deal",
            GraphEntityLink.record_id == opportunity_id,
        ).all()
    ]
    if not root_ids:
        return 0

    source_rows = (
        select(GraphRelationship.target_entity_id.label("entity_id"))
        .where(
            GraphRelationship.is_current.is_(True),
            GraphRelationship.source_entity_id.in_(root_ids),
        )
    )
    target_rows = (
        select(GraphRelationship.source_entity_id.label("entity_id"))
        .where(
            GraphRelationship.is_current.is_(True),
            GraphRelationship.target_entity_id.in_(root_ids),
        )
    )
    unioned = union_all(source_rows, target_rows).subquery()
    return (
        db.query(func.count(func.distinct(unioned.c.entity_id)))
        .scalar()
        or 0
    )
