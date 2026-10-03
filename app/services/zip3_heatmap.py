"""ZIP3 market heat from stored signals and parcel-candidate activity."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from math import log1p
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.models.parcel import NearbyParcelCandidate, ParcelRecord
from app.models.ingestion import PermitRecord
from app.services.parcel_availability import availability_label, verified_availability_fact
from app.utils.org_scope import active_query


def _zip3(value: str | None) -> str | None:
    digits = "".join(char for char in (value or "") if char.isdigit())
    return digits[:3] if len(digits) >= 3 else None


def _valid_coordinate(latitude: float | None, longitude: float | None) -> bool:
    return latitude is not None and longitude is not None and -85 <= latitude <= 85 and -180 <= longitude <= 180


def _stage_weight(stage: str | None) -> float:
    if stage == "pre_approval":
        return 2.5
    if stage == "approved":
        return 1.2
    return 0.8


def _empty_bucket(zip3: str) -> dict[str, Any]:
    return {
        "zip3": zip3,
        "score": 0.0,
        "signal_count": 0,
        "pre_approval_signals": 0,
        "approved_signals": 0,
        "mapped_signals": 0,
        "parcel_candidate_count": 0,
        "shortlisted_parcel_count": 0,
        "verified_for_sale_count": 0,
        "candidate_not_listing_count": 0,
        "states": set(),
        "cities": set(),
        "sample_signals": [],
        "sample_parcels": [],
        "latest_signal_at": None,
        "_latitude_sum": 0.0,
        "_longitude_sum": 0.0,
        "_coordinate_count": 0,
    }


def zip3_heatmap(db: Session, *, limit: int = 50, state: str | None = None) -> dict[str, Any]:
    if not 1 <= limit <= 100:
        raise ValueError("Limit must be between 1 and 100")
    state_filter = state.strip().upper() if state else None
    buckets: dict[str, dict[str, Any]] = {}

    permit_query = active_query(db.query(PermitRecord), PermitRecord).filter(PermitRecord.is_active.is_(True))
    if state_filter:
        permit_query = permit_query.filter(PermitRecord.state.ilike(state_filter))
    permits = permit_query.order_by(PermitRecord.updated_at.desc(), PermitRecord.id).limit(10_000).all()
    for permit in permits:
        key = _zip3(permit.postal_code)
        if key is None:
            continue
        bucket = buckets.setdefault(key, _empty_bucket(key))
        bucket["signal_count"] += 1
        if permit.approval_stage == "pre_approval":
            bucket["pre_approval_signals"] += 1
        elif permit.approval_stage == "approved":
            bucket["approved_signals"] += 1
        if _valid_coordinate(permit.latitude, permit.longitude):
            bucket["mapped_signals"] += 1
            bucket["_latitude_sum"] += permit.latitude
            bucket["_longitude_sum"] += permit.longitude
            bucket["_coordinate_count"] += 1
        if permit.state:
            bucket["states"].add(permit.state.upper())
        if permit.city:
            bucket["cities"].add(permit.city)
        occurred = permit.filed_at or permit.approved_at or permit.issued_at or permit.updated_at
        if occurred and (bucket["latest_signal_at"] is None or occurred > bucket["latest_signal_at"]):
            bucket["latest_signal_at"] = occurred
        bucket["score"] += _stage_weight(permit.approval_stage)
        if len(bucket["sample_signals"]) < 3:
            bucket["sample_signals"].append({
                "id": permit.id,
                "title": permit.project_name or permit.permit_number or permit.external_record_id,
                "stage": permit.approval_stage,
                "status": permit.status,
                "city": permit.city,
                "state": permit.state,
                "source_url": permit.source_url,
            })

    candidate_query = active_query(db.query(NearbyParcelCandidate), NearbyParcelCandidate).options(
        joinedload(NearbyParcelCandidate.parcel).joinedload(ParcelRecord.facts),
    ).join(ParcelRecord, NearbyParcelCandidate.parcel_id == ParcelRecord.id)
    if state_filter:
        candidate_query = candidate_query.filter(ParcelRecord.state.ilike(state_filter))
    candidates = candidate_query.order_by(NearbyParcelCandidate.created_at.desc(), NearbyParcelCandidate.id).limit(10_000).all()
    seen_parcels_by_zip: dict[str, set[str]] = defaultdict(set)
    shortlisted_by_zip: dict[str, set[str]] = defaultdict(set)
    verified_for_sale_by_zip: dict[str, set[str]] = defaultdict(set)
    for candidate in candidates:
        parcel = candidate.parcel
        key = _zip3(parcel.postal_code)
        if key is None:
            continue
        bucket = buckets.setdefault(key, _empty_bucket(key))
        seen_parcels_by_zip[key].add(parcel.id)
        if candidate.review_status == "shortlisted":
            shortlisted_by_zip[key].add(parcel.id)
        availability_fact = verified_availability_fact(parcel.facts)
        if availability_fact is not None:
            verified_for_sale_by_zip[key].add(parcel.id)
        if parcel.state:
            bucket["states"].add(parcel.state.upper())
        if parcel.city:
            bucket["cities"].add(parcel.city)
        if _valid_coordinate(parcel.latitude, parcel.longitude):
            bucket["_latitude_sum"] += parcel.latitude
            bucket["_longitude_sum"] += parcel.longitude
            bucket["_coordinate_count"] += 1
        bucket["score"] += max(0.0, candidate.score) * 0.35
        if candidate.review_status == "shortlisted":
            bucket["score"] += 1.5
        if len(bucket["sample_parcels"]) < 3:
            bucket["sample_parcels"].append({
                "id": parcel.id,
                "external_parcel_id": parcel.external_parcel_id,
                "address": parcel.address,
                "city": parcel.city,
                "state": parcel.state,
                "review_status": candidate.review_status,
                "candidate_score": candidate.score,
                "availability_label": availability_label(parcel.facts),
                "availability_source_url": availability_fact.source_url if availability_fact else None,
            })

    for key, bucket in buckets.items():
        candidate_count = len(seen_parcels_by_zip.get(key, set()))
        shortlisted_count = len(shortlisted_by_zip.get(key, set()))
        verified_count = len(verified_for_sale_by_zip.get(key, set()))
        bucket["parcel_candidate_count"] = candidate_count
        bucket["shortlisted_parcel_count"] = shortlisted_count
        bucket["verified_for_sale_count"] = verified_count
        bucket["candidate_not_listing_count"] = max(0, candidate_count - verified_count)
        bucket["score"] += log1p(candidate_count) * 2.0 + log1p(shortlisted_count) * 2.0
        bucket["score"] += log1p(verified_count) * 2.5

    items = sorted(
        buckets.values(),
        key=lambda item: (item["score"], item["pre_approval_signals"], item["parcel_candidate_count"], item["zip3"]),
        reverse=True,
    )[:limit]
    for item in items:
        item["score"] = round(item["score"], 2)
        item["states"] = sorted(item["states"])
        item["cities"] = sorted(item["cities"])[:8]
        coordinate_count = item.pop("_coordinate_count", 0)
        latitude_sum = item.pop("_latitude_sum", 0.0)
        longitude_sum = item.pop("_longitude_sum", 0.0)
        item["latitude"] = round(latitude_sum / coordinate_count, 6) if coordinate_count else None
        item["longitude"] = round(longitude_sum / coordinate_count, 6) if coordinate_count else None
        latest = item["latest_signal_at"]
        item["latest_signal_at"] = latest.isoformat() if isinstance(latest, datetime) else None

    return {
        "items": items,
        "limit": limit,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method_version": "zip3-opportunity-heat-v1",
        "state": state_filter,
        "for_sale_semantics": {
            "nearby_candidate": "Public parcel or ranked nearby result near a signal; not a listing.",
            "verified_for_sale": "Requires listing, broker, owner, or explicit availability evidence. No such source is inferred here.",
        },
    }
