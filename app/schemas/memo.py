from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class MemoCreate(BaseModel):
    deal_id: str
    title: Optional[str] = Field(None, max_length=500)
    content: Optional[str] = None
    version: int = 1


class MemoUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=500)
    content: Optional[str] = None
    version: Optional[int] = None


class MemoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    deal_id: str
    title: Optional[str] = None
    content: Optional[str] = None
    version: int
    created_at: datetime
    updated_at: datetime
