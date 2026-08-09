from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.brand import PermitBrandMatchResponse
from app.schemas.graph import GraphEntityDetailResponse, GraphRelatedEntityResponse


class FieldMappingCreate(BaseModel):
    source_field: str = Field(min_length=1, max_length=255)
    canonical_field: str = Field(min_length=1, max_length=255)
    value_semantics: Literal["unknown", "business_dba", "legal_entity", "person"] = "unknown"
    transform: Optional[str] = Field(default=None, max_length=100)
    transform_options: Optional[dict[str, Any]] = None
    default_value: Optional[dict[str, Any]] = None
    is_required: bool = False
    is_active: bool = True


class FieldMappingResponse(FieldMappingCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_id: str
    created_at: datetime
    updated_at: datetime


class IngestionSourceCreate(BaseModel):
    key: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=255)
    adapter: str = Field(min_length=1, max_length=100)
    record_type: str = Field(default="permit", min_length=1, max_length=100)
    jurisdiction: Optional[str] = Field(default=None, max_length=255)
    base_url: Optional[str] = Field(default=None, max_length=1000)
    settings: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    field_mappings: list[FieldMappingCreate] = Field(default_factory=list)

    @model_validator(mode="after")
    def reject_embedded_secrets(self):
        _reject_secrets(self.settings)
        return self


class IngestionSourceUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    jurisdiction: Optional[str] = Field(default=None, max_length=255)
    base_url: Optional[str] = Field(default=None, max_length=1000)
    settings: Optional[dict[str, Any]] = None
    is_active: Optional[bool] = None
    field_mappings: Optional[list[FieldMappingCreate]] = None

    @model_validator(mode="after")
    def reject_embedded_secrets(self):
        if self.settings is not None:
            _reject_secrets(self.settings)
        return self


class IngestionSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    key: str
    name: str
    adapter: str
    record_type: str
    jurisdiction: Optional[str]
    base_url: Optional[str]
    settings: Optional[dict[str, Any]]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    field_mappings: list[FieldMappingResponse] = Field(default_factory=list)


class IngestionRunRequest(BaseModel):
    max_pages: int = Field(default=1, ge=1, le=100)
    checkpoint: Optional[dict[str, Any]] = None


class SourceCanaryRequest(BaseModel):
    sample_size: int = Field(default=10, ge=1, le=100)


class SourceCanaryResponse(BaseModel):
    source_id: str
    source_key: str
    ok: bool
    records_fetched: int
    records_valid: int
    records_failed: int
    approval_stages: dict[str, int]
    sample_record_ids: list[str]
    next_checkpoint: Optional[dict[str, Any]]
    errors: list[str]


class SourceHealthResponse(BaseModel):
    source_id: str
    source_key: str
    source_name: str
    jurisdiction: Optional[str]
    license: Optional[str]
    signal_stage: Optional[str]
    official_landing_page: Optional[str] = None
    attribution_required: bool
    share_alike_review_required: bool
    status: Literal["healthy", "degraded", "critical", "unknown"]
    active_run_id: Optional[str]
    active_heartbeat_at: Optional[datetime]
    heartbeat_age_seconds: Optional[float]
    active_run_stale: bool
    last_run_at: Optional[datetime]
    last_success_at: Optional[datetime]
    ingestion_age_hours: Optional[float]
    source_watermark_at: Optional[datetime]
    source_lag_hours: Optional[float]
    freshness_sla_hours: float = 36.0
    freshness_sla_configured: bool = False
    freshness_semantics: Literal[
        "record_updated_at",
        "dataset_refreshed_at",
        "filing_event_at",
        "ingestion_observed_at",
        "unclassified_source_timestamp",
    ] = "ingestion_observed_at"
    freshness_label: str = "Collection observed"
    source_watermark_enforced: bool = False
    terminal_runs: int
    unhealthy_runs: int
    run_failure_rate: Optional[float]
    records_seen: int
    records_failed: int
    record_failure_rate: Optional[float]
    cursor: Optional[dict[str, Any]]
    cursor_updated_at: Optional[datetime]
    cursor_stalled: bool
    reasons: list[str]


class IngestionCandidateResponse(BaseModel):
    key: str
    name: str
    adapter: str
    record_type: Literal["permit", "parcel"]
    jurisdiction: str
    base_url: str
    official_landing_page: str
    license: str
    status: Literal[
        "operational_retry",
        "legal_hold",
        "technical_hold",
        "freshness_hold",
        "lifecycle_hold",
        "queued",
    ]
    blocker_summary: str
    early_warning_value: str
    candidate_source_fields: list[str]
    production_page_size: Optional[int] = None
    can_run_canary: bool = False
    last_canary_at: Optional[datetime] = None
    last_canary_ok: Optional[bool] = None
    last_canary_records_valid: Optional[int] = None
    last_canary_records_failed: Optional[int] = None
    last_checked_on: date
    next_audit_on: date
    notes: str


class ReliabilityWatchlistItemResponse(BaseModel):
    source_id: str
    source_name: str
    jurisdiction: Optional[str] = None
    status: str
    active_run_stale: bool
    cursor_stalled: bool
    reasons: list[str]


class IngestionReliabilitySummaryResponse(BaseModel):
    healthy_sources: int
    attention_sources: int
    critical_sources: int
    stale_runs: int
    stalled_cursors: int
    failed_retry_canaries: int
    watchlist_sources: list[ReliabilityWatchlistItemResponse]


class CandidateCanaryResponse(BaseModel):
    candidate_key: str
    candidate_name: str
    ok: bool
    records_fetched: int
    records_valid: int
    records_failed: int
    approval_stages: dict[str, int]
    sample_record_ids: list[str]
    next_checkpoint: Optional[dict[str, Any]]
    errors: list[str]


class CandidateCanaryAttemptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    candidate_key: str
    candidate_name: str
    sample_size: int
    ok: bool
    records_fetched: int
    records_valid: int
    records_failed: int
    approval_stages: dict[str, int]
    sample_record_ids: list[str]
    next_checkpoint: Optional[dict[str, Any]]
    errors: list[str]
    created_at: datetime


class CoverageJurisdictionBucket(BaseModel):
    jurisdiction: str
    live_sources: int
    candidate_sources: int


class StateCoverageBucket(BaseModel):
    state: str
    live_sources: int
    candidate_sources: int
    retailer_opening_sources: int
    pre_approval_sources: int
    approved_only_sources: int
    priority_score: int
    priority_reasons: list[str]


class StateRolloutItem(BaseModel):
    state: str
    rollout_cluster: int
    rollout_label: str
    coverage_status: str
    live_sources: int
    candidate_sources: int
    jurisdiction_count: int
    priority_score: int
    next_action: str
    next_action_label: str


class RetailerOpeningCoverageSourceResponse(BaseModel):
    source_key: str
    source_name: str
    jurisdiction: Optional[str] = None
    signal_stage: Optional[str] = None
    official_landing_page: Optional[str] = None


class ApprovedOnlyCoverageSourceResponse(BaseModel):
    source_key: str
    source_name: str
    jurisdiction: Optional[str] = None
    signal_stage: Optional[str] = None
    official_landing_page: Optional[str] = None


class IngestionCoverageResponse(BaseModel):
    live_source_count: int
    candidate_count: int
    jurisdiction_count: int
    retailer_opening_source_count: int
    retailer_opening_sources: list[RetailerOpeningCoverageSourceResponse]
    approved_only_sources: list[ApprovedOnlyCoverageSourceResponse]
    pre_approval_source_count: int
    approved_only_source_count: int
    live_signal_stage_counts: dict[str, int]
    live_signal_sources_by_stage: dict[str, list[RetailerOpeningCoverageSourceResponse]]
    candidate_status_counts: dict[str, int]
    top_jurisdictions: list[CoverageJurisdictionBucket]
    state_buckets: list[StateCoverageBucket]
    activation_queue: list[StateCoverageBucket]
    rollout_queue: list[StateRolloutItem]
    candidate_only_state_count: int
    candidate_only_states: list[str]
    covered_state_count: int
    missing_state_count: int
    covered_states: list[str]
    missing_states: list[str]


class IngestionRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_id: str
    status: str
    trigger: str
    started_at: datetime
    heartbeat_at: datetime
    completed_at: Optional[datetime]
    checkpoint: Optional[dict[str, Any]]
    parameters: Optional[dict[str, Any]]
    records_seen: int
    records_inserted: int
    records_updated: int
    records_failed: int
    error_message: Optional[str]
    created_at: datetime


class PermitEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    permit_id: str
    raw_source_record_id: str
    source_event_id: str
    event_type: str
    status: Optional[str] = None
    approval_stage: Optional[Literal["pre_approval", "approved"]] = None
    occurred_at: datetime
    description: Optional[str] = None
    attributes: Optional[dict[str, Any]] = None
    created_at: datetime


class PermitRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_id: str
    external_record_id: str
    application_number: Optional[str]
    permit_number: Optional[str]
    approval_stage: Optional[Literal["pre_approval", "approved"]]
    permit_type: Optional[str]
    permit_subtype: Optional[str]
    work_class: Optional[str]
    review_type: Optional[str]
    proposed_use: Optional[str]
    occupancy_type: Optional[str]
    status: Optional[str]
    description: Optional[str]
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
    contractor_name: Optional[str]
    contractor_license: Optional[str]
    architect_name: Optional[str]
    engineer_name: Optional[str]
    valuation: Optional[Decimal]
    square_feet: Optional[int]
    units: Optional[int]
    latitude: Optional[float]
    longitude: Optional[float]
    filed_at: Optional[datetime]
    status_updated_at: Optional[datetime]
    approved_at: Optional[datetime]
    issued_at: Optional[datetime]
    expires_at: Optional[datetime]
    completed_at: Optional[datetime]
    source_url: Optional[str]
    is_active: bool
    retired_at: Optional[datetime]
    first_seen_at: datetime
    last_seen_at: datetime


class PermitDetailResponse(BaseModel):
    permit: PermitRecordResponse
    source_key: str
    source_name: str
    source_landing_page: Optional[str] = None
    events: list[PermitEventResponse] = Field(default_factory=list)
    brand_matches: list["PermitBrandMatchResponse"] = Field(default_factory=list)
    graph_entity: Optional["GraphEntityDetailResponse"] = None
    graph_related: list["GraphRelatedEntityResponse"] = Field(default_factory=list)


def _reject_secrets(value: Any, path: str = "settings") -> None:
    if not isinstance(value, dict):
        return
    forbidden = {"token", "app_token", "api_key", "password", "secret", "authorization"}
    for key, child in value.items():
        lowered = str(key).lower()
        if lowered in forbidden or any(lowered.endswith(f"_{suffix}") for suffix in forbidden):
            if not lowered.endswith("_env"):
                raise ValueError(f"Store secret references as environment variable names, not {path}.{key}")
        _reject_secrets(child, f"{path}.{key}")
