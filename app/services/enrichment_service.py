"""Deal enrichment service.

Uses OpenRouter when configured and preserves the deterministic local
enrichment path as a no-key fallback for tests and development.
"""

from __future__ import annotations

import hashlib
from typing import Union

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.models.deal import Deal
from app.models.deal_assumptions import DealAssumptions
from app.services.llm_client import get_default_llm_client, is_openrouter_configured
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


class DealEnrichmentLLMOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    property_type: str | None = None
    units: int | None = None
    sq_ft: int | None = None
    year_built: int | None = None
    asking_price: float | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None


def _apply_default_enrichment(deal: Deal) -> None:
    """Fill missing fields with deterministic local values."""

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


def _deal_context(deal: Deal) -> str:
    return "\n".join(
        [
            f"name: {deal.name}",
            f"address: {deal.address or 'unknown'}",
            f"city: {deal.city or 'unknown'}",
            f"state: {deal.state or 'unknown'}",
            f"zip_code: {deal.zip_code or 'unknown'}",
            f"property_type: {deal.property_type or 'unknown'}",
            f"units: {deal.units if deal.units is not None else 'unknown'}",
            f"sq_ft: {deal.sq_ft if deal.sq_ft is not None else 'unknown'}",
            f"year_built: {deal.year_built if deal.year_built is not None else 'unknown'}",
            f"asking_price: {deal.asking_price if deal.asking_price is not None else 'unknown'}",
            f"source: {deal.source or 'unknown'}",
            f"notes: {deal.notes or 'none'}",
        ]
    )


def _apply_llm_enrichment(deal: Deal) -> None:
    if not is_openrouter_configured():
        _apply_default_enrichment(deal)
        return

    result = get_default_llm_client().chat_completion(
        messages=[
            {
                "role": "system",
                "content": (
                    "You enrich commercial real-estate deal records. Return only JSON with "
                    "these optional fields: property_type, units, sq_ft, year_built, "
                    "asking_price, address, city, state, zip_code. Use null when evidence "
                    "is missing. Do not invent a precise value when the context does not support it."
                ),
            },
            {
                "role": "user",
                "content": f"Enrich missing fields for this deal:\n{_deal_context(deal)}",
            },
        ],
        temperature=0.1,
        max_tokens=700,
        response_format={"type": "json_object"},
    )
    enriched = DealEnrichmentLLMOutput.model_validate_json(result.content)

    for field in (
        "property_type",
        "units",
        "sq_ft",
        "year_built",
        "asking_price",
        "address",
        "city",
        "state",
        "zip_code",
    ):
        if getattr(deal, field) is None and getattr(enriched, field) is not None:
            setattr(deal, field, getattr(enriched, field))

    deal.property_type = normalize_property_type(deal.property_type)


def _ensure_default_assumptions(db: Session, deal: Deal) -> None:
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


def enrich_deal(db: Session, deal: Deal) -> Deal:
    """Fill missing fields on *deal* and create default assumptions if none exist."""

    _apply_llm_enrichment(deal)
    # Keep the deterministic baseline as a completeness backstop. The LLM is
    # asked not to invent unsupported precision; old API consumers still expect
    # this endpoint to return a usable enriched record.
    _apply_default_enrichment(deal)
    _ensure_default_assumptions(db, deal)

    db.add(deal)
    db.commit()
    db.refresh(deal)
    return deal
