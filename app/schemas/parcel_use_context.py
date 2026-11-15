from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ParcelUseEvidence(BaseModel):
    fact_id: str
    kind: Literal["zoning", "land_use"]
    recorded_value: str = Field(min_length=1, max_length=255)
    source_url: str | None
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    observed_at: datetime
    last_verified_at: datetime


class ParcelUseContextResponse(BaseModel):
    parcel_id: str
    as_of: datetime
    method_version: Literal["parcel-use-context-v1"] = "parcel-use-context-v1"
    jurisdiction: str | None
    state: str | None
    status: Literal["missing", "reported", "conflicting", "incomplete"]
    recorded_zoning_code: str | None
    reported_zoning_codes: list[str] = Field(default_factory=list, max_length=50)
    recorded_land_uses: list[str] = Field(default_factory=list, max_length=51)
    evidence: list[ParcelUseEvidence] = Field(default_factory=list, max_length=50)
    gaps: list[str]
    potential_uses: list[str] = Field(default_factory=list, max_length=0)
    potential_uses_status: Literal["not_assessed"] = "not_assessed"
    ai_used: Literal[False] = False
