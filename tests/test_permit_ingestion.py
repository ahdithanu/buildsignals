from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest

import app.services.ingestion.service as ingestion_service
from app.models.graph import GraphEntity, GraphRelationship, GraphRelationshipEvidence
from app.models.ingestion import (
    IngestionRun,
    PermitEvent,
    PermitRecord,
    RawSourceRecord,
    RawSourceRecordObservation,
)
from app.services.brand_intelligence import load_brand_catalog, sync_brand_catalog
from app.services.ingestion.connectors import FetchEnvelope
from app.services.ingestion.service import _claim_source_run, execute_source_run


def _source_payload(csv_path: str) -> dict:
    fields = {
        "id": "source_record_id",
        "application_no": "application_number",
        "permit_no": "permit_number",
        "approval_stage": "approval_stage",
        "type": "permit_type",
        "status": "status",
        "description": "description",
        "address": "address",
        "city": "city",
        "state": "state",
        "zip": "postal_code",
        "parcel": "parcel_id",
        "owner": "owner_name",
        "developer": "developer_name",
        "contractor": "contractor_name",
        "architect": "architect_name",
        "engineer": "engineer_name",
        "valuation": "valuation",
        "filed": "filed_at",
    }
    return {
        "key": "austin_open_data",
        "name": "Austin building permits",
        "adapter": "csv",
        "record_type": "permit",
        "jurisdiction": "Austin",
        "base_url": csv_path,
        "settings": {"connector": {"page_size": 100}},
        "field_mappings": [
            {"source_field": source, "canonical_field": canonical}
            for source, canonical in fields.items()
        ],
    }


def _write_csv(
    path,
    *,
    status: str = "Issued",
    approval_stage: str = "approved",
    description: str = "12 story office",
) -> None:
    path.write_text(
        "id,application_no,permit_no,approval_stage,type,status,description,address,city,state,zip,parcel,owner,developer,contractor,architect,engineer,valuation,filed\n"
        f'1001,APP-1001,BP-1001,{approval_stage},Commercial,{status},"{description}",100 Main St,Austin,TX,78701,PARCEL-7,Main Street Owner LLC,Acme Development LLC,BuildCo Inc,Studio A,Engineer Partners,12500000,2026-07-01\n'
    )


def _raise_graph_failure(*_args, **_kwargs):
    raise RuntimeError("graph failed")


def test_register_source_and_reject_embedded_secret(client, tmp_path):
    payload = _source_payload(str(tmp_path / "permits.csv"))
    response = client.post("/ingestion/sources", json=payload)
    assert response.status_code == 201, response.text
    assert response.json()["adapter"] == "csv"
    assert len(response.json()["field_mappings"]) == len(payload["field_mappings"])

    payload["key"] = "unsafe"
    payload["settings"] = {"api_key": "plaintext"}
    response = client.post("/ingestion/sources", json=payload)
    assert response.status_code == 422


def test_csv_run_is_idempotent_and_versions_corrections(client, db, tmp_path):
    csv_path = tmp_path / "permits.csv"
    _write_csv(csv_path)
    source = client.post("/ingestion/sources", json=_source_payload(str(csv_path))).json()

    first = client.post(f"/ingestion/sources/{source['id']}/runs", json={"max_pages": 1})
    assert first.status_code == 201, first.text
    assert first.json()["records_inserted"] == 1
    assert first.json()["records_failed"] == 0
    first_raw = db.query(RawSourceRecord).one()
    first_received_at = first_raw.received_at
    first_run_id = first_raw.run_id
    first_observed_at = db.query(RawSourceRecordObservation).one().last_observed_at

    second = client.post(f"/ingestion/sources/{source['id']}/runs", json={"max_pages": 1})
    assert second.status_code == 201
    assert second.json()["records_inserted"] == 0
    assert second.json()["records_updated"] == 0
    assert db.query(RawSourceRecord).count() == 1
    observation = db.query(RawSourceRecordObservation).one()
    assert observation.last_observed_at > first_observed_at
    advanced_observed_at = observation.last_observed_at
    assert db.query(RawSourceRecord).one().received_at == first_received_at
    assert db.query(RawSourceRecord).one().run_id == first_run_id
    assert db.query(PermitEvent).count() == 1
    ingestion_service._touch_raw_observation(
        db, first_raw, first_observed_at - timedelta(days=1)
    )
    assert db.query(RawSourceRecordObservation).one().last_observed_at == advanced_observed_at

    _write_csv(csv_path, status="Finaled")
    third = client.post(f"/ingestion/sources/{source['id']}/runs", json={"max_pages": 1})
    assert third.status_code == 201, third.text
    assert third.json()["records_updated"] == 1
    assert db.query(RawSourceRecord).count() == 2
    assert db.query(RawSourceRecordObservation).count() == 2
    assert db.query(PermitEvent).count() == 2
    assert db.query(PermitRecord).one().status == "Finaled"

    _write_csv(csv_path, status="Issued")
    reverted = client.post(f"/ingestion/sources/{source['id']}/runs", json={"max_pages": 1})
    assert reverted.status_code == 201, reverted.text
    assert reverted.json()["records_updated"] == 1
    assert db.query(RawSourceRecord).count() == 2
    assert db.query(RawSourceRecordObservation).count() == 2
    assert db.query(PermitEvent).count() == 3
    assert db.query(PermitRecord).one().status == "Issued"


def test_raw_source_record_rejects_orm_mutation(client, db, tmp_path):
    csv_path = tmp_path / "permits.csv"
    _write_csv(csv_path)
    source = client.post(
        "/ingestion/sources", json=_source_payload(str(csv_path))
    ).json()
    response = client.post(
        f"/ingestion/sources/{source['id']}/runs", json={"max_pages": 1}
    )
    assert response.status_code == 201, response.text

    raw = db.query(RawSourceRecord).one()
    raw.payload = {"tampered": True}
    with pytest.raises(ValueError, match="RawSourceRecord rows are immutable"):
        db.commit()
    db.rollback()

    raw = db.query(RawSourceRecord).one()
    unreferenced = RawSourceRecord(
        organization_id=raw.organization_id,
        source_id=raw.source_id,
        run_id=raw.run_id,
        external_record_id="unreferenced-record",
        record_type="permit",
        content_hash="unreferenced-hash",
        payload={"id": "unreferenced-record"},
        received_at=datetime.now(timezone.utc),
    )
    db.add(unreferenced)
    db.commit()

    db.delete(unreferenced)
    with pytest.raises(ValueError, match="RawSourceRecord rows are immutable"):
        db.commit()
    db.rollback()
    assert db.query(RawSourceRecord).count() == 2


def test_source_record_filters_skip_out_of_scope_rows(client, db, tmp_path):
    csv_path = tmp_path / "permits.csv"
    csv_path.write_text(
        "id,application_no,permit_no,approval_stage,type,status,description,address,city,state,zip,parcel,owner,developer,contractor,architect,engineer,valuation,filed\n"
        "1001,APP-1001,BP-1001,approved,Commercial,Issued,Storefront,100 Main St,Austin,TX,78701,PARCEL-7,Owner LLC,Dev LLC,BuildCo,Studio A,Engineer Partners,125000,2026-07-01\n"
        "1002,APP-1002,BP-1002,approved,Residential,Issued,Kitchen remodel,200 Main St,Austin,TX,78701,PARCEL-8,Owner LLC,Dev LLC,BuildCo,Studio A,Engineer Partners,25000,2026-07-01\n"
    )
    payload = _source_payload(str(csv_path))
    payload["settings"]["record_filters"] = [
        {"field": "type", "values": ["Commercial"]}
    ]
    source = client.post("/ingestion/sources", json=payload).json()

    response = client.post(f"/ingestion/sources/{source['id']}/runs", json={"max_pages": 1})

    assert response.status_code == 201, response.text
    assert response.json()["records_seen"] == 2
    assert response.json()["records_inserted"] == 1
    assert response.json()["records_failed"] == 0
    assert db.query(PermitRecord).one().external_record_id == "1001"
    assert db.query(RawSourceRecord).count() == 1


def test_interrupted_run_is_finalized_as_failed(client, db, tmp_path, monkeypatch):
    csv_path = tmp_path / "permits.csv"
    _write_csv(csv_path)
    source_payload = client.post(
        "/ingestion/sources", json=_source_payload(str(csv_path))
    ).json()
    source = db.get(ingestion_service.IngestionSource, source_payload["id"])

    def interrupt_persist(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(ingestion_service, "_persist_permit", interrupt_persist)

    with pytest.raises(KeyboardInterrupt):
        execute_source_run(db, source, max_pages=1)

    run = db.query(IngestionRun).one()
    assert run.status == "failed"
    assert run.completed_at is not None
    assert run.records_seen == 1
    assert run.error_message == "Interrupted by operator"


def test_ingested_permit_projects_evidence_backed_opportunity_context(client, db, tmp_path):
    deal = client.post("/deals", json={
        "name": "Riverside Tower",
        "address": "100 Main Street",
        "city": "Austin",
        "state": "TX",
        "zip_code": "78701",
        "property_type": "office",
    })
    assert deal.status_code == 201, deal.text

    csv_path = tmp_path / "permits.csv"
    _write_csv(csv_path)
    source = client.post("/ingestion/sources", json=_source_payload(str(csv_path))).json()
    run = client.post(f"/ingestion/sources/{source['id']}/runs", json={"max_pages": 1})
    assert run.status_code == 201, run.text
    assert run.json()["status"] == "completed"

    context = client.get(f"/deals/{deal.json()['id']}/graph-context")
    assert context.status_code == 200, context.text
    body = context.json()
    assert {item["entity"]["display_name"] for item in body["permits"]} == {"BP-1001"}
    assert {item["entity"]["display_name"] for item in body["owners"]} == {"Main Street Owner LLC"}
    assert {item["entity"]["display_name"] for item in body["developers"]} == {"Acme Development LLC"}
    assert {item["entity"]["display_name"] for item in body["contractors"]} == {"BuildCo Inc"}
    assert {item["entity"]["display_name"] for item in body["architects"]} == {"Studio A"}
    assert {item["entity"]["display_name"] for item in body["engineers"]} == {"Engineer Partners"}
    assert {item["entity"]["display_name"] for item in body["parcels"]} == {"PARCEL-7"}
    assert {item["entity"]["display_name"] for item in body["cities"]} == {"Austin"}
    assert db.query(GraphRelationshipEvidence).count() >= 8
    assert db.query(GraphEntity).filter(GraphEntity.entity_type == "permit").count() == 1


def test_bad_record_rolls_back_and_reports_committed_counts(client, db, tmp_path):
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("id,address\n,100 Main St\n")
    payload = _source_payload(str(csv_path))
    payload["field_mappings"] = [
        {"source_field": "id", "canonical_field": "source_record_id", "is_required": True},
        {"source_field": "address", "canonical_field": "address"},
    ]
    source = client.post("/ingestion/sources", json=payload).json()

    response = client.post(f"/ingestion/sources/{source['id']}/runs", json={"max_pages": 1})

    assert response.status_code == 201, response.text
    assert response.json()["status"] == "partial_with_errors"
    assert response.json()["records_seen"] == 1
    assert response.json()["records_inserted"] == 0
    assert response.json()["records_failed"] == 1
    assert "Missing required source fields" in response.json()["error_message"]
    assert db.query(PermitRecord).count() == 0
    assert db.query(RawSourceRecord).count() == 0


def test_downstream_failure_rolls_back_new_raw_observation(
    client, db, tmp_path, monkeypatch
):
    csv_path = tmp_path / "downstream-new.csv"
    _write_csv(csv_path)
    source = client.post("/ingestion/sources", json=_source_payload(str(csv_path))).json()
    monkeypatch.setattr(
        ingestion_service,
        "_project_permit_to_graph",
        _raise_graph_failure,
    )

    response = client.post(f"/ingestion/sources/{source['id']}/runs", json={"max_pages": 1})

    assert response.status_code == 201, response.text
    assert response.json()["records_failed"] == 1
    assert db.query(RawSourceRecord).count() == 0
    assert db.query(RawSourceRecordObservation).count() == 0


def test_downstream_failure_does_not_advance_existing_observation(
    client, db, tmp_path, monkeypatch
):
    csv_path = tmp_path / "downstream-existing.csv"
    _write_csv(csv_path)
    payload = _source_payload(str(csv_path))
    source = client.post("/ingestion/sources", json=payload).json()
    first = client.post(f"/ingestion/sources/{source['id']}/runs", json={"max_pages": 1})
    assert first.status_code == 201, first.text
    observed_at = db.query(RawSourceRecordObservation).one().last_observed_at
    patched = client.patch(
        f"/ingestion/sources/{source['id']}",
        json={
            "field_mappings": [
                mapping
                for mapping in payload["field_mappings"]
                if mapping["canonical_field"] != "owner_name"
            ]
        },
    )
    assert patched.status_code == 200, patched.text
    monkeypatch.setattr(
        ingestion_service,
        "_project_permit_to_graph",
        _raise_graph_failure,
    )

    response = client.post(f"/ingestion/sources/{source['id']}/runs", json={"max_pages": 1})

    assert response.status_code == 201, response.text
    assert response.json()["records_failed"] == 1
    db.expire_all()
    assert db.query(RawSourceRecordObservation).one().last_observed_at == observed_at


def test_mapping_change_reprocesses_raw_and_expires_removed_relationship(client, db, tmp_path):
    csv_path = tmp_path / "permits.csv"
    _write_csv(csv_path)
    payload = _source_payload(str(csv_path))
    source = client.post("/ingestion/sources", json=payload).json()
    first = client.post(f"/ingestion/sources/{source['id']}/runs", json={"max_pages": 1})
    assert first.status_code == 201, first.text
    assert db.query(GraphRelationship).filter(
        GraphRelationship.is_current.is_(True),
        GraphRelationship.attributes["role"].as_string() == "owner",
    ).count() == 1

    mappings_without_owner = [
        mapping for mapping in payload["field_mappings"]
        if mapping["canonical_field"] != "owner_name"
    ]
    patched = client.patch(
        f"/ingestion/sources/{source['id']}",
        json={"field_mappings": mappings_without_owner},
    )
    assert patched.status_code == 200, patched.text
    second = client.post(f"/ingestion/sources/{source['id']}/runs", json={"max_pages": 1})

    assert second.status_code == 201, second.text
    assert second.json()["records_updated"] == 1, second.json()
    assert db.query(RawSourceRecord).count() == 1
    assert db.query(PermitEvent).count() == 2
    assert db.query(PermitRecord).one().owner_name is None
    owner_relationships = db.query(GraphRelationship).filter(
        GraphRelationship.attributes["role"].as_string() == "owner"
    ).all()
    assert len(owner_relationships) == 1
    assert owner_relationships[0].is_current is False
    assert owner_relationships[0].valid_to is not None
    assert len(owner_relationships[0].evidence) == 1


def test_pre_approval_filing_advances_to_approved_without_duplicate_graph_node(
    client, db, tmp_path
):
    csv_path = tmp_path / "lifecycle.csv"
    _write_csv(csv_path, status="Under Review", approval_stage="pre_approval")
    source = client.post("/ingestion/sources", json=_source_payload(str(csv_path))).json()

    first = client.post(f"/ingestion/sources/{source['id']}/runs", json={"max_pages": 1})
    assert first.status_code == 201, first.text
    permit = db.query(PermitRecord).one()
    assert permit.status == "Under Review"
    assert permit.approval_stage == "pre_approval"
    assert [event.approval_stage for event in permit.events] == ["pre_approval"]

    pre_approval = client.get("/ingestion/permits?approval_stage=pre_approval")
    assert pre_approval.status_code == 200
    assert [row["application_number"] for row in pre_approval.json()] == ["APP-1001"]

    _write_csv(csv_path, status="Issued", approval_stage="approved")
    second = client.post(f"/ingestion/sources/{source['id']}/runs", json={"max_pages": 1})
    assert second.status_code == 201, second.text
    db.expire_all()
    permit = db.query(PermitRecord).one()
    assert permit.approval_stage == "approved"
    assert [event.approval_stage for event in permit.events] == ["pre_approval", "approved"]
    assert db.query(GraphEntity).filter(GraphEntity.entity_type == "permit").count() == 1
    permit_entity = db.query(GraphEntity).filter(GraphEntity.entity_type == "permit").one()
    assert permit_entity.attributes["approval_stage"] == "approved"

    approved = client.get("/ingestion/permits?approval_stage=approved")
    assert approved.status_code == 200
    assert [row["permit_number"] for row in approved.json()] == ["BP-1001"]


def test_permit_detail_exposes_lifecycle_brand_matches_and_graph_context(client, db, tmp_path):
    sync_brand_catalog(db, load_brand_catalog())
    db.commit()
    csv_path = tmp_path / "starbucks.csv"
    _write_csv(
        csv_path,
        status="Under Review",
        approval_stage="pre_approval",
        description="Interior retail build-out for Starbucks Coffee",
    )
    source = client.post("/ingestion/sources", json=_source_payload(str(csv_path))).json()

    run = client.post(f"/ingestion/sources/{source['id']}/runs", json={"max_pages": 1})
    assert run.status_code == 201, run.text

    permit = db.query(PermitRecord).one()
    detail = client.get(f"/ingestion/permits/{permit.id}")
    assert detail.status_code == 200, detail.text
    body = detail.json()

    assert body["source_name"] == "Austin building permits"
    assert body["permit"]["approval_stage"] == "pre_approval"
    assert [event["event_type"] for event in body["events"]] == ["created"]
    assert body["brand_matches"]
    assert body["brand_matches"][0]["brand"]["name"] == "Starbucks"
    assert body["graph_entity"]["display_name"] == "BP-1001"
    related_names = {item["entity"]["display_name"] for item in body["graph_related"]}
    assert {"Main Street Owner LLC", "Acme Development LLC", "BuildCo Inc", "Studio A", "Engineer Partners", "Austin"}.issubset(related_names)


def test_completed_keyset_run_preserves_final_resume_checkpoint(
    client, db, tmp_path, monkeypatch
):
    calls = []

    class KeysetConnector:
        def fetch_page(self, checkpoint=None):
            calls.append(checkpoint)
            if checkpoint:
                return FetchEnvelope(
                    source="test", records=(), checkpoint=checkpoint, has_more=False
                )
            final = {"keyset": {"loaded_at": "2026-07-16", "record_id": "1"}}
            return FetchEnvelope(
                source="test",
                records=({
                    "id": "1", "approval_stage": "pre_approval",
                    "loaded_at": "2026-07-16T04:38:02.190",
                },),
                checkpoint=final,
                has_more=False,
            )

    monkeypatch.setattr(
        "app.services.ingestion.service.build_connector",
        lambda adapter, config: KeysetConnector(),
    )
    payload = _source_payload(str(tmp_path / "unused.csv"))
    payload["settings"]["freshness_field"] = "loaded_at"
    source = client.post("/ingestion/sources", json=payload).json()

    first = client.post(f"/ingestion/sources/{source['id']}/runs", json={"max_pages": 1})
    assert first.status_code == 201, first.text
    checkpoint = first.json()["checkpoint"]
    assert first.json()["status"] == "completed"
    assert checkpoint == {"keyset": {"loaded_at": "2026-07-16", "record_id": "1"}}

    second = client.post(
        f"/ingestion/sources/{source['id']}/runs",
        json={"max_pages": 1, "checkpoint": checkpoint},
    )
    assert second.status_code == 201, second.text
    assert second.json()["records_seen"] == 0
    assert calls == [None, checkpoint]
    assert db.query(RawSourceRecord).count() == 1
    assert db.query(RawSourceRecord).one().source_updated_at is not None


def test_runtime_rejects_repeated_checkpoint(client, tmp_path, monkeypatch):
    class StalledConnector:
        def fetch_page(self, checkpoint=None):
            return FetchEnvelope(
                source="test",
                records=({"id": "1"},),
                checkpoint=checkpoint,
                has_more=True,
            )

    monkeypatch.setattr(
        "app.services.ingestion.service.build_connector",
        lambda adapter, config: StalledConnector(),
    )
    source = client.post(
        "/ingestion/sources", json=_source_payload(str(tmp_path / "unused.csv"))
    ).json()

    response = client.post(
        f"/ingestion/sources/{source['id']}/runs",
        json={"max_pages": 1, "checkpoint": {"offset": 10}},
    )

    assert response.status_code == 201, response.text
    assert response.json()["status"] == "failed"
    assert "repeated checkpoint" in response.json()["error_message"]


def test_fresh_run_lease_returns_conflict(client, db, tmp_path):
    source = client.post(
        "/ingestion/sources", json=_source_payload(str(tmp_path / "unused.csv"))
    ).json()
    db.add(IngestionRun(
        organization_id="default-org",
        source_id=source["id"],
        status="running",
        trigger="scheduled",
        heartbeat_at=datetime.now(timezone.utc),
    ))
    db.commit()

    response = client.post(
        f"/ingestion/sources/{source['id']}/runs", json={"max_pages": 1}
    )

    assert response.status_code == 409, response.text
    assert "running job" in response.json()["detail"]


def test_run_rejects_invalid_stale_lease_setting(client, tmp_path):
    payload = _source_payload(str(tmp_path / "unused.csv"))
    payload["settings"]["stale_run_after_seconds"] = 0
    source = client.post("/ingestion/sources", json=payload).json()

    response = client.post(
        f"/ingestion/sources/{source['id']}/runs", json={"max_pages": 1}
    )

    assert response.status_code == 422, response.text
    assert "stale_run_after_seconds must be positive" in response.json()["detail"]


def test_stale_run_lease_is_reclaimed(db, client, tmp_path):
    source = client.post(
        "/ingestion/sources", json=_source_payload(str(tmp_path / "unused.csv"))
    ).json()
    stale = IngestionRun(
        organization_id="default-org",
        source_id=source["id"],
        status="running",
        trigger="scheduled",
        started_at=datetime.now(timezone.utc) - timedelta(minutes=11),
        heartbeat_at=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    db.add(stale)
    db.commit()

    replacement = _claim_source_run(
        db,
        source["id"],
        checkpoint=None,
        trigger="scheduled",
        parameters={"max_pages": 1},
    )
    db.expire_all()

    assert replacement.status == "running"
    assert db.query(IngestionRun).filter(IngestionRun.id == stale.id).one().status == "failed"
    assert "reclaimed" in db.query(IngestionRun).filter(
        IngestionRun.id == stale.id
    ).one().error_message


def test_slow_fetch_renews_heartbeat(client, db, tmp_path, monkeypatch):
    class SlowConnector:
        def fetch_page(self, checkpoint=None):
            time.sleep(0.04)
            return FetchEnvelope(source="test", records=(), checkpoint=None, has_more=False)

    monkeypatch.setattr(
        "app.services.ingestion.service.HEARTBEAT_INTERVAL_SECONDS", 0.01
    )
    monkeypatch.setattr(
        "app.services.ingestion.service.build_connector",
        lambda adapter, config: SlowConnector(),
    )
    source = client.post(
        "/ingestion/sources", json=_source_payload(str(tmp_path / "unused.csv"))
    ).json()

    response = client.post(
        f"/ingestion/sources/{source['id']}/runs", json={"max_pages": 1}
    )
    assert response.status_code == 201, response.text
    run = db.query(IngestionRun).filter(IngestionRun.id == response.json()["id"]).one()

    assert run.status == "completed"
    assert run.heartbeat_at >= run.started_at


def test_committed_page_survives_next_fetch_failure(client, db, tmp_path, monkeypatch):
    class FailingSecondPageConnector:
        calls = 0

        def fetch_page(self, checkpoint=None):
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("publisher disconnected")
            return FetchEnvelope(
                source="test",
                records=({"id": "durable-1", "approval_stage": "pre_approval"},),
                checkpoint={"offset": 1},
                has_more=True,
            )

    monkeypatch.setattr(
        "app.services.ingestion.service.build_connector",
        lambda adapter, config: FailingSecondPageConnector(),
    )
    source = client.post(
        "/ingestion/sources", json=_source_payload(str(tmp_path / "unused.csv"))
    ).json()

    response = client.post(
        f"/ingestion/sources/{source['id']}/runs", json={"max_pages": 2}
    )

    assert response.status_code == 201, response.text
    assert response.json()["status"] == "failed"
    assert response.json()["checkpoint"] == {"offset": 1}
    assert response.json()["records_seen"] == 1
    assert db.query(RawSourceRecord).filter(
        RawSourceRecord.external_record_id == "durable-1"
    ).count() == 1


def test_full_snapshot_resume_retires_missing_records_only_after_completion(
    client, db, tmp_path
):
    csv_path = tmp_path / "snapshot.csv"
    csv_path.write_text(
        "id,address,approval_stage\n"
        "1,100 Main St,pre_approval\n"
        "2,200 Main St,pre_approval\n"
    )
    payload = _source_payload(str(csv_path))
    payload["key"] = "snapshot_reconciliation"
    payload["settings"] = {
        "connector": {"page_size": 1},
        "reconciliation_mode": "daily_full_snapshot",
        "max_snapshot_retirement_fraction": 0.6,
    }
    source = client.post("/ingestion/sources", json=payload).json()

    partial = client.post(
        f"/ingestion/sources/{source['id']}/runs", json={"max_pages": 1}
    )
    assert partial.status_code == 201, partial.text
    assert partial.json()["status"] == "partial"
    checkpoint = partial.json()["checkpoint"]
    snapshot_id = checkpoint["_build_signals_snapshot"]["snapshot_id"]
    assert db.query(PermitRecord).one().is_active is True

    completed = client.post(
        f"/ingestion/sources/{source['id']}/runs",
        json={"max_pages": 1, "checkpoint": checkpoint},
    )
    assert completed.status_code == 201, completed.text
    assert completed.json()["status"] == "completed"
    assert completed.json()["checkpoint"] is None
    permits = db.query(PermitRecord).order_by(PermitRecord.external_record_id).all()
    assert [permit.last_seen_snapshot_id for permit in permits] == [snapshot_id, snapshot_id]
    assert all(permit.is_active for permit in permits)

    csv_path.write_text("id,address,approval_stage\n1,100 Main St,pre_approval\n")
    reconciled = client.post(
        f"/ingestion/sources/{source['id']}/runs", json={"max_pages": 1}
    )
    assert reconciled.status_code == 201, reconciled.text
    db.expire_all()
    missing = db.query(PermitRecord).filter(PermitRecord.external_record_id == "2").one()
    assert missing.is_active is False
    assert missing.retired_at is not None
    assert missing.events[-1].event_type == "retired_from_source_snapshot"
    assert client.get("/ingestion/permits").json()[0]["external_record_id"] == "1"
    assert db.query(GraphRelationship).filter(
        GraphRelationship.attributes["permit_record_id"].as_string() == missing.id,
        GraphRelationship.is_current.is_(True),
    ).count() == 0


def test_partial_snapshot_never_retires_and_reappearance_reactivates(
    client, db, tmp_path
):
    csv_path = tmp_path / "reactivation.csv"
    csv_path.write_text(
        "id,address,approval_stage\n"
        "1,100 Main St,pre_approval\n"
        "2,200 Main St,pre_approval\n"
    )
    payload = _source_payload(str(csv_path))
    payload["key"] = "snapshot_reactivation"
    payload["settings"] = {
        "connector": {"page_size": 100},
        "reconciliation_mode": "daily_full_snapshot",
        "max_snapshot_retirement_fraction": 0.6,
    }
    source = client.post("/ingestion/sources", json=payload).json()
    client.post(f"/ingestion/sources/{source['id']}/runs", json={"max_pages": 1})

    csv_path.write_text("id,address,approval_stage\n1,100 Main St,pre_approval\n")
    client.post(f"/ingestion/sources/{source['id']}/runs", json={"max_pages": 1})
    retired = db.query(PermitRecord).filter(PermitRecord.external_record_id == "2").one()
    assert retired.is_active is False

    csv_path.write_text(
        "id,address,approval_stage\n"
        "1,100 Main St,pre_approval\n"
        "2,200 Main St,pre_approval\n"
    )
    client.post(f"/ingestion/sources/{source['id']}/runs", json={"max_pages": 1})
    db.expire_all()
    reactivated = db.query(PermitRecord).filter(PermitRecord.external_record_id == "2").one()
    assert reactivated.is_active is True
    assert reactivated.retired_at is None
    assert reactivated.events[-1].event_type == "reactivated"
    assert db.query(GraphRelationship).filter(
        GraphRelationship.attributes["permit_record_id"].as_string() == reactivated.id,
        GraphRelationship.is_current.is_(True),
    ).count() > 0


def test_snapshot_guard_blocks_unexpected_empty_source(client, db, tmp_path):
    csv_path = tmp_path / "guarded.csv"
    csv_path.write_text("id,address\n1,100 Main St\n2,200 Main St\n")
    payload = _source_payload(str(csv_path))
    payload["key"] = "guarded_snapshot"
    payload["settings"]["reconciliation_mode"] = "daily_full_snapshot"
    source = client.post("/ingestion/sources", json=payload).json()
    client.post(f"/ingestion/sources/{source['id']}/runs", json={"max_pages": 1})

    csv_path.write_text("id,address\n")
    guarded = client.post(
        f"/ingestion/sources/{source['id']}/runs", json={"max_pages": 1}
    )
    assert guarded.status_code == 201, guarded.text
    assert guarded.json()["status"] == "failed"
    assert "snapshot was empty" in guarded.json()["error_message"]
    assert db.query(PermitRecord).filter(PermitRecord.is_active.is_(True)).count() == 2
