from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from sqlalchemy.orm import Session, joinedload

from app.models.ingestion import IngestionSource, PermitRecord
from app.utils.org_scope import active_query

CONTRACT_VERSION = "1.0"
MAX_BATCH_RECORDS = 500
EXPORTABLE_STAGES = {"pre_approval", "approved"}


@dataclass(frozen=True)
class PublishResult:
    batch_id: str
    source_key: str
    records_found: int
    records_inserted: int
    records_updated: int


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def _clean_mapping(value: dict) -> dict:
    return {key: item for key, item in value.items() if item is not None}


def _market_id(permit: PermitRecord) -> str:
    state = (permit.state or "unknown").strip().lower()
    locality = (permit.city or permit.jurisdiction or "unknown").strip().lower()
    locality = "-".join(part for part in "".join(
        char if char.isalnum() else " " for char in locality
    ).split() if part)
    return f"{state}-{locality}"


def serialize_permit(permit: PermitRecord) -> dict:
    source = permit.source
    record_url = permit.source_url or source.base_url
    if not record_url:
        raise ValueError(
            f"Permit {permit.external_record_id} has no source evidence URL"
        )

    description = (permit.description or permit.project_name or permit.permit_type or "").strip()
    if not description:
        raise ValueError(
            f"Permit {permit.external_record_id} has no exportable description"
        )

    attributes = dict(permit.attributes or {})
    attributes.update(_clean_mapping({
        "valuation": float(permit.valuation) if permit.valuation is not None else None,
        "squareFeet": permit.square_feet,
        "units": permit.units,
        "lastSeenAt": _iso(permit.last_seen_at),
        "firstSeenAt": _iso(permit.first_seen_at),
    }))
    confidence = attributes.pop("confidence", 0.9 if permit.approval_stage in EXPORTABLE_STAGES else 0.75)
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.75
    confidence = max(0.0, min(1.0, confidence))

    return {
        "externalRecordId": permit.external_record_id,
        "marketId": _market_id(permit),
        "jurisdiction": permit.jurisdiction or source.jurisdiction or "Unknown jurisdiction",
        "approvalStage": permit.approval_stage or "unknown",
        "applicationNumber": permit.application_number,
        "permitNumber": permit.permit_number,
        "permitType": permit.permit_type or source.record_type or "Development record",
        "permitSubtype": permit.permit_subtype,
        "workClass": permit.work_class,
        "proposedUse": permit.proposed_use,
        "occupancyType": permit.occupancy_type,
        "status": permit.status,
        "description": description,
        "projectName": permit.project_name,
        "location": _clean_mapping({
            "address": permit.address,
            "city": permit.city,
            "state": permit.state,
            "postalCode": permit.postal_code,
            "parcelId": permit.parcel_id,
            "latitude": permit.latitude,
            "longitude": permit.longitude,
        }),
        "parties": _clean_mapping({
            "applicant": permit.applicant_name,
            "owner": permit.owner_name,
            "developer": permit.developer_name,
            "contractor": permit.contractor_name,
            "architect": permit.architect_name,
            "engineer": permit.engineer_name,
        }),
        "dates": _clean_mapping({
            "filedAt": _iso(permit.filed_at),
            "statusUpdatedAt": _iso(permit.status_updated_at),
            "approvedAt": _iso(permit.approved_at),
            "issuedAt": _iso(permit.issued_at),
            "completedAt": _iso(permit.completed_at),
        }),
        "evidence": {
            "recordUrl": record_url,
            "pageUrl": source.base_url,
            "excerpt": description[:2_000],
            "publishedAt": _iso(permit.status_updated_at or permit.filed_at),
            "accessedAt": _iso(permit.last_seen_at) or _iso(datetime.now(timezone.utc)),
        },
        "confidence": confidence,
        "attributes": attributes,
    }


def build_batches(
    permits: Iterable[PermitRecord], *, generated_at: datetime | None = None
) -> list[dict]:
    generated_at = generated_at or datetime.now(timezone.utc)
    records_by_scope: dict[tuple[str, str], list[PermitRecord]] = {}
    for permit in permits:
        scope = (permit.source.key, _market_id(permit))
        records_by_scope.setdefault(scope, []).append(permit)

    batches: list[dict] = []
    for source_key, market_id in sorted(records_by_scope):
        source_records = records_by_scope[(source_key, market_id)]
        source = source_records[0].source
        for chunk_index in range(0, len(source_records), MAX_BATCH_RECORDS):
            chunk = source_records[chunk_index : chunk_index + MAX_BATCH_RECORDS]
            sequence = chunk_index // MAX_BATCH_RECORDS + 1
            timestamp = generated_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            batches.append({
                "version": CONTRACT_VERSION,
                "batchId": f"{source.key}-{market_id}-{timestamp}-{sequence}",
                "generatedAt": _iso(generated_at),
                "source": {
                    "key": source.key,
                    "name": source.name,
                    "jurisdiction": source.jurisdiction,
                    "sourceUrl": source.base_url or chunk[0].source_url,
                },
                "records": [serialize_permit(permit) for permit in chunk],
            })
    return batches


def list_exportable_permits(
    db: Session,
    *,
    source_keys: list[str] | None = None,
    stages: set[str] | None = None,
    limit: int = 5_000,
) -> list[PermitRecord]:
    stages = stages or EXPORTABLE_STAGES
    query = active_query(db.query(PermitRecord), PermitRecord).options(
        joinedload(PermitRecord.source)
    ).filter(
        PermitRecord.is_active.is_(True),
        PermitRecord.approval_stage.in_(sorted(stages)),
    )
    if source_keys:
        query = query.filter(PermitRecord.source.has(IngestionSource.key.in_(source_keys)))
    return query.order_by(PermitRecord.last_seen_at.desc()).limit(limit).all()


def validate_target_url(target_url: str) -> None:
    parsed = urlparse(target_url)
    local_hosts = {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme == "https" and parsed.netloc:
        return
    if parsed.scheme == "http" and parsed.hostname in local_hosts:
        return
    raise ValueError("Build Signals target URL must use HTTPS (HTTP is allowed only for localhost)")


def publish_batch(target_url: str, secret: str, batch: dict, *, timeout: int = 30) -> PublishResult:
    validate_target_url(target_url)
    if not secret.strip():
        raise ValueError("BUILD_SIGNALS_INGESTION_SECRET is required")
    request = Request(
        target_url,
        data=json.dumps(batch, separators=(",", ":")).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {secret}",
            "Content-Type": "application/json",
            "User-Agent": "build-signals-nationwide-ingestion/1.0",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - URL validated above
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1_000]
        raise RuntimeError(f"Build Signals import returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Build Signals import request failed: {exc.reason}") from exc

    if not payload.get("ok") or not isinstance(payload.get("result"), dict):
        raise RuntimeError("Build Signals import returned an invalid acknowledgement")
    result = payload["result"]
    return PublishResult(
        batch_id=str(result["batchId"]),
        source_key=str(result["sourceKey"]),
        records_found=int(result["recordsFound"]),
        records_inserted=int(result["recordsInserted"]),
        records_updated=int(result["recordsUpdated"]),
    )
