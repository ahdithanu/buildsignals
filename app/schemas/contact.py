from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ContactStatus(str, Enum):
    not_contacted = "not_contacted"
    contacted = "contacted"
    responded = "responded"
    qualified = "qualified"
    dead = "dead"


class ContactCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    role: Optional[str] = Field(None, max_length=100)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    company: Optional[str] = Field(None, max_length=255)
    status: ContactStatus = ContactStatus.not_contacted
    notes: Optional[str] = Field(None, max_length=10000)


class ContactUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    role: Optional[str] = Field(None, max_length=100)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    company: Optional[str] = Field(None, max_length=255)
    status: Optional[ContactStatus] = None
    notes: Optional[str] = Field(None, max_length=10000)


class ContactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    deal_id: str
    name: str
    role: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    status: ContactStatus
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
