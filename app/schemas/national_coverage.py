from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class NationalParcelStateCoverage(BaseModel):
    state: str
    posture: Literal["measured", "configured_only", "candidate_only", "uncovered"]
    configured_source_count: int
    candidate_source_count: int
    measured_source_count: int
    stored_parcel_records: int
    geocoded_parcel_records: int
    recently_seen_parcel_records: int
    nearby_candidate_parcels: int
    verified_available_parcels: int
    nearby_verified_available_parcels: int
    candidate_status_counts: dict[str, int]
    next_action: str
    priority_score: int
    priority_reason: str


class NationalParcelCoverageSummary(BaseModel):
    state_count: int
    measured_state_count: int
    configured_only_state_count: int
    candidate_only_state_count: int
    uncovered_state_count: int
    states_with_nearby_candidates: int
    states_with_verified_available_parcels: int
    stored_parcel_records: int
    geocoded_parcel_records: int
    nearby_candidate_parcels: int
    verified_available_parcels: int
    nearby_verified_available_parcels: int


class NationalParcelCoverageResponse(BaseModel):
    measured_at: datetime
    record_type: Literal["parcel"]
    scope: str
    coverage_claim: str
    summary: NationalParcelCoverageSummary
    states: list[NationalParcelStateCoverage]
    next_connector_targets: list[NationalParcelStateCoverage]
    warnings: list[str]
