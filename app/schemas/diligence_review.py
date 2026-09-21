from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

OBSERVATION_CRITERIA = {
    "leased_area_occupancy_percent": "occupancy",
    "largest_tenant_base_rent_percent": "concentration",
    "restaurant_base_rent_percent": "restaurants",
    "base_rent_weighted_lease_term_years": "walt",
    "tenant_bay_count": "bays",
}


class DiligenceObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    metric: Literal["leased_area_occupancy_percent", "largest_tenant_base_rent_percent",
                    "restaurant_base_rent_percent", "base_rent_weighted_lease_term_years",
                    "tenant_bay_count"]
    value: float = Field(strict=True, ge=0, allow_inf_nan=False)
    as_of: date
    scope: Literal["whole_property", "partial"]
    methodology: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def validate_measurement(self):
        if self.metric.endswith("_percent") and self.value > 100:
            raise ValueError("Percent observations must be between zero and 100")
        if self.metric == "tenant_bay_count" and (not self.value.is_integer() or self.value > 10000):
            raise ValueError("Bay count must be a whole number no greater than 10000")
        if self.metric == "base_rent_weighted_lease_term_years" and self.value > 100:
            raise ValueError("Lease term must not exceed 100 years")
        return self


class DiligenceReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    document_id: str = Field(min_length=1, max_length=36)
    expected_text_sha256: str = Field(pattern="^[a-f0-9]{64}$")
    criterion: Literal["units", "sq_ft", "year_built", "asking_price", "market", "asset_type",
                       "bays", "occupancy", "concentration", "restaurants", "tenant_mix", "leases",
                       "walt", "rent", "access", "traffic", "parking", "population", "capex"]
    assessment: Literal["supports", "contradicts", "inconclusive"]
    rationale: str = Field(min_length=10, max_length=2000)
    observation: DiligenceObservation | None = None

    @model_validator(mode="after")
    def observation_matches_criterion(self):
        if self.observation and OBSERVATION_CRITERIA[self.observation.metric] != self.criterion:
            raise ValueError("Observation metric does not match the reviewed criterion")
        return self
