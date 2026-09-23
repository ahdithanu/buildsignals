"""Bounded, provider-neutral contracts for evidence regression evaluations."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

Workflow = Literal[
    "copilot_answer", "opportunity_memo", "multi_agent_research", "score_explanation"
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class Evidence(StrictModel):
    id: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=10000)
    source_url: str | None = Field(default=None, max_length=2000)


class Citation(StrictModel):
    source_id: str = Field(min_length=1, max_length=200)
    quote: str = Field(default="", max_length=2000)


class ExpectedOutput(StrictModel):
    required_phrases: list[str] = Field(default_factory=list, max_length=50)
    forbidden_phrases: list[str] = Field(default_factory=list, max_length=50)
    required_citation_ids: list[str] = Field(default_factory=list, max_length=50)
    expected_score: float | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def meaningful_rubric(self):
        if not (
            self.required_phrases or self.required_citation_ids or self.expected_score is not None
        ):
            raise ValueError(
                "At least one required phrase, citation, or expected score is required"
            )
        for values in (self.required_phrases, self.forbidden_phrases, self.required_citation_ids):
            if any(not value.strip() or len(value) > 1000 for value in values):
                raise ValueError("Rubric entries must be nonblank and at most 1000 characters")
        return self


class EvalOutput(StrictModel):
    text: str = Field(min_length=1, max_length=50000)
    citations: list[Citation] = Field(default_factory=list, max_length=100)
    score: float | None = Field(default=None, ge=0, le=100)
    tokens_input: int | None = Field(default=None, ge=0, le=10000000, strict=True)
    tokens_output: int | None = Field(default=None, ge=0, le=10000000, strict=True)
    cost_usd: float | None = Field(default=None, ge=0, le=100000)
    latency_ms: float | None = Field(default=None, ge=0, le=86400000)


class CaseCreate(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    input_json: dict[str, JsonValue] = Field(default_factory=dict)
    expected_output: ExpectedOutput
    retrieved_context: list[Evidence] = Field(default_factory=list, max_length=100)
    critical: bool = True

    @model_validator(mode="after")
    def bounded_context(self):
        # Read models add IDs/timestamps; the input budget must not change after saving.
        inputs = self.model_dump(mode="json", include=set(CaseCreate.model_fields))
        if len(json.dumps(inputs)) > 100000:
            raise ValueError("Each eval case must fit within 100 KB")
        ids = [item.id for item in self.retrieved_context]
        if len(set(ids)) != len(ids):
            raise ValueError("Evidence IDs must be unique within a case")
        return self


class DatasetCreate(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    workflow: Workflow
    cases: list[CaseCreate] = Field(min_length=1, max_length=25)


class Thresholds(StrictModel):
    minimum_quality: float = Field(default=0.8, ge=0, le=1)
    minimum_citation_accuracy: float = Field(default=1.0, ge=0, le=1)
    minimum_factual_coverage: float = Field(default=0.8, ge=0, le=1)
    maximum_hallucination_risk: float = Field(default=0.0, ge=0, le=1)


class RunCreate(StrictModel):
    mode: Literal["live", "replay"] = "live"
    model: str = Field(default="current", min_length=1, max_length=200)
    prompt_version: str = Field(default="current", min_length=1, max_length=200)
    thresholds: Thresholds = Field(default_factory=Thresholds)
    outputs: dict[str, EvalOutput] = Field(default_factory=dict, max_length=25)

    @model_validator(mode="after")
    def validate_mode(self):
        if self.mode == "live" and (
            self.outputs or self.model != "current" or self.prompt_version != "current"
        ):
            raise ValueError(
                "Live runs use the installed workflow and cannot accept supplied outputs or version overrides"
            )
        if self.mode == "replay" and (
            not self.outputs or self.model == "current" or self.prompt_version == "current"
        ):
            raise ValueError(
                "Replay requires captured outputs and explicit model and prompt version labels"
            )
        return self


class DatasetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    description: str
    workflow: Workflow
    created_at: datetime


class CaseRead(CaseCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    dataset_id: str
    created_at: datetime


class DatasetDetail(DatasetRead):
    cases: list[CaseRead]


class RunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    dataset_id: str
    mode: str
    model: str
    prompt_version: str
    status: str
    dataset_fingerprint: str
    thresholds: dict[str, float]
    summary: dict[str, JsonValue]
    gate_passed: bool
    started_at: datetime
    finished_at: datetime | None


class ResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    case_id: str
    case_snapshot: dict[str, JsonValue]
    actual_output: dict[str, JsonValue] | None
    retrieved_context: list[dict[str, JsonValue]]
    status: str
    error_code: str | None
    model: str
    prompt_version: str
    latency_ms: float | None
    tokens_input: int | None
    tokens_output: int | None
    cost_usd: float | None
    metrics: dict[str, float]


class RunDetail(RunRead):
    results: list[ResultRead]


class RunComparison(BaseModel):
    baseline_id: str
    candidate_id: str
    comparable: bool
    reasons: list[str]
    metric_deltas: dict[str, float]
    regressed_case_ids: list[str]
    candidate_gate_passed: bool
    baseline_gate_passed: bool
