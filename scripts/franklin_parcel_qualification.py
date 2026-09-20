"""Offline sample diagnostics, not a production identifier mapping or importer."""
import re
from collections import Counter, defaultdict

from app.services.graph_service import normalize_address


def county_reference(reference):
    """Only test the observed Columbus nine-digit to county hyphen hypothesis."""
    if not isinstance(reference, str) or not re.fullmatch(r"[0-9]{9}", reference):
        return None
    return f"{reference[:3]}-{reference[3:]}"


def qualify_sample(permits, response):
    """Compare caller-supplied local evidence; never fetch, mutate, or accept it."""
    if response.get("error") or response.get("exceededTransferLimit"):
        raise ValueError("Failed or truncated source responses cannot measure matching")
    features = response.get("features")
    if not isinstance(features, list):
        raise ValueError("A complete ArcGIS features response is required")
    parcels = defaultdict(list)
    for feature in features:
        attributes = feature.get("attributes")
        if not isinstance(attributes, dict) or not isinstance(attributes.get("PARCELID"), str):
            raise ValueError("Every parcel needs its original source identifier")
        parcels[attributes["PARCELID"]].append(attributes)
    counts = Counter({key: 0 for key in (
        "unsupported_reference", "unmatched", "ambiguous",
        "street_match_only", "conflicting_street", "missing_street",
    )})
    items = []
    for permit in permits:
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
