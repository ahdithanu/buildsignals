"""Development Velocity v0 — a pure, unvalidated research signal over permit counts.

This layers on top of the descriptive counting contract in
``app/schemas/activity_baseline.py``. The baseline request is embedded verbatim so
the cohort, geography, window, and attribute validation cannot drift. Nothing here
is a validated or predictive output: the 0-100 score is a research output pending
the P2 evaluation gate and every numeric response carries ``score_is_validated``
set to ``False``.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.activity_baseline import ActivityBaselineRequest, ActivityWindow


class DevelopmentVelocityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Reused, embedded: pins cohort, geography, windows, attribute, and sample floor.
    baseline: ActivityBaselineRequest
    minimum_populated_baseline_windows: int = Field(default=3, ge=1, le=12)
    # v0 ships with seasonality off; only "off" is accepted (see design §3).
    seasonal_adjustment: Literal["off"] = "off"


class SourceVelocity(BaseModel):
    source_id: str
    methodology_version: str
    status: Literal[
        "calculated",
        "zero_baseline",
        "zero_variance_baseline",
        "abstained_insufficient_sample",
        "ambiguous_latest_observation",
        "needs_coverage_review",
    ]
    windows: list[ActivityWindow]
    baseline_mean: float
    baseline_std: float | None
    baseline_total: int
    populated_baseline_windows: int
    current: int
    delta: float | None
    percent_change: float | None
    z: float | None
    source_score: float | None
    evidence_fingerprint: str


class DevelopmentVelocitySignal(BaseModel):
    method_id: Literal["development-velocity-v0"] = "development-velocity-v0"
    schema_version: Literal["1"] = "1"
    request_fingerprint: str
    as_of: datetime
    city: str
    state: str
    attribute: str
    period_days: int
    baseline_periods: int
    reporting_lag_days: int
    status: Literal[
        "calculated",
        "abstained_insufficient_sample",
        "coverage_unverified",
        "bounded_query_exceeded",
    ]
    what_changed: str | None
    score: float | None = None
    score_is_validated: Literal[False] = False
    confidence: Literal["low", "medium", "high", "unassessed"]
    confidence_rationale: str
    seasonal_adjustment_applied: Literal[False] = False
    sources: list[SourceVelocity]
    cited_driver_observation_ids: list[str]
    invalidation_conditions: list[str]
    unavailable_fields: list[str]
    warnings: list[str]
