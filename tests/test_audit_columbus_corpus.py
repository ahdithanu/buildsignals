import json
import sqlite3
from datetime import date

import pytest

from scripts.audit_columbus_corpus import audit_corpus
from scripts.columbus_corpus_capture import capture_batch
from scripts.columbus_corpus_preflight import build_report
from tests.test_columbus_corpus_capture import KEY, intake


def fixture(tmp_path):
    class Client:
        def get_json(self, *args, **kwargs):
            return {"count": 1}
    report = build_report(KEY, date(2024, 1, 1), date(2024, 3, 1), client=Client())
    capture_batch(report, tmp_path, capture=True, intake=intake)
    for index, month in enumerate(["2024-01", "2024-02"]):
        p = tmp_path / f"{month}.db"
        with sqlite3.connect(p) as db:
            db.execute("ALTER TABLE permit_records ADD filed_at TEXT")
            db.execute("UPDATE permit_records SET filed_at=?", (f"{month}-02T00:00:00",))
            db.execute("CREATE TABLE raw_source_records (external_record_id TEXT, received_at TEXT, source_updated_at TEXT)")
            db.execute("INSERT INTO raw_source_records VALUES (?, ?, ?)", (str(index), "2026-10-22T01:00:01", "2024-01-01"))
            db.execute("CREATE TABLE temporal_observations (recorded_at TEXT)")
            db.execute("INSERT INTO temporal_observations VALUES ('2026-10-22T01:00:01')")
        receipt_path = p.with_suffix(".qualification.json")
        receipt = json.loads(receipt_path.read_text())
        receipt.pop("database_sha256")
        receipt.update(checkpoint=None, started_at="2026-10-22T01:00:00+00:00", finished_at="2026-10-22T01:01:00+00:00")
        receipt_path.write_text(json.dumps(receipt))
    return report


def test_aggregate_has_no_raw_identifiers_or_backdated_knowledge(tmp_path):
    report = fixture(tmp_path)
    (tmp_path / "partial.db").write_bytes(b"partial")
    result = audit_corpus(report, tmp_path)
    assert result["total_records"] == 2
    assert result["historical_known_then_observations"] == 0
    assert result["missing_months"] == []
    assert result["ignored_partial_databases"] == ["partial.db"]
    assert result["coverage_verified"] is False
    assert "external_record_id" not in json.dumps(result)


def test_duplicate_completed_month_refused(tmp_path):
    report = fixture(tmp_path)
    p = tmp_path / "2024-01.qualification.json"
    import shutil
    shutil.copyfile(tmp_path / "2024-01.db", tmp_path / "duplicate.db")
    receipt = json.loads(p.read_text())
    receipt["database"] = str((tmp_path / "duplicate.db").resolve())
    (tmp_path / "duplicate.qualification.json").write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="Duplicate"):
        audit_corpus(report, tmp_path)


def test_bad_receipt_refused(tmp_path):
    report = fixture(tmp_path)
    p = tmp_path / "2024-01.qualification.json"
    receipt = json.loads(p.read_text())
    receipt["checkpoint"] = {"offset": 1}
    p.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="receipt"):
        audit_corpus(report, tmp_path)


def test_duplicates_outside_month_and_backdating_are_findings(tmp_path):
    report = fixture(tmp_path)
    with sqlite3.connect(tmp_path / "2024-02.db") as db:
        db.execute("UPDATE raw_source_records SET external_record_id='0', received_at='2024-01-01'")
        db.execute("UPDATE permit_records SET filed_at='2023-01-01'")
        db.execute("UPDATE temporal_observations SET recorded_at='2024-01-01'")
    result = audit_corpus(report, tmp_path)
    assert result["duplicate_stable_ids"] == 1
    assert result["months"][1]["filed_outside_month"] == 1
    assert result["months"][1]["capture_time_violations"] == 2
    assert result["historical_known_then_observations"] == 1
    assert result["audit_passed"] is False


def test_future_source_date_and_missing_month_are_explicit(tmp_path):
    report = fixture(tmp_path)
    (tmp_path / "2024-02.qualification.json").unlink()
    with sqlite3.connect(tmp_path / "2024-01.db") as db:
        db.execute("UPDATE raw_source_records SET source_updated_at='2027-01-01'")
    result = audit_corpus(report, tmp_path)
    assert result["missing_months"] == ["2024-02"]
    assert result["ignored_partial_databases"] == ["2024-02.db"]
    assert result["months"][0]["future_source_updated"] == 1
    assert result["audit_passed"] is False


def test_reconciled_current_count_drift_is_explicit_not_failed(tmp_path):
    report = fixture(tmp_path)
    report["months"][0]["count"] = 2
    result = audit_corpus(report, tmp_path)
    assert result["audit_passed"] is True
    assert result["months"][0]["preflight_delta"] == -1
    assert result["months"][0]["provider_count_changed"] is True
    assert result["months"][0]["raw_count_matches"] is True


def test_failed_and_empty_receipts_are_ignored_beside_successful_attempt(tmp_path):
    report = fixture(tmp_path)
    original = tmp_path / "2024-01.qualification.json"
    receipt = json.loads(original.read_text())
    attempt = tmp_path / "attempts" / "2024-01-retry"
    attempt.mkdir(parents=True)
    database = attempt / "2024-01.db"
    import shutil
    shutil.copyfile(tmp_path / "2024-01.db", database)
    receipt["database"] = str(database.resolve())
    (attempt / "2024-01.qualification.json").write_text(json.dumps(receipt))
    receipt["status"] = "failed"
    original.write_text(json.dumps(receipt))
    (tmp_path / "pending.qualification.json").write_text("")
    result = audit_corpus(report, tmp_path)
    assert result["audit_passed"] is True
    assert result["ignored_incomplete_receipts"] == ["2024-01.qualification.json", "pending.qualification.json"]
    assert "2024-01.db" in result["ignored_partial_databases"]


def test_forged_completed_receipt_not_ignored_beside_valid_attempt(tmp_path):
    report = fixture(tmp_path)
    receipt = json.loads((tmp_path / "2024-01.qualification.json").read_text())
    receipt["count_reconciled"] = False
    (tmp_path / "forged.qualification.json").write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="Unverified receipt"):
        audit_corpus(report, tmp_path)
