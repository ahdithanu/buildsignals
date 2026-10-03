"""Geocode at most 25 distinct demo addresses; never runs in request handlers or seeds."""
import argparse
import json
import time
from collections import defaultdict
from urllib.request import Request, urlopen

from app import config
from app.db import SessionLocal
from app.models.ingestion import PermitRecord
from app.models.permit_geocode import PermitGeocode
from app.services.demo_access import DEMO_ORG_ID
from app.services.demo_geocoding import address_hash, request_url, save_match
from app.utils.org_scope import RequestContext, reset_current_context, set_current_context


def run(limit: int) -> dict:
    if not config.DATABASE_URL.startswith("sqlite:"):
        raise ValueError("This qualification command accepts only a local SQLite database")
    context = set_current_context(RequestContext(DEMO_ORG_ID, "demo-geocode-qualification"))
    results = {"addresses_attempted": 0, "addresses_matched": 0, "filings_located": 0,
               "ambiguous_or_unmatched": 0, "method": "census_address_range_estimate", "production_activated": False}
    try:
        with SessionLocal() as db:
            permits = db.query(PermitRecord).filter_by(organization_id=DEMO_ORG_ID, is_active=True).order_by(
                PermitRecord.id,
            ).all()
            current = {row.permit_id: row.address_hash for row in db.query(PermitGeocode).filter_by(
                organization_id=DEMO_ORG_ID,
            ).all()}
            groups = defaultdict(list)
            for permit in permits:
                if permit.latitude is not None or permit.longitude is not None:
                    continue
                if current.get(permit.id) == address_hash(permit):
                    continue
                try:
                    url = request_url(permit)
                except ValueError:
                    continue
                groups[url].append(permit)
            for url, rows in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))[:limit]:
                results["addresses_attempted"] += 1
                try:
                    with urlopen(Request(url, headers={"User-Agent": "BuildSignals-local-qualification/1"}), timeout=12) as stream:
                        data = stream.read(65_537)
                        if len(data) > 65_536:
                            raise ValueError("Geocoder response exceeds the bounded limit")
                        response = json.loads(data)
                except (OSError, ValueError):
                    results["ambiguous_or_unmatched"] += 1
                    continue
                matched = 0
                for permit in rows:
                    if save_match(db, permit, response, url):
                        matched += 1
                if matched:
                    db.commit()
                    results["addresses_matched"] += 1
                    results["filings_located"] += matched
                else:
                    results["ambiguous_or_unmatched"] += 1
                time.sleep(0.2)
    finally:
        reset_current_context(context)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--confirm-local-demo", action="store_true", required=True)
    args = parser.parse_args()
    if not 1 <= args.limit <= 25:
        parser.error("limit must be between 1 and 25")
    print(json.dumps(run(args.limit)))


if __name__ == "__main__":
    main()
