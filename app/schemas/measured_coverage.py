from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ObservedStateCoverage(BaseModel):
    state: str | None
    stored_records: int
    geocoded_records: int
    recently_seen_records: int
    unknown_source_date_records: int
    future_source_date_records: int
    recent_source_date_records: int
    newest_seen_at: datetime | None
    newest_source_date: datetime | None
    observed_jurisdiction_count: int
    min_latitude: float | None
    max_latitude: float | None
    min_longitude: float | None
    max_longitude: float | None


class MeasuredSourceCoverage(BaseModel):
    source_id: str
    source_key: str
    configured_active: bool
    configured_jurisdiction: str | None
    stored_records: int
    observed_states: list[ObservedStateCoverage]


class MeasuredCoverageTotals(BaseModel):
    source_count: int
    stored_records: int
    geocoded_records: int
    recently_seen_records: int
    unknown_source_date_records: int
    future_source_date_records: int
    recent_source_date_records: int
    observed_state_count: int
    observed_jurisdiction_count: int


class MeasuredCoverageReadiness(BaseModel):
    total_source_count: int
    active_source_count: int
    disabled_source_count: int
    sources_with_records: int
    empty_source_count: int
    sources_with_recent_collection: int
    sources_with_recent_source_date: int
    sources_with_unknown_source_dates: int
    sources_with_future_source_dates: int
    sources_with_geocoded_records: int
    stale_collection_source_count: int
    stale_source_date_source_count: int
    stored_records: int
    geocoded_records: int
    recently_seen_records: int
    recent_source_date_records: int
    observed_state_count: int
    observed_jurisdiction_count: int


class MeasuredCoverageStateRollup(BaseModel):
    state: str | None
    source_count: int
    stored_records: int
    geocoded_records: int
    recently_seen_records: int
    recent_source_date_records: int
    unknown_source_date_records: int


class MeasuredCoverageJurisdictionRollup(BaseModel):
    jurisdiction: str | None
    state: str | None
    source_count: int
    stored_records: int
    geocoded_records: int
    recently_seen_records: int
    recent_source_date_records: int


class MeasuredCoverageResponse(BaseModel):
    measured_at: datetime
    record_type: Literal["parcel", "permit", "planning"]
    scope: str
    count_semantics: str
    freshness_hours: int
    limit: int
    offset: int
    has_more: bool
    page_totals: MeasuredCoverageTotals
    readiness: MeasuredCoverageReadiness
    readiness_states: list[MeasuredCoverageStateRollup]
    readiness_jurisdictions: list[MeasuredCoverageJurisdictionRollup]
    sources: list[MeasuredSourceCoverage]
    warnings: list[str]
