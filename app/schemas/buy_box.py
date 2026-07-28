from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class BuyBoxCreate(BaseModel):
    asset_type: Optional[str] = Field(None, max_length=100)
    locations: Optional[str] = Field(None, max_length=2000, description="Comma-separated locations (e.g. 'Austin TX, Dallas TX')")
    min_price: Optional[float] = Field(None, ge=0)
    max_price: Optional[float] = Field(None, ge=0)
    min_irr: Optional[float] = Field(None, ge=0, le=1, description="Minimum IRR as decimal (e.g. 0.12 = 12%)")
    deal_type: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = Field(None, max_length=10000)


class BuyBoxResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    user_id: Optional[str] = None
    asset_type: Optional[str] = None
    locations: Optional[str] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    min_irr: Optional[float] = None
    deal_type: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
