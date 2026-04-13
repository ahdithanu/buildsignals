from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.assumptions import AssumptionsResponse
from app.schemas.outputs import OutputsResponse


# ── Enums (mirror SQLAlchemy enums) ──────────────────────────────────────────

class DealStatus(str, Enum):
    new = "new"
    qualified = "qualified"
    underwriting = "underwriting"
    ic_review = "ic_review"
    loi_sent = "loi_sent"
    psa = "psa"
    closing = "closing"
    closed = "closed"
    dead = "dead"


class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


# ── Create ───────────────────────────────────────────────────────────────────

class DealCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    address: Optional[str] = Field(None, max_length=500)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=50)
    zip_code: Optional[str] = Field(None, max_length=20)
    property_type: Optional[str] = Field(None, max_length=100)
    units: Optional[int] = Field(None, ge=0)
    sq_ft: Optional[int] = Field(None, ge=0)
    year_built: Optional[int] = Field(None, ge=1800, le=2100)
    asking_price: Optional[float] = Field(None, ge=0)
    source: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = None


# ── Update (all optional) ───────────────────────────────────────────────────

class DealUpdate(BaseModel):
    """Partial update — status, score, and risk_level are system-managed.
    Use POST /deals/{id}/move-stage and POST /deals/{id}/score instead."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    address: Optional[str] = Field(None, max_length=500)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=50)
    zip_code: Optional[str] = Field(None, max_length=20)
    property_type: Optional[str] = Field(None, max_length=100)
    units: Optional[int] = Field(None, ge=0)
    sq_ft: Optional[int] = Field(None, ge=0)
    year_built: Optional[int] = Field(None, ge=1800, le=2100)
    asking_price: Optional[float] = Field(None, ge=0)
    source: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = None


# ── Response ─────────────────────────────────────────────────────────────────

class DealResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    property_type: Optional[str] = None
    units: Optional[int] = None
    sq_ft: Optional[int] = None
    year_built: Optional[int] = None
    asking_price: Optional[float] = None
    status: DealStatus
    risk_level: Optional[RiskLevel] = None
    score: Optional[float] = None
    source: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class DealDetailResponse(DealResponse):
    """Full deal with nested relations."""
    assumptions: Optional[AssumptionsResponse] = None
    outputs: Optional[OutputsResponse] = None
    contacts_count: int = 0
