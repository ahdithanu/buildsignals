from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ActivityType(str, Enum):
    call = "call"
    email = "email"
    sms = "sms"
    note = "note"
    meeting = "meeting"
    system = "system"


class ActivityCreate(BaseModel):
    deal_id: str
    contact_id: Optional[str] = None
    activity_type: ActivityType
    subject: Optional[str] = Field(None, max_length=500)
    body: Optional[str] = None
    follow_up_date: Optional[datetime] = None
    completed: bool = False


class ActivityUpdate(BaseModel):
    contact_id: Optional[str] = None
    activity_type: Optional[ActivityType] = None
    subject: Optional[str] = Field(None, max_length=500)
    body: Optional[str] = None
    follow_up_date: Optional[datetime] = None
    completed: Optional[bool] = None


class ActivityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    deal_id: str
    contact_id: Optional[str] = None
    activity_type: ActivityType
    subject: Optional[str] = None
    body: Optional[str] = None
    follow_up_date: Optional[datetime] = None
    completed: bool
    created_at: datetime
