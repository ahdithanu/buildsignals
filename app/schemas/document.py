from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class DocumentCreate(BaseModel):
    filename: str = Field(..., min_length=1, max_length=500)
    doc_type: Optional[str] = Field(None, max_length=100)
    file_path: Optional[str] = Field(None, max_length=1000)
    size_bytes: Optional[int] = Field(None, ge=0)


class DocumentUpdate(BaseModel):
    filename: Optional[str] = Field(None, min_length=1, max_length=500)
    doc_type: Optional[str] = Field(None, max_length=100)
    file_path: Optional[str] = Field(None, max_length=1000)
    size_bytes: Optional[int] = Field(None, ge=0)


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    deal_id: str
    filename: str
    doc_type: Optional[str] = None
    file_path: Optional[str] = None
    size_bytes: Optional[int] = None
    uploaded_at: datetime
