from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.brand import BrandProfileResponse


class PlanningCompanyMatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    review_status: str
    confidence: float
    matched_alias: str
    matched_field: str
    excerpt: str
    detector_version: str
    first_seen_at: datetime
    last_seen_at: datetime
    brand: BrandProfileResponse


class PlanningRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_id: str
    external_record_id: str
    event_type: str
    stage: Optional[str]
    title: str
    summary: Optional[str]
    evidence_excerpt: Optional[str]
    agenda_item_number: Optional[str]
    meeting_name: Optional[str]
    governing_body: Optional[str]
    project_name: Optional[str]
    address: Optional[str]
    city: Optional[str]
    state: Optional[str]
    postal_code: Optional[str]
    parcel_id: Optional[str]
    jurisdiction: Optional[str]
    applicant_name: Optional[str]
    owner_name: Optional[str]
    developer_name: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    meeting_at: Optional[datetime]
    published_at: Optional[datetime]
    decision_at: Optional[datetime]
    source_url: Optional[str]
    signal_categories: list[str] = Field(default_factory=list)
    priority_reasons: list[str] = Field(default_factory=list)
    priority_score: float
    confidence: float
    first_seen_at: datetime
    last_seen_at: datetime
    company_matches: list[PlanningCompanyMatchResponse] = Field(default_factory=list)


class PlanningCompanyMatchReview(BaseModel):
    review_status: str = Field(pattern=r"^(candidate|confirmed|dismissed)$")
