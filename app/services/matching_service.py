"""Simple deal-to-buy-box matching service.

Scores each buy box against a deal on four criteria:
  1. Asset type match (exact, normalized)
  2. Price range fit (asking_price within min/max)
  3. Location match (city/state overlap with buy box locations)
  4. IRR threshold (deal IRR >= buy box min_irr)

Each criterion is 0 or 1.  Total score = sum / applicable criteria.
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.buy_box import BuyBox
from app.models.deal import Deal
from app.utils.org_scope import scope_query


def _normalize(s: Optional[str]) -> str:
    return (s or "").strip().lower()


def _locations_list(locations: Optional[str]) -> List[str]:
    """Parse comma-separated locations into normalized tokens."""
    if not locations:
        return []
    return [_normalize(loc) for loc in locations.split(",") if loc.strip()]


def score_deal_vs_box(deal: Deal, box: BuyBox, deal_irr: Optional[float] = None) -> float:
    """Return a 0–100 match score for a deal against a single buy box."""
    points = 0.0
    criteria = 0

    # 1. Asset type match
    if box.asset_type:
        criteria += 1
        if _normalize(deal.property_type) == _normalize(box.asset_type):
            points += 1

    # 2. Price range
    if box.min_price is not None or box.max_price is not None:
        criteria += 1
        price = deal.asking_price
        if price is not None:
            above_min = price >= box.min_price if box.min_price is not None else True
            below_max = price <= box.max_price if box.max_price is not None else True
            if above_min and below_max:
                points += 1

    # 3. Location match
    box_locs = _locations_list(box.locations)
    if box_locs:
        criteria += 1
        deal_tokens = {_normalize(deal.city), _normalize(deal.state)}
        deal_combo = _normalize(f"{deal.city} {deal.state}")
        for loc in box_locs:
            if loc in deal_tokens or loc == deal_combo or loc in deal_combo:
                points += 1
                break

    # 4. IRR threshold
    if box.min_irr is not None:
        criteria += 1
        if deal_irr is not None and deal_irr >= box.min_irr:
            points += 1

    if criteria == 0:
        return 50.0  # no criteria → neutral score

    return round((points / criteria) * 100, 1)


def match_deal(db: Session, deal: Deal) -> List[dict]:
    """Return all org buy boxes ranked by match score against the given deal."""
    boxes = scope_query(db.query(BuyBox), BuyBox).all()

    # Get deal IRR from outputs if available
    deal_irr: Optional[float] = None
    if deal.outputs and deal.outputs.irr is not None:
        deal_irr = deal.outputs.irr

    results = []
    for box in boxes:
        score = score_deal_vs_box(deal, box, deal_irr)
        results.append({
            "buy_box_id": box.id,
            "asset_type": box.asset_type,
            "locations": box.locations,
            "min_price": box.min_price,
            "max_price": box.max_price,
            "min_irr": box.min_irr,
            "match_score": score,
        })

    results.sort(key=lambda r: r["match_score"], reverse=True)
    return results
