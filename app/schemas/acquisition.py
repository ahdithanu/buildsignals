from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ParcelAcquisitionCaseUpdate(BaseModel):
    status: Optional[
        Literal["candidate", "shortlisted", "contacted", "dismissed", "promoted"]
    ] = None
    assigned_to_user_id: Optional[str] = Field(default=None, min_length=1)
    follow_up_at: Optional[datetime] = None


class ParcelAcquisitionActivityCreate(BaseModel):
    activity_type: Literal["call", "email", "sms", "meeting", "note"]
    notes: Optional[str] = Field(default=None, max_length=5000)
    occurred_at: Optional[datetime] = None
    follow_up_at: Optional[datetime] = None


class ParcelAcquisitionSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    candidate_id: str
    search_id: str
    created_at: datetime


class ParcelAcquisitionActivityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    activity_type: str
    notes: Optional[str]
    actor_user_id: Optional[str]
    occurred_at: datetime
    follow_up_at: Optional[datetime]
    created_at: datetime


class ParcelAcquisitionCaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    parcel_id: str
    status: str
    assigned_to_user_id: Optional[str]
    assigned_to_name: Optional[str]
    assigned_by_user_id: Optional[str]
    assigned_at: Optional[datetime]
    contacted_at: Optional[datetime]
    follow_up_at: Optional[datetime]
    promoted_deal_id: Optional[str]
    created_at: datetime
    updated_at: datetime
    sources: list[ParcelAcquisitionSourceResponse] = Field(default_factory=list)
    activities: list[ParcelAcquisitionActivityResponse] = Field(default_factory=list)
