"""Deterministic mock enrichment service for deals.

Uses a hash of the deal name as a seed so that enrichment is repeatable
and does not depend on any external API.
"""

from __future__ import annotations

import hashlib
from typing import Union

from sqlalchemy.orm import Session

from app.models.deal import Deal
from app.models.deal_assumptions import DealAssumptions
from app.services.normalization_service import normalize_property_type


# ── Property-type ranges ────────────────────────────────────────────────────

_RANGES: dict[str, dict] = {
    "multifamily": {
        "units": (50, 200),
        "sq_ft": (40_000, 150_000),
        "year_built": (1970, 2010),
        "asking_price": (5_000_000, 50_000_000),
    },
    "office": {
        "units": None,
        "sq_ft": (10_000, 100_000),
        "year_built": (1980, 2015),
        "asking_price": (3_000_000, 30_000_000),
    },
    "retail": {
        "units": None,
        "sq_ft": (5_000, 50_000),
        "year_built": (1990, 2020),
        "asking_price": (1_000_000, 15_000_000),
    },
    "industrial": {
        "units": None,
        "sq_ft": (20_000, 200_000),
        "year_built": (1985, 2015),
        "asking_price": (2_000_000, 20_000_000),
    },
}

_DEFAULT_RANGE: dict = {
    "units": (20, 100),
    "sq_ft": (10_000, 80_000),
    "year_built": (1980, 2015),
    "asking_price": (2_000_000, 20_000_000),
}


def _seed_from_name(name: str) -> int:
    """Return a stable integer seed derived from the deal name."""
    return int(hashlib.sha256(name.encode()).hexdigest(), 16)


def _pick(seed: int, low: Union[int, float], high: Union[int, float], as_int: bool = True):
    """Deterministically pick a value in [low, high] from the seed."""
    # Use modulo to get a fraction, then scale
    fraction = (seed % 10_000) / 10_000
    value = low + fraction * (high - low)
    return int(value) if as_int else round(value, 2)


def enrich_deal(db: Session, deal: Deal) -> Deal:
    """Fill missing fields on *deal* with plausible mock data and create
    default assumptions if none exist.  Returns the updated deal."""

    seed = _seed_from_name(deal.name)
    ptype = (deal.property_type or "").lower()
    ranges = _RANGES.get(ptype, _DEFAULT_RANGE)

    # Fill missing property fields ------------------------------------------------
    if deal.units is None and ranges.get("units") is not None:
        lo, hi = ranges["units"]
        deal.units = _pick(seed, lo, hi)

    if deal.sq_ft is None and ranges.get("sq_ft") is not None:
        lo, hi = ranges["sq_ft"]
        deal.sq_ft = _pick(seed ^ 1, lo, hi)

    if deal.year_built is None:
        lo, hi = ranges["year_built"]
        deal.year_built = _pick(seed ^ 2, lo, hi)

    if deal.asking_price is None:
        lo, hi = ranges["asking_price"]
        deal.asking_price = _pick(seed ^ 3, lo, hi, as_int=False)

    if deal.address is None:
        street_num = _pick(seed ^ 4, 100, 9999)
        deal.address = f"{street_num} Main St"

    if deal.city is None:
        cities = ["Austin", "Dallas", "Phoenix", "Denver", "Atlanta",
                  "Nashville", "Charlotte", "Tampa", "Orlando", "Raleigh"]
        deal.city = cities[seed % len(cities)]

    if deal.state is None:
        deal.state = "TX"  # sensible default

    if deal.zip_code is None:
        deal.zip_code = str(70000 + _pick(seed ^ 5, 0, 29999))

    deal.property_type = normalize_property_type(deal.property_type)

    # Ensure default assumptions exist -------------------------------------------
    if deal.assumptions is None:
        price = deal.asking_price or 5_000_000
        assumptions = DealAssumptions(
            deal_id=deal.id,
            purchase_price=price,
            closing_costs_pct=0.02,
            renovation_cost=round(price * 0.05, 2),
            loan_amount=round(price * 0.70, 2),
            interest_rate=0.065,
            loan_term_years=30,
            gross_rental_income=round(price * 0.09, 2),
            vacancy_pct=0.05,
            opex_pct=0.35,
            cap_rate_market=0.06,
            exit_cap_rate=0.065,
            hold_period_years=5,
            rent_growth_pct=0.03,
        )
        assumptions.organization_id = deal.organization_id
        db.add(assumptions)

    db.add(deal)
    db.commit()
    db.refresh(deal)
    return deal
