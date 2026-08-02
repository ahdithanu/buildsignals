from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class CandidateFieldMapping(BaseModel):
    source_field: str = Field(min_length=1, max_length=255)
    canonical_field: str = Field(min_length=1, max_length=255)
    transform: str | None = Field(default=None, max_length=100)
    transform_options: dict[str, Any] | None = None
    default_value: dict[str, Any] | None = None
    is_required: bool = False
    is_active: bool = True


class IngestionSourceCandidate(BaseModel):
    key: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9][a-z0-9_]*$")
    name: str = Field(min_length=1, max_length=255)
    adapter: str = Field(min_length=1, max_length=50)
    record_type: Literal["permit", "parcel"]
    jurisdiction: str = Field(min_length=1, max_length=255)
    base_url: str = Field(min_length=1, max_length=2000)
    official_landing_page: str = Field(min_length=1, max_length=2000)
    license: str = Field(min_length=1, max_length=255)
    status: Literal[
        "operational_retry",
        "legal_hold",
        "technical_hold",
        "freshness_hold",
        "lifecycle_hold",
        "queued",
    ]
    blocker_summary: str = Field(min_length=1, max_length=2000)
    early_warning_value: str = Field(min_length=1, max_length=2000)
    candidate_source_fields: list[str] = Field(default_factory=list, max_length=50)
    probe_settings: dict[str, Any] | None = None
    probe_field_mappings: list[CandidateFieldMapping] = Field(default_factory=list)
    production_page_size: int | None = Field(default=None, ge=1, le=10000)
    can_run_canary: bool = False
    last_checked_on: date
    next_audit_on: date
    notes: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def validate_probe_config(self):
        has_probe_settings = isinstance(self.probe_settings, dict) and bool(self.probe_settings)
        has_probe_mappings = bool(self.probe_field_mappings)
        self.can_run_canary = (
            self.status == "operational_retry"
            and has_probe_settings
            and has_probe_mappings
        )
        if self.status == "operational_retry" and not self.can_run_canary:
            raise ValueError(
                "operational_retry candidates require probe_settings and "
                "probe_field_mappings"
            )
        return self
