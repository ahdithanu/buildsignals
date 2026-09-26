from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.models.graph import GraphEntityType, GraphRelationship
from app.models.ingestion import IngestionRun, IngestionSource, RawSourceRecord
from app.models.organization import Organization
from app.models.parcel import ParcelRecord
from app.models.parcel_lineage import (
    ParcelLineageEvent,
    ParcelLineageEvidence,
    ParcelLineageParticipant,
)
from app.schemas.graph import GraphEntityCreate
from app.services.graph_service import link_entity_to_record, resolve_entity
from app.services.ingestion.normalization import normalize_parcel
from app.services.parcel_ingestion import upsert_parcel_snapshot
from app.services.parcel_lineage import (
    reconcile_lineage_participants,
    upsert_lineage_from_snapshot,
)


def _raw(db, source, run, external_id, content_hash, received_at):
    raw = RawSourceRecord(
        id=str(uuid4()),
        organization_id="default-org",
        source_id=source.id,
        run_id=run.id,
        external_record_id=external_id,
        record_type="parcel",
        content_hash=content_hash,
        payload={"id": external_id},
        received_at=received_at,
    )
    db.add(raw)
    db.flush()
    return raw


def _parcel(db, source, raw, external_id, verified_at):
    parcel, _ = upsert_parcel_snapshot(
        db,
        source=source,
        raw_record=raw,
        external_parcel_id=external_id,
        values={
            "address": f"{external_id} Main Street",
            "city": "Austin",
            "state": "TX",
            "latitude": 30.2672,
            "longitude": -97.7431,
        },
        facts=[],
        verified_at=verified_at,
    )
    entity, _ = resolve_entity(db, GraphEntityCreate(
        entity_type=GraphEntityType.parcel,
        display_name=external_id,
        source_system=source.key,
        source_id=f"{source.key}:{external_id}",
        attributes={"parcel_record_id": parcel.id},
    ))
    link_entity_to_record(db, entity.id, "parcel", parcel.id, source.key)
    return parcel


def _setup(db):
    now = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)
    db.add(Organization(
        id="default-org", name="Default Org", slug="default-org", is_active=True
    ))
    source = IngestionSource(
        id=str(uuid4()),
        organization_id="default-org",
        key="lineage-assessor",
        name="Lineage Assessor",
        adapter="csv",
        record_type="parcel",
        base_url="https://example.gov/parcels",
        settings={"lineage_delimiter": "|"},
    )
    db.add(source)
    db.flush()
    run = IngestionRun(
        id=str(uuid4()),
        organization_id="default-org",
        source_id=source.id,
        status="completed",
        trigger="manual",
    )
    db.add(run)
    db.flush()
    return source, run, now


def test_normalize_parcel_preserves_generic_lineage_fields():
    observed_at = "2026-08-14T12:00:00Z"
    normalized = normalize_parcel(
        {
            "id": "CHILD-1",
            "lineage_id": "SPLIT-2026-100",
            "lineage_type": "split",
            "parents": ["PARENT-1", "PARENT-2"],
            "lineage_date": observed_at,
            "lineage_score": "0.96",
        },
        {
            "id": "source_record_id",
            "lineage_id": "lineage_event_id",
            "lineage_type": "lineage_event_type",
            "parents": "lineage_predecessor_ids",
            "lineage_date": "lineage_observed_at",
            "lineage_score": "lineage_confidence",
        },
    )

    assert normalized.values["lineage_predecessor_ids"] == [
        "PARENT-1",
        "PARENT-2",
    ]
    assert normalized.values["lineage_event_type"] == "split"
    assert float(normalized.values["lineage_confidence"]) == 0.96
    assert normalized.values["lineage_observed_at"].isoformat().startswith(
        "2026-08-14T12:00:00"
    )


def test_csv_parcel_ingestion_persists_lineage_and_graph(client, db, tmp_path):
    csv_path = tmp_path / "parcel-lineage.csv"
    csv_path.write_text(
        "parcel,address,lat,lon,lineage_id,lineage_type,parents,lineage_date,confidence,evidence\n"
        "PARENT,100 Main St,30.2672,-97.7431,,,,,,\n"
        "CHILD,102 Main St,30.2673,-97.7432,SPLIT-42,split,PARENT,2026-08-14T12:00:00Z,0.98,Recorded plat split\n"
    )
    mappings = {
        "parcel": "source_record_id",
        "address": "address",
        "lat": "latitude",
        "lon": "longitude",
        "lineage_id": "lineage_event_id",
        "lineage_type": "lineage_event_type",
        "parents": "lineage_predecessor_ids",
        "lineage_date": "lineage_observed_at",
        "confidence": "lineage_confidence",
        "evidence": "lineage_excerpt",
    }
    source_response = client.post("/ingestion/sources", json={
        "key": "lineage_csv_test",
        "name": "Lineage CSV test",
        "adapter": "csv",
        "record_type": "parcel",
        "base_url": str(csv_path),
        "settings": {"connector": {"page_size": 100}},
        "field_mappings": [
            {
                "source_field": source_field,
                "canonical_field": canonical_field,
                "is_required": source_field in {"parcel", "lat", "lon"},
            }
            for source_field, canonical_field in mappings.items()
        ],
    })
    assert source_response.status_code == 201, source_response.text

    run = client.post(
        f"/ingestion/sources/{source_response.json()['id']}/runs",
        json={"max_pages": 1},
    )
    assert run.status_code == 201, run.text
    assert run.json()["status"] == "completed", run.text

    event = db.query(ParcelLineageEvent).one()
    assert event.external_event_id == "SPLIT-42"
    assert event.event_type == "split"
    assert event.confidence == 0.98
    assert {
        (participant.role, participant.external_parcel_id)
        for participant in event.participants
    } == {("predecessor", "PARENT"), ("successor", "CHILD")}
    assert db.query(ParcelLineageEvidence).one().excerpt == "Recorded plat split"
    relationship = db.query(GraphRelationship).filter(
        GraphRelationship.attributes["lineage_event_id"].as_string() == event.id
    ).one()
    assert relationship.attributes["lineage_event_type"] == "split"
    assert db.query(ParcelRecord).count() == 2


def test_split_lineage_groups_children_versions_evidence_and_projects_graph(client, db):
    source, run, now = _setup(db)
    parent_raw = _raw(db, source, run, "PARENT", "parent-hash", now)
    parent = _parcel(db, source, parent_raw, "PARENT", now)

    first_raw = _raw(db, source, run, "CHILD-1", "child-1-hash", now)
    first_child = _parcel(db, source, first_raw, "CHILD-1", now)
    first = upsert_lineage_from_snapshot(
        db,
        source=source,
        raw_record=first_raw,
        current_parcel=first_child,
        values={
            "lineage_event_id": "SPLIT-2026-100",
            "lineage_event_type": "split",
            "lineage_predecessor_ids": "PARENT",
            "lineage_observed_at": now,
            "lineage_confidence": 0.97,
            "lineage_excerpt": "Parcel PARENT split into two tax lots.",
            "source_url": "https://example.gov/parcels/SPLIT-2026-100",
        },
        verified_at=now,
    )
    assert first is not None

    second_raw = _raw(db, source, run, "CHILD-2", "child-2-hash", now)
    second_child = _parcel(db, source, second_raw, "CHILD-2", now)
    second = upsert_lineage_from_snapshot(
        db,
        source=source,
        raw_record=second_raw,
        current_parcel=second_child,
        values={
            "lineage_event_id": "SPLIT-2026-100",
            "lineage_event_type": "split",
            "lineage_predecessor_ids": ["PARENT"],
            "lineage_confidence": 0.95,
            "lineage_observed_at": now,
        },
        verified_at=now,
    )
    db.commit()

    assert second is not None and second.id == first.id
    assert db.query(ParcelLineageEvent).count() == 1
    assert db.query(ParcelLineageParticipant).count() == 3
    assert db.query(ParcelLineageEvidence).count() == 2
    assert {
        (participant.role, participant.external_parcel_id)
        for participant in second.participants
    } == {
        ("predecessor", "PARENT"),
        ("successor", "CHILD-1"),
        ("successor", "CHILD-2"),
    }
    relationships = db.query(GraphRelationship).filter(
        GraphRelationship.attributes["lineage_event_id"].as_string() == second.id
    ).all()
    assert len(relationships) == 2
    assert all(row.attributes["lineage_event_type"] == "split" for row in relationships)

    later = now + timedelta(days=1)
    replay = upsert_lineage_from_snapshot(
        db,
        source=source,
        raw_record=first_raw,
        current_parcel=first_child,
        values={
            "lineage_event_id": "SPLIT-2026-100",
            "lineage_event_type": "split",
            "lineage_predecessor_ids": "PARENT",
        },
        verified_at=later,
    )
    db.commit()
    assert replay is not None
    assert db.query(ParcelLineageEvent).count() == 1
    assert db.query(ParcelLineageEvidence).count() == 2
    replay_verified_at = db.query(ParcelLineageEvidence).filter_by(
        raw_source_record_id=first_raw.id
    ).one().last_verified_at
    assert replay_verified_at.replace(tzinfo=timezone.utc) == later

    detail = client.get(f"/parcels/{parent.id}")
    assert detail.status_code == 200, detail.text
    lineage = detail.json()["lineage_events"][0]
    assert lineage["event_type"] == "split"
    assert lineage["source_key"] == source.key
    assert len(lineage["participants"]) == 3
    event_detail = client.get(f"/parcel-lineage-events/{second.id}")
    assert event_detail.status_code == 200, event_detail.text
    assert len(event_detail.json()["evidence"]) == 2

    other_org = client.post("/auth/register", json={
        "email": "lineage-other@example.com",
        "password": "CorrectHorseBattery42",
        "full_name": "Lineage Other",
        "organization_name": "Lineage Other Org",
    })
    assert other_org.status_code == 201, other_org.text
    headers = {"Authorization": f"Bearer {other_org.json()['access_token']}"}
    assert client.get(
        f"/parcel-lineage-events/{second.id}", headers=headers
    ).status_code == 404
    assert client.get(f"/parcels/{parent.id}", headers=headers).status_code == 404


def test_unresolved_lineage_participant_links_when_parcel_arrives(db):
    source, run, now = _setup(db)
    current_raw = _raw(db, source, run, "CURRENT", "current-hash", now)
    current = _parcel(db, source, current_raw, "CURRENT", now)
    event = upsert_lineage_from_snapshot(
        db,
        source=source,
        raw_record=current_raw,
        current_parcel=current,
        values={
            "lineage_event_id": "CORRECTION-9",
            "lineage_event_type": "correction",
            "lineage_predecessor_ids": "FUTURE-PARCEL",
        },
        verified_at=now,
    )
    assert event is not None
    unresolved = next(
        participant
        for participant in event.participants
        if participant.external_parcel_id == "FUTURE-PARCEL"
    )
    assert unresolved.parcel_id is None

    future_raw = _raw(db, source, run, "FUTURE-PARCEL", "future-hash", now)
    future = _parcel(db, source, future_raw, "FUTURE-PARCEL", now)
    assert reconcile_lineage_participants(
        db, source=source, parcel=future
    ) == 1
    db.commit()
    db.refresh(unresolved)
    assert unresolved.parcel_id == future.id
    relationship = db.query(GraphRelationship).filter(
        GraphRelationship.attributes["lineage_event_id"].as_string() == event.id
    ).one()
    assert relationship.attributes["lineage_event_type"] == "correction"
