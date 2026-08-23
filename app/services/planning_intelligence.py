from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session, joinedload

from app.models.brand import BrandAlias, BrandProfile
from app.models.ingestion import RawSourceRecord
from app.models.planning import PlanningCompanyMatch, PlanningRecord
from app.utils.org_scope import active_query, get_org_id

DETECTOR_VERSION = "planning-v1"
FIELD_CONFIDENCE = {
    "project_name": 0.98,
    "title": 0.95,
    "applicant_name": 0.94,
    "developer_name": 0.92,
    "owner_name": 0.88,
    "summary": 0.82,
    "evidence_excerpt": 0.78,
}
DATA_CENTER_TERMS = (
    "data center",
    "data centre",
    "hyperscale",
    "server farm",
    "cloud computing campus",
    "mission critical facility",
)
INCENTIVE_TERMS = (
    "tax incentive",
    "tax abatement",
    "economic development agreement",
    "development agreement",
    "performance agreement",
    "chapter 380",
    "chapter 381",
    "payment in lieu of taxes",
    "pilot agreement",
)
LAND_ACTION_TERMS = (
    "rezoning",
    "zoning amendment",
    "conditional use",
    "special use",
    "site plan",
    "annexation",
    "comprehensive plan amendment",
)
EXPANSION_TERMS = (
    "new facility",
    "new location",
    "expansion",
    "distribution center",
    "distribution centre",
    "fulfillment center",
    "manufacturing facility",
    "corporate campus",
    "regional headquarters",
)


def enrich_planning_record(
    db: Session,
    planning_record: PlanningRecord,
    raw_record: RawSourceRecord,
) -> list[PlanningCompanyMatch]:
    """Classify a planning event and persist exact, reviewable company mentions."""
    fields = {
        field: value
        for field in FIELD_CONFIDENCE
        if isinstance((value := getattr(planning_record, field, None)), str) and value.strip()
    }
    combined = _normalize(" ".join(fields.values()))
    categories: list[str] = []
    reasons: list[str] = []
    score = 0.0

    if _contains_any(combined, DATA_CENTER_TERMS):
        categories.append("data_center")
        reasons.append(
            "Data-center or hyperscale facility language appears in public planning evidence"
        )
        score += 50
    if _contains_any(combined, INCENTIVE_TERMS):
        categories.append("economic_incentive")
        reasons.append("Public incentive or development-agreement language appears in the record")
        score += 20
    if _contains_any(combined, LAND_ACTION_TERMS):
        categories.append("land_use_action")
        reasons.append("A zoning, site-plan, annexation, or entitlement action is referenced")
        score += 15
    if _contains_any(combined, EXPANSION_TERMS):
        categories.append("corporate_expansion")
        reasons.append("Expansion or new-facility language appears in the record")
        score += 25

    aliases = (
        active_query(db.query(BrandAlias), BrandAlias)
        .options(joinedload(BrandAlias.brand))
        .join(BrandProfile)
        .filter(
            BrandAlias.is_active.is_(True),
            BrandProfile.is_active.is_(True),
        )
        .all()
    )
    best: dict[str, tuple[BrandAlias, str, str, float]] = {}
    for alias in aliases:
        normalized_alias = alias.normalized_alias
        if alias.requires_context and not _contains_any(combined, alias.context_terms or []):
            continue
        for field, value in fields.items():
            if not _contains(_normalize(value), normalized_alias):
                continue
            confidence = round(FIELD_CONFIDENCE[field] * alias.confidence, 4)
            current = best.get(alias.brand_id)
            if current is None or confidence > current[3]:
                best[alias.brand_id] = (alias, field, _excerpt(value, alias.alias), confidence)

    now = datetime.now(timezone.utc)
    matches: list[PlanningCompanyMatch] = []
    for alias, field, excerpt, confidence in best.values():
        match = (
            active_query(db.query(PlanningCompanyMatch), PlanningCompanyMatch)
            .filter(
                PlanningCompanyMatch.planning_record_id == planning_record.id,
                PlanningCompanyMatch.brand_id == alias.brand_id,
            )
            .first()
        )
        if match is None:
            match = PlanningCompanyMatch(
                organization_id=get_org_id(),
                planning_record_id=planning_record.id,
                brand_id=alias.brand_id,
                raw_record_id=raw_record.id,
                confidence=confidence,
                matched_alias=alias.alias,
                matched_field=field,
                excerpt=excerpt,
                detector_version=DETECTOR_VERSION,
                first_seen_at=now,
                last_seen_at=now,
            )
            db.add(match)
        else:
            match.raw_record_id = raw_record.id
            match.last_seen_at = now
            if match.review_status == "retracted":
                match.review_status = "candidate"
            if confidence >= match.confidence:
                match.confidence = confidence
                match.matched_alias = alias.alias
                match.matched_field = field
                match.excerpt = excerpt
                match.detector_version = DETECTOR_VERSION
        matches.append(match)

    detected_ids = set(best)
    existing = (
        active_query(db.query(PlanningCompanyMatch), PlanningCompanyMatch)
        .filter(
            PlanningCompanyMatch.planning_record_id == planning_record.id,
            PlanningCompanyMatch.review_status == "candidate",
        )
        .all()
    )
    for match in existing:
        if match.brand_id not in detected_ids:
            match.review_status = "retracted"
            match.raw_record_id = raw_record.id
            match.last_seen_at = now

    if matches:
        categories.append("tracked_company")
        company_names = sorted({match.brand.name for match in matches})
        reasons.append(f"Tracked company mentioned: {', '.join(company_names)}")
        score += min(30, 15 + 5 * len(company_names))
    if planning_record.meeting_at:
        score += 5
    if planning_record.parcel_id or (
        planning_record.latitude is not None and planning_record.longitude is not None
    ):
        categories.append("parcel_locatable")
        reasons.append("The planning evidence can be tied to a parcel or map location")
        score += 10

    planning_record.signal_categories = list(dict.fromkeys(categories))
    planning_record.priority_reasons = reasons
    planning_record.priority_score = min(100.0, score)
    db.flush()
    return matches


def list_planning_records(
    db: Session,
    *,
    state: str | None = None,
    city: str | None = None,
    category: str | None = None,
    minimum_priority: float = 0,
    limit: int = 100,
) -> list[PlanningRecord]:
    query = active_query(db.query(PlanningRecord), PlanningRecord).options(
        joinedload(PlanningRecord.latest_raw_record),
        joinedload(PlanningRecord.company_matches).joinedload(PlanningCompanyMatch.brand)
    )
    if state:
        query = query.filter(PlanningRecord.state == state.upper())
    if city:
        query = query.filter(PlanningRecord.city.ilike(city))
    if category:
        # JSON containment differs across SQLite and Postgres; keep this bounded
        # and portable until category volume warrants a normalized join table.
        query = query.filter(PlanningRecord.signal_categories.contains(category))
    query = query.filter(PlanningRecord.priority_score >= minimum_priority)
    return (
        query.order_by(
            PlanningRecord.priority_score.desc(),
            PlanningRecord.meeting_at.desc(),
            PlanningRecord.first_seen_at.desc(),
        )
        .limit(limit)
        .all()
    )


def get_planning_record(db: Session, record_id: str) -> PlanningRecord | None:
    return (
        active_query(db.query(PlanningRecord), PlanningRecord)
        .options(
            joinedload(PlanningRecord.latest_raw_record),
            joinedload(PlanningRecord.company_matches).joinedload(PlanningCompanyMatch.brand),
        )
        .filter(PlanningRecord.id == record_id)
        .first()
    )


def review_company_match(
    db: Session, match_id: str, review_status: str
) -> PlanningCompanyMatch | None:
    match = (
        active_query(db.query(PlanningCompanyMatch), PlanningCompanyMatch)
        .filter(PlanningCompanyMatch.id == match_id)
        .first()
    )
    if match is None:
        return None
    match.review_status = review_status
    db.commit()
    db.refresh(match)
    return match


def _normalize(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


def _contains(haystack: str, needle: str) -> bool:
    normalized = _normalize(needle)
    return bool(normalized and re.search(rf"(?:^|\s){re.escape(normalized)}(?:$|\s)", haystack))


def _contains_any(haystack: str, terms: list[str] | tuple[str, ...]) -> bool:
    return any(_contains(haystack, term) for term in terms)


def _excerpt(value: str, alias: str, radius: int = 120) -> str:
    index = value.casefold().find(alias.casefold())
    if index < 0:
        return value[: radius * 2]
    return value[max(0, index - radius) : index + len(alias) + radius].strip()
