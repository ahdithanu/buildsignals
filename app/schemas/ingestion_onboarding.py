from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class IngestionOnboardingRequest(BaseModel):
    coverage_mode: Literal["nationwide", "selected_states"] = "nationwide"
    state_codes: list[str] = Field(default_factory=list, max_length=51)
    record_types: list[Literal["permit", "planning", "parcel"]] = Field(
        default_factory=lambda: ["permit", "planning", "parcel"],
        min_length=1,
        max_length=3,
    )
    rollout_waves: list[int] = Field(
        default_factory=lambda: [1, 2, 3, 4], min_length=1, max_length=4
    )
    shard_count: int = Field(default=4, ge=1, le=128)
    enabled: bool = True

    @model_validator(mode="after")
    def validate_coverage_scope(self):
        if self.coverage_mode == "nationwide" and self.state_codes:
            raise ValueError("state_codes must be empty for nationwide coverage")
        if self.coverage_mode == "selected_states" and not self.state_codes:
            raise ValueError("selected_states coverage requires at least one state")
        if len(self.record_types) != len(set(self.record_types)):
            raise ValueError("record_types must not contain duplicates")
        if len(self.rollout_waves) != len(set(self.rollout_waves)):
            raise ValueError("rollout_waves must not contain duplicates")
        if any(wave < 1 or wave > 4 for wave in self.rollout_waves):
            raise ValueError("rollout_waves must contain values between 1 and 4")
        return self


class OnboardingSourceItemResponse(BaseModel):
    source_key: str
    source_name: str
    region: str
    jurisdiction: Optional[str]
    record_type: str
    signal_stage: str
    rollout_wave: int
    shard_index: int
    schedule_mode: str
    interval_minutes: int
    max_pages_per_run: int


class OnboardingRegionCoverageResponse(BaseModel):
    region: str
    coverage_status: Literal["covered", "missing"]
    source_count: int
    permit_source_count: int
    planning_source_count: int
    parcel_source_count: int
    pre_approval_source_count: int
    approved_only_source_count: int


class IngestionOnboardingPlanResponse(BaseModel):
    coverage_mode: Literal["nationwide", "selected_states"]
    requested_regions: list[str]
    covered_regions: list[str]
    missing_regions: list[str]
    source_count: int
    permit_source_count: int
    planning_source_count: int
    parcel_source_count: int
    pre_approval_source_count: int
    approved_only_source_count: int
    automatic_source_count: int
    manual_source_count: int
    shard_count: int
    rollout_waves: list[int]
    regions: list[OnboardingRegionCoverageResponse]
    sources: list[OnboardingSourceItemResponse]


class IngestionEnrollmentSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    ingestion_source_id: Optional[str]
    source_key: str
    state_code: str
    record_type: str
    status: str
    cadence_minutes: int
    max_pages_per_run: int
    next_run_at: Optional[datetime]
    consecutive_failures: int
    last_dispatched_at: Optional[datetime]
    last_completed_at: Optional[datetime]
    last_error: Optional[str]
    created_at: datetime
    updated_at: datetime


class IngestionEnrollmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    organization_id: str
    enabled: bool
    coverage_mode: Literal["nationwide", "selected_states"]
    state_codes: Optional[list[str]]
    record_types: list[str]
    rollout_waves: list[int]
    shard_count: int
    catalog_manifest_digest: str
    last_catalog_sync_at: datetime
    last_dispatch_at: Optional[datetime]
    last_error: Optional[str]
    created_by: Optional[str]
    created_at: datetime
    updated_at: datetime
    sources: list[IngestionEnrollmentSourceResponse] = Field(default_factory=list)


class IngestionOnboardingActivationResponse(BaseModel):
    plan: IngestionOnboardingPlanResponse
    enrollment: IngestionEnrollmentResponse
    catalog_created: int
    catalog_updated: int
    catalog_unchanged: int
    enrollment_sources_created: int
    enrollment_sources_updated: int
    enrollment_sources_unchanged: int
    enrollment_sources_removed: int
    dry_run: bool
