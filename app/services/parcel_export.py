from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.logging_config import get_request_id
from app.models.ingestion import IngestionSource
from app.models.parcel import NearbyParcelCandidate, NearbyParcelSearch, ParcelRecord
from app.services.audit_service import log_change
from app.utils.org_scope import active_query, get_org_id

EXPORT_COLUMNS = (
    "rank",
    "external_parcel_id",
    "address",
    "city",
    "state",
    "distance_miles",
    "score",
    "score_confidence_percent",
    "review_status",
    "zoning_code",
    "land_use",
    "reason",
    "caution",
    "source_key",
    "last_verified_at",
)

# These are the exact policy decisions reviewed for parcel-context export. New
# values must be deliberately admitted here; policy-like free text fails closed.
_POLICY_FIELDS: dict[str, frozenset[str]] = {
    "derived_parcel_context_no_raw_source_replacement_export": frozenset(
        {"identity", "state", "situs", "land_context"}
    ),
    "derived_parcel_context_no_raw_polygon_source_replacement_export": frozenset(
        {"identity", "state", "situs", "land_context"}
    ),
    "derived_geometry_situs_only_no_raw_source_export": frozenset(
        {"identity", "state", "situs"}
    ),
    "derived_geometry_parcel_id_only_no_raw_pva_source_export": frozenset(
        {"identity", "state"}
    ),
    "derived_geometry_context_only_no_raw_assessor_source_resale": frozenset(
        {"identity", "state", "land_context"}
    ),
    "derived_geometry_nearby_parcel_context_only_no_raw_polygon_or_source_replacement_export": frozenset(
        {"identity", "state", "situs", "land_context"}
    ),
    "derived_statewide_parcel_context_only_no_raw_fdor_cadastral_resale": frozenset(
        {"identity", "state", "situs", "land_context"}
    ),
}
for _policy in (
    "derived_nearby_parcel_context_only_no_raw_delaware_firstmap_resale",
    "derived_nearby_parcel_context_only_no_raw_vgin_parcel_resale",
    "derived_nearby_parcel_context_only_no_raw_dcgis_owner_polygon_resale",
    "derived_nearby_parcel_context_only_no_raw_vcgi_source_resale",
    "derived_nearby_parcel_context_only_no_raw_ri_tax_parcel_resale",
    "derived_nearby_parcel_context_only_no_raw_nh_parcel_mosaic_resale",
    "derived_nearby_parcel_context_only_no_raw_alabama_local_parcel_resale",
    "derived_nearby_parcel_context_only_no_raw_arkansas_cadastral_resale",
    "derived_nearby_parcel_context_only_no_raw_collin_cad_resale",
    "derived_nearby_parcel_context_only_no_raw_tennessee_comptroller_resale",
    "derived_nearby_parcel_context_only_no_raw_greenville_county_sc_resale",
    "derived_nearby_parcel_context_only_no_raw_sedgwick_resale",
    "derived_nearby_parcel_context_only_no_owner_or_raw_assessor_resale",
    "derived_nearby_parcel_context_only_no_raw_sioux_falls_parcel_resale",
    "derived_nearby_parcel_context_only_no_raw_cass_county_nd_resale",
    "derived_nearby_parcel_context_only_no_raw_polygon_or_source_resale",
    "derived_nearby_parcel_context_only_no_raw_polygon_or_source_replacement_export",
):
    _POLICY_FIELDS[_policy] = frozenset(
        {"identity", "state", "situs", "land_context"}
    )


class ParcelExportDenied(ValueError):
    """A policy or data-isolation decision denied a parcel export."""


@dataclass(frozen=True)
class NearbyParcelExport:
    content: str
    filename: str
    exported_count: int
    omitted_count: int


def export_nearby_parcel_search(
    db: Session,
    *,
    search_id: str,
    actor_user_id: str,
) -> NearbyParcelExport:
    organization_id = get_org_id()
    search = active_query(db.query(NearbyParcelSearch), NearbyParcelSearch).filter(
        NearbyParcelSearch.id == search_id
    ).first()
    if search is None:
        raise LookupError("Nearby parcel search not found")

    all_candidate_count = db.query(NearbyParcelCandidate.id).filter(
        NearbyParcelCandidate.search_id == search.id
    ).count()
    candidates = (
        db.query(NearbyParcelCandidate, ParcelRecord, IngestionSource)
        .join(ParcelRecord, ParcelRecord.id == NearbyParcelCandidate.parcel_id)
        .join(IngestionSource, IngestionSource.id == ParcelRecord.source_id)
        .filter(
            NearbyParcelCandidate.search_id == search.id,
            NearbyParcelCandidate.organization_id == organization_id,
            ParcelRecord.organization_id == organization_id,
            IngestionSource.organization_id == organization_id,
            ParcelRecord.is_active.is_(True),
        )
        .order_by(NearbyParcelCandidate.rank)
        .all()
    )
    if len(candidates) != all_candidate_count:
        _log_export_decision(
            db,
            search_id=search.id,
            actor_user_id=actor_user_id,
            action="export_denied",
            details={
                "reason": "candidate_tenant_or_integrity_mismatch",
                "candidate_count": all_candidate_count,
                "eligible_candidate_count": len(candidates),
            },
        )
        raise ParcelExportDenied("Parcel export failed organization integrity checks")

    rows: list[list[Any]] = []
    omitted = 0
    exported_candidate_ids: list[str] = []
    policy_decisions: dict[str, dict[str, Any]] = {}
    for candidate, parcel, source in candidates:
        settings = source.settings if isinstance(source.settings, dict) else {}
        fields = derived_export_fields(settings) if source.is_active else frozenset()
        policy = settings.get("export_policy")
        policy_decisions[source.key] = {
            "active": source.is_active,
            "policy": policy if isinstance(policy, str) else None,
            "policy_version": source.updated_at.isoformat(),
            "approved": bool(fields),
        }
        if not fields:
            omitted += 1
            continue
        explanation = candidate.explanation or {}
        rows.append([
            candidate.rank,
            parcel.external_parcel_id,
            _field(parcel.address, "situs", fields),
            _field(parcel.city, "situs", fields),
            _field(parcel.state, "state", fields),
            round(candidate.distance_miles, 4),
            round(candidate.score, 2),
            round(candidate.score_confidence * 100, 1),
            candidate.review_status,
            _field(parcel.zoning_code, "land_context", fields),
            _field(parcel.land_use, "land_context", fields),
            _first_text(explanation.get("reasons")),
            _first_text(explanation.get("cautions")),
            source.key,
            parcel.last_verified_at.isoformat(),
        ])
        exported_candidate_ids.append(candidate.id)

    if not rows:
        _log_export_decision(
            db,
            search_id=search.id,
            actor_user_id=actor_user_id,
            action="export_denied",
            details={
                "reason": "no_reviewed_active_source_policy",
                "candidate_count": len(candidates),
                "policy_decisions": policy_decisions,
            },
        )
        raise ParcelExportDenied(
            "No candidates are exportable under their reviewed source policies"
        )

    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(EXPORT_COLUMNS)
    writer.writerows([[_spreadsheet_safe(value) for value in row] for row in rows])
    content = buffer.getvalue()
    _log_export_decision(
        db,
        search_id=search.id,
        actor_user_id=actor_user_id,
        action="export",
        details={
            "format": "csv",
            "exported_count": len(rows),
            "omitted_count": omitted,
            "candidate_ids": exported_candidate_ids,
            "policy_decisions": policy_decisions,
            "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "columns": list(EXPORT_COLUMNS),
            "raw_geometry_included": False,
            "ownership_included": False,
        },
    )
    return NearbyParcelExport(
        content=content,
        filename=f"nearby-parcels-{search.id}.csv",
        exported_count=len(rows),
        omitted_count=omitted,
    )


def derived_export_fields(settings: dict[str, Any] | None) -> frozenset[str]:
    if not isinstance(settings, dict):
        return frozenset()
    policy = settings.get("export_policy")
    if not isinstance(policy, str):
        return frozenset()
    return _POLICY_FIELDS.get(policy.strip().casefold(), frozenset())


def _log_export_decision(
    db: Session,
    *,
    search_id: str,
    actor_user_id: str,
    action: str,
    details: dict[str, Any],
) -> None:
    log_change(
        db,
        "nearby_parcel_search",
        search_id,
        action,
        actor_id=actor_user_id,
        organization_id=get_org_id(),
        request_id=get_request_id(),
        new_values=details,
    )


def _field(value: Any, field: str, allowed: frozenset[str]) -> Any:
    return value if field in allowed and value is not None else ""


def _first_text(value: Any) -> str:
    if not isinstance(value, list) or not value:
        return ""
    first = value[0]
    return first if isinstance(first, str) else ""


def _spreadsheet_safe(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value
