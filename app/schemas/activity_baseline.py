"""Explicit, version-pinned cohorts for descriptive permit activity baselines."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.schemas.temporal import NonblankKey, RecordId, UtcCutoff


class SourceCohort(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: RecordId
    methodology_version: NonblankKey


class ActivityBaselineRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of: UtcCutoff
    sources: list[SourceCohort] = Field(min_length=1, max_length=10)
    city: NonblankKey
    state: Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Z]{2}$")]
    attribute: Literal["permit.filed_at", "permit.issued_at"] = "permit.filed_at"
    period_days: int = Field(default=30, ge=7, le=90)
    baseline_periods: int = Field(default=6, ge=3, le=12)
    reporting_lag_days: int = Field(default=7, ge=0, le=60)
    minimum_baseline_records: int = Field(default=20, ge=1, le=1000)

    @model_validator(mode="after")
    def unique_sources(self):
        if len({source.source_id for source in self.sources}) != len(self.sources):
            raise ValueError("Pin exactly one methodology version per source")
        return self


class ActivityWindow(BaseModel):
    start: datetime
    end: datetime
    role: Literal["baseline", "current"]
    observed_records: int
    evidence_observation_ids: list[str]


class SourceBaseline(BaseModel):
    source_id: str
    methodology_version: str
    status: Literal["needs_coverage_review", "insufficient_observed_sample", "ambiguous_latest_observation"]
    windows: list[ActivityWindow]
    baseline_mean_observed_records: float
    diagnostics: dict[str, int]
    evidence_fingerprint: str


class ActivityBaselineResponse(BaseModel):
    methodology_version: str
    request_fingerprint: str
    as_of: datetime
    city: str
    state: str
    attribute: str
    status: Literal["coverage_unverified", "bounded_query_exceeded"]
    sources: list[SourceBaseline]
    score: None = None
    warnings: list[str]
