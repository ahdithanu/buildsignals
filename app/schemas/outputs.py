from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class OutputsCreate(BaseModel):
    noi: Optional[float] = None
    dscr: Optional[float] = None
    cash_on_cash: Optional[float] = None
    cap_rate: Optional[float] = None
    irr: Optional[float] = None
    equity_multiple: Optional[float] = None
    total_project_cost: Optional[float] = None
    equity_required: Optional[float] = None
    annual_debt_service: Optional[float] = None
    net_cash_flow: Optional[float] = None
    exit_value: Optional[float] = None
    profit: Optional[float] = None


class OutputsUpdate(BaseModel):
    noi: Optional[float] = None
    dscr: Optional[float] = None
    cash_on_cash: Optional[float] = None
    cap_rate: Optional[float] = None
    irr: Optional[float] = None
    equity_multiple: Optional[float] = None
    total_project_cost: Optional[float] = None
    equity_required: Optional[float] = None
    annual_debt_service: Optional[float] = None
    net_cash_flow: Optional[float] = None
    exit_value: Optional[float] = None
    profit: Optional[float] = None


class OutputsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    deal_id: str
    noi: Optional[float] = None
    dscr: Optional[float] = None
    cash_on_cash: Optional[float] = None
    cap_rate: Optional[float] = None
    irr: Optional[float] = None
    equity_multiple: Optional[float] = None
    total_project_cost: Optional[float] = None
    equity_required: Optional[float] = None
    annual_debt_service: Optional[float] = None
    net_cash_flow: Optional[float] = None
    exit_value: Optional[float] = None
    profit: Optional[float] = None
    created_at: datetime
    updated_at: datetime
