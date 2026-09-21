from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DocumentExcerptCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_title: str = Field(min_length=1, max_length=500)
    document_type: Literal["rent_roll", "lease", "cam", "capex_report"]
    source_date: date
    locator: str = Field(min_length=1, max_length=500)
    text: str = Field(min_length=1, max_length=20000)
    authorized_to_store: bool = Field(strict=True)

    @field_validator("source_title", "locator", "text")
    @classmethod
    def meaningful_text(cls, value: str) -> str:
        if not value.strip() or "\x00" in value:
            raise ValueError("Nonblank text without null characters is required")
        if len(value.encode("utf-8")) > 60000:
            raise ValueError("Excerpt exceeds the UTF-8 byte limit")
        return value

    @field_validator("authorized_to_store")
    @classmethod
    def require_authorization(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Authorization to store the excerpt must be affirmed")
        return value
