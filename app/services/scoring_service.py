"""Score a deal 0-100 based on weighted factors and set its risk level."""

from sqlalchemy.orm import Session

from app.models.deal import Deal, RiskLevel


def evaluate_deal_score(deal: Deal) -> dict:
    """Compute the production scoring rubric without changing the deal."""

    breakdown: dict[str, dict] = {}

    # 1. has_asking_price (10 pts)
    has_price = deal.asking_price is not None and deal.asking_price > 0
    breakdown["has_asking_price"] = {"max": 10, "earned": 10 if has_price else 0}

    # 2. price_per_unit / price_per_sqft in reasonable range (20 pts)
    price_metric_pts = 0
    if has_price:
        if deal.units and deal.units > 0:
            ppu = deal.asking_price / deal.units
            # Reasonable per-unit: $30k – $500k
            if 30_000 <= ppu <= 500_000:
                price_metric_pts = 20
            elif 15_000 <= ppu <= 750_000:
                price_metric_pts = 10
        elif deal.sq_ft and deal.sq_ft > 0:
            ppsf = deal.asking_price / deal.sq_ft
            # Reasonable per-sqft: $50 – $600
            if 50 <= ppsf <= 600:
                price_metric_pts = 20
            elif 25 <= ppsf <= 1000:
                price_metric_pts = 10
    breakdown["price_per_unit_or_sqft"] = {"max": 20, "earned": price_metric_pts}

    # 3. has_contacts (10 pts)
    has_contacts = len(deal.contacts) > 0 if deal.contacts else False
    breakdown["has_contacts"] = {"max": 10, "earned": 10 if has_contacts else 0}

    # 4. has_assumptions (10 pts)
    has_assumptions = deal.assumptions is not None
    breakdown["has_assumptions"] = {"max": 10, "earned": 10 if has_assumptions else 0}

    # 5. noi_positive (15 pts)
    noi_positive = False
    if deal.outputs and deal.outputs.noi is not None:
        noi_positive = deal.outputs.noi > 0
    breakdown["noi_positive"] = {"max": 15, "earned": 15 if noi_positive else 0}

    # 6. dscr_above_1_2 (15 pts)
    dscr_ok = False
    if deal.outputs and deal.outputs.dscr is not None:
        dscr_ok = deal.outputs.dscr >= 1.2
    breakdown["dscr_above_1_2"] = {"max": 15, "earned": 15 if dscr_ok else 0}

    # 7. cap_rate_reasonable (10 pts — between 4% and 12%)
    cap_ok = False
    if deal.outputs and deal.outputs.cap_rate is not None:
        cap_ok = 0.04 <= deal.outputs.cap_rate <= 0.12
    breakdown["cap_rate_reasonable"] = {"max": 10, "earned": 10 if cap_ok else 0}

    # 8. year_built_after_1970 (10 pts)
    year_ok = deal.year_built is not None and deal.year_built >= 1970
    breakdown["year_built_after_1970"] = {"max": 10, "earned": 10 if year_ok else 0}

    # Total
    total = sum(v["earned"] for v in breakdown.values())

    # Risk level
    if total >= 70:
        risk = RiskLevel.low
    elif total >= 40:
        risk = RiskLevel.medium
    else:
        risk = RiskLevel.high

    return {
        "deal_id": deal.id,
        "score": total,
        "risk_level": risk.value,
        "breakdown": breakdown,
    }


def score_deal(db: Session, deal: Deal) -> dict:
    """Evaluate the deal and persist the result using the shared scoring rubric."""
    result = evaluate_deal_score(deal)
    deal.score = result["score"]
    deal.risk_level = RiskLevel(result["risk_level"])
    db.add(deal)
    db.commit()
    db.refresh(deal)

    return result
