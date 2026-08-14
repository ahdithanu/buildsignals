from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.deal import DealDetailResponse


class NearbyParcelSearchCreate(BaseModel):
    anchor_brand_match_id: str
    radius_miles: float = Field(default=2.0, ge=0.25, le=5.0)
    persona: Literal["developer", "investor", "broker", "realtor"] = "developer"
    minimum_land_area_sq_ft: Optional[float] = Field(default=None, ge=0)
    zoning_codes: list[str] = Field(default_factory=list, max_length=50)
    land_uses: list[str] = Field(default_factory=list, max_length=50)
    limit: int = Field(default=50, ge=1, le=100)


class NearbyParcelCandidateReview(BaseModel):
    review_status: Literal["candidate", "shortlisted", "dismissed"]


class NearbyParcelCandidateAssignment(BaseModel):
    assigned_to_user_id: str = Field(..., min_length=1)


class NearbyParcelOpportunityCreate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)


class ParcelFactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    fact_type: str
    value: Any
    source_url: Optional[str]
    field_path: Optional[str]
    excerpt: Optional[str]
    confidence: float
    observed_at: datetime
    last_verified_at: datetime


class ParcelSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    external_parcel_id: str
    parcel_group_id: Optional[str]
    jurisdiction: Optional[str]
    county: Optional[str]
    state: Optional[str]
    address: Optional[str]
    city: Optional[str]
    postal_code: Optional[str]
    latitude: float
    longitude: float
    land_area_sq_ft: Optional[float]
    improvement_area_sq_ft: Optional[float]
    land_value: Optional[float]
    improvement_value: Optional[float]
    total_assessed_value: Optional[float]
    land_use: Optional[str]
    zoning_code: Optional[str]
    boundary_geometry: Optional[dict[str, Any]] = None
    last_verified_at: datetime


class NearbyParcelCandidateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    rank: int
    distance_miles: float
    score: float
    score_confidence: float
    explanation: dict[str, Any]
    review_status: str
    assigned_to_user_id: Optional[str] = None
    assigned_to_name: Optional[str] = None
    assigned_by_user_id: Optional[str] = None
    assigned_at: Optional[datetime] = None
    ranker_version: str
    parcel: ParcelSummaryResponse
    facts: list[ParcelFactResponse] = Field(default_factory=list)


class NearbyParcelSearchSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    deal_id: str
    anchor_brand_match_id: Optional[str]
    anchor_permit_id: str
    anchor_latitude: float
    anchor_longitude: float
    radius_miles: float
    persona: str
    filters: Optional[dict[str, Any]]
    result_limit: int
    as_of: datetime
    ranker_version: str
    created_at: datetime


class NearbyParcelSearchResponse(NearbyParcelSearchSummary):
    candidates: list[NearbyParcelCandidateResponse] = Field(default_factory=list)


class ParcelSearchHitResponse(BaseModel):
    search_id: str
    deal_id: str
    deal_name: Optional[str] = None
    persona: str
    radius_miles: float
    created_at: datetime
    rank: int
    distance_miles: float
    score: float
    score_confidence: float
    review_status: str


class ParcelDetailResponse(BaseModel):
    parcel: ParcelSummaryResponse
    facts: list[ParcelFactResponse] = Field(default_factory=list)
    search_count: int = 0
    search_hits: list[ParcelSearchHitResponse] = Field(default_factory=list)
    graph_entity: Optional[dict[str, Any]] = None
    graph_related: list[dict[str, Any]] = Field(default_factory=list)


class NearbyParcelOpportunityResponse(BaseModel):
    created: bool
    candidate_id: str
    deal: DealDetailResponse


class AcquisitionRadarSignalResponse(BaseModel):
    candidate_id: str
    search_id: str
    deal_id: str
    deal_name: str
    persona: str
    approval_stage: Optional[str] = None
    signal_confidence: Optional[float] = None
    distance_miles: float
    candidate_score: float
    created_at: datetime


class AcquisitionRadarItemResponse(BaseModel):
    parcel: ParcelSummaryResponse
    candidate_id: str
    radar_score: float
    best_candidate_score: float
    score_confidence: float
    appearance_count: int
    opportunity_count: int
    personas: list[str]
    review_status: str
    assigned_to_user_id: Optional[str] = None
    assigned_to_name: Optional[str] = None
    latest_signal_at: datetime
    reasons: list[str]
    cautions: list[str]
    signals: list[AcquisitionRadarSignalResponse]


class AcquisitionRadarSummaryResponse(BaseModel):
    total_parcels: int
    shortlisted_parcels: int
    multi_opportunity_parcels: int
    assigned_parcels: int
    state_count: int


class AcquisitionRadarResponse(BaseModel):
    items: list[AcquisitionRadarItemResponse]
    total: int
    limit: int
    offset: int
    summary: AcquisitionRadarSummaryResponse
