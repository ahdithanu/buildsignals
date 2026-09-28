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
