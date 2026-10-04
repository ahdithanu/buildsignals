from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AcquisitionCriteria(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)

    version: Literal[1] = 1
    profile: Literal["small_multifamily", "small_bay_retail"]
    market_city: str = Field(min_length=1, max_length=100)
    market_state: str = Field(pattern="^[A-Z]{2}$")
    min_price: float = Field(gt=0)
    max_price: float = Field(gt=0)
    min_size: int = Field(gt=0, strict=True)
    max_size: int = Field(gt=0, strict=True)
    min_year_built: int = Field(ge=1000, le=9999, strict=True)

    @model_validator(mode="after")
    def ordered_ranges(self):
        if self.min_price > self.max_price or self.min_size > self.max_size:
            raise ValueError("Minimum criteria must not exceed maximum criteria")
        return self


class BuyBoxCreate(BaseModel):
    asset_type: Optional[str] = Field(None, max_length=100)
    locations: Optional[str] = Field(None, max_length=2000, description="Comma-separated locations (e.g. 'Austin TX, Dallas TX')")
    min_price: Optional[float] = Field(None, ge=0)
    max_price: Optional[float] = Field(None, ge=0)
    min_irr: Optional[float] = Field(None, ge=0, le=1, description="Minimum IRR as decimal (e.g. 0.12 = 12%)")
    deal_type: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = Field(None, max_length=10000)
    acquisition_criteria: Optional[AcquisitionCriteria] = None


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
    acquisition_criteria: Optional[AcquisitionCriteria] = None
    created_at: datetime
