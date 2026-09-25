from __future__ import annotations

import csv
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models.graph import (
    GraphEntity,
    GraphEntityLink,
    GraphEntityType,
    GraphRelationshipEvidence,
)
from app.models.ingestion import IngestionSource, PermitRecord, RawSourceRecord
from app.models.planning import PlanningRecord
from app.services.brand_intelligence import load_brand_catalog, sync_brand_catalog
from app.services.ingestion.normalization import normalize_permit, normalize_planning_record
from app.services.ingestion.service import execute_source_run


def _source(client, tmp_path, record_type, rows):
    path = tmp_path / f"{record_type}.csv"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    fields = {"id": "source_record_id", "address": "address", "parcel": "parcel_id"}
    fields["title"] = "title" if record_type == "planning" else "description"
    result = client.post("/ingestion/sources", json={
        "key": f"graph_contract_{record_type}",
        "name": "Graph contract test source",
        "adapter": "csv",
        "record_type": record_type,
        "base_url": str(path),
        "settings": {"connector": {"page_size": 100}},
        "field_mappings": [
            {"source_field": source, "canonical_field": canonical}
            for source, canonical in fields.items()
        ],
    })
    assert result.status_code == 201, result.text
    return result.json()["id"]


@pytest.mark.parametrize("title", [
    "Consider a public hearing for a land-use application",
    ("Consider a public hearing for a land-use application. " * 12).strip(),
    ("Consider a public hearing for a land-use application. " * 60).strip(),
])
def test_planning_graph_keeps_distinct_source_ids_and_full_titles(client, db, tmp_path, title):
    source_id = _source(client, tmp_path, "planning", [
        {"id": "ITEM-1", "title": title, "address": "10 Main Street", "parcel": ""},
        {"id": "ITEM-2", "title": title, "address": "10 Main Street", "parcel": ""},
    ])
    for expected_inserts in (2, 0):
        response = client.post(f"/ingestion/sources/{source_id}/runs", json={"max_pages": 1})
        assert response.status_code == 201, response.text
        assert response.json()["records_failed"] == 0
        assert response.json()["records_inserted"] == expected_inserts

    records = db.query(PlanningRecord).all()
    assert len(records) == 2
    assert all(record.title == title for record in records)
    entities = db.query(GraphEntity).filter_by(entity_type=GraphEntityType.source_record).all()
    assert len(entities) == 2
    assert len({entity.source_id for entity in entities}) == 2
    assert all(len(entity.display_name) <= 255 for entity in entities)
    assert all(entity.attributes["title"] == title for entity in entities)
    links = db.query(GraphEntityLink).filter_by(record_type="planning").all()
    assert len({link.entity_id for link in links}) == 2
    assert all(row.excerpt == title for row in db.query(GraphRelationshipEvidence).all())


@pytest.mark.parametrize("record_type", ["permit", "planning"])
@pytest.mark.parametrize("length", [255, 256])
def test_optional_parcel_reference_bound_preserves_evidence(record_type, length):
    reference = "P" * length
    source = {"id": "ITEM-1", "title": "Development application", "parcel": reference}
    fields = {"id": "source_record_id", "parcel": "parcel_id"}
    normalizer = normalize_permit
    if record_type == "planning":
        fields["title"] = "title"
        normalizer = normalize_planning_record
    result = normalizer(source, fields)
    if length == 255:
        assert result.values["parcel_id"] == reference
        assert "_unresolved_parcel_reference" not in result.unmapped
    else:
        assert result.values["parcel_id"] is None
        assert result.unmapped["_unresolved_parcel_reference"] == {
            "value": reference,
            "reason": "exceeds_single_parcel_id_limit",
            "max_length": 255,
        }


@pytest.mark.parametrize("record_type", ["permit", "planning"])
def test_oversized_parcel_reference_does_not_drop_record_or_invent_parcel(
    client, db, tmp_path, record_type,
):
    reference = " * ".join(f"PARCEL-{number:012}" for number in range(25))
    source_id = _source(client, tmp_path, record_type, [{
        "id": "ASSEMBLAGE-1", "title": "Development application",
        "address": "20 Main Street", "parcel": reference,
    }])
    response = client.post(f"/ingestion/sources/{source_id}/runs", json={"max_pages": 1})
    assert response.status_code == 201, response.text
    assert response.json()["records_inserted"] == 1
    assert response.json()["records_failed"] == 0
    model = PermitRecord if record_type == "permit" else PlanningRecord
    record = db.query(model).one()
    assert record.parcel_id is None
    assert record.attributes["_unresolved_parcel_reference"]["value"] == reference
    assert db.query(RawSourceRecord).one().payload["parcel"] == reference
    assert db.query(GraphEntity).filter_by(entity_type=GraphEntityType.parcel).count() == 0
    assert db.query(GraphRelationshipEvidence).count() > 0


def test_planning_brand_detection_works_without_autoflush(client, db, tmp_path):
    db.autoflush = False
    sync_brand_catalog(db, load_brand_catalog())
    db.commit()
    source_id = _source(client, tmp_path, "planning", [{
        "id": "COMPANY-1", "title": "Wawa site plan public hearing",
        "address": "20 Main Street", "parcel": "",
    }])
    source = db.get(IngestionSource, source_id)
    result = execute_source_run(db, source, max_pages=1)
    assert result.records_inserted == 1
    assert result.records_failed == 0
    record = db.query(PlanningRecord).one()
    assert "tracked_company" in record.signal_categories
    assert record.company_matches[0].brand.name == "Wawa"
    assert record.company_matches[0].review_status == "candidate"


def test_planning_title_downgrade_refuses_to_discard_long_evidence(client, db, tmp_path):
    title = ("Long public planning title. " * 100).strip()
    source_id = _source(client, tmp_path, "planning", [{
        "id": "LONG-1", "title": title, "address": "20 Main Street", "parcel": "",
    }])
    response = client.post(f"/ingestion/sources/{source_id}/runs", json={"max_pages": 1})
    assert response.status_code == 201, response.text
    assert response.json()["records_failed"] == 0
    path = Path(__file__).resolve().parents[1] / "alembic/versions/20260911_0001_planning_title_text.py"
    spec = importlib.util.spec_from_file_location("planning_title_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    migration.op = SimpleNamespace(get_bind=db.connection)
    with pytest.raises(RuntimeError, match="refusing a data-losing downgrade"):
        migration.downgrade()
    assert db.query(PlanningRecord).one().title == title
