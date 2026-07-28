from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.schemas.deal import DealDetailResponse
from app.schemas.parcel import NearbyParcelSearchSummary


class BrandAliasDefinition(BaseModel):
    alias: str = Field(min_length=2, max_length=255)
    confidence: float = Field(default=1.0, ge=0, le=1)
    requires_context: bool = False
    minimum_field_matches: int = Field(default=1, ge=1, le=5)
    context_terms: list[str] = Field(default_factory=list)


class BrandDefinition(BaseModel):
    key: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=255)
    category: Optional[str] = Field(default=None, max_length=100)
    scale: Optional[str] = Field(default=None, max_length=50)
    priority: int = Field(default=3, ge=1, le=5)
    is_active: bool = True
    attributes: dict[str, Any] = Field(default_factory=dict)
    aliases: list[BrandAliasDefinition] = Field(min_length=1)


class BrandProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    key: str
    name: str
    category: Optional[str]
    scale: Optional[str]
    priority: int
    is_active: bool


class BrandPermitSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    is_active: bool = True
    application_number: Optional[str]
    permit_number: Optional[str]
    approval_stage: Optional[Literal["pre_approval", "approved"]]
    status: Optional[str]
    project_name: Optional[str]
    description: Optional[str]
    address: Optional[str]
    city: Optional[str]
    state: Optional[str]
    jurisdiction: Optional[str]
    permit_type: Optional[str]
    work_class: Optional[str]
    proposed_use: Optional[str]
    valuation: Optional[float]
    latitude: Optional[float]
    longitude: Optional[float]
    filed_at: Optional[datetime]
    source_url: Optional[str]


class LinkedDealSummary(BaseModel):
    id: str
    name: str


class PermitBrandMatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    permit_id: str
    review_status: Literal["candidate", "confirmed", "dismissed", "retracted"]
    confidence: float
    matched_alias: str
    matched_field: str
    matched_fields: list[str] = Field(default_factory=list)
    rule_ids: list[str] = Field(default_factory=list)
    excerpt: str
    detector_version: str
    first_seen_at: datetime
    last_seen_at: datetime
    brand: BrandProfileResponse
    permit: BrandPermitSummary
    linked_deals: list[LinkedDealSummary] = Field(default_factory=list)

    @computed_field
    @property
    def signal_quality(self) -> str:
        if self.matched_field == "project_name" and self.permit.permit_type == "Restaurant permit applicant":
            return "applicant_dba"
        if self.matched_field == "project_name":
            return "direct_project_name"
        if self.matched_field == "description":
            return "description_context"
        return "supporting_context"

    @computed_field
    @property
    def signal_quality_label(self) -> str:
        labels = {
            "applicant_dba": "Applicant DBA",
            "direct_project_name": "Direct project name",
            "description_context": "Description context",
            "supporting_context": "Supporting context",
        }
        return labels[self.signal_quality]

    @computed_field
    @property
    def signal_quality_note(self) -> str:
        notes = {
            "applicant_dba": "Brand appears as the applicant or establishment name before approval activity.",
            "direct_project_name": "Brand appears in the project or business name field.",
            "description_context": "Brand appears in work-description text and needs human review.",
            "supporting_context": "Brand appears in a supporting permit context field.",
        }
        return notes[self.signal_quality]


class PermitBrandMatchReview(BaseModel):
    review_status: Literal["confirmed", "dismissed", "candidate"]


class PermitBrandOpportunityCreate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)


class PermitBrandOpportunityResponse(BaseModel):
    match_id: str
    created: bool
    deal: DealDetailResponse
    nearby_parcel_search: Optional[NearbyParcelSearchSummary] = None
    nearby_parcel_searches: list[NearbyParcelSearchSummary] = Field(default_factory=list)


class BrandMatchRawEvidence(BaseModel):
    raw_record_id: str
    external_record_id: str
    content_hash: str
    received_at: datetime
    source_updated_at: Optional[datetime]
    source_key: str
    source_name: str
    source_url: Optional[str]
    payload_excerpt: dict[str, Any]

    @computed_field
    @property
    def received_age_hours(self) -> Optional[float]:
        return _age_hours(self.received_at)

    @computed_field
    @property
    def source_lag_hours(self) -> Optional[float]:
        return _age_hours(self.source_updated_at)


class BrandMatchGraphContext(BaseModel):
    class RelatedEntity(BaseModel):
        id: str
        entity_type: str
        display_name: str
        address: Optional[str] = None
        city: Optional[str] = None
        state: Optional[str] = None

    class EvidencePreview(BaseModel):
        source_system: str
        source_url: Optional[str] = None
        excerpt: Optional[str] = None

    relationship_id: str
    relationship_type: str
    source_entity_id: str
    source_entity_type: str
    source_entity_name: str
    target_entity_id: str
    target_entity_type: str
    target_entity_name: str
    review_status: Optional[str]
    is_current: bool
    confidence: float
    evidence_count: int
    valid_from: datetime
    valid_to: Optional[datetime]
    last_verified_at: datetime
    related_entity: RelatedEntity
    evidence_preview: Optional[EvidencePreview] = None


class PermitBrandMatchEvidenceResponse(BaseModel):
    id: str
    brand: BrandProfileResponse
    permit: BrandPermitSummary
    review_status: Literal["candidate", "confirmed", "dismissed", "retracted"]
    confidence: float
    matched_alias: str
    matched_field: str
    matched_fields: list[str] = Field(default_factory=list)
    excerpt: str
    signal_quality: str
    signal_quality_label: str
    signal_quality_note: str
    rule_ids: list[str] = Field(default_factory=list)
    detector_version: str
    first_seen_at: datetime
    last_seen_at: datetime
    linked_deals: list[LinkedDealSummary] = Field(default_factory=list)
    first_evidence: BrandMatchRawEvidence
    latest_evidence: BrandMatchRawEvidence
    graph_context: list[BrandMatchGraphContext] = Field(default_factory=list)


def _age_hours(value: Optional[datetime]) -> Optional[float]:
    if value is None:
        return None
    timestamp = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return round((datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)).total_seconds() / 3600, 2)
