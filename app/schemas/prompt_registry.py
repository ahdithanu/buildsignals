"""Validated prompt registry input and output contracts."""

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Workflow = Literal["copilot_answer", "opportunity_memo", "multi_agent_research", "score_explanation"]
_TOKEN = re.compile(r"{{\s*([a-z][a-z0-9_]*)\s*}}")
_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class VersionCreate(StrictModel):
    body: str = Field(min_length=1, max_length=20000)
    variables: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def validate_tokens(self):
        if any(not _NAME.fullmatch(name) or len(name) > 64 for name in self.variables):
            raise ValueError("Variables must be lowercase identifiers up to 64 characters")
        if len(set(self.variables)) != len(self.variables):
            raise ValueError("Variables must be unique")
        tokens = set(_TOKEN.findall(self.body))
        if tokens != set(self.variables):
            raise ValueError("Declared variables must match all body placeholders")
        remainder = _TOKEN.sub("", self.body)
        if "{{" in remainder or "}}" in remainder:
            raise ValueError("Malformed placeholder")
        return self


class TemplateCreate(VersionCreate):
    key: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,99}$")
    name: str = Field(min_length=1, max_length=200)
    workflow: Workflow
    description: str = Field(default="", max_length=2000)


class PreviewRequest(StrictModel):
    version: int = Field(ge=1)
    values: dict[str, str] = Field(default_factory=dict, max_length=32)

    @model_validator(mode="after")
    def bounded_values(self):
        if any(len(value) > 5000 for value in self.values.values()):
            raise ValueError("Preview values must be at most 5000 characters")
        return self


class PreviewResponse(BaseModel):
    rendered: str
    version: int


class TemplateSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    key: str
    name: str
    workflow: Workflow
    description: str
    active_version: int | None
    created_at: datetime


class VersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    version: int
    body: str
    variables: list[str]
    checksum: str
    created_at: datetime
    created_by: str | None
    activated_at: datetime | None


class HistoryRead(BaseModel):
    id: str
    action: str
    version: int
    actor_id: str | None
    created_at: datetime


class TemplateDetail(TemplateSummary):
    versions: list[VersionRead]
    history: list[HistoryRead]


def render(body: str, values: dict[str, str]) -> str:
    return _TOKEN.sub(lambda match: values[match.group(1)], body)
