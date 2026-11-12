"""Bounded SF derived geocodes. Default plan mode makes no requests or writes."""
from __future__ import annotations

import argparse
import json
import time

from app.db import SessionLocal
from app.models.ingestion import IngestionSource, PermitRecord
from app.models.organization import Organization
from app.models.permit_geocode import PermitGeocode
from app.services.demo_access import DEMO_ORG_ID, demo_read_only
from app.services.ingestion.connectors.base import ConnectorError, RetryingHttpClient
from app.services.sf_geocoding import (
    LOCATION_METHOD,
    SOURCE_KEY,
    SOURCE_URL,
    is_current_geocode,
    request_url,
    save_match,
)
from app.utils.org_scope import RequestContext, reset_current_context, set_current_context

MAX_LIMIT = 200
MAX_SCAN = 5000


def _fetch(url):
    client = RetryingHttpClient(timeout=12, max_retries=0,
        allowed_hosts=frozenset({"geocoding.geo.census.gov"}))
    body, _ = client.get_bytes(url, max_bytes=65_536)
    return json.loads(body)


def run(organization_id: str, *, limit=20, scan_limit=1000, after_permit_id=None,
        execute=False, fetch=_fetch, sleep=time.sleep, session_factory=SessionLocal):
    if (not organization_id or organization_id == DEMO_ORG_ID
            or type(limit) is not int or not 1 <= limit <= MAX_LIMIT
            or type(scan_limit) is not int or not 1 <= scan_limit <= MAX_SCAN
            or (after_permit_id is not None and (not isinstance(after_permit_id, str)
                or not 1 <= len(after_permit_id) <= 36))):
        raise ValueError("Explicit non-demo tenant and bounded limits/cursor are required")
    if demo_read_only.get():
        raise PermissionError("Demo sessions cannot run production geocoding")
    token = set_current_context(RequestContext(organization_id, "sf-geocode-operator"))
    result = {"mode": "execute" if execute else "plan", "status": "completed",
        "source_key": SOURCE_KEY, "method": LOCATION_METHOD, "records_scanned": 0,
        "addresses_planned": 0, "addresses_attempted": 0, "addresses_matched": 0,
        "filings_located": 0, "already_located": 0, "held": 0,
        "next_after_permit_id": None}
    try:
        with session_factory() as db:
            org = db.get(Organization, organization_id)
            source = db.query(IngestionSource).filter_by(organization_id=organization_id,
                key=SOURCE_KEY, base_url=SOURCE_URL, is_active=True).one_or_none()
            if org is None or not org.is_active or source is None:
                raise ValueError("An active tenant and reviewed SF source are required")
            query = db.query(PermitRecord, PermitGeocode).outerjoin(PermitGeocode,
                (PermitGeocode.permit_id == PermitRecord.id)
                & (PermitGeocode.organization_id == PermitRecord.organization_id),
            ).filter(PermitRecord.organization_id == organization_id, PermitRecord.source_id == source.id,
                PermitRecord.is_active.is_(True), PermitRecord.latitude.is_(None), PermitRecord.longitude.is_(None))
            if after_permit_id:
                query = query.filter(PermitRecord.id > after_permit_id)
            rows = query.order_by(PermitRecord.id).limit(scan_limit + 1).all()
            cache, matched_urls = {}, set()
            last = after_permit_id
            for permit, geocode in rows[:scan_limit]:
                try:
                    url = request_url(permit, source)
                except ValueError:
                    result["records_scanned"] += 1
                    result["held"] += 1
                    last = permit.id
                    continue
                if geocode is not None and is_current_geocode(permit, source, geocode):
                    result["records_scanned"] += 1
                    result["already_located"] += 1
                    last = permit.id
                    continue
                if url not in cache and len(cache) >= limit:
                    result["next_after_permit_id"] = last
                    break
                result["records_scanned"] += 1
                if url not in cache:
                    result["addresses_planned"] += 1
                    if execute:
                        result["addresses_attempted"] += 1
                        try:
                            cache[url] = fetch(url)
                        except (OSError, ValueError, ConnectorError):
                            result["status"] = "provider_error"
                            result["next_after_permit_id"] = last
                            break  # Stop on provider/access errors; never hammer another address.
                        finally:
                            sleep(1)
                    else:
                        cache[url] = None
                if execute:
                    db.refresh(permit)
                    try:
                        saved = save_match(db, permit, cache[url], url)
                    except ValueError:
                        saved = False  # Address/source changed while the request was in flight.
                    if saved:
                        db.commit()
                        result["filings_located"] += 1
                        matched_urls.add(url)
                    else:
                        result["held"] += 1
                last = permit.id
            else:
                if len(rows) > scan_limit:
                    result["next_after_permit_id"] = last
            result["addresses_matched"] = len(matched_urls)
            if result["status"] == "completed":
                result["status"] = ("planned" if not execute else
                    "partial" if result["next_after_permit_id"] else "completed")
    finally:
        reset_current_context(token)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organization-id", required=True)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--scan-limit", type=int, default=1000)
    parser.add_argument("--after-permit-id")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-address-transmission", action="store_true")
    parser.add_argument("--confirm-derived-writes", action="store_true")
    args = parser.parse_args()
    if args.execute and not (args.confirm_address_transmission and args.confirm_derived_writes):
        parser.error("Execution requires explicit address-transmission and derived-write confirmations")
    try:
        result = run(args.organization_id, limit=args.limit, scan_limit=args.scan_limit,
            after_permit_id=args.after_permit_id, execute=args.execute)
    except Exception as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__}))
        raise SystemExit(1) from None
    print(json.dumps(result))
    if result["status"] not in {"planned", "partial", "completed"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
