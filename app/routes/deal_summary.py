from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.deal import Deal
from app.models.organization_membership import MemberRole
from app.utils.auth_deps import require_role
from app.utils.org_scope import active_query

router = APIRouter(tags=["deal-summary"])


def _fmt_price(val):
    if val is None:
        return "N/A"
    if val >= 1_000_000:
        return f"${val / 1_000_000:,.1f}M"
    return f"${val:,.0f}"


def _fmt_pct(val):
    if val is None:
        return "N/A"
    return f"{val * 100:.1f}%"


def _build_summary(deal: Deal) -> dict:
    """Build a plain-text deal summary optimized for email / copy-paste."""

    # Key metrics
    metrics = {}
    if deal.asking_price:
        metrics["Asking Price"] = _fmt_price(deal.asking_price)
    if deal.property_type:
        metrics["Property Type"] = deal.property_type
    if deal.units:
        metrics["Units"] = str(deal.units)
    if deal.sq_ft:
        metrics["Square Feet"] = f"{deal.sq_ft:,}"
    if deal.year_built:
        metrics["Year Built"] = str(deal.year_built)
    if deal.score is not None:
        metrics["Deal Score"] = f"{deal.score}/100"
    if deal.risk_level:
        metrics["Risk Level"] = deal.risk_level.value.title()

    # Underwriting metrics from outputs
    outputs = deal.outputs
    if outputs:
        if outputs.noi is not None:
            metrics["NOI"] = _fmt_price(outputs.noi)
        if outputs.cap_rate is not None:
            metrics["Cap Rate"] = _fmt_pct(outputs.cap_rate)
        if outputs.irr is not None:
            metrics["IRR"] = _fmt_pct(outputs.irr)
        if outputs.dscr is not None:
            metrics["DSCR"] = f"{outputs.dscr:.2f}x"
        if outputs.cash_on_cash is not None:
            metrics["Cash-on-Cash"] = _fmt_pct(outputs.cash_on_cash)
        if outputs.equity_multiple is not None:
            metrics["Equity Multiple"] = f"{outputs.equity_multiple:.2f}x"

    # Location
    location_parts = [p for p in [deal.address, deal.city, deal.state, deal.zip_code] if p]
    location = ", ".join(location_parts) if location_parts else "N/A"

    # Risks
    risks = []
    if deal.risk_level and deal.risk_level.value == "high":
        risks.append("High overall risk rating")
    if outputs and outputs.dscr is not None and outputs.dscr < 1.25:
        risks.append(f"DSCR below 1.25x ({outputs.dscr:.2f}x)")
    if outputs and outputs.irr is not None and outputs.irr < 0.08:
        risks.append(f"IRR below 8% ({_fmt_pct(outputs.irr)})")
    signals = deal.signals or []
    for sig in signals[:3]:
        if sig.severity and sig.severity >= 7.0:
            risks.append(f"{sig.signal_type}: {sig.description or 'High severity signal'}")
    if not risks:
        risks.append("No significant risk flags identified")

    # Upside
    upside = []
    if outputs and outputs.irr is not None and outputs.irr >= 0.15:
        upside.append(f"Strong projected IRR of {_fmt_pct(outputs.irr)}")
    if deal.score is not None and deal.score >= 80:
        upside.append(f"High deal score ({deal.score}/100)")
    if outputs and outputs.equity_multiple is not None and outputs.equity_multiple >= 2.0:
        upside.append(f"Attractive equity multiple ({outputs.equity_multiple:.2f}x)")
    if not upside:
        upside.append("Standard risk/return profile")

    # Overview
    overview = f"{deal.name} is a {deal.property_type or 'commercial'} property located at {location}."
    if deal.status:
        overview += f" Currently in {deal.status.value.replace('_', ' ')} stage."
    if deal.notes:
        overview += f" {deal.notes}"

    return {
        "title": deal.name,
        "location": location,
        "status": deal.status.value if deal.status else None,
        "overview": overview,
        "metrics": metrics,
        "risks": risks,
        "upside": upside,
    }


@router.get(
    "/deals/{deal_id}/summary",
    dependencies=[Depends(require_role(MemberRole.admin, MemberRole.editor, MemberRole.viewer))],
)
def get_deal_summary(deal_id: str, db: Session = Depends(get_db)):
    deal = active_query(db.query(Deal), Deal).filter(Deal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")
    return _build_summary(deal)
