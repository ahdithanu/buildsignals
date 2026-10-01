from datetime import datetime
from typing import Literal

from pydantic import AnyUrl, BaseModel, ConfigDict, Field, field_validator

WEBHOOK_EVENT_TYPES = {
    "deal.created",
    "deal.updated",
    "signal.created",
    "assessment.revision.created",
    "assessment.review.created",
    "assessment.publication.created",
    "eval.run.completed",
    "eval.run.failed",
}

WebhookStatus = Literal["active", "disabled"]
WebhookDeliveryStatus = Literal["pending", "delivered", "failed"]


def normalize_event_types(value: list[str]) -> list[str]:
    normalized = sorted({item.strip().lower() for item in value if item.strip()})
    if not normalized:
        raise ValueError("At least one event type is required")
    unknown = set(normalized) - WEBHOOK_EVENT_TYPES
    if unknown:
        raise ValueError(f"Unsupported webhook event type(s): {', '.join(sorted(unknown))}")
    return normalized


class WebhookSubscriptionCreate(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    target_url: AnyUrl
    event_types: list[str] = Field(min_length=1, max_length=50)
    secret_reference: str | None = Field(default=None, max_length=255)

    @field_validator("event_types")
    @classmethod
    def validate_event_types(cls, value: list[str]) -> list[str]:
        return normalize_event_types(value)

    @field_validator("secret_reference")
    @classmethod
    def validate_secret_reference(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        if cleaned.startswith(("http://", "https://")):
            raise ValueError("Store webhook signing material as a secret reference, not a URL or raw value")
        return cleaned


class WebhookSubscriptionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=120)
    target_url: AnyUrl | None = None
    event_types: list[str] | None = Field(default=None, min_length=1, max_length=50)
    status: WebhookStatus | None = None
    secret_reference: str | None = Field(default=None, max_length=255)

    @field_validator("event_types")
    @classmethod
    def validate_event_types(cls, value: list[str] | None) -> list[str] | None:
        return normalize_event_types(value) if value is not None else None

    @field_validator("secret_reference")
    @classmethod
    def validate_secret_reference(cls, value: str | None) -> str | None:
        return WebhookSubscriptionCreate.validate_secret_reference(value)


class WebhookSubscriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    name: str
    target_url: str
    event_types: list[str]
    status: WebhookStatus
    secret_reference: str | None
    created_by: str | None
    created_at: datetime
    updated_at: datetime
    disabled_at: datetime | None


class WebhookDeliveryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    subscription_id: str
    event_type: str
    event_id: str
    payload: dict
    status: WebhookDeliveryStatus
    attempt_count: int
    next_attempt_at: datetime | None
    last_attempted_at: datetime | None
    response_status_code: int | None
    response_body_excerpt: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class WebhookDeliverySummaryResponse(BaseModel):
    organization_id: str
    total: int
    pending: int
    delivered: int
    failed: int
    dead_lettered: int
    subscriptions_active: int
    subscriptions_disabled: int
    failure_rate: float
    latest_attempted_at: datetime | None
    latest_created_at: datetime | None
    last_error_message: str | None


class WebhookDeadLetterAcknowledgeRequest(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class WebhookTestEventRequest(BaseModel):
    event_type: str = Field(default="deal.created")
    event_id: str = Field(default="test-event", min_length=1, max_length=120)
    payload: dict = Field(default_factory=lambda: {"test": True})
    subscription_id: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, value: str) -> str:
        [normalized] = normalize_event_types([value])
        return normalized
