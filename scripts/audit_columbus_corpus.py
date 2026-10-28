"""Offline, read-only audit of local Columbus shards; emits aggregate evidence only."""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from scripts.columbus_corpus_capture import _file_hash, _verified, validate_preflight
from scripts.columbus_corpus_preflight import _digest


def _time(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def audit_corpus(preflight, directory):
    validate_preflight(preflight)
    directory = Path(directory).resolve()
    planned = {m["start_inclusive"]: m for m in preflight["months"]}
    result = {"method": "columbus-local-shard-audit-v0", "plan_sha256": preflight["plan_sha256"],
              "coverage_verified": False, "known_then_verified": False,
              "limitations": "Count reconciliation is not historical completeness or signal validation.",
              "months": [], "duplicate_stable_ids": 0, "total_records": 0,
              "historical_known_then_observations": 0, "ignored_incomplete_receipts": []}
    accepted, seen_ids, databases = set(), set(), set()
    for path in sorted(directory.rglob("*.qualification.json")):
        if path.is_symlink():
            raise ValueError("Symlink receipt refused")
        contents = path.read_text()
        if not contents.strip():
            result["ignored_incomplete_receipts"].append(str(path.relative_to(directory)))
            continue
        receipt = json.loads(contents)
        if not isinstance(receipt, dict):
            raise ValueError("Invalid receipt")
        if receipt.get("status") != "completed":
            result["ignored_incomplete_receipts"].append(str(path.relative_to(directory)))
            continue
        scope = receipt.get("scope", {})
        interval = scope.get("settings", {}).get("historical_qualification", {})
        start = interval.get("start_inclusive")
        month = planned.get(start)
        if month is None:
            raise ValueError("Receipt outside pinned preflight")
        database = path.with_suffix("").with_suffix(".db")
        if ("checkpoint" not in receipt or receipt["checkpoint"] is not None
                or not _verified(receipt, database, month, preflight["source_key"])):
            raise ValueError("Unverified receipt or incomplete checkpoint")
        if start in accepted:
            raise ValueError("Duplicate completed month receipt")
        accepted.add(start)
        databases.add(database.resolve())
        lower, upper = _time(start), _time(month["end_exclusive"])
        began, finished = _time(receipt["started_at"]), _time(receipt["finished_at"])
        if began > finished:
            raise ValueError("Invalid receipt capture interval")
        with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as db:
            filed = [row[0] for row in db.execute("SELECT filed_at FROM permit_records")]
            raw = db.execute("SELECT external_record_id, received_at, source_updated_at FROM raw_source_records").fetchall()
            recorded = [row[0] for row in db.execute("SELECT recorded_at FROM temporal_observations")]
        ids = [row[0] for row in raw]
        if any(not isinstance(value, str) or not value.strip() for value in ids):
            raise ValueError("Missing stable source identity")
        result["duplicate_stable_ids"] += len(ids) - len(set(ids)) + len(set(ids) & seen_ids)
        seen_ids.update(ids)
        received = [_time(row[1]) for row in raw]
        recorded_times = [_time(value) for value in recorded]
        source_times = [_time(row[2]) for row in raw if row[2]]
        known_then = sum(value < upper for value in recorded_times)
        summary = {
            "month": start[:7], "records": len(filed), "raw_records": len(raw),
            "temporal_observations": len(recorded),
            "raw_count_matches": len(raw) == receipt["provider_count_before"],
            "preflight_count": month["count"],
            "capture_count": receipt["provider_count_before"],
            "preflight_delta": receipt["provider_count_before"] - month["count"],
            "provider_count_changed": receipt["provider_count_before"] != month["count"],
            "filed_missing": sum(value is None for value in filed),
            "filed_outside_month": sum(not lower <= _time(value) < upper for value in filed if value),
            "future_source_updated": sum(value > finished for value in source_times),
            "capture_time_violations": sum(not began <= value <= finished for value in received + recorded_times),
            "raw_received_earliest": min(received).isoformat() if received else None,
            "raw_received_latest": max(received).isoformat() if received else None,
            "temporal_recorded_earliest": min(recorded_times).isoformat() if recorded_times else None,
            "temporal_recorded_latest": max(recorded_times).isoformat() if recorded_times else None,
            "historical_known_then_observations": known_then,
            "database_sha256": _file_hash(database), "receipt_sha256": _file_hash(path),
        }
        result["months"].append(summary)
        result["total_records"] += len(filed)
        result["historical_known_then_observations"] += known_then
    result["months"].sort(key=lambda row: row["month"])
    result["missing_months"] = [start[:7] for start in planned if start not in accepted]
    result["ignored_partial_databases"] = sorted(
        str(p.relative_to(directory)) for p in directory.rglob("*.db") if p.resolve() not in databases)
    result["audit_passed"] = not (
        result["missing_months"] or result["duplicate_stable_ids"]
        or any(not m["raw_count_matches"] or m["filed_missing"] or m["filed_outside_month"]
               or m["future_source_updated"] or m["capture_time_violations"] for m in result["months"]))
    result["evidence_sha256"] = _digest(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit_corpus(json.loads(args.preflight.read_text()), args.directory)
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        with args.output.open("x") as output:
            output.write(rendered)
    print(rendered, end="")
    if not result["audit_passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
