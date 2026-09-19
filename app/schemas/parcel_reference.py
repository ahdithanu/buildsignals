from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ParcelReferenceCandidate(BaseModel):
    parcel_id: str
    external_parcel_id: str
    reference_kind: Literal["external_id", "parcel_group"]
    state_matches: bool
    address_matches: bool
    state_comparison: Literal["match", "missing", "conflict"]
    city_comparison: Literal["match", "missing", "conflict"]
    street_comparison: Literal["match", "missing", "conflict"]
    address_comparison: Literal["match", "missing", "conflict"]
    identity_assessment: Literal["address_corroborated", "needs_review"]
    has_valid_coordinates: bool
    raw_source_record_id: str
    captured_at: datetime
    source_updated_at: datetime | None
    last_verified_at: datetime


class PermitParcelCandidates(BaseModel):
    permit_id: str
    permit_raw_source_record_id: str
    permit_parcel_reference: str | None
    parcel_source_id: str
    status: Literal["no_match", "missing_reference", "ambiguous", "candidate_requires_review"]
    method: str
    candidates: list[ParcelReferenceCandidate]
    truncated: bool
    limitations: list[str]


class ParcelReferenceAuditItem(BaseModel):
    category: Literal["missing_reference", "no_match", "ambiguous", "address_corroborated",
                      "conflicting_address", "missing_address_evidence"]
    result: PermitParcelCandidates


class ParcelReferenceAudit(BaseModel):
    permit_source_id: str
    parcel_source_id: str
    measured_at: datetime
    status: Literal["measured_page", "parcel_evidence_unavailable"]
    counts: dict[str, int]
    evaluated_permits: int
    limit: int
    after_id: str | None
    next_after_id: str | None
    has_more: bool
    items: list[ParcelReferenceAuditItem]
    coverage_verified: Literal[False]
    limitations: list[str]


class ParcelReferenceAcceptance(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    parcel_source_id: str = Field(min_length=1, max_length=36)
    parcel_id: str = Field(min_length=1, max_length=36)
    expected_permit_raw_id: str = Field(min_length=1, max_length=36)
    expected_parcel_raw_id: str = Field(min_length=1, max_length=36)
    reason: str = Field(min_length=10, max_length=1000)
    confidence: float = Field(ge=0, le=1)
