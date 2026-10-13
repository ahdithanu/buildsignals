"""Tenant-scoped operational summary contracts."""

from datetime import datetime
from enum import IntEnum
from typing import Literal

from pydantic import BaseModel

ReadinessStatus = Literal["pass", "warning", "fail"]
DatabaseProvider = Literal["postgres", "sqlite"]


class ObservabilityWindow(IntEnum):
    day = 1
    week = 7
    month = 30


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


class WebhookCounts(BaseModel):
    deliveries: int
    pending: int
    delivered: int
    failed: int
    due_now: int
    scheduled: int
    exhausted: int
    active_leases: int
    subscriptions_active: int
    subscriptions_disabled: int
    failure_rate: float


class AttentionItem(BaseModel):
    code: str
    level: Literal["critical", "warning"]
    summary: str
    count: int
    href: str


class DeploymentReadinessCheck(BaseModel):
    code: str
    label: str
    status: ReadinessStatus
    summary: str
    action: str | None = None


class DeploymentReadiness(BaseModel):
    environment: str
    database_provider: DatabaseProvider
    overall_status: ReadinessStatus
    pass_count: int
    warning_count: int
    fail_count: int
    checks: list[DeploymentReadinessCheck]


class ObservabilityOverview(BaseModel):
    generated_at: datetime
    window_start: datetime
    window_end: datetime
    days: ObservabilityWindow
    evaluations: EvaluationCounts
    ingestion: IngestionCounts
    webhooks: WebhookCounts
    deployment: DeploymentReadiness
    attention: list[AttentionItem]
