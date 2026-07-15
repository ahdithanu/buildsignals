from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class DealDistributionCreate(BaseModel):
    recipient_name: str = Field(..., min_length=1, max_length=255)
    recipient_email: str = Field(..., min_length=1, max_length=255)
    notes: Optional[str] = Field(None, max_length=5000)


class DealDistributionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    deal_id: str
    recipient_name: str
    recipient_email: str
    sent_at: datetime
    status: Optional[str] = None
    notes: Optional[str] = None
