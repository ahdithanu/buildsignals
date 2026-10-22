"""Real local intake -> unified archive -> bound offline replay, without HTTP."""
import json
from datetime import date, datetime, timezone

import pytest

from app.services.ingestion.connectors.base import FetchEnvelope
from app.services.ingestion.historical_intake import historical_entry, run_local_intake
from eval.replay.columbus_snapshot import run_snapshot
from scripts.columbus_corpus_preflight import build_report
from scripts.unify_columbus_corpus import build_snapshot

KEY = "columbus_oh_site_engineering_applications"


def snapshot(tmp_path, monkeypatch):
    class Counts:
        def get_json(self, *args, **kwargs):
            return {"count": 2}

    preflight = build_report(KEY, date(2024, 1, 1), date(2024, 4, 1), client=Counts())
    shards = tmp_path / "shards"
    shards.mkdir()
    monkeypatch.setattr("app.services.ingestion.historical_intake.provider_count", lambda *_: 2)
    for month in preflight["months"]:
        start = date.fromisoformat(month["start_inclusive"])
        stamp = int(datetime(start.year, start.month, 2, tzinfo=timezone.utc).timestamp() * 1000)
        records = tuple({
            "OBJECTID": i, "B1_ALT_ID": f"TEST-{start}-{i}", "SITE_ADDRESS": "100 TEST ST",
            "B1_FILE_DD": stamp, "LAST_STATUS_DT": stamp, "B1_APPL_STATUS": "Under Review",
        } for i in (1, 2))
        monkeypatch.setattr(
            "app.services.ingestion.connectors.arcgis.ArcGISFeatureServerConnector.fetch",
            lambda *_, rows=records: FetchEnvelope(source="arcgis", records=rows, has_more=False, checkpoint=None),
        )
        dbpath = shards / f"{start:%Y-%m}.db"
        result = run_local_intake(dbpath, historical_entry(
            KEY, start, date.fromisoformat(month["end_exclusive"])), max_pages=1)
        dbpath.with_suffix(".qualification.json").write_text(json.dumps(result))
    database = tmp_path / "unified.db"
    build_snapshot(preflight, shards, database)
    return database


def test_real_intake_to_snapshot_bound_replay_stays_honest(tmp_path, monkeypatch):
    database = snapshot(tmp_path, monkeypatch)
    first = run_snapshot(database, tmp_path / "run-one")
    second = run_snapshot(database, tmp_path / "run-two")
    assert first["decision"] == "HOLD"
    assert first["score_is_validated"] is False
    assert first["qualification_verdict"] == "insufficient_depth"
    assert first["binding_verified"] is True
    assert first["binding_qualified"] is False
    assert first["run_fingerprint"] == second["run_fingerprint"]
    assert first["snapshot_id"] == second["snapshot_id"]
    assert first["observations"] >= 6
    assert (tmp_path / "run-one" / "corpus-binding.json").is_file()
    assert (tmp_path / "run-one" / "manifest.json").is_file()
    assert (tmp_path / "run-one" / "metrics.json").is_file()
    with pytest.raises(FileExistsError):
        run_snapshot(database, tmp_path / "run-one")


def test_changed_database_cannot_reuse_snapshot_sidecar(tmp_path, monkeypatch):
    database = snapshot(tmp_path, monkeypatch)
    with database.open("ab") as stream:
        stream.write(b"tamper")
    with pytest.raises(ValueError, match="hash|digest|changed"):
        run_snapshot(database, tmp_path / "rejected")
    assert not (tmp_path / "rejected").exists()
