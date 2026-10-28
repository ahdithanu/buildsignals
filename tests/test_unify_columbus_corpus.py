import json
import sqlite3
from datetime import date

import pytest

from app.services.ingestion.connectors.base import FetchEnvelope
from scripts.columbus_corpus_capture import capture_batch
from scripts.columbus_corpus_preflight import build_report
from scripts.unify_columbus_corpus import build_snapshot

KEY = "columbus_oh_site_engineering_applications"


@pytest.fixture
def shards(tmp_path, monkeypatch):
    class Client:
        def get_json(self, *args, **kwargs):
            return {"count": 1}
    preflight = build_report(KEY, date(2024, 1, 1), date(2024, 3, 1), client=Client())
    monkeypatch.setattr("app.services.ingestion.historical_intake.provider_count", lambda *_: 1)
    counter = iter([1, 2])
    def fetch(*_args, **_kwargs):
        month = next(counter)
        return FetchEnvelope(source="arcgis_featureserver", records=({
            "OBJECTID": month, "B1_ALT_ID": f"TEST-{month}", "SITE_ADDRESS": "PRIVATE TEST ADDRESS",
            "B1_FILE_DD": 1704067200000 if month == 1 else 1706745600000,
            "B1_PER_TYPE": "Site Compliance Plan", "B1_APPL_STATUS": "Submitted",
        },), has_more=False, checkpoint=None)
    monkeypatch.setattr("app.services.ingestion.connectors.arcgis.ArcGISFeatureServerConnector.fetch", fetch)
    directory = tmp_path / "shards"
    capture_batch(preflight, directory, capture=True)
    return preflight, directory


def test_preserves_evidence_timestamps_payload_events_and_digest(shards, tmp_path):
    preflight, directory = shards
    output = tmp_path / "unified.db"
    manifest = build_snapshot(preflight, directory, output)
    again = build_snapshot(preflight, directory, tmp_path / "again.db")
    assert manifest["content_sha256"] == again["content_sha256"]
    assert manifest["counts"]["permit_records"] == 2
    assert manifest["known_then_verified"] is False
    assert "PRIVATE TEST ADDRESS" not in json.dumps(manifest)
    with sqlite3.connect(output) as unified:
        assert unified.execute("SELECT count(DISTINCT organization_id) FROM temporal_observations").fetchone()[0] == 1
        for shard in directory.glob("*.db"):
            with sqlite3.connect(shard) as original:
                for table, columns in [
                    ("raw_source_records", "id,payload,content_hash,received_at,source_updated_at"),
                    ("temporal_observations", "id,value,recorded_at,first_observed_at,effective_at,content_hash"),
                    ("temporal_events", "id,event_type,occurred_at,recorded_at"),
                    ("permit_events", "id,event_type,occurred_at,attributes"),
                ]:
                    for row in original.execute(f"SELECT {columns} FROM {table}"):
                        assert unified.execute(f"SELECT {columns} FROM {table} WHERE id=?", (row[0],)).fetchone() == row
        assert unified.execute("PRAGMA foreign_key_check").fetchall() == []
    with pytest.raises(FileExistsError):
        build_snapshot(preflight, directory, output)


def test_missing_month_refused_without_final_artifact(shards, tmp_path):
    preflight, directory = shards
    (directory / "2024-02.qualification.json").unlink()
    with pytest.raises(ValueError):
        build_snapshot(preflight, directory, tmp_path / "bad.db")
    assert not (tmp_path / "bad.db").exists()


def test_forged_receipt_refused(shards, tmp_path):
    preflight, directory = shards
    path = directory / "2024-02.qualification.json"
    receipt = json.loads(path.read_text())
    receipt["scope_sha256"] = "forged"
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        build_snapshot(preflight, directory, tmp_path / "bad.db")


def test_duplicate_completed_month_refused(shards, tmp_path):
    import shutil

    preflight, directory = shards
    duplicate = directory / "duplicate"
    duplicate.mkdir()
    original = directory / "2024-01.db"
    copied = duplicate / "2024-01.db"
    shutil.copyfile(original, copied)
    receipt = json.loads(original.with_suffix(".qualification.json").read_text())
    receipt["database"] = str(copied.resolve())
    copied.with_suffix(".qualification.json").write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="Duplicate"):
        build_snapshot(preflight, directory, tmp_path / "bad.db")
    assert not (tmp_path / "bad.db").exists()
