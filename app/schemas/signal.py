from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class SignalCreate(BaseModel):
    deal_id: Optional[str] = None
    signal_type: str = Field(..., min_length=1, max_length=100)
    source: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    severity: Optional[float] = Field(None, ge=0, le=10)


class SignalUpdate(BaseModel):
    deal_id: Optional[str] = None
    signal_type: Optional[str] = Field(None, min_length=1, max_length=100)
    source: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    severity: Optional[float] = Field(None, ge=0, le=10)


class SignalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    deal_id: Optional[str] = None
    signal_type: str
    source: Optional[str] = None
    description: Optional[str] = None
    severity: Optional[float] = None
    created_at: datetime
