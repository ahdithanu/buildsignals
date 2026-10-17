"""Production-safe, bounded backfill of derived Census geocodes for the demo tenant.

Unlike ``scripts/qualify`` helpers, this may run against the deployed demo tenant
(Postgres) so the read-only demo map shows filing locations. It is still tightly
bounded and defensive:

- Only the fixed demo organization is touched; every write goes through
  ``demo_geocoding.save_match``, which re-validates the permit, the exact request
  URL, the matched address, and a Columbus bounding box before storing a point.
- Distinct addresses are geocoded at most once; already-located or unchanged
  permits are skipped, so reruns accumulate coverage idempotently.
- Each run is capped (``--limit`` distinct addresses) and rate-limited, and the
  free Census geocoder is the only host contacted. No source is activated and no
  customer tenant is read or written.

Run (deployed demo tenant): ``python scripts/backfill_demo_geocode.py --limit 500 --confirm-production``
"""
from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from urllib.request import Request, urlopen

from app.db import SessionLocal
from app.models.ingestion import PermitRecord
from app.models.permit_geocode import PermitGeocode
from app.services.demo_access import DEMO_ORG_ID
from app.services.demo_geocoding import address_hash, request_url, save_match
from app.utils.org_scope import RequestContext, reset_current_context, set_current_context

MAX_LIMIT = 2000
_MAX_RESPONSE_BYTES = 65_536


def _default_fetch(url: str) -> dict:
    request = Request(url, headers={"User-Agent": "BuildSignals-demo-geocode/1"})
    with urlopen(request, timeout=12) as stream:
        data = stream.read(_MAX_RESPONSE_BYTES + 1)
    if len(data) > _MAX_RESPONSE_BYTES:
        raise ValueError("Geocoder response exceeds the bounded limit")
    return json.loads(data)


def run(limit: int, *, fetch=_default_fetch, sleep=time.sleep, session_factory=SessionLocal) -> dict:
    if not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")
    context = set_current_context(RequestContext(DEMO_ORG_ID, "demo-geocode-backfill"))
    results = {
        "addresses_attempted": 0,
        "addresses_matched": 0,
        "filings_located": 0,
        "ambiguous_or_unmatched": 0,
        "method": "census_address_range_estimate",
        "tenant": DEMO_ORG_ID,
    }
    try:
        with session_factory() as db:
            permits = db.query(PermitRecord).filter_by(
                organization_id=DEMO_ORG_ID, is_active=True
            ).order_by(PermitRecord.id).all()
            located = {
                row.permit_id: row.address_hash
                for row in db.query(PermitGeocode).filter_by(organization_id=DEMO_ORG_ID).all()
            }
            groups: dict[str, list] = defaultdict(list)
            for permit in permits:
                if permit.latitude is not None or permit.longitude is not None:
                    continue
                if located.get(permit.id) == address_hash(permit):
                    continue
                try:
                    url = request_url(permit)
                except ValueError:
                    continue
                groups[url].append(permit)
            # Geocode the densest addresses first so a bounded run maps the most filings.
            for url, rows in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))[:limit]:
                results["addresses_attempted"] += 1
                try:
                    response = fetch(url)
                except (OSError, ValueError):
                    results["ambiguous_or_unmatched"] += 1
                    continue
                matched = sum(1 for permit in rows if save_match(db, permit, response, url))
                if matched:
                    db.commit()
                    results["addresses_matched"] += 1
                    results["filings_located"] += matched
                else:
                    results["ambiguous_or_unmatched"] += 1
                sleep(0.2)
    finally:
        reset_current_context(context)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--confirm-production", action="store_true", required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.limit)))


if __name__ == "__main__":
    main()
