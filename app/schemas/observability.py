"""Tenant-scoped operational summary contracts."""

from datetime import datetime

from pydantic import BaseModel


class WorkflowCounts(BaseModel):
    workflow: str
    runs: int
    gate_passed: int
    failed: int


class DailyCounts(BaseModel):
    date: str
    runs: int
    case_errors: int


class EvaluationCounts(BaseModel):
    runs: int
    completed: int
    failed: int
    running: int
    gates_passed: int
    live_runs: int
    replay_runs: int
    results: int
    case_errors: int
    cost_usd_known: float | None
    cost_reported_results: int
    cost_unknown_results: int
    tokens_input_known: int | None
    tokens_output_known: int | None
    tokens_reported_results: int
    tokens_unknown_results: int
    input_tokens_reported_results: int
    input_tokens_unknown_results: int
    output_tokens_reported_results: int
    output_tokens_unknown_results: int
    avg_latency_ms_known: float | None
    latency_reported_results: int
    latency_unknown_results: int
    by_workflow: list[WorkflowCounts]
    daily: list[DailyCounts]


class IngestionCounts(BaseModel):
    runs: int
    completed: int
    failed: int
    partial: int
    partial_with_errors: int
    running: int
    records_seen: int
    records_failed: int
    stalled_runs: int


class AttentionItem(BaseModel):
    code: str
    level: str
    summary: str
    count: int
    href: str


class ObservabilityOverview(BaseModel):
    generated_at: datetime
    window_start: datetime
    window_end: datetime
    days: int
    evaluations: EvaluationCounts
    ingestion: IngestionCounts
    attention: list[AttentionItem]
