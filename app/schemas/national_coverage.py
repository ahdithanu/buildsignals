from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, model_validator


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

    @model_validator(mode="after")
    def require_complete_state_matrix(self):
        # Keep the endpoint honest: a 50-state report cannot silently degrade
        # into a partial list while retaining a statewide label.
        from app.services.ingestion.catalog import US_STATE_CODES

        expected = set(US_STATE_CODES)
        actual = {row.state for row in self.states}
        if actual != expected or len(self.states) != len(expected):
            raise ValueError("National parcel coverage must include exactly one row for every US state")
        if self.summary.state_count != len(self.states):
            raise ValueError("National parcel coverage summary does not match the state matrix")

        posture_counts = {
            "measured": sum(row.posture == "measured" for row in self.states),
            "configured_only": sum(row.posture == "configured_only" for row in self.states),
            "candidate_only": sum(row.posture == "candidate_only" for row in self.states),
            "uncovered": sum(row.posture == "uncovered" for row in self.states),
        }
        expected_summary = {
            "measured_state_count": posture_counts["measured"],
            "configured_only_state_count": posture_counts["configured_only"],
            "candidate_only_state_count": posture_counts["candidate_only"],
            "uncovered_state_count": posture_counts["uncovered"],
            "states_with_nearby_candidates": sum(
                row.nearby_candidate_parcels > 0 for row in self.states
            ),
            "states_with_verified_available_parcels": sum(
                row.verified_available_parcels > 0 for row in self.states
            ),
            "stored_parcel_records": sum(row.stored_parcel_records for row in self.states),
            "geocoded_parcel_records": sum(row.geocoded_parcel_records for row in self.states),
            "nearby_candidate_parcels": sum(row.nearby_candidate_parcels for row in self.states),
            "verified_available_parcels": sum(row.verified_available_parcels for row in self.states),
            "nearby_verified_available_parcels": sum(
                row.nearby_verified_available_parcels for row in self.states
            ),
        }
        for field, expected_value in expected_summary.items():
            if getattr(self.summary, field) != expected_value:
                raise ValueError(f"National parcel coverage summary mismatch for {field}")

        target_states = [row.state for row in self.next_connector_targets]
        if len(target_states) != len(set(target_states)) or not set(target_states).issubset(actual):
            raise ValueError("National parcel coverage connector targets must be unique known states")
        return self
