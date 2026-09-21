"""Versioned user-requested acquisition criteria; not an investment recommendation."""
from decimal import Decimal
from math import isfinite

from app.models.deal import Deal
from app.schemas.buy_box import AcquisitionCriteria

PROFILES = {
    "small_multifamily": (
        ("units", "Units", 16, 32, "16–32 units"),
        ("year_built", "Construction year", 1980, None, "1980 or newer"),
        ("asking_price", "Asking price", 1_000_000, 3_000_000, "$1M–$3M"),
    ),
    "small_bay_retail": (
        ("sq_ft", "Building area", 8_000, 25_000, "8,000–25,000 SF"),
        ("year_built", "Construction year", 1985, None, "1985 or newer"),
        ("asking_price", "Asking price", 1_500_000, 4_000_000, "$1.5M–$4M"),
    ),
}

RETAIL_DILIGENCE = (
    ("bays", "Tenant bays", "5–12 bays, typically 1,200–2,500 SF each"),
    ("occupancy", "Occupancy", "80–100%"),
    ("concentration", "Largest tenant rent share", "No more than 30% of gross rent"),
    ("restaurants", "Restaurant rent share", "Less than 25%"),
    ("tenant_mix", "Tenant mix", "Necessity and service tenants"),
    ("leases", "Lease structure and CAM", "NNN or modified NNN with CAM reconciliation"),
    ("walt", "Weighted average lease term", "At least 3 years"),
    ("rent", "Rent versus market", "In-place rent at or below supported market rent"),
    ("access", "Access", "Signalized intersection or strong frontage"),
    ("traffic", "Traffic", "15,000+ vehicles per day; validate count date and road"),
    ("parking", "Parking", "At least 4 spaces per 1,000 SF"),
    ("population", "Three-mile population", "Stable or growing with dated comparison"),
    ("capex", "Roof, HVAC, and parking lot", "Remaining useful life verified before LOI"),
)


def screen_acquisition(deal: Deal, profile: str, market_city: str | None = None,
                       market_state: str | None = None, *,
                       custom_criteria: AcquisitionCriteria | None = None) -> dict:
    if custom_criteria is not None:
        profile = custom_criteria.profile
        market_city, market_state = custom_criteria.market_city, custom_criteria.market_state
    if profile not in PROFILES:
        raise ValueError("Unsupported acquisition profile")
    criteria = []
    for field, label, lower, upper, target in PROFILES[profile]:
        if custom_criteria is not None:
            if field == "asking_price":
                lower, upper = custom_criteria.min_price, custom_criteria.max_price
                target = f"${lower:,.0f}-${upper:,.0f}"
            elif field == "year_built":
                lower, upper = custom_criteria.min_year_built, None
                target = f"{lower} or newer"
            else:
                lower, upper = custom_criteria.min_size, custom_criteria.max_size
                target = f"{lower:,}-{upper:,} {'units' if field == 'units' else 'SF'}"
        value = getattr(deal, field)
        valid = (
            isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)
            and isfinite(value) and value > 0
        )
        status = "unknown" if not valid else "pass" if value >= lower and (
            upper is None or value <= upper
        ) else "fail"
        criteria.append({
            "key": field, "label": label, "target": target, "status": status,
            "value": value if valid else None,
            "basis": f"deal.{field}" if valid else None,
            "reason": "Stored deal value; independently verify against source documents."
            if valid else "A usable deal value has not been recorded.",
        })
    def clean_location(value):
        return value.strip() if isinstance(value, str) else ""

    target_city, target_state = clean_location(market_city), clean_location(market_state)
    deal_city, deal_state = clean_location(deal.city), clean_location(deal.state)
    market_known = all((target_city, target_state, deal_city, deal_state))
    market_matches = market_known and deal_city.casefold() == target_city.casefold() and (
        deal_state.casefold() == target_state.casefold()
    )
    criteria.append({
        "key": "market", "label": "Target market",
        "target": f"{target_city}, {target_state}" if target_city and target_state else "Select one city and state",
        "status": ("pass" if market_matches else "fail") if market_known else "unknown",
        "value": ", ".join(filter(None, (deal_city, deal_state))) or None,
        "basis": "deal.city,deal.state" if market_known else None,
        "reason": "Exact city/state comparison; not a metro-area inference." if market_known
        else "Target market or deal location is incomplete.",
    })
    diligence = [("asset_type", "Asset configuration", "Multifamily building")]
    if profile == "small_bay_retail":
        diligence = [("asset_type", "Asset configuration", "Unanchored or shadow-anchored multi-tenant strip"), *RETAIL_DILIGENCE]
    for key, label, target in diligence:
        criteria.append({"key": key, "label": label, "target": target, "status": "unknown",
                         "value": None, "basis": None,
                         "reason": "Requires documented diligence; not inferred from permits or proximity."})
    counts = {state: sum(c["status"] == state for c in criteria) for state in ("pass", "fail", "unknown")}
    return {"deal_id": deal.id, "profile": profile, "method_version": "acquisition-screen-v3",
            "criteria": criteria, "counts": counts,
            "status": "outside_buy_box" if counts["fail"] else "needs_diligence" if counts["unknown"] else "fits_recorded_criteria",
            "evidence_verified": False}
