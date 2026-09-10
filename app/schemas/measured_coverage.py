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


class MeasuredCoverageResponse(BaseModel):
    measured_at: datetime
    record_type: Literal["parcel", "permit", "planning"]
    scope: str
    count_semantics: str
    freshness_hours: int
    limit: int
    offset: int
    has_more: bool
    sources: list[MeasuredSourceCoverage]
    warnings: list[str]
