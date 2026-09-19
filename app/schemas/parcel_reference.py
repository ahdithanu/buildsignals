from datetime import datetime
from typing import Literal

from pydantic import BaseModel


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
