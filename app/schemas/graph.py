from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.models.graph import GraphEntityType, GraphRelationshipType
from app.schemas.brand import PermitBrandMatchResponse


class GraphEvidenceCreate(BaseModel):
    source_system: str = Field(..., min_length=1, max_length=100)
    source_id: Optional[str] = Field(None, max_length=255)
    source_url: Optional[str] = Field(None, max_length=1000)
    evidence_type: Optional[str] = Field(None, max_length=100)
    excerpt: Optional[str] = None
    observed_at: Optional[datetime] = None
    confidence: float = Field(1.0, ge=0, le=1)
    payload: Optional[dict[str, Any]] = None


class GraphEntityCreate(BaseModel):
    entity_type: GraphEntityType
    display_name: str = Field(..., min_length=1, max_length=255)
    source_system: Optional[str] = Field(None, max_length=100)
    source_id: Optional[str] = Field(None, max_length=255)
    address: Optional[str] = Field(None, max_length=500)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=50)
    zip_code: Optional[str] = Field(None, max_length=20)
    confidence: float = Field(1.0, ge=0, le=1)
    attributes: Optional[dict[str, Any]] = None
    aliases: list[str] = Field(default_factory=list)


class GraphEntityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    entity_type: GraphEntityType
    display_name: str
    normalized_name: str
    normalized_address: Optional[str] = None
    source_system: Optional[str] = None
    source_id: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    confidence: float
    attributes: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
    last_verified_at: datetime


class GraphRelationshipCreate(BaseModel):
    source_entity_id: str
    target_entity_id: str
    relationship_type: GraphRelationshipType
    confidence: float = Field(1.0, ge=0, le=1)
    source_system: Optional[str] = Field(None, max_length=100)
    source_id: Optional[str] = Field(None, max_length=255)
    attributes: Optional[dict[str, Any]] = None
    evidence: list[GraphEvidenceCreate] = Field(..., min_length=1)


class GraphRelationshipVerify(BaseModel):
    evidence: list[GraphEvidenceCreate] = Field(..., min_length=1)
    confidence: Optional[float] = Field(None, ge=0, le=1)
    verification_interval_days: int = Field(90, ge=1, le=3650)
    reason: str = Field(..., min_length=3, max_length=500)


class GraphRelationshipEvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_system: str
    source_id: Optional[str] = None
    source_url: Optional[str] = None
    evidence_type: Optional[str] = None
    excerpt: Optional[str] = None
    observed_at: Optional[datetime] = None
    confidence: float
    payload: Optional[dict[str, Any]] = None
    created_at: datetime


class GraphRelationshipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_entity_id: str
    target_entity_id: str
    relationship_type: GraphRelationshipType
    confidence: float
    source_system: Optional[str] = None
    source_id: Optional[str] = None
    attributes: Optional[dict[str, Any]] = None
    is_current: bool
    valid_from: datetime
    valid_to: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    last_verified_at: datetime
    verification_due_at: datetime
    evidence: list[GraphRelationshipEvidenceResponse] = Field(default_factory=list)

    @computed_field
    @property
    def verification_status(self) -> Literal["fresh", "due", "stale", "historical"]:
        if not self.is_current:
            return "historical"
        now = datetime.now(timezone.utc)
        due_at = self.verification_due_at
        if due_at.tzinfo is None:
            due_at = due_at.replace(tzinfo=timezone.utc)
        if due_at <= now:
            return "stale"
        if due_at <= now + timedelta(days=14):
            return "due"
        return "fresh"


class GraphRelatedEntityResponse(BaseModel):
    entity: GraphEntityResponse
    relationship: GraphRelationshipResponse
    direction: str


class GraphRelationshipDetailResponse(BaseModel):
    relationship: GraphRelationshipResponse
    source_entity: GraphEntityResponse
    target_entity: GraphEntityResponse


class GraphRelationshipReviewQueueItem(GraphRelationshipDetailResponse):
    review_reasons: list[str] = Field(default_factory=list)


class GraphEntityDetailResponse(GraphEntityResponse):
    aliases: list[str] = Field(default_factory=list)
    source_identities: list["GraphEntitySourceIdentityResponse"] = Field(default_factory=list)
    links: list[dict[str, str]] = Field(default_factory=list)
    related: list[GraphRelatedEntityResponse] = Field(default_factory=list)


class GraphEntitySearchResponse(GraphEntityResponse):
    aliases: list[str] = Field(default_factory=list)


class GraphEntityMergeCandidateResponse(BaseModel):
    entity: GraphEntityResponse
    score: float
    reasons: list[str] = Field(default_factory=list)


class GraphEntitySourceIdentityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_system: str
    source_id: str
    confidence: float
    last_verified_at: datetime


class GraphEntityMergeCreate(BaseModel):
    duplicate_entity_id: str = Field(..., min_length=1, max_length=36)
    reason: str = Field(..., min_length=3, max_length=500)


class GraphEntityMergeResponse(BaseModel):
    merge_id: str
    merged_entity_id: str
    survivor: GraphEntityResponse
    aliases_moved: int
    source_identities_moved: int
    links_moved: int
    relationships_rewired: int
    relationships_collapsed: int
    evidence_moved: int
    created_at: datetime


class GraphPathResponse(BaseModel):
    entities: list[GraphEntityResponse]
    relationships: list[GraphRelationshipResponse]


class GraphBuyerLensSummary(BaseModel):
    persona: str
    search_count: int
    latest_radius_miles: float
    latest_created_at: datetime
    top_parcels: list["GraphParcelPreviewSummary"] = Field(default_factory=list)


class GraphParcelPreviewSummary(BaseModel):
    parcel_id: str
    external_parcel_id: str
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    distance_miles: float
    score: float
    rank: int


class GraphSharedParcelSummary(BaseModel):
    parcel_id: str
    external_parcel_id: str
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    best_distance_miles: float
    best_score: float
    best_persona: str
    personas: list[str] = Field(default_factory=list)
    lens_count: int


class OpportunityGraphContextResponse(BaseModel):
    opportunity_id: str
    root_entities: list[GraphEntityResponse]
    nearby_parcel_searches: int = 0
    buyer_lenses: list[GraphBuyerLensSummary] = Field(default_factory=list)
    shared_parcels: list[GraphSharedParcelSummary] = Field(default_factory=list)
    permit_brand_matches: list[PermitBrandMatchResponse] = Field(default_factory=list)
    companies: list[GraphRelatedEntityResponse] = Field(default_factory=list)
    developers: list[GraphRelatedEntityResponse] = Field(default_factory=list)
    parcels: list[GraphRelatedEntityResponse] = Field(default_factory=list)
    owners: list[GraphRelatedEntityResponse] = Field(default_factory=list)
    contractors: list[GraphRelatedEntityResponse] = Field(default_factory=list)
    architects: list[GraphRelatedEntityResponse] = Field(default_factory=list)
    engineers: list[GraphRelatedEntityResponse] = Field(default_factory=list)
    permits: list[GraphRelatedEntityResponse] = Field(default_factory=list)
    cities: list[GraphRelatedEntityResponse] = Field(default_factory=list)
    lenders: list[GraphRelatedEntityResponse] = Field(default_factory=list)
    brokers: list[GraphRelatedEntityResponse] = Field(default_factory=list)
    other: list[GraphRelatedEntityResponse] = Field(default_factory=list)
