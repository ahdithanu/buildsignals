"""Evidence-linked investment hypotheses, separate from observed source facts."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AssessmentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EvidenceCitation(AssessmentModel):
    evidence_id: str = Field(min_length=1, max_length=36)
    stance: Literal["supports", "contradicts", "context"]
    claim: Literal["change", "thesis"]
    rationale: str = Field(min_length=1, max_length=2000)


class ConfidenceAssessment(AssessmentModel):
    level: Literal["low", "medium", "high", "unassessed"]
    rationale: str = Field(min_length=1, max_length=2000)


class InvestmentImplication(AssessmentModel):
    entity_id: str = Field(min_length=1, max_length=36)
    mechanism: str = Field(min_length=1, max_length=2000)
    direction: Literal["positive", "negative", "mixed", "uncertain"]
    horizon: str = Field(min_length=1, max_length=255)
    evidence_ids: list[str] = Field(min_length=1, max_length=50)


class BuildSignalAssessmentDraft(AssessmentModel):
    detected_change: str = Field(min_length=1, max_length=5000)
    event_at: datetime | None = None
    investment_thesis: str = Field(min_length=1, max_length=5000)
    change_confidence: ConfidenceAssessment
    thesis_confidence: ConfidenceAssessment
    citations: list[EvidenceCitation] = Field(min_length=1, max_length=100)
    implications: list[InvestmentImplication] = Field(min_length=1, max_length=50)
    further_investigation: list[str] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def validate_evidence_links(self):
        keys = [(c.evidence_id, c.claim) for c in self.citations]
        if len(keys) != len(set(keys)):
            raise ValueError("Each evidence record may have one stance per claim")
        if not any(c.claim == "change" and c.stance == "supports" for c in self.citations):
            raise ValueError("The detected change requires supporting evidence")
        cited = {c.evidence_id for c in self.citations}
        if any(set(item.evidence_ids) - cited for item in self.implications):
            raise ValueError("Implications must reference included citations")
        if any(not item.strip() or len(item) > 2000 for item in self.further_investigation):
            raise ValueError("Investigation items must contain 1 to 2000 characters")
        return self


class ResolvedCitation(EvidenceCitation):
    source_system: str
    source_id: str | None
    source_url: str | None
    excerpt: str | None
    observed_at: datetime | None
    relationship_id: str
    relationship_is_current: bool
    relationship_last_verified_at: datetime


class ResolvedImplication(InvestmentImplication):
    entity_name: str
    entity_type: str


class BuildSignalAssessmentResponse(BuildSignalAssessmentDraft):
    schema_version: Literal["1"] = "1"
    signal_id: str
    status: Literal["draft"] = "draft"
    generated_at: datetime
    citations: list[ResolvedCitation]
    implications: list[ResolvedImplication]
    review_flags: list[str]


class BuildSignalRevisionResponse(AssessmentModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    signal_id: str
    author_id: str | None
    created_at: datetime
    snapshot: BuildSignalAssessmentResponse


class BuildSignalReviewCreate(AssessmentModel):
    decision: Literal["approved", "changes_requested", "rejected"]
    rationale: str = Field(min_length=1, max_length=5000)


class BuildSignalReviewResponse(BuildSignalReviewCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    revision_id: str
    reviewer_id: str | None
    created_at: datetime
