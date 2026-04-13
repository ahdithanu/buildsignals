"""Underwriting engine: calculate and persist financial outputs from assumptions."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.deal_assumptions import DealAssumptions
from app.models.deal_outputs import DealOutputs


class UnderwritingError(Exception):
    """Raised when assumptions fail validation."""


def _validate(assumptions: DealAssumptions) -> None:
    """Raise UnderwritingError for obviously invalid inputs."""
    if assumptions.purchase_price is None or assumptions.purchase_price <= 0:
        raise UnderwritingError("purchase_price must be > 0")
    if assumptions.interest_rate is None or not (0 <= assumptions.interest_rate <= 1):
        raise UnderwritingError("interest_rate must be between 0 and 1")
    if assumptions.vacancy_pct is None or not (0 <= assumptions.vacancy_pct <= 1):
        raise UnderwritingError("vacancy_pct must be between 0 and 1")
    if assumptions.opex_pct is None or not (0 <= assumptions.opex_pct <= 1):
        raise UnderwritingError("opex_pct must be between 0 and 1")
    if assumptions.closing_costs_pct is None or not (0 <= assumptions.closing_costs_pct <= 1):
        raise UnderwritingError("closing_costs_pct must be between 0 and 1")
    if assumptions.exit_cap_rate is None or assumptions.exit_cap_rate <= 0:
        raise UnderwritingError("exit_cap_rate must be > 0")
    if assumptions.hold_period_years is None or assumptions.hold_period_years < 1:
        raise UnderwritingError("hold_period_years must be >= 1")
    if assumptions.loan_amount is None or assumptions.loan_amount < 0:
        raise UnderwritingError("loan_amount must be >= 0")
    if assumptions.gross_rental_income is None or assumptions.gross_rental_income < 0:
        raise UnderwritingError("gross_rental_income must be >= 0")
    if assumptions.loan_term_years is None or assumptions.loan_term_years < 1:
        raise UnderwritingError("loan_term_years must be >= 1")


def calculate(assumptions: DealAssumptions) -> dict:
    """Run the underwriting model and return the outputs dict.

    Does NOT persist — call ``calculate_and_persist`` for that.
    """
    _validate(assumptions)

    purchase_price: float = assumptions.purchase_price
    closing_costs_pct: float = assumptions.closing_costs_pct
    renovation_cost: float = assumptions.renovation_cost or 0.0
    loan_amount: float = assumptions.loan_amount
    interest_rate: float = assumptions.interest_rate
    loan_term_years: int = assumptions.loan_term_years
    gross_rental_income: float = assumptions.gross_rental_income
    vacancy_pct: float = assumptions.vacancy_pct
    opex_pct: float = assumptions.opex_pct
    exit_cap_rate: float = assumptions.exit_cap_rate
    hold_period_years: int = assumptions.hold_period_years
    rent_growth_pct: float = assumptions.rent_growth_pct or 0.0

    # ── Core calculations ────────────────────────────────────────────────────

    total_project_cost = purchase_price + (purchase_price * closing_costs_pct) + renovation_cost

    equity_required = total_project_cost - loan_amount

    # Annual debt service (standard amortisation formula)
    if loan_amount > 0 and interest_rate > 0:
        rate = interest_rate / 12
        n = loan_term_years * 12
        monthly_payment = loan_amount * (rate * (1 + rate) ** n) / ((1 + rate) ** n - 1)
        annual_debt_service = monthly_payment * 12
    elif loan_amount > 0 and interest_rate == 0:
        # Interest-free: simple straight-line
        annual_debt_service = loan_amount / loan_term_years
    else:
        annual_debt_service = 0.0

    effective_gross_income = gross_rental_income * (1 - vacancy_pct)
    noi = effective_gross_income * (1 - opex_pct)
    cap_rate = noi / purchase_price if purchase_price > 0 else 0.0

    net_cash_flow = noi - annual_debt_service

    dscr = noi / annual_debt_service if annual_debt_service > 0 else None

    cash_on_cash = net_cash_flow / equity_required if equity_required > 0 else None

    # Exit / return metrics
    future_noi = noi * (1 + rent_growth_pct) ** hold_period_years
    exit_value = future_noi / exit_cap_rate

    profit = exit_value - total_project_cost

    total_cash_flows = profit + (net_cash_flow * hold_period_years)
    equity_multiple = total_cash_flows / equity_required if equity_required > 0 else None

    # IRR approximation
    irr = None
    if equity_multiple is not None and equity_multiple > 0 and hold_period_years > 0:
        irr = (equity_multiple ** (1.0 / hold_period_years)) - 1

    return {
        "total_project_cost": round(total_project_cost, 2),
        "equity_required": round(equity_required, 2),
        "annual_debt_service": round(annual_debt_service, 2),
        "noi": round(noi, 2),
        "dscr": round(dscr, 4) if dscr is not None else None,
        "cap_rate": round(cap_rate, 6),
        "net_cash_flow": round(net_cash_flow, 2),
        "cash_on_cash": round(cash_on_cash, 6) if cash_on_cash is not None else None,
        "exit_value": round(exit_value, 2),
        "profit": round(profit, 2),
        "equity_multiple": round(equity_multiple, 4) if equity_multiple is not None else None,
        "irr": round(irr, 6) if irr is not None else None,
    }


def calculate_and_persist(db: Session, assumptions: DealAssumptions) -> DealOutputs:
    """Run underwriting and upsert the DealOutputs row.

    Returns the persisted DealOutputs instance.
    """
    results = calculate(assumptions)

    outputs = db.query(DealOutputs).filter_by(deal_id=assumptions.deal_id).first()
    if outputs is None:
        outputs = DealOutputs(deal_id=assumptions.deal_id)
        outputs.organization_id = assumptions.organization_id
        db.add(outputs)

    for key, value in results.items():
        setattr(outputs, key, value)

    db.commit()
    db.refresh(outputs)
    return outputs
