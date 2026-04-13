from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class AssumptionsCreate(BaseModel):
    purchase_price: Optional[float] = Field(None, ge=0)
    closing_costs_pct: Optional[float] = Field(0.02, ge=0, le=1)
    renovation_cost: Optional[float] = Field(0.0, ge=0)
    loan_amount: Optional[float] = Field(None, ge=0)
    interest_rate: Optional[float] = Field(0.065, ge=0, le=1)
    loan_term_years: Optional[int] = Field(30, ge=1, le=50)
    gross_rental_income: Optional[float] = Field(None, ge=0)
    vacancy_pct: Optional[float] = Field(0.05, ge=0, le=1)
    opex_pct: Optional[float] = Field(0.35, ge=0, le=1)
    cap_rate_market: Optional[float] = Field(0.06, ge=0, le=1)
    exit_cap_rate: Optional[float] = Field(0.065, ge=0, le=1)
    hold_period_years: Optional[int] = Field(5, ge=1, le=30)
    rent_growth_pct: Optional[float] = Field(0.03, ge=-0.5, le=1)


class AssumptionsUpdate(BaseModel):
    purchase_price: Optional[float] = Field(None, ge=0)
    closing_costs_pct: Optional[float] = Field(None, ge=0, le=1)
    renovation_cost: Optional[float] = Field(None, ge=0)
    loan_amount: Optional[float] = Field(None, ge=0)
    interest_rate: Optional[float] = Field(None, ge=0, le=1)
    loan_term_years: Optional[int] = Field(None, ge=1, le=50)
    gross_rental_income: Optional[float] = Field(None, ge=0)
    vacancy_pct: Optional[float] = Field(None, ge=0, le=1)
    opex_pct: Optional[float] = Field(None, ge=0, le=1)
    cap_rate_market: Optional[float] = Field(None, ge=0, le=1)
    exit_cap_rate: Optional[float] = Field(None, ge=0, le=1)
    hold_period_years: Optional[int] = Field(None, ge=1, le=30)
    rent_growth_pct: Optional[float] = Field(None, ge=-0.5, le=1)


class AssumptionsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    deal_id: str
    purchase_price: Optional[float] = None
    closing_costs_pct: Optional[float] = None
    renovation_cost: Optional[float] = None
    loan_amount: Optional[float] = None
    interest_rate: Optional[float] = None
    loan_term_years: Optional[int] = None
    gross_rental_income: Optional[float] = None
    vacancy_pct: Optional[float] = None
    opex_pct: Optional[float] = None
    cap_rate_market: Optional[float] = None
    exit_cap_rate: Optional[float] = None
    hold_period_years: Optional[int] = None
    rent_growth_pct: Optional[float] = None
    created_at: datetime
    updated_at: datetime
