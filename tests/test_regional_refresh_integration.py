"""Regional checkpoint aggregation backed by real local CSV ingestion."""
from dataclasses import replace

from app.models.ingestion import (
    IngestionRun,
    IngestionSource,
    PermitRecord,
    RawSourceRecord,
)
from app.services.ingestion.connectors.csv import CSVConnector
from app.services.ingestion.service import execute_source_run
from scripts import recurring_regions as worker
from tests.internal_operations_fixtures import internal_operator as internal_operator


def test_regional_refresh_resumes_real_runs_and_aggregates_counts(
    client, internal_operator, db, tmp_path, monkeypatch,
):
    assert db.get_bind().dialect.name == "sqlite"
    csv_path = tmp_path / "regional.csv"
    csv_path.write_text(
        "id,permit,address,city,state\n"
        "1,BP-1,100 Main St,Austin,TX\n"
        "2,BP-2,200 Main St,Austin,TX\n",
        encoding="utf-8",
    )
    response = client.post("/ingestion/sources", json={
        "key": "regional_checkpoint_integration",
        "name": "Local regional permits",
        "adapter": "csv",
        "record_type": "permit",
        "jurisdiction": "Austin",
        "base_url": str(csv_path),
        "settings": {
            "connector": {"page_size": 1},
            "reconciliation_mode": "incremental",
        },
        "field_mappings": [
            {"source_field": source, "canonical_field": canonical}
            for source, canonical in {
                "id": "source_record_id",
                "permit": "permit_number",
                "address": "address",
                "city": "city",
                "state": "state",
            }.items()
        ],
    })
    assert response.status_code == 201, response.text
    source = db.get(IngestionSource, response.json()["id"])

    real_fetch = CSVConnector.fetch

    def fetch_with_exhaustion_probe(connector, checkpoint=None):
        envelope = real_fetch(connector, checkpoint)
        # Model feeds requiring an empty probe after every full data page.
        if len(envelope.records) == connector.page_size:
            offset = (checkpoint or {}).get("row_offset", 0)
            return replace(
                envelope, has_more=True,
                checkpoint={"row_offset": offset + len(envelope.records)},
            )
        return envelope

    requested_pages = []
    checkpoints = []
    runs = []

    def execute_one_page(session, ingestion_source, *, max_pages, checkpoint, trigger):
        assert 1 <= max_pages <= 100
        requested_pages.append(max_pages)
        checkpoints.append(checkpoint)
        run = execute_source_run(
            session, ingestion_source, max_pages=1,
            checkpoint=checkpoint, trigger=trigger,
        )
        runs.append(run)
        return run

    monkeypatch.setattr(CSVConnector, "fetch", fetch_with_exhaustion_probe)
    monkeypatch.setattr(worker, "execute_source_run", execute_one_page)
    monkeypatch.setattr(worker, "MAX_PAGES_PER_RUN", 201)

    result = worker.execute_regional_refresh(db, source)

    assert requested_pages == [100, 100, 1]
    assert checkpoints == [None, {"row_offset": 1}, {"row_offset": 2}]
    assert [run.status for run in runs] == ["partial", "partial", "completed"]
    assert [run.records_seen for run in runs] == [1, 1, 0]
    assert [run.checkpoint for run in runs] == [
        {"row_offset": 1}, {"row_offset": 2}, None,
    ]
    assert all(run.trigger == "scheduled" for run in runs)
    assert result.run_ids == [run.id for run in runs]
    assert len(set(result.run_ids)) == 3
    assert result.id == runs[-1].id
    assert result.status == "completed"
    assert result.checkpoint is None
    assert result.error_message is None
    assert result.records_seen == result.records_inserted == 2
    assert result.records_updated == result.records_failed == 0
    assert worker.run_reconciled(result, before=2, after=2)
    db.expire_all()
    assert db.query(IngestionRun).filter_by(source_id=source.id).count() == 3
    for model in (RawSourceRecord, PermitRecord):
        records = db.query(model).filter_by(source_id=source.id).all()
        assert len(records) == 2
        assert {record.external_record_id for record in records} == {"1", "2"}
