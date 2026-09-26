from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy.orm import Session, joinedload

from app.models.graph import GraphRelationshipType
from app.models.ingestion import IngestionSource, RawSourceRecord
from app.models.parcel import ParcelRecord
from app.models.parcel_lineage import (
    ParcelLineageEvent,
    ParcelLineageEvidence,
    ParcelLineageParticipant,
)
from app.schemas.graph import GraphEvidenceCreate, GraphRelationshipCreate
from app.services.graph_service import create_relationship, entity_for_record
from app.utils.org_scope import active_query, get_org_id

LINEAGE_EVENT_TYPES = {"split", "merge", "replat", "correction"}
PARTICIPANT_ROLES = {"predecessor", "successor"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def upsert_lineage_from_snapshot(
    db: Session,
    *,
    source: IngestionSource,
    raw_record: RawSourceRecord,
    current_parcel: ParcelRecord,
    values: dict[str, Any],
    verified_at: datetime | None = None,
) -> ParcelLineageEvent | None:
    predecessor_ids = _external_ids(
        values.get("lineage_predecessor_ids"), source
    )
    successor_ids = _external_ids(values.get("lineage_successor_ids"), source)
    event_type = _clean(values.get("lineage_event_type"))
    external_event_id = _clean(values.get("lineage_event_id"))
    if not predecessor_ids and not successor_ids and not event_type and not external_event_id:
        reconcile_lineage_participants(db, source=source, parcel=current_parcel)
        return None
    if not event_type or event_type not in LINEAGE_EVENT_TYPES:
        raise ValueError("Parcel lineage event_type must be split, merge, replat, or correction")
    if not external_event_id:
        raise ValueError("Parcel lineage event_id is required when lineage is declared")
    if not predecessor_ids and not successor_ids:
        raise ValueError("Parcel lineage requires predecessor or successor parcel ids")
    if source.organization_id != get_org_id():
        raise ValueError("Parcel lineage source belongs to another organization")
    if raw_record.organization_id != get_org_id() or raw_record.source_id != source.id:
        raise ValueError("Parcel lineage evidence belongs to another source or organization")
    if (
        current_parcel.organization_id != get_org_id()
        or current_parcel.source_id != source.id
    ):
        raise ValueError("Current parcel belongs to another source or organization")

    if predecessor_ids and not successor_ids:
        successor_ids = [current_parcel.external_parcel_id]
    elif successor_ids and not predecessor_ids:
        predecessor_ids = [current_parcel.external_parcel_id]

    now = verified_at or utcnow()
    observed_at = values.get("lineage_observed_at") or values.get("observed_at") or now
    confidence = float(values.get("lineage_confidence", 1.0))
    if not 0 <= confidence <= 1:
        raise ValueError("Parcel lineage confidence must be between 0 and 1")

    event = active_query(db.query(ParcelLineageEvent), ParcelLineageEvent).filter(
        ParcelLineageEvent.source_id == source.id,
        ParcelLineageEvent.external_event_id == external_event_id,
    ).first()
    if event is None:
        event = ParcelLineageEvent(
            organization_id=get_org_id(),
            source_id=source.id,
            external_event_id=external_event_id,
            event_type=event_type,
            confidence=confidence,
            observed_at=observed_at,
            last_verified_at=now,
            attributes={"source_record_id": current_parcel.external_parcel_id},
        )
        db.add(event)
        db.flush()
    elif event.event_type != event_type:
        raise ValueError("Parcel lineage event type changed for an existing source event")
    else:
        event.confidence = max(event.confidence, confidence)
        event.last_verified_at = now

    for role, external_ids in (
        ("predecessor", predecessor_ids),
        ("successor", successor_ids),
    ):
        for external_parcel_id in external_ids:
            _upsert_participant(
                db,
                event=event,
                source=source,
                role=role,
                external_parcel_id=external_parcel_id,
                verified_at=now,
            )

    evidence = active_query(
        db.query(ParcelLineageEvidence), ParcelLineageEvidence
    ).filter(
        ParcelLineageEvidence.event_id == event.id,
        ParcelLineageEvidence.raw_source_record_id == raw_record.id,
    ).first()
    if evidence is None:
        evidence = ParcelLineageEvidence(
            organization_id=get_org_id(),
            event=event,
            raw_source_record_id=raw_record.id,
            source_url=values.get("source_url") or source.base_url,
            excerpt=_clean(values.get("lineage_excerpt")),
            confidence=confidence,
            observed_at=observed_at,
            last_verified_at=now,
            payload={
                "content_hash": raw_record.content_hash,
                "source_record_id": raw_record.external_record_id,
            },
        )
        db.add(evidence)
    else:
        evidence.last_verified_at = now
        evidence.confidence = max(evidence.confidence, confidence)

    reconcile_lineage_participants(db, source=source, parcel=current_parcel)
    db.flush()
    event = get_lineage_event(db, event.id) or event
    _project_lineage_to_graph(db, event)
    return event


def reconcile_lineage_participants(
    db: Session,
    *,
    source: IngestionSource,
    parcel: ParcelRecord,
) -> int:
    if source.organization_id != get_org_id() or parcel.organization_id != get_org_id():
        raise ValueError("Parcel lineage reconciliation crossed an organization boundary")
    if parcel.source_id != source.id:
        raise ValueError("Parcel lineage reconciliation crossed a source boundary")
    participants = active_query(
        db.query(ParcelLineageParticipant), ParcelLineageParticipant
    ).filter(
        ParcelLineageParticipant.source_id == source.id,
        ParcelLineageParticipant.external_parcel_id == parcel.external_parcel_id,
        ParcelLineageParticipant.parcel_id.is_(None),
    ).all()
    for participant in participants:
        participant.parcel_id = parcel.id
        participant.last_verified_at = parcel.last_verified_at
    db.flush()
    if participants:
        event_ids = {participant.event_id for participant in participants}
        for event_id in event_ids:
            event = get_lineage_event(db, event_id)
            if event is not None:
                _project_lineage_to_graph(db, event)
    return len(participants)


def lineage_events_for_parcel(
    db: Session, parcel_id: str
) -> list[ParcelLineageEvent]:
    return active_query(db.query(ParcelLineageEvent), ParcelLineageEvent).join(
        ParcelLineageParticipant,
        ParcelLineageParticipant.event_id == ParcelLineageEvent.id,
    ).options(
        joinedload(ParcelLineageEvent.participants).joinedload(
            ParcelLineageParticipant.parcel
        ),
        joinedload(ParcelLineageEvent.evidence),
        joinedload(ParcelLineageEvent.source),
    ).filter(
        ParcelLineageParticipant.parcel_id == parcel_id,
        ParcelLineageParticipant.organization_id == get_org_id(),
    ).order_by(
        ParcelLineageEvent.observed_at.desc(), ParcelLineageEvent.id
    ).all()


def get_lineage_event(
    db: Session, event_id: str
) -> ParcelLineageEvent | None:
    return active_query(db.query(ParcelLineageEvent), ParcelLineageEvent).options(
        joinedload(ParcelLineageEvent.participants).joinedload(
            ParcelLineageParticipant.parcel
        ),
        joinedload(ParcelLineageEvent.evidence),
        joinedload(ParcelLineageEvent.source),
    ).filter(ParcelLineageEvent.id == event_id).first()


def _upsert_participant(
    db: Session,
    *,
    event: ParcelLineageEvent,
    source: IngestionSource,
    role: str,
    external_parcel_id: str,
    verified_at: datetime,
) -> ParcelLineageParticipant:
    if role not in PARTICIPANT_ROLES:
        raise ValueError("Invalid parcel lineage participant role")
    participant = active_query(
        db.query(ParcelLineageParticipant), ParcelLineageParticipant
    ).filter(
        ParcelLineageParticipant.event_id == event.id,
        ParcelLineageParticipant.role == role,
        ParcelLineageParticipant.external_parcel_id == external_parcel_id,
    ).first()
    parcel = active_query(db.query(ParcelRecord), ParcelRecord).filter(
        ParcelRecord.source_id == source.id,
        ParcelRecord.external_parcel_id == external_parcel_id,
    ).first()
    if participant is None:
        participant = ParcelLineageParticipant(
            organization_id=get_org_id(),
            event=event,
            source_id=source.id,
            parcel_id=parcel.id if parcel else None,
            external_parcel_id=external_parcel_id,
            role=role,
            last_verified_at=verified_at,
        )
        db.add(participant)
    else:
        participant.last_verified_at = verified_at
        if participant.parcel_id is None and parcel is not None:
            participant.parcel_id = parcel.id
    return participant


def _project_lineage_to_graph(db: Session, event: ParcelLineageEvent) -> None:
    predecessors = [
        participant
        for participant in event.participants
        if participant.role == "predecessor" and participant.parcel_id
    ]
    successors = [
        participant
        for participant in event.participants
        if participant.role == "successor" and participant.parcel_id
    ]
    for predecessor in predecessors:
        predecessor_entity = entity_for_record(db, "parcel", predecessor.parcel_id)
        if predecessor_entity is None:
            continue
        for successor in successors:
            successor_entity = entity_for_record(db, "parcel", successor.parcel_id)
            if successor_entity is None or successor_entity.id == predecessor_entity.id:
                continue
            source_id = _bounded_id(
                event.source.key,
                event.external_event_id,
                predecessor.external_parcel_id,
                successor.external_parcel_id,
            )
            create_relationship(
                db,
                GraphRelationshipCreate(
                    source_entity_id=predecessor_entity.id,
                    target_entity_id=successor_entity.id,
                    relationship_type=GraphRelationshipType.related_to,
                    confidence=event.confidence,
                    source_system=event.source.key,
                    source_id=source_id,
                    attributes={
                        "lineage_event_id": event.id,
                        "lineage_external_event_id": event.external_event_id,
                        "lineage_event_type": event.event_type,
                        "predecessor_parcel_id": predecessor.parcel_id,
                        "successor_parcel_id": successor.parcel_id,
                    },
                    evidence=[
                        GraphEvidenceCreate(
                            source_system=event.source.key,
                            source_id=evidence.raw_source_record_id,
                            source_url=evidence.source_url,
                            evidence_type="parcel_lineage",
                            excerpt=evidence.excerpt,
                            observed_at=evidence.observed_at,
                            confidence=evidence.confidence,
                            payload={
                                **(evidence.payload or {}),
                                "lineage_event_id": event.id,
                                "lineage_event_type": event.event_type,
                            },
                        )
                        for evidence in event.evidence
                    ],
                ),
                validate_entities=False,
            )


def _external_ids(value: Any, source: IngestionSource) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        raw_values: Iterable[Any] = value
    else:
        delimiter = (source.settings or {}).get("lineage_delimiter", ",")
        if not isinstance(delimiter, str) or not delimiter:
            raise ValueError("source lineage_delimiter must be a non-empty string")
        raw_values = str(value).split(delimiter)
    return list(dict.fromkeys(
        cleaned for item in raw_values if (cleaned := _clean(item))
    ))


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(str(value).strip().split())
    return cleaned or None


def _bounded_id(*parts: str) -> str:
    value = ":".join(parts)
    if len(value) <= 255:
        return value
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"{value[:189]}:{digest}"
