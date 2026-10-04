"""Temporal write inputs exclude tenant identity and server-owned known times."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
)

MAX_JSON_BYTES = 32 * 1024


def _utc_cutoff(value: datetime) -> datetime:
    try:
        return value.astimezone(timezone.utc)
    except OverflowError as exc:
        raise ValueError("Cutoff exceeds the supported UTC date range") from exc


UtcCutoff = Annotated[AwareDatetime, AfterValidator(_utc_cutoff)]


def _validate_json(value: JsonValue) -> JsonValue:
    try:
        encoded = json.dumps(
            value, allow_nan=False, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError("Must be valid JSON with finite numeric values") from exc
    if len(encoded) > MAX_JSON_BYTES:
        raise ValueError("Serialized JSON must not exceed 32 KiB")
    return value


BoundedJsonValue = Annotated[JsonValue, AfterValidator(_validate_json)]
NonblankKey = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
RecordId = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=36)
]
ObservationKey = Annotated[
    str, Field(min_length=64, max_length=64, pattern=r"^[0-9a-fA-F]{64}$")
]
Confidence = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class ObservationCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    entity_id: RecordId
    raw_source_record_id: RecordId
    observation_key: ObservationKey
    attribute: NonblankKey
    value: BoundedJsonValue
    unit: str | None = Field(default=None, max_length=50)
    effective_at: AwareDatetime | None = None
    confidence: Confidence
    geography: BoundedJsonValue = None
    source_url: str | None = None
    methodology_version: NonblankKey


class ObservationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    entity_id: str
    raw_source_record_id: str
    source_id: str
    observation_key: str
    series_key: str
    attribute: str
    value: BoundedJsonValue
    unit: str | None
    effective_at: datetime | None
    first_observed_at: datetime
    recorded_at: datetime
    source_updated_at: datetime | None
    source_system: str
    source_type: str
    source_url: str | None
    confidence: Confidence
    geography: BoundedJsonValue
    methodology_version: str
    content_hash: str


class EventCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    observation_id: RecordId
    event_type: NonblankKey
    occurred_at: AwareDatetime | None = None


class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    observation_id: str
    event_type: str
    occurred_at: datetime | None
    recorded_at: datetime
