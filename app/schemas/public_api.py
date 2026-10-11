"""Public API response contracts for integration-facing workflow exports."""

from datetime import datetime

from pydantic import BaseModel

from app.schemas.buildsignal import (
    BuildSignalReviewResponse,
    BuildSignalRevisionResponse,
    PublicationResponse,
)
from app.schemas.signal import SignalResponse


class PublicSignalWorkflowResponse(BaseModel):
    signal: SignalResponse
    assessment_revisions: list[BuildSignalRevisionResponse]
    reviews: list[BuildSignalReviewResponse]
    publication_events: list[PublicationResponse]


class PublicDealWorkflowHistoryResponse(BaseModel):
    deal_id: str
    generated_at: datetime
    signals: list[PublicSignalWorkflowResponse]

    @property
    def workflow_event_count(self) -> int:
        return sum(
            1
            + len(item.assessment_revisions)
            + len(item.reviews)
            + len(item.publication_events)
            for item in self.signals
        )


class PublicApiKeySelfResponse(BaseModel):
    id: str
    name: str
    key_prefix: str
    scopes: list[str]
    expires_at: datetime | None
    created_at: datetime
    last_used_at: datetime | None


class PublicApiRateLimitResponse(BaseModel):
    limit: int
    window_seconds: int


class PublicApiUsageEndpointResponse(BaseModel):
    path: str
    method: str
    total_calls: int
    total_items: int
    last_called_at: datetime | None


class PublicApiUsageDailyResponse(BaseModel):
    usage_date: str
    total_calls: int
    total_items: int
    average_latency_ms: int
    last_status_code: int | None = None


class PublicApiUsageResponse(BaseModel):
    total_calls: int
    total_items: int
    last_called_at: datetime | None
    endpoints: list[PublicApiUsageEndpointResponse]
    daily: list[PublicApiUsageDailyResponse]


class PublicApiSelfResponse(BaseModel):
    api_key: PublicApiKeySelfResponse
    rate_limit: PublicApiRateLimitResponse
    usage: PublicApiUsageResponse
