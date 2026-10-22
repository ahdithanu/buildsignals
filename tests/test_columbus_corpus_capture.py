"""Local orchestration safety checks use fake intake, never provider requests."""
import sqlite3
from datetime import date

import pytest

from scripts.columbus_corpus_capture import capture_batch
from scripts.columbus_corpus_preflight import build_report

KEY = "columbus_oh_site_engineering_applications"


def preflight():
    class Counts:
        def get_json(self, *args, **kwargs):
            return {"count": 1}
    return build_report(KEY, date(2024, 1, 1), date(2024, 3, 1), client=Counts())


def intake(path, entry, *, max_pages):
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE permit_records (id INTEGER)")
        db.execute("INSERT INTO permit_records VALUES (1)")
    scope = entry.model_dump(mode="json")
    from scripts.columbus_corpus_preflight import _digest
    return {"source_key": KEY, "database": str(path.resolve()), "scope": scope,
            "scope_sha256": _digest(scope), "count_reconciled": True,
            "status": "completed", "checkpoint": None, "records_seen": 1, "records_inserted": 1,
            "records_failed": 0, "provider_count_before": 1, "provider_count_after": 1}


def test_default_plan_creates_nothing(tmp_path):
    target = tmp_path / "new"
    result = capture_batch(preflight(), target)
    assert result["mode"] == "plan_only"
    assert not target.exists()


@pytest.mark.parametrize("field,value", [("plan_sha256", "tampered"), ("date_field", "ISSUED_DT")])
def test_changed_preflight_refused_before_creating_files(tmp_path, field, value):
    report = preflight()
    report[field] = value
    with pytest.raises(ValueError):
        capture_batch(report, tmp_path / "new", capture=True, intake=intake)
    assert not (tmp_path / "new").exists()


def test_capture_and_verified_resume(tmp_path):
    report = preflight()
    result = capture_batch(report, tmp_path, capture=True, intake=intake)
    assert [m["status"] for m in result["months"]] == ["captured", "captured"]
    resumed = capture_batch(report, tmp_path, capture=True, intake=lambda *_a, **_k: pytest.fail("network"))
    assert [m["status"] for m in resumed["months"]] == ["resumed", "resumed"]


def test_partial_month_requires_separate_attempt(tmp_path):
    partial = tmp_path / "2024-01.db"
    partial.write_bytes(b"partial")
    with pytest.raises(ValueError, match="Partial"):
        capture_batch(preflight(), tmp_path, capture=True, intake=intake)
    result = capture_batch(preflight(), tmp_path, capture=True, retry_partial=True, intake=intake)
    assert result["months"][0]["status"] == "captured"
    assert partial.read_bytes() == b"partial"
    assert list((tmp_path / "attempts").glob("2024-01-*/*.qualification.json"))


def test_count_mismatch_writes_receipt_and_stops(tmp_path):
    def changed(path, entry, **kwargs):
        receipt = intake(path, entry, **kwargs)
        receipt["provider_count_after"] = 2
        return receipt
    with pytest.raises(ValueError, match="reconcile"):
        capture_batch(preflight(), tmp_path, capture=True, intake=changed)
    assert (tmp_path / "2024-01.qualification.json").exists()
    assert not (tmp_path / "2024-02.db").exists()


def test_resume_refuses_modified_database(tmp_path):
    capture_batch(preflight(), tmp_path, capture=True, intake=intake)
    with sqlite3.connect(tmp_path / "2024-01.db") as db:
        db.execute("DELETE FROM permit_records")
    with pytest.raises(ValueError, match="Partial"):
        capture_batch(preflight(), tmp_path, capture=True, intake=intake)


def test_bad_month_counts_refused_without_intake(tmp_path):
    report = preflight()
    report["months"][1]["count"] = 1001
    with pytest.raises(ValueError):
        capture_batch(report, tmp_path, capture=True, intake=intake)
    assert not list(tmp_path.iterdir())


def test_current_reconciled_capture_may_differ_from_stale_preflight(tmp_path):
    report = preflight()
    report["months"][0]["count"] = 2
    result = capture_batch(report, tmp_path, capture=True, intake=intake)
    assert result["months"][0]["preflight_delta"] == -1
    assert result["months"][0]["provider_count_changed"] is True
    resumed = capture_batch(report, tmp_path, capture=True, intake=lambda *_a, **_k: pytest.fail("network"))
    assert resumed["months"][0]["status"] == "resumed"
    assert resumed["months"][0]["preflight_delta"] == -1


@pytest.mark.parametrize("checkpoint", ["missing", {"offset": 250}])
def test_resume_refuses_missing_or_incomplete_checkpoint(tmp_path, checkpoint):
    import json

    report = preflight()
    capture_batch(report, tmp_path, capture=True, intake=intake)
    path = tmp_path / "2024-01.qualification.json"
    receipt = json.loads(path.read_text())
    if checkpoint == "missing":
        receipt.pop("checkpoint")
    else:
        receipt["checkpoint"] = checkpoint
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="Partial"):
        capture_batch(report, tmp_path, capture=True, intake=intake)
