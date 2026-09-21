from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DiligenceReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    document_id: str = Field(min_length=1, max_length=36)
    expected_text_sha256: str = Field(pattern="^[a-f0-9]{64}$")
    criterion: Literal["units", "sq_ft", "year_built", "asking_price", "market", "asset_type",
                       "bays", "occupancy", "concentration", "restaurants", "tenant_mix", "leases",
                       "walt", "rent", "access", "traffic", "parking", "population", "capex"]
    assessment: Literal["supports", "contradicts", "inconclusive"]
    rationale: str = Field(min_length=10, max_length=2000)
