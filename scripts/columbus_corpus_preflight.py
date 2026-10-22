"""Plan Columbus monthly intake offline; opt in to at most 36 logical count queries.

Run from the repository root: python -m scripts.columbus_corpus_preflight --help.
No retries; the allowlisted client can follow redirects or use IP fallbacks.
No source activation, row retrieval, database access, or completeness certification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from app.services.ingestion.connectors.base import ConnectorError, RetryingHttpClient
from app.services.ingestion.historical_intake import (
    SOURCE_FIELDS,
    historical_entry,
    provider_count,
)


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def build_report(source_key, start, end, *, today=None, client=None):
    """A supplied client explicitly opts into one count request per full month."""
    today = today or datetime.now(timezone.utc).date()
    months = (end.year - start.year) * 12 + end.month - start.month
    if (start.day != 1 or end.day != 1 or not 1 <= months <= 36
            or end > today.replace(day=1)):
        raise ValueError("Choose 1-36 completed full months; end is exclusive")
    if source_key not in SOURCE_FIELDS:
        raise ValueError("Choose a fixed Columbus source")
    report = {
        "method": "columbus-monthly-count-preflight-v0",
        "mode": "count_probe" if client is not None else "plan_only",
        "source_key": source_key,
        "date_field": SOURCE_FIELDS[source_key],
        "start_inclusive": start.isoformat(), "end_exclusive": end.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "maximum_count_queries": months if client is not None else 0,
        "coverage_verified": False, "known_then_verified": False,
        "commercial_reuse_verified": False,
        "limitations": [
            "Current provider counts are not a frozen snapshot or historical completeness proof.",
            "Current historical values cannot establish what was known at historical cutoffs.",
            "Count availability does not establish commercial reuse rights or authorize import.",
            "Months above 1000 rows require smaller intake intervals before existing bounded intake.",
            "An observed zero is not proof of no development activity.",
        ],
        "months": [],
    }
    cursor = start
    while cursor < end:
        following = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
        entry = historical_entry(source_key, cursor, following)
        scope = entry.model_dump(mode="json")
        month = {
            "start_inclusive": cursor.isoformat(), "end_exclusive": following.isoformat(),
            "url": entry.base_url,
            "query": {"f": "json", "where": entry.settings["connector"]["where"],
                      "returnCountOnly": "true", "returnGeometry": "false"},
            "scope": scope, "scope_sha256": _digest(scope),
            "count": None, "status": "not_probed", "error": None,
        }
        if client is not None:
            try:
                month["count"] = provider_count(entry, client)
                month["status"] = "split_required" if month["count"] > 1000 else "count_observed"
            except (ConnectorError, ValueError) as exc:
                month["status"] = "unavailable"
                month["error"] = type(exc).__name__
            month["observed_at"] = datetime.now(timezone.utc).isoformat()
        report["months"].append(month)
        cursor = following
    report["plan_sha256"] = _digest([
        {"url": month["url"], "query": month["query"], "scope_sha256": month["scope_sha256"]}
        for month in report["months"]
    ])
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-key", choices=SOURCE_FIELDS, required=True)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--probe", action="store_true", help="Explicitly permit bounded count-only GETs")
    parser.add_argument("--output", type=Path, help="New JSON artifact; existing files are refused")
    args = parser.parse_args()
    # Validate the entire scope before opening an artifact or making any requests.
    plan = build_report(args.source_key, args.start, args.end)
    output = args.output.open("x") if args.output else None
    try:
        if args.probe:
            hosts = frozenset(urlsplit(month["url"]).hostname for month in plan["months"])
            client = RetryingHttpClient(timeout=15, max_retries=0, allowed_hosts=hosts)
            plan = build_report(args.source_key, args.start, args.end, client=client)
        rendered = json.dumps(plan, indent=2) + "\n"
        if output:
            output.write(rendered)
        print(rendered, end="")
    finally:
        if output:
            output.close()
    if any(month["status"] == "unavailable" for month in plan["months"]):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
