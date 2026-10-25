"""Read-only, explicit-scope production ingestion acceptance; no scheduling/writes."""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlsplit

import httpx


def validate_origin(value):
    parts = urlsplit(value)
    if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
            or parts.query or parts.fragment or parts.path not in {"", "/"}):
        raise ValueError("An HTTPS origin without credentials, path or query is required")
    return value.rstrip("/")


def _date(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timezone required")
    return parsed


def _identifier(value):
    return isinstance(value, str) and 0 < len(value) <= 100 and value.strip() == value


def evaluate_source(source, run, *, now, freshness_hours):
    reasons = []
    stored = source.get("stored_records")
    if not isinstance(source.get("source_id"), str) or not source["source_id"]:
        reasons.append("missing_source_identity")
    if source.get("configured_active") is not True:
        reasons.append("source_not_active")
    if type(stored) is not int or stored <= 0:
        reasons.append("missing_inventory")
    if not isinstance(run, dict):
        reasons.append("missing_latest_run")
    else:
        if not _identifier(run.get("id")) or run.get("source_id") != source.get("source_id"):
            reasons.append("run_identity_mismatch")
        if run.get("status") != "completed" or run.get("trigger") != "scheduled":
            reasons.append("latest_run_not_scheduled_completion")
        if type(run.get("records_failed")) is not int or run["records_failed"] != 0:
            reasons.append("record_failures_or_unknown")
        if type(run.get("records_seen")) is not int or run["records_seen"] < 0:
            reasons.append("invalid_seen_count")
        try:
            started, completed = _date(run["started_at"]), _date(run["completed_at"])
            age = (now - started).total_seconds() / 3600
            if not -30 / 3600 <= age <= freshness_hours or not started <= completed <= now + timedelta(seconds=30):
                reasons.append("stale_or_inconsistent_run_time")
        except (KeyError, ValueError, TypeError, AttributeError):
            reasons.append("missing_or_invalid_run_time")
    return {"source_key": source.get("source_key"), "passed": not reasons,
            "stored_records": stored if type(stored) is int else None,
            "latest_run_id": run.get("id") if isinstance(run, dict) and _identifier(run.get("id")) else None,
            "reasons": reasons}


def verify(*, api_base, organization_id, source_keys, token, allow_live,
           record_type="permit", freshness_hours=36, get=None, now=None):
    blocked = {"status": "blocked", "checks": [], "scope": "Specified workspace and sources only"}
    if (not allow_live or not token or not organization_id or not source_keys
            or len(source_keys) > 50 or len(set(source_keys)) != len(source_keys)
            or record_type not in {"permit", "planning"} or not 1 <= freshness_hours <= 8760):
        return {**blocked, "reason": "Explicit live scope, workspace, unique sources and bearer credential required"}
    clock = (lambda: now) if now is not None else (lambda: datetime.now(timezone.utc))
    deadline = time.monotonic() + 120
    try:
        origin = validate_origin(api_base)
        def fetch(path):
            # Never follow redirects carrying bearer credentials; bound response bytes.
            with httpx.Client(timeout=20, follow_redirects=False) as client:
                with client.stream("GET", origin + path, headers={"Authorization": "Bearer " + token, "Accept-Encoding": "identity"}) as response:
                    response.raise_for_status()
                    body = bytearray()
                    for chunk in response.iter_raw():
                        if time.monotonic() > deadline:
                            raise ValueError("Verification deadline exceeded")
                        if len(body) + len(chunk) > 2_000_000:
                            raise ValueError("Response bound exceeded")
                        body.extend(chunk)
                    return json.loads(body)
        def read(path):
            if time.monotonic() > deadline:
                raise ValueError("Verification deadline exceeded")
            result = (get or fetch)(path)
            if time.monotonic() > deadline:
                raise ValueError("Verification deadline exceeded")
            return result
        actor = read("/v1/auth/me")
        if actor.get("is_demo") is not False or actor.get("organization_id") != organization_id:
            return {**blocked, "reason": "Demo, unknown or mismatched workspace identity"}
        sources = {}
        for page in range(10):
            query = urlencode({"record_type": record_type, "limit": 100, "offset": page * 100,
                               "freshness_hours": freshness_hours})
            payload = read("/v1/ingestion/coverage/measured?" + query)
            age = (clock() - _date(payload["measured_at"])).total_seconds()
            if not -30 <= age <= 300:
                raise ValueError("Stale measurement")
            if (payload.get("record_type") != record_type or payload.get("freshness_hours") != freshness_hours
                    or payload.get("offset") != page * 100 or payload.get("limit") != 100
                    or not isinstance(payload.get("sources"), list) or len(payload["sources"]) > 100):
                raise ValueError("Mismatched measurement scope")
            for source in payload["sources"]:
                key = source["source_key"]
                if key in sources:
                    raise ValueError("Duplicate source evidence")
                sources[key] = source
            if payload["has_more"] is False:
                break
            if payload["has_more"] is not True or len(payload["sources"]) != 100:
                raise ValueError("Incomplete pagination")
        else:
            raise ValueError("Coverage exceeds bounded pagination")
        checks = []
        for key in source_keys:
            if key not in sources:
                checks.append({"source_key": key, "passed": False, "reasons": ["missing_source"]})
                continue
            source = sources[key]
            runs = read("/v1/ingestion/runs?" + urlencode({"source_id": source["source_id"], "limit": 1}))
            if not isinstance(runs, list) or len(runs) > 1:
                raise ValueError("Invalid run evidence")
            checks.append(evaluate_source(source, runs[0] if runs else None,
                                          now=clock(), freshness_hours=freshness_hours))
        return {"status": "passed" if all(c["passed"] for c in checks) else "blocked",
                "checked_at": clock().isoformat(), "checks": checks,
                "scope": "Specified workspace/source collection only; not source completeness, parcel availability or filing freshness"}
    except Exception:
        # Exceptions can contain URLs, credentials or raw provider data.
        return {**blocked, "reason": "Evidence request or validation failed; details withheld"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", required=True)
    parser.add_argument("--organization-id", required=True)
    parser.add_argument("--source-key", action="append", required=True)
    parser.add_argument("--record-type", choices=["permit", "planning"], default="permit")
    parser.add_argument("--freshness-hours", type=int, default=36)
    parser.add_argument("--live-acceptance", action="store_true")
    args = parser.parse_args(argv)
    report = verify(api_base=args.api_base, organization_id=args.organization_id,
                    source_keys=args.source_key, record_type=args.record_type,
                    freshness_hours=args.freshness_hours, allow_live=args.live_acceptance,
                    token=os.environ.get("INGESTION_VERIFY_TOKEN"))
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
