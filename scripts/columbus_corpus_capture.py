"""Plan a local Columbus batch; --capture explicitly permits bounded live intake.

This creates separate local monthly databases, never connects to production, and
never certifies rights, historical completeness, or known-then validation.
Partial files are preserved; --retry-partial starts a separate attempt folder.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import date
from pathlib import Path
from uuid import uuid4

from app.services.ingestion.historical_intake import historical_entry, run_local_intake
from scripts.columbus_corpus_preflight import _digest, build_report


def validate_preflight(report):
    expected = build_report(report["source_key"], date.fromisoformat(report["start_inclusive"]),
                            date.fromisoformat(report["end_exclusive"]))
    if (report.get("method") != expected["method"] or report.get("mode") != "count_probe"
            or report.get("date_field") != expected["date_field"]
            or report.get("plan_sha256") != expected["plan_sha256"]
            or len(report["months"]) != len(expected["months"])):
        raise ValueError("Preflight method, series, or plan hash does not match current catalog")
    for month, planned in zip(report["months"], expected["months"], strict=True):
        for key in ("start_inclusive", "end_exclusive", "url", "query", "scope_sha256"):
            if month.get(key) != planned[key]:
                raise ValueError("Preflight month scope does not match current catalog")
        if (month.get("status") != "count_observed" or month.get("error") is not None
                or type(month.get("count")) is not int or not 0 <= month["count"] <= 1000):
            raise ValueError("Every month needs an observed count of 0-1000 before capture")
        if "scope" in month and month["scope"] != planned["scope"]:
            raise ValueError("Preflight stored scope was modified")
    return expected


def _file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _verified(receipt, database, month, source_key):
    if not isinstance(receipt, dict):
        return False
    count = receipt.get("provider_count_before")
    if type(count) is not int or not 0 <= count <= 1000:
        return False
    if ("checkpoint" not in receipt or receipt["checkpoint"] is not None
            or receipt.get("source_key") != source_key or receipt.get("status") != "completed"
            or receipt.get("count_reconciled") is not True
            or receipt.get("records_failed") != 0
            or receipt.get("scope_sha256") != month["scope_sha256"]
            or _digest(receipt.get("scope")) != month["scope_sha256"]
            or receipt.get("database") != str(database.resolve())
            or any(type(receipt.get(key)) is not int or receipt[key] != count for key in (
                "records_seen", "records_inserted", "provider_count_before", "provider_count_after"))):
        return False
    if not database.is_file() or database.is_symlink():
        return False
    if receipt.get("database_sha256") and receipt["database_sha256"] != _file_hash(database):
        return False
    # Legacy receipts have no database hash: verify local SQLite health and row count.
    try:
        with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as db:
            return (db.execute("PRAGMA quick_check").fetchone() == ("ok",)
                    and db.execute("SELECT count(*) FROM permit_records").fetchone()[0] == count)
    except sqlite3.Error:
        return False


def capture_batch(report, directory, *, capture=False, retry_partial=False, intake=run_local_intake):
    validate_preflight(report)  # Entire batch validated before side effects.
    directory = Path(directory).resolve()
    result = {"mode": "capture" if capture else "plan_only", "plan_sha256": report["plan_sha256"],
              "coverage_verified": False, "known_then_verified": False, "months": []}
    if capture:
        directory.mkdir(parents=True, exist_ok=True)
    for month in report["months"]:
        label = month["start_inclusive"][:7]
        database = directory / f"{label}.db"
        receipt_path = database.with_suffix(".qualification.json")
        status = "planned"
        if capture:
            candidates = [database, *sorted((directory / "attempts").glob(f"{label}-*/*.db"))]
            resumed = False
            for candidate in candidates:
                candidate_receipt = candidate.with_suffix(".qualification.json")
                if candidate_receipt.is_file() and not candidate_receipt.is_symlink():
                    try:
                        receipt = json.loads(candidate_receipt.read_text())
                        resumed = _verified(receipt, candidate, month, report["source_key"])
                    except (ValueError, OSError):
                        resumed = False
                    if resumed:
                        database, receipt_path, status = candidate, candidate_receipt, "resumed"
                        break
            if not resumed:
                if any(p.exists() or p.is_symlink() for p in (database, receipt_path)):
                    if not retry_partial:
                        raise ValueError(f"Partial or unverifiable month {label}; use a separate attempt")
                    attempt = directory / "attempts" / f"{label}-{uuid4().hex}"
                    attempt.mkdir(parents=True)
                    database = attempt / f"{label}.db"
                    receipt_path = database.with_suffix(".qualification.json")
                entry = historical_entry(report["source_key"], date.fromisoformat(month["start_inclusive"]),
                                         date.fromisoformat(month["end_exclusive"]))
                # Reserve receipt before intake; interruptions remain visible and non-overwritable.
                with receipt_path.open("x") as output:
                    receipt = intake(database, entry, max_pages=4)
                    receipt["preflight_plan_sha256"] = report["plan_sha256"]
                    receipt["database_sha256"] = _file_hash(database)
                    json.dump(receipt, output, indent=2)
                    output.write("\n")
                if not _verified(receipt, database, month, report["source_key"]):
                    raise ValueError(f"Month {label} did not reconcile its capture counts and scope; batch stopped")
                status = "captured"
        observed = receipt["provider_count_before"] if capture else None
        result["months"].append({"month": label, "status": status,
                                 "preflight_count": month["count"], "capture_count": observed,
                                 "preflight_delta": observed - month["count"] if capture else None,
                                 "provider_count_changed": observed != month["count"] if capture else None,
                                 "database": str(database), "receipt": str(receipt_path)})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--retry-partial", action="store_true")
    args = parser.parse_args()
    result = capture_batch(json.loads(args.preflight.read_text()), args.directory,
                           capture=args.capture, retry_partial=args.retry_partial)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
