"""Offline sample diagnostics, not a production identifier mapping or importer."""
import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from app.services.graph_service import normalize_address

MAX_INPUT_BYTES = 10_000_000
MAX_RECORDS = 10_000


def county_reference(reference):
    """Only test the observed Columbus nine-digit to county hyphen hypothesis."""
    if not isinstance(reference, str) or not re.fullmatch(r"[0-9]{9}", reference):
        return None
    return f"{reference[:3]}-{reference[3:]}"


def qualify_sample(permits, response):
    """Compare caller-supplied local evidence; never fetch, mutate, or accept it."""
    if not isinstance(permits, list) or len(permits) > MAX_RECORDS:
        raise ValueError("Permits must be a list of at most 10000 records")
    if not isinstance(response, dict):
        raise ValueError("An ArcGIS response object is required")
    if "error" in response or response.get("exceededTransferLimit") not in (None, False):
        raise ValueError("Failed or truncated source responses cannot measure matching")
    features = response.get("features")
    if not isinstance(features, list) or len(features) > MAX_RECORDS:
        raise ValueError("A complete ArcGIS features response is required")
    parcels = defaultdict(list)
    for feature in features:
        attributes = feature.get("attributes") if isinstance(feature, dict) else None
        if not isinstance(attributes, dict) or not isinstance(attributes.get("PARCELID"), str) or not attributes["PARCELID"].strip():
            raise ValueError("Every parcel needs its original source identifier")
        if attributes.get("SITEADDRESS") is not None and not isinstance(attributes["SITEADDRESS"], str):
            raise ValueError("Parcel street evidence must be text or null")
        parcels[attributes["PARCELID"]].append(attributes)
    counts = Counter({key: 0 for key in (
        "unsupported_reference", "unmatched", "ambiguous",
        "street_match_only", "conflicting_street", "missing_street",
    )})
    items = []
    for permit in permits:
        if not isinstance(permit, dict):
            raise ValueError("Every permit must be an object")
        if permit.get("address") is not None and not isinstance(permit["address"], str):
            raise ValueError("Permit street evidence must be text or null")
        reference = county_reference(permit.get("parcel_id"))
        candidates = parcels.get(reference, [])
        if reference is None:
            outcome = "unsupported_reference"
        elif not candidates:
            outcome = "unmatched"
        elif len(candidates) > 1:
            outcome = "ambiguous"
        else:
            left = normalize_address(permit.get("address") or "")
            right = normalize_address(candidates[0].get("SITEADDRESS") or "")
            outcome = "missing_street" if not left or not right else (
                "street_match_only" if left == right else "conflicting_street"
            )
        counts[outcome] += 1
        items.append({
            "permit_reference": permit.get("parcel_id"),
            "candidate_count": len(candidates), "county_reference_hypothesis": reference,
            "outcome": outcome,
        })
    return {
        "method": "columbus_franklin_sample_v1", "evaluated_permits": len(items),
        "distinct_supported_references": len({item["county_reference_hypothesis"] for item in items
                                              if item["county_reference_hypothesis"] is not None}),
        "returned_parcel_rows": len(features), "distinct_returned_parcel_ids": len(parcels),
        "counts": dict(counts), "items": items,
        "identity_verified": False, "production_eligible": False,
        "limitations": [
            "Formatting is a sample hypothesis, not a qualified cross-source identity rule.",
            "Street agreement alone does not verify city, state, current identity, or ownership.",
            "Address ranges remain conflicts; no house-number containment inference is made.",
            "Counts describe supplied records, not county completeness or market coverage.",
            "Source-use rights, historical changes, coordinates, and acreage remain unqualified.",
        ],
    }


def _read_evidence(path):
    with Path(path).open("rb") as stream:
        data = stream.read(MAX_INPUT_BYTES + 1)
    if len(data) > MAX_INPUT_BYTES:
        raise ValueError("Evidence file exceeds the 10 MB local analysis limit")
    return json.loads(data), hashlib.sha256(data).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--permits", required=True, help="Local JSON array of permit references and addresses")
    parser.add_argument("--parcels", required=True, help="Local complete ArcGIS JSON response")
    args = parser.parse_args(argv)
    try:
        permits, permit_hash = _read_evidence(args.permits)
        response, parcel_hash = _read_evidence(args.parcels)
        report = qualify_sample(permits, response)
    except (OSError, ValueError) as exc:
        # Do not expose file contents, paths, or raw upstream error messages.
        parser.exit(2, f"Qualification failed: {type(exc).__name__}; check input format, completeness, and limits.\n")
    report["measured_at"] = datetime.now(timezone.utc).isoformat()
    report["input_sha256"] = {"permits": permit_hash, "parcels": parcel_hash}
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
